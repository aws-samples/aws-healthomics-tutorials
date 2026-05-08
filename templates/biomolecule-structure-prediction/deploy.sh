#!/usr/bin/env bash
set -euo pipefail

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

###############################################################################
# deploy.sh — Deploy CloudFormation stacks (including HealthOmics workflow),
#              then start a run using the resources they create.
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate credentials
#
# Usage:
#   ./deploy.sh [--bucket <s3-bucket-name>] [--stacks-only|--run-only]
#
# If --bucket is omitted, a default bucket name is generated:
#   openfold3-<account-id>-<region>
#
# Examples:
#   ./deploy.sh
#   ./deploy.sh --bucket my-omics-bucket
#   ./deploy.sh --stacks-only
#   ./deploy.sh --bucket my-omics-bucket --run-only
###############################################################################

# --- Parse arguments ---------------------------------------------------------
DEPLOY_STACKS=true
START_RUN=true
WORKFLOW_BUCKET=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bucket)
            WORKFLOW_BUCKET="$2"
            shift 2
            ;;
        --stacks-only)
            START_RUN=false
            shift
            ;;
        --run-only)
            DEPLOY_STACKS=false
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./deploy.sh [--bucket <s3-bucket-name>] [--stacks-only|--run-only]"
            exit 1
            ;;
    esac
done

# --- Default bucket name if not provided ------------------------------------
REGION="us-west-2"

if [[ -z "${WORKFLOW_BUCKET}" ]]; then
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "${REGION}")
    WORKFLOW_BUCKET="openfold3-${ACCOUNT_ID}-${REGION}"
    echo "No --bucket specified. Using default: ${WORKFLOW_BUCKET}"
fi

# --- Validate bucket name ----------------------------------------------------
# S3 bucket naming rules: 3-63 chars, lowercase alphanumeric, hyphens, and dots.
# Must start and end with a letter or number.
if [[ ! "${WORKFLOW_BUCKET}" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]]; then
    echo "ERROR: Invalid bucket name: '${WORKFLOW_BUCKET}'" >&2
    echo "Bucket names must be 3-63 characters, lowercase alphanumeric, hyphens, and dots." >&2
    echo "Must start and end with a lowercase letter or number." >&2
    exit 1
fi

# --- Configuration -----------------------------------------------------------
VPC_STACK_NAME="openfold3-vpc"
SERVICES_STACK_NAME="openfold3-services"
WORKFLOW_DIR="workflow"
CFN_DIR="cloudformation"

WORKFLOW_DEF_S3="s3://${WORKFLOW_BUCKET}/workflow-definition/workflow.zip"
RUN_OUTPUT_URI="s3://${WORKFLOW_BUCKET}/healthomics-outputs/"

# Query JSON to upload and use for the run
WORKFLOW_NAME="openfold3-inference"

# Model parameters
MODEL_PARAMS_SOURCE="s3://openfold3-data/openfold3-parameters/of3-p2-155k.pt"
MODEL_PARAMS_S3="s3://${WORKFLOW_BUCKET}/model-parameters/of3-p2-155k.pt"

# --- Helper ------------------------------------------------------------------
wait_for_stack() {
    local stack_name="$1"
    echo "  Waiting for ${stack_name} to complete..."
    aws cloudformation wait stack-create-complete \
        --stack-name "${stack_name}" --region "${REGION}" 2>/dev/null \
    || aws cloudformation wait stack-update-complete \
        --stack-name "${stack_name}" --region "${REGION}" 2>/dev/null \
    || true
}

get_stack_output() {
    local stack_name="$1"
    local output_key="$2"
    aws cloudformation describe-stacks \
        --stack-name "${stack_name}" \
        --region "${REGION}" \
        --query "Stacks[0].Outputs[?OutputKey=='${output_key}'].OutputValue" \
        --output text
}

# create_bucket_if_needed — Create the workflow S3 bucket if it does not
# already exist.
# Security: The bucket is created with encryption at rest (SSE-S3), Block Public
# Access (all four settings), versioning, server access logging, and a bucket
# policy that denies all non-HTTPS requests. These settings follow AWS security
# best practices and satisfy the requirements documented in the README.
create_bucket_if_needed() {
    local bucket="$1"
    local region="$2"

    if aws s3api head-bucket --bucket "${bucket}" --region "${region}" 2>/dev/null; then
        echo "  Bucket s3://${bucket} already exists — skipping creation"
        return 0
    fi

    echo "  Creating bucket s3://${bucket} in ${region}..."
    aws s3api create-bucket \
        --bucket "${bucket}" \
        --region "${region}" \
        --create-bucket-configuration LocationConstraint="${region}"

    echo "  Enabling default encryption (SSE-S3)..."
    aws s3api put-bucket-encryption \
        --bucket "${bucket}" \
        --server-side-encryption-configuration '{
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        }'

    echo "  Enabling Block Public Access..."
    aws s3api put-public-access-block \
        --bucket "${bucket}" \
        --public-access-block-configuration '{
            "BlockPublicAcls": true,
            "IgnorePublicAcls": true,
            "BlockPublicPolicy": true,
            "RestrictPublicBuckets": true
        }'

    echo "  Enabling versioning..."
    aws s3api put-bucket-versioning \
        --bucket "${bucket}" \
        --versioning-configuration Status=Enabled

    # Note: TLS-enforcement bucket policy is managed by the CloudFormation
    # services stack (WorkflowBucketPolicy resource) to avoid conflicts.

    echo "  Creating access logs bucket s3://${bucket}-logs..."
    aws s3api create-bucket \
        --bucket "${bucket}-logs" \
        --region "${region}" \
        --create-bucket-configuration LocationConstraint="${region}"

    aws s3api put-public-access-block \
        --bucket "${bucket}-logs" \
        --public-access-block-configuration '{
            "BlockPublicAcls": true,
            "IgnorePublicAcls": true,
            "BlockPublicPolicy": true,
            "RestrictPublicBuckets": true
        }'

    echo "  Enabling server access logging..."
    aws s3api put-bucket-logging \
        --bucket "${bucket}" \
        --bucket-logging-status "{
            \"LoggingEnabled\": {
                \"TargetBucket\": \"${bucket}-logs\",
                \"TargetPrefix\": \"access-logs/\"
            }
        }"

    echo "  Bucket s3://${bucket} created with security best practices"
}

# --- Step 0: Create the workflow S3 bucket if needed -------------------------
echo "==> Checking workflow bucket: ${WORKFLOW_BUCKET}"
create_bucket_if_needed "${WORKFLOW_BUCKET}" "${REGION}"

# --- Step 1: Deploy CloudFormation stacks ------------------------------------
if [[ "${DEPLOY_STACKS}" == true ]]; then
    echo "==> Deploying VPC stack: ${VPC_STACK_NAME}"
    aws cloudformation deploy \
        --template-file "${CFN_DIR}/vpc.yaml" \
        --stack-name "${VPC_STACK_NAME}" \
        --capabilities CAPABILITY_IAM \
        --region "${REGION}" \
        --no-fail-on-empty-changeset

    # Resolve VPC stack outputs for services stack parameters
    VPC_ID=$(get_stack_output "${VPC_STACK_NAME}" "VpcId")
    PRIVATE_SUBNET_IDS=$(get_stack_output "${VPC_STACK_NAME}" "PrivateSubnets")

    # Package and upload workflow definition to S3
    echo "==> Packaging and uploading workflow definition..."
    WORKFLOW_ZIP="$(mktemp /tmp/workflow-XXXXXX).zip"
    (cd "${WORKFLOW_DIR}" && zip -r "${WORKFLOW_ZIP}" main.nf nextflow.config)
    aws s3 cp "${WORKFLOW_ZIP}" "${WORKFLOW_DEF_S3}" --region "${REGION}"
    rm -f "${WORKFLOW_ZIP}"

    echo "==> Deploying services stack: ${SERVICES_STACK_NAME}"
    # Security: Docker Hub credentials are passed via environment variables to
    # prevent exposure in version control or CloudFormation stack history.
    # They are stored in AWS Secrets Manager encrypted with a customer-managed
    # KMS key. CloudFormation NoEcho parameters prevent values from being logged
    # in stack events or the console.
    if [[ -z "${DOCKER_HUB_USERNAME:-}" ]] || [[ -z "${DOCKER_HUB_ACCESS_TOKEN:-}" ]]; then
        echo "ERROR: DOCKER_HUB_USERNAME and DOCKER_HUB_ACCESS_TOKEN must be set" >&2
        exit 1
    fi
    aws cloudformation deploy \
        --template-file "${CFN_DIR}/services.yaml" \
        --stack-name "${SERVICES_STACK_NAME}" \
        --parameter-overrides \
            DockerHubUsername="${DOCKER_HUB_USERNAME:?Set DOCKER_HUB_USERNAME env var}" \
            DockerHubAccessToken="${DOCKER_HUB_ACCESS_TOKEN:?Set DOCKER_HUB_ACCESS_TOKEN env var}" \
            WorkflowBucketName="${WORKFLOW_BUCKET}" \
            WorkflowDefinitionUri="${WORKFLOW_DEF_S3}" \
            VpcId="${VPC_ID}" \
            PrivateSubnetIds="${PRIVATE_SUBNET_IDS}" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "${REGION}" \
        --no-fail-on-empty-changeset

    echo "==> Stacks deployed successfully"
fi

# --- Step 2: Resolve stack outputs -------------------------------------------
echo "==> Resolving stack outputs..."
ROLE_ARN=$(get_stack_output "${SERVICES_STACK_NAME}" "HealthOmicsWorkflowRoleArn")
echo "  Role ARN: ${ROLE_ARN}"

OMICS_VPC_CONFIG=$(get_stack_output "${SERVICES_STACK_NAME}" "OmicsVpcConfigurationName")
echo "  VPC Configuration: ${OMICS_VPC_CONFIG}"

WORKFLOW_ID=$(get_stack_output "${SERVICES_STACK_NAME}" "OmicsWorkflowId")
echo "  Workflow ID: ${WORKFLOW_ID}"

# --- Step 3: Upload inputs and start a run ----------------------------------
if [[ "${START_RUN}" == true ]]; then
    echo "==> Syncing model parameters to workflow bucket..."
    aws s3 sync "s3://openfold3-data/openfold3-parameters/" "s3://${WORKFLOW_BUCKET}/model-parameters/" --region "${REGION}"

    echo "==> Uploading example data to S3..."
    aws s3 sync "examples/" "s3://${WORKFLOW_BUCKET}/examples/" --region "${REGION}"

    echo "==> Starting HealthOmics run..."
    RUN_RESPONSE=$(aws omics start-run \
        --workflow-id "${WORKFLOW_ID}" \
        --role-arn "${ROLE_ARN}" \
        --output-uri "${RUN_OUTPUT_URI}" \
        --storage-type DYNAMIC \
        --name "${WORKFLOW_NAME}-$(date +%Y%m%d-%H%M%S)" \
        --parameters "{\"query_json\": \"s3://${WORKFLOW_BUCKET}/examples/query_ubiquitin.json\", \"params\": \"${MODEL_PARAMS_S3}\"}" \
        --networking-mode VPC \
        --configuration-name "${OMICS_VPC_CONFIG}" \
        --region "${REGION}" \
        --output json)

    RUN_ID=$(echo "${RUN_RESPONSE}" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('id', ''))" 2>/dev/null) || true
    if [[ -z "${RUN_ID}" ]]; then
        echo "ERROR: Failed to parse run ID from response" >&2
        echo "  Response: ${RUN_RESPONSE}" >&2
        exit 1
    fi
    echo "  Run started: ${RUN_ID}"
    echo "  Monitor with: aws omics get-run --id ${RUN_ID} --region ${REGION}"
fi

echo "==> Done"
