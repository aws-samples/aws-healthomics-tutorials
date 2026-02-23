#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Usage: ./scripts/run-glue-job.sh <job_name> [region]
#
# Starts a Glue job run using parameters from glueParameters.json.
#
# Example:
#   ./scripts/run-glue-job.sh vincent-variant-import-test us-west-2

JOB_NAME="${1:?Usage: $0 <job_name> [region]}"
REGION="${2:-us-west-2}"

if [[ ! -f glueParameters.json ]]; then
  echo "Error: glueParameters.json not found in current directory."
  exit 1
fi

PARAMS=$(cat glueParameters.json)

echo "Starting Glue job: $JOB_NAME"
echo "Region: $REGION"
echo "Parameters:"
echo "$PARAMS" | head -5
echo "  ..."
echo ""

RUN_ID=$(aws glue start-job-run \
  --job-name "$JOB_NAME" \
  --arguments "$PARAMS" \
  --region "$REGION" \
  --query "JobRunId" \
  --output text)

echo "Job run started: $RUN_ID"
echo ""
echo "Monitor with:"
echo "  aws glue get-job-run --job-name $JOB_NAME --run-id $RUN_ID --region $REGION"