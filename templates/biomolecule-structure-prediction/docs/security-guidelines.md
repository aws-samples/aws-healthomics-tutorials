<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Security Guidelines

Per-service security guidelines for operating the OpenFold3 AWS HealthOmics
workflow deployment.

## Shared responsibility model

Security is a shared responsibility between AWS and customers.

**AWS is responsible for** securing the underlying infrastructure for all AWS
services used in this deployment, including AWS HealthOmics, Amazon S3, Amazon
VPC, Amazon ECR, AWS Secrets Manager, AWS KMS, Amazon CloudWatch Logs, AWS
CloudFormation, AWS Systems Manager, and IAM service endpoints.

**Customers are responsible for** implementing the security controls described
in this document, including configuring encryption, managing IAM permissions,
rotating credentials, monitoring logs, and maintaining compliance with
organizational security policies.

## Implementation priority

### Phase 1: Critical security controls (deploy day)

1. Verify Amazon S3 default encryption and Block Public Access (Amazon S3 section)
2. Review IAM role permissions with IAM Access Analyzer (IAM section)
3. Confirm AWS KMS key is active for AWS Secrets Manager (Secrets Manager section)

### Phase 2: Monitoring and detection (week 1)

4. Review Amazon VPC Flow Logs for baseline traffic patterns (Amazon VPC section)
5. Enable Amazon ECR image scanning (Amazon ECR section)
6. Set Amazon CloudWatch Logs retention policies (CloudWatch section)

### Phase 3: Operational security (month 1)

7. Establish credential rotation schedule (Secrets Manager section)
8. Enable AWS CloudFormation termination protection (CloudFormation section)
9. Verify Amazon S3 access logging is active (Amazon S3 section)

---

## Amazon Simple Storage Service (Amazon S3)

- Enable default encryption (SSE-S3 or SSE-KMS) on the workflow bucket to
  achieve 100% encryption at rest for all objects.
- Enable Block Public Access (all four settings) to reduce public access risk
  to 0%.
- Enable versioning to protect against accidental overwrites and deletions.
- Enable server access logging to a separate bucket for audit trails.
  `deploy.sh` configures this automatically for new buckets.
- Review bucket policies quarterly. The `openfold3-services` stack attaches a
  policy that denies non-HTTPS requests — this policy should remain in place.
- Consider Amazon S3 Object Lock if compliance requirements mandate immutable
  storage.
- Enable AWS CloudTrail data events for the bucket to log object-level
  operations.

## AWS Identity and Access Management (IAM)

- Review the `HealthOmicsWorkflowRole` permissions after deployment using
  [IAM Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html).
  Target: remove unused permissions within 30 days, reducing effective
  permission scope by an estimated 20–40%.
- Wildcard actions (`*`) should not be added to the workflow policy.
- Use [Service Control Policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
  (SCPs) to prevent privilege escalation at the organization level.
- Rotate IAM credentials used for deployment (AWS CLI profiles)
  according to organizational policy.
- Audit role usage through AWS CloudTrail and remove unused permissions.

## AWS Secrets Manager

- Rotate Docker Hub credentials periodically. Update the secret
  value via the AWS CLI or console — the Amazon ECR pull-through cache rule
  references the secret ARN and picks up new values automatically.
- The customer-managed AWS KMS key (`alias/openfold3-secrets`) should remain
  enabled. Disabling it will make the secret unreadable.
- Monitor secret access through AWS CloudTrail `GetSecretValue` events.
- Restrict `secretsmanager:GetSecretValue` permissions to only the principals
  that need them.

## Amazon Virtual Private Cloud (Amazon VPC)

- Review Amazon VPC Flow Logs in Amazon CloudWatch Logs
  (`/aws/vpc/flowlogs/openfold3`) for anomalous traffic patterns such as
  unexpected destination IPs or high volumes. Target: establish traffic baseline
  within the first week; alert on patterns deviating more than 50% from
  baseline.
- Additional inbound ports on the AWS HealthOmics run security group should
  only be opened when required for specific use cases.
- The `NoIngressSecurityGroup` allows HTTPS egress only within the Amazon VPC
  CIDR. Verify this meets security requirements and adjust if needed.
- Consider enabling
  [Amazon VPC Flow Log integration with Amazon GuardDuty](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_vpc.html)
  for automated threat detection.

## Amazon Elastic Container Registry (Amazon ECR)

- Enable [image scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html)
  on repositories under the `docker-hub/` prefix to detect vulnerabilities.
  Target: scan 100% of pulled images; remediate Critical/High findings within
  7 days.
- Use immutable image tags when pinning to specific container versions.
- Review the Amazon ECR registry policy periodically — it grants
  `ecr:CreateRepository` and `ecr:BatchImportUpstreamImage` to the
  AWS HealthOmics service principal.
- Monitor Amazon ECR repository creation through AWS CloudTrail to detect
  unexpected images.

## AWS HealthOmics

- Use Amazon VPC-connected runs (the default in this deployment) for network
  isolation.
- Monitor workflow runs through Amazon CloudWatch Logs and the
  `aws omics get-run` API.
- Set run storage to `DYNAMIC` (the default) to avoid over-provisioning.
- Review run costs periodically — GPU instances (`nvidia-l4-a10g`) are the
  primary cost driver.

## Amazon CloudWatch Logs

- Set retention policies on all log groups. The Amazon VPC Flow Log group is
  set to 90 days by default — adjust based on compliance requirements.
- Enable log group encryption with an AWS KMS key for sensitive workloads.
- Broad `logs:*` permissions should be avoided. The workflow role is scoped to
  the specific `/aws/omics/WorkflowLog` log group.
- Consider exporting logs to Amazon S3 for long-term archival.

## AWS CloudFormation

- Enable [termination protection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-protect-stacks.html)
  on production stacks to prevent accidental deletion:

  ```bash
  aws cloudformation update-termination-protection \
    --enable-termination-protection \
    --stack-name openfold3-services \
    --region us-west-2
  ```

- Use [stack policies](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html)
  to prevent unintended updates to critical resources (IAM role, AWS KMS key).
- Review stack drift periodically using `aws cloudformation detect-stack-drift`.
- Sensitive values should not be stored in stack outputs. Credentials are
  protected with `NoEcho` parameters and stored in AWS Secrets Manager.

## AWS Key Management Service (AWS KMS)

- Monitor AWS KMS key usage through AWS CloudTrail `Decrypt`, `Encrypt`, and
  `GenerateDataKey` events to detect anomalous encryption operations.
- Review the customer-managed key policy (`alias/openfold3-secrets`) quarterly
  to verify only authorized principals have decrypt permissions.
- Verify automatic key rotation is enabled (already configured in the
  deployment) and confirm rotation occurs annually.
- The `alias/openfold3-secrets` key should remain enabled — disabling it will
  make AWS Secrets Manager secrets unreadable and break the Amazon ECR
  pull-through cache authentication.
- Consider setting up Amazon CloudWatch alarms for failed decryption attempts
  to detect potential unauthorized access.
