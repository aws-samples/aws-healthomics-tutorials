#!/bin/bash
set -euo pipefail

REPO_NAME="healthomics-gff3-loader"
IMAGE_TAG="latest"
SKIP_BUILD=false
CONTAINER_RUNTIME="finch"

while [[ $# -gt 0 ]]; do
    case $1 in
        --account-id) AWS_ACCOUNT_ID="$2"; shift 2 ;;
        --region) AWS_REGION="$2"; shift 2 ;;
        --repo) REPO_NAME="$2"; shift 2 ;;
        --tag) IMAGE_TAG="$2"; shift 2 ;;
        --skip-build) SKIP_BUILD=true; shift ;;
        --docker) CONTAINER_RUNTIME="docker"; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "${AWS_ACCOUNT_ID:-}" ]; then echo "Error: --account-id is required"; exit 1; fi
if [ -z "${AWS_REGION:-}" ]; then echo "Error: --region is required"; exit 1; fi

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
FULL_IMAGE="${ECR_URI}/${REPO_NAME}:${IMAGE_TAG}"
LOCAL_IMAGE="${REPO_NAME}:${IMAGE_TAG}"

echo "============================================"
echo "HealthOmics GFF3 Loader - Build & Push to ECR"
echo "============================================"
echo "Account:   ${AWS_ACCOUNT_ID}"
echo "Region:    ${AWS_REGION}"
echo "Repo:      ${REPO_NAME}"
echo "Tag:       ${IMAGE_TAG}"
echo "ECR Image: ${FULL_IMAGE}"
echo "============================================"

if [ "${SKIP_BUILD}" = false ]; then
    echo ">> Building container for amd64..."
    ${CONTAINER_RUNTIME} build --platform linux/amd64 -t "${LOCAL_IMAGE}" .
    echo "   Build complete."
fi

echo ">> Authenticating to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | \
    ${CONTAINER_RUNTIME} login --username AWS --password-stdin "${ECR_URI}"

echo ">> Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names "${REPO_NAME}" --region "${AWS_REGION}" > /dev/null 2>&1 || \
aws ecr create-repository --repository-name "${REPO_NAME}" --region "${AWS_REGION}" --image-scanning-configuration scanOnPush=true

echo ">> Setting ECR repository policy for HealthOmics..."
POLICY_JSON=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AllowHealthOmicsAccess",
    "Effect": "Allow",
    "Principal": {"Service": "omics.amazonaws.com"},
    "Action": ["ecr:GetDownloadUrlForLayer","ecr:BatchGetImage","ecr:BatchCheckLayerAvailability"],
    "Condition": {"StringEquals": {"aws:SourceAccount": "${AWS_ACCOUNT_ID}"}}
  }]
}
EOF
)
aws ecr set-repository-policy --repository-name "${REPO_NAME}" --region "${AWS_REGION}" --policy-text "${POLICY_JSON}" > /dev/null

echo ">> Tagging and pushing..."
${CONTAINER_RUNTIME} tag "${LOCAL_IMAGE}" "${FULL_IMAGE}"
${CONTAINER_RUNTIME} push "${FULL_IMAGE}"

echo "============================================"
echo "Push complete!"
echo "Image URI: ${FULL_IMAGE}"
echo "============================================"
