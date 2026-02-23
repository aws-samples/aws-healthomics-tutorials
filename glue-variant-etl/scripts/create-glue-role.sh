#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Usage: ./scripts/create-glue-role.sh <role_name> <s3_bucket> <region>
#
# Creates an IAM role for Glue job execution with permissions for:
#   - S3 read/write on the specified bucket
#   - Glue catalog access
#   - Omics API access (for reference genome downloads)
#   - CloudWatch Logs (for Glue job logging)
#
# Example:
#   ./scripts/create-glue-role.sh VincentGlueRole my-data-bucket us-west-2

ROLE_NAME="${1:?Usage: $0 <role_name> <s3_bucket> <region>}"
S3_BUCKET="${2:?Missing s3_bucket}"
REGION="${3:?Missing region}"

# Strip s3:// or s3a:// prefix if provided
S3_BUCKET="${S3_BUCKET#s3://}"
S3_BUCKET="${S3_BUCKET#s3a://}"
# Strip trailing slash
S3_BUCKET="${S3_BUCKET%/}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

echo "Creating Glue execution role: $ROLE_NAME"
echo "  Account:  $ACCOUNT_ID"
echo "  S3 bucket: $S3_BUCKET"
echo "  Region:   $REGION"

# Trust policy — allow Glue to assume this role
TRUST_POLICY=$(cat <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "glue.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
)

# Create the role
aws iam create-role \
  --role-name "$ROLE_NAME" \
  --assume-role-policy-document "$TRUST_POLICY" \
  --description "Glue execution role for AwsVincentJobs pipeline" \
  --output text --query "Role.Arn"

echo "  Role created: $ROLE_ARN"

# Inline policy with required permissions
POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::${S3_BUCKET}",
        "arn:aws:s3:::${S3_BUCKET}/*",
        "arn:aws:s3:::${ACCOUNT_ID}-awsvincentjobs-test-jar",
        "arn:aws:s3:::${ACCOUNT_ID}-awsvincentjobs-test-jar/*"
      ]
    },
    {
      "Sid": "GlueCatalog",
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetDatabases",
        "glue:GetTable",
        "glue:GetTables",
        "glue:GetPartition",
        "glue:GetPartitions",
        "glue:UpdateTable",
        "glue:CreateTable",
        "glue:BatchGetPartition",
        "glue:BatchCreatePartition"
      ],
      "Resource": [
        "arn:aws:glue:${REGION}:${ACCOUNT_ID}:catalog",
        "arn:aws:glue:${REGION}:${ACCOUNT_ID}:database/*",
        "arn:aws:glue:${REGION}:${ACCOUNT_ID}:table/*/*"
      ]
    },
    {
      "Sid": "OmicsAccess",
      "Effect": "Allow",
      "Action": [
        "omics:GetReference",
        "omics:GetReferenceMetadata",
        "omics:ListReferences",
        "omics:GetReferenceStore"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/aws-glue/*"
    }
  ]
}
EOF
)

aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "VincentGlueJobPolicy" \
  --policy-document "$POLICY"

echo "  Policy attached."
echo ""
echo "Done. Use this role ARN when creating your Glue job:"
echo "  $ROLE_ARN"