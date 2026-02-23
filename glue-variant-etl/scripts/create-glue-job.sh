#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Usage: ./scripts/create-glue-job.sh <job_name> <role_arn> <region>
#
# Creates an AWS Glue ETL job configured for AwsVincentJobs.
# The job uses the super JAR uploaded via ./gradlew upload.
#
# Example:
#   ./scripts/create-glue-job.sh vincent-variant-import \
#     arn:aws:iam::111111111111:role/VincentGlueRole \
#     us-east-1

JOB_NAME="${1:?Usage: $0 <job_name> <role_arn> [region]}"
ROLE_ARN="${2:?Missing role_arn}"
REGION="${3:-us-east-1}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
JAR_BUCKET="${ACCOUNT_ID}-awsvincentjobs-test-jar"
JAR_PATH="s3://${JAR_BUCKET}/AwsVincentJobs-super.jar"

# Glue ETL jobs require a script location even when using --extra-jars.
# We upload a minimal placeholder script.
SCRIPT_PATH="s3://${JAR_BUCKET}/placeholder.scala"
echo 'object Placeholder { def main(args: Array[String]): Unit = {} }' | \
  aws s3 cp - "$SCRIPT_PATH" --region "$REGION" 2>/dev/null || true

echo "Creating Glue job: $JOB_NAME"
echo "  Role:   $ROLE_ARN"
echo "  Region: $REGION"
echo "  JAR:    $JAR_PATH"

aws glue create-job \
  --name "$JOB_NAME" \
  --role "$ROLE_ARN" \
  --command "{
    \"Name\": \"glueetl\",
    \"ScriptLocation\": \"${SCRIPT_PATH}\",
    \"PythonVersion\": \"3\"
  }" \
  --default-arguments "{
    \"--extra-jars\": \"${JAR_PATH}\",
    \"--job-language\": \"scala\",
    \"--class\": \"com.amazon.vincent.job.VariantImportJob\",
    \"--enable-continuous-cloudwatch-log\": \"true\",
    \"--continuous-log-logGroup\": \"/aws-glue/jobs/logs\",
    \"--enable-continuous-log-filter\": \"false\",
    \"--enable-s3-parquet-optimized-committer\": \"true\",
    \"--enable-auto-scaling\": \"true\",
    \"--job-bookmark-option\": \"job-bookmark-disable\",
    \"--datalake-formats\": \"iceberg\"
  }" \
  --glue-version "3.0" \
  --number-of-workers 2 \
  --worker-type "G.1X" \
  --region "$REGION" \
  --output text \
  --query "Name"

echo ""
echo "Done. Run the job with:"
echo "  ./scripts/run-glue-job.sh $JOB_NAME $REGION"