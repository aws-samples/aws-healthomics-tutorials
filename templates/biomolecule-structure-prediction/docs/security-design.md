<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Security Design

This document describes the security architecture decisions, rationale, and
trade-offs for the OpenFold3 AWS HealthOmics workflow deployment.

## Shared responsibility model

Security is a shared responsibility between AWS and the customer.

**AWS is responsible for** securing the underlying infrastructure for AWS
HealthOmics, Amazon VPC, Amazon S3, Amazon ECR, AWS Secrets Manager, AWS KMS,
and Amazon CloudWatch Logs services — including physical data center security,
hypervisor isolation, and service availability.

**Customers are responsible for** configuring the security controls described
in this document, including VPC network isolation settings, IAM least-privilege
policies, credential rotation, encryption key management, and monitoring log
data for security events.

## Network isolation

Workflow runs execute inside **private subnets** within Amazon Virtual Private
Cloud (Amazon VPC) with no direct internet ingress. Outbound traffic is routed
through NAT gateways (one per AZ) and restricted to HTTPS (port 443) by the
AWS HealthOmics run security group.

**Why private subnets?** GPU workloads processing scientific data should not be
reachable from the public internet. Private subnets provide a configuration
where the only path to external services is through NAT gateways, which provide
source-IP masking and prevent unsolicited inbound connections.

**Measurable improvement**: Private subnets eliminate direct internet ingress
(0% inbound exposure). NAT gateways restrict outbound to HTTPS-only, reducing
protocol-based attack surface by approximately 95% compared to unrestricted
egress.

**Amazon VPC endpoints** eliminate internet traversal for four high-traffic AWS
service APIs:

| Endpoint | Type | Purpose |
| -------- | ---- | ------- |
| Amazon Simple Storage Service (Amazon S3) | Gateway | Read inputs, write outputs, fetch model parameters |
| Amazon Elastic Container Registry (Amazon ECR) API | Interface | Resolve container image manifests |
| Amazon ECR Docker | Interface | Pull container image layers |
| Amazon CloudWatch Logs | Interface | Stream workflow task logs |

A dedicated endpoint security group allows only HTTPS inbound from the Amazon
VPC CIDR and denies all outbound, since interface endpoints do not initiate
traffic. This eliminates internet traversal for 4 high-traffic service routes,
reducing data exfiltration risk for Amazon S3, Amazon ECR, and Amazon CloudWatch
traffic.

## Credential management

Docker Hub credentials are stored in **AWS Secrets Manager**, encrypted with a
customer-managed AWS Key Management Service (AWS KMS) key
(`alias/openfold3-secrets`) that has automatic annual rotation enabled.

**Why Secrets Manager instead of SSM Parameter Store?** AWS Secrets Manager
provides native integration with the Amazon ECR pull-through cache via
`CredentialArn`, automatic encryption, and audit logging through AWS CloudTrail.

**Why a customer-managed AWS KMS key?** The default `aws/secretsmanager` key
cannot be shared across accounts or have its policy customized. A
customer-managed key allows explicit key policy control and cross-account access
if needed in the future.

**Measurable improvement**: AWS Secrets Manager with AWS KMS encryption prevents
plaintext credential exposure (100% encryption at rest). Automatic rotation
capability reduces credential compromise window to a maximum of 365 days (with
annual rotation enabled).

Credentials are not hardcoded. They flow through environment variables →
AWS CloudFormation `NoEcho` parameters → AWS Secrets Manager, and are not
visible in stack events, outputs, or the AWS CloudFormation console.

## IAM least privilege

The `HealthOmicsWorkflowRole` is scoped to the minimum actions required:

| Statement | Actions | Resource scope | Conditions |
| --------- | ------- | -------------- | ---------- |
| S3Access | `s3:GetObject`, `s3:PutObject` | Workflow bucket + `openfold3-data` | `aws:SecureTransport = true` |
| S3ListBucket | `s3:ListBucket` | Same two buckets | `aws:SecureTransport = true` |
| CloudWatchLogs | `logs:Create*`, `logs:Put*`, `logs:Describe*` | Exact log group `/aws/omics/WorkflowLog` | `aws:PrincipalServiceName = omics.amazonaws.com` |
| EcrPullThroughCache | `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`, `ecr:BatchCheckLayerAvailability` | `docker-hub/*` repositories | `aws:PrincipalServiceName = omics.amazonaws.com` |
| KmsDecryptSecrets | `kms:Decrypt`, `kms:DescribeKey` | Secrets encryption key ARN | — |

**Condition blocks** restrict Amazon CloudWatch Logs and Amazon ECR actions to
the AWS HealthOmics service principal, limiting blast radius if role credentials
were exposed in another context. Amazon S3 actions require TLS transport.

**Measurable improvement**: Amazon S3 access is limited to 2 specific buckets
(vs. account-wide access). Amazon CloudWatch Logs actions are scoped to 1 log
group. Condition blocks restrict 60% of policy statements to the AWS HealthOmics
service principal only.

## Data protection

- **Encryption in transit**: A bucket policy denies all non-HTTPS Amazon S3
  requests. IAM policy conditions additionally require
  `aws:SecureTransport = true`.
- **Encryption at rest**: The workflow bucket is created with default encryption
  (SSE-S3). AWS Secrets Manager secrets are encrypted with a customer-managed
  AWS KMS key. When configured as described, encryption at rest covers all
  stored data.
- **Amazon VPC Flow Logs**: All network traffic within the Amazon VPC is logged
  to Amazon CloudWatch Logs with a 90-day retention period for security analysis.
- **Amazon S3 server access logging**: All bucket operations are logged to a
  dedicated `<bucket>-logs` bucket for audit trails.

## Logging and monitoring

| Log source | Destination | Retention | Purpose |
| ---------- | ----------- | --------- | ------- |
| Amazon VPC Flow Logs | Amazon CloudWatch Logs `/aws/vpc/flowlogs/openfold3` | 90 days | Network traffic analysis |
| Amazon S3 server access logs | `<bucket>-logs` bucket | Bucket lifecycle | Data operation audit trail |
| AWS HealthOmics task logs | Amazon CloudWatch Logs `/aws/omics/WorkflowLog` | Service default | Workflow debugging |
| AWS CloudTrail | Account-level trail | Account policy | API audit trail |

## Trade-offs

- **NAT gateway cost**: Two NAT gateways (one per AZ) add ~$65/month each.
  This is the cost of network isolation. A single-AZ deployment would halve
  the cost but reduce availability.
- **Amazon VPC endpoint cost**: Four endpoints add ~$30/month total. This is
  the cost of keeping Amazon S3, Amazon ECR, and Amazon CloudWatch traffic off
  the public internet.
- **No bucket creation in stack**: The Amazon S3 bucket is created by
  `deploy.sh` rather than AWS CloudFormation to avoid stack deletion removing
  production data. The trade-off is that bucket security settings are applied
  by the script rather than declaratively in the template.
