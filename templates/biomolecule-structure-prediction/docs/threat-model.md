<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Threat Model

This document identifies assets, trust boundaries, threats, and mitigations for
the OpenFold3 AWS HealthOmics workflow deployment.

## Assets

| Asset | Classification | Location |
| ----- | -------------- | -------- |
| Docker Hub credentials | Highly sensitive | AWS Secrets Manager (KMS-encrypted) |
| Genomic/molecular query data | Sensitive | S3 workflow bucket |
| Prediction outputs (3D structures) | Sensitive | S3 workflow bucket |
| Model parameters (`of3-p2-155k.pt`) | Internal | Public S3 bucket / workflow bucket |
| Workflow definition (Nextflow code) | Internal | S3 workflow bucket |
| VPC Flow Logs | Internal | Amazon CloudWatch Logs |

## Trust boundaries

```text
┌─────────────────────────────────────────────────────────┐
│  AWS Account                                            │
│  ┌───────────────────────────────────────────────────┐  │
│  │  VPC (10.192.0.0/16)                              │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  Private subnets (HealthOmics task runtime) │  │  │
│  │  │  ← No inbound from internet                 │  │  │
│  │  │  → Outbound HTTPS only via NAT              │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  │  ┌──────────────┐  ┌──────────────────────────┐   │  │
│  │  │ NAT Gateways │  │ VPC Endpoints            │   │  │
│  │  │ (internet)   │  │ (S3, ECR, Logs, SSM)     │   │  │
│  │  └──────────────┘  └──────────────────────────┘   │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────┐   │
│  │ S3 Bucket    │ │ Secrets Mgr  │ │ ECR Cache      │   │
│  │ (data plane) │ │ (credentials)│ │ (images)       │   │
│  └──────────────┘ └──────────────┘ └────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │                                    │
    ┌────┴────┐                         ┌─────┴─────┐
    │ Users   │                         │ Docker Hub│
    │ (CLI)   │                         │ (upstream)│
    └─────────┘                         └───────────┘
```

## Threats and mitigations

### T1 — Credential exposure

**Threat**: Docker Hub credentials leaked through code, logs, or stack events.

**Mitigations**:

- Credentials passed via environment variables, never hardcoded
- CloudFormation parameters use `NoEcho: true`
- Secrets Manager encrypts at rest with customer-managed KMS key
- KMS key policy restricts decryption to Secrets Manager service

**Residual risk**: Credentials could be exposed if an operator echoes environment
variables in a shared terminal session. Mitigate with operational procedures.

### T2 — Unauthorized workflow execution

**Threat**: An attacker starts workflow runs using stolen IAM credentials.

**Mitigations**:

- IAM role trust policy restricts `sts:AssumeRole` to `omics.amazonaws.com`
- IAM policy conditions restrict actions to the HealthOmics service principal
- CloudTrail logs all `omics:StartRun` API calls

**Residual risk**: An attacker with account-level access could modify the trust
policy. Mitigate with SCPs and CloudTrail alerting.

### T3 — Data exfiltration via S3

**Threat**: Workflow outputs (predicted structures) exfiltrated from S3.

**Mitigations**:

- S3 Block Public Access prevents accidental public exposure
- Bucket policy denies non-HTTPS requests
- IAM role scoped to specific bucket only
- VPC endpoint for S3 keeps traffic off the public internet

**Residual risk**: An IAM principal with `s3:GetObject` on the bucket could
read data. Mitigate with bucket policies, S3 access logging, and CloudTrail
data events.

### T4 — Container image tampering

**Threat**: Malicious code injected into the `openfoldconsortium/openfold3`
Docker image on Docker Hub.

**Mitigations**:

- ECR pull-through cache stores a local copy after first pull
- ECR repository policy restricts access to HealthOmics service principal
- Workflow pins to a specific container image tag

**Residual risk**: If the upstream image is compromised before the first pull,
the cached copy will also be compromised. Mitigate by verifying image digests
and enabling ECR image scanning.

### T5 — Network-based attacks on MSA server

**Threat**: When `use_msa_server=true`, the workflow makes outbound HTTP
requests to an external MSA server, which could be intercepted or spoofed.

**Mitigations**:

- MSA server usage is opt-in (disabled by default)
- Outbound traffic restricted to HTTPS (port 443) by security group
- NAT gateways provide source-IP masking

**Residual risk**: The MSA server endpoint is not authenticated. Mitigate by
using a private MSA server deployment when processing sensitive sequences.

### T6 — Overly permissive IAM role

**Threat**: The workflow IAM role grants more permissions than needed, increasing
blast radius if compromised.

**Mitigations**:

- Actions scoped to specific S3 buckets, ECR repositories, and log groups
- Condition blocks restrict CloudWatch and ECR to HealthOmics service principal
- S3 actions require TLS transport
- No wildcard actions (`*`) in any policy statement

**Residual risk**: The role can read from the public `openfold3-data` bucket.
This is by design (model parameters) and the bucket is read-only.

## Recommended operational controls

### Critical (implement immediately after deployment)

1. Enable Amazon ECR image scanning on the `docker-hub/` repository prefix to
   detect vulnerabilities before they reach production
2. Enable AWS CloudTrail with data events for the workflow Amazon S3 bucket to
   establish an audit trail from day one

### High priority (implement within first week)

3. Configure Amazon CloudWatch alarms for unexpected `omics:StartRun` calls to
   detect unauthorized workflow execution
4. Review IAM role permissions using IAM Access Analyzer to identify and remove
   unused permissions

### Ongoing (establish schedule)

5. Rotate Docker Hub credentials every 90 days and update the AWS Secrets
   Manager secret
