#!/usr/bin/env bash
set -euo pipefail

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

###############################################################################
# destroy.sh — Tear down all resources created by deploy.sh.
#
# Deletes (in order):
#   1. ECR repositories created by the pull-through cache (docker-hub/*)
#   2. CloudFormation stacks (services first, then VPC)
#   3. S3 objects uploaded by deploy.sh
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate credentials
#
# Usage:
#   ./destroy.sh [--bucket <s3-bucket-name>]
#
# If --bucket is omitted, a default bucket name is generated:
#   openfold3-<account-id>-<region>
###############################################################################

# --- Parse arguments ---------------------------------------------------------
WORKFLOW_BUCKET=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bucket)
            WORKFLOW_BUCKET="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./destroy.sh [--bucket <s3-bucket-name>]"
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

# --- Step 1: Delete ECR pull-through cache repositories ----------------------
# HealthOmics runs create docker-hub/* repos via the pull-through cache.
# These are not managed by CloudFormation and must be removed before the
# cache rule (in the services stack) can be deleted cleanly.
echo "==> Deleting ECR pull-through cache repositories (docker-hub/*)..."
REPOS=$(aws ecr describe-repositories \
    --region "${REGION}" \
    --query "repositories[?starts_with(repositoryName, 'docker-hub/')].repositoryName" \
    --output text 2>/dev/null || true)

if [[ -n "${REPOS}" ]]; then
    for repo in ${REPOS}; do
        echo "  Deleting repository: ${repo}"
        aws ecr delete-repository \
            --repository-name "${repo}" \
            --force \
            --region "${REGION}" > /dev/null
    done
else
    echo "  No docker-hub/* repositories found."
fi

# --- Step 2: Delete CloudFormation stacks ------------------------------------
# Services stack first (depends on VPC resources).
echo "==> Deleting services stack: ${SERVICES_STACK_NAME}"
aws cloudformation delete-stack \
    --stack-name "${SERVICES_STACK_NAME}" \
    --region "${REGION}" 2>/dev/null || true

echo "  Waiting for ${SERVICES_STACK_NAME} deletion..."
aws cloudformation wait stack-delete-complete \
    --stack-name "${SERVICES_STACK_NAME}" \
    --region "${REGION}" 2>/dev/null || true

echo "==> Deleting VPC stack: ${VPC_STACK_NAME}"
aws cloudformation delete-stack \
    --stack-name "${VPC_STACK_NAME}" \
    --region "${REGION}" 2>/dev/null || true

echo "  Waiting for ${VPC_STACK_NAME} deletion..."
aws cloudformation wait stack-delete-complete \
    --stack-name "${VPC_STACK_NAME}" \
    --region "${REGION}" 2>/dev/null || true

# --- Step 3: Remove S3 objects uploaded by deploy.sh -------------------------
echo "==> Removing S3 objects uploaded by deploy.sh..."
aws s3 rm "s3://${WORKFLOW_BUCKET}/workflow-definition/workflow.zip" \
    --region "${REGION}" 2>/dev/null || true
aws s3 rm "s3://${WORKFLOW_BUCKET}/inputs/query_ubiquitin.json" \
    --region "${REGION}" 2>/dev/null || true
aws s3 rm "s3://${WORKFLOW_BUCKET}/model-parameters/of3-p2-155k.pt" \
    --region "${REGION}" 2>/dev/null || true

echo "==> Done"
