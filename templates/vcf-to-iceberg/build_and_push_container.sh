#!/bin/bash
#
# Build and push the HealthOmics VCF Loader container to Amazon ECR.
#
# Usage:
#   ./build_and_push_container.sh --account-id 123456789012 --region us-east-1
#   ./build_and_push_container.sh --account-id 123456789012 --region us-east-1 --repo my-repo --tag v1.0.0
#
# Options:
#   --account-id   AWS account ID (required)
#   --region       AWS region (required)
#   --repo         ECR repository name (default: healthomics-vcf-loader)
#   --tag          Image tag (default: latest)
#   --skip-build   Skip the build step, only tag and push
#

set -euo pipefail

# Defaults
REPO_NAME="healthomics-vcf-loader"
IMAGE_TAG="latest"
SKIP_BUILD=false
CONTAINER_RUNTIME="finch"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --account-id)
            AWS_ACCOUNT_ID="$2"
            shift 2
            ;;
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        --repo)
            REPO_NAME="$2"
            shift 2
            ;;
        --tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --docker)
            CONTAINER_RUNTIME="docker"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 --account-id <id> --region <region> [--repo <name>] [--tag <tag>] [--skip-build] [--docker]"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "${AWS_ACCOUNT_ID:-}" ]; then
    echo "Error: --account-id is required"
    exit 1
fi

if [ -z "${AWS_REGION:-}" ]; then
    echo "Error: --region is required"
    exit 1
fi

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
FULL_IMAGE="${ECR_URI}/${REPO_NAME}:${IMAGE_TAG}"
LOCAL_IMAGE="${REPO_NAME}:${IMAGE_TAG}"

echo "============================================"
echo "HealthOmics VCF Loader - Build & Push to ECR"
echo "============================================"
echo "Account:   ${AWS_ACCOUNT_ID}"
echo "Region:    ${AWS_REGION}"
echo "Repo:      ${REPO_NAME}"
echo "Tag:       ${IMAGE_TAG}"
echo "Runtime:   ${CONTAINER_RUNTIME}"
echo "ECR Image: ${FULL_IMAGE}"
echo "============================================"
echo ""

# Step 1: Build the container (amd64 for HealthOmics)
if [ "${SKIP_BUILD}" = false ]; then
    echo ">> Building container for amd64 (required by HealthOmics)..."
    ${CONTAINER_RUNTIME} build --platform linux/amd64 -t "${LOCAL_IMAGE}" .
    echo "   Build complete."
    echo ""

    echo ">> Verifying container dependencies..."
    # Skip verification when cross-compiling (amd64 on ARM) — QEMU emulation
    # can segfault on some Python C extensions. The container runs natively on
    # HealthOmics (x86_64) so this is safe to skip.
    HOST_ARCH=$(uname -m)
    if [ "${HOST_ARCH}" = "x86_64" ]; then
        ${CONTAINER_RUNTIME} run --rm "${LOCAL_IMAGE}" python -c "
import pyiceberg; import pyarrow; import boto3
print('All dependencies loaded successfully')
"
    else
        echo "   Skipping verification (cross-compiling amd64 on ${HOST_ARCH})."
        echo "   Container will run natively on HealthOmics (x86_64)."
    fi
    echo ""
fi

# Step 2: Authenticate to ECR
echo ">> Authenticating to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | \
    ${CONTAINER_RUNTIME} login --username AWS --password-stdin "${ECR_URI}"
echo ""

# Step 3: Create ECR repository if it doesn't exist
echo ">> Ensuring ECR repository exists..."
aws ecr describe-repositories \
    --repository-names "${REPO_NAME}" \
    --region "${AWS_REGION}" > /dev/null 2>&1 || \
aws ecr create-repository \
    --repository-name "${REPO_NAME}" \
    --region "${AWS_REGION}" \
    --image-scanning-configuration scanOnPush=true
echo ""

# Step 4: Set ECR repository policy for HealthOmics access
echo ">> Setting ECR repository policy for HealthOmics..."
POLICY_JSON=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowHealthOmicsAccess",
      "Effect": "Allow",
      "Principal": {
        "Service": "omics.amazonaws.com"
      },
      "Action": [
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:BatchCheckLayerAvailability"
      ],
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "${AWS_ACCOUNT_ID}"
        }
      }
    }
  ]
}
EOF
)

aws ecr set-repository-policy \
    --repository-name "${REPO_NAME}" \
    --region "${AWS_REGION}" \
    --policy-text "${POLICY_JSON}" > /dev/null
echo "   HealthOmics (omics.amazonaws.com) granted pull access."
echo ""

# Step 5: Tag and push
echo ">> Tagging image for ECR..."
${CONTAINER_RUNTIME} tag "${LOCAL_IMAGE}" "${FULL_IMAGE}"

echo ">> Pushing to ECR..."
${CONTAINER_RUNTIME} push "${FULL_IMAGE}"
echo ""

echo "============================================"
echo "Push complete!"
echo ""
echo "Image URI: ${FULL_IMAGE}"
echo ""
echo "Use this container URI in your WDL parameters:"
echo "  \"container\": \"${FULL_IMAGE}\""
echo "============================================"
