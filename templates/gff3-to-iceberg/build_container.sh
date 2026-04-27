#!/bin/bash
set -euo pipefail

CONTAINER_RUNTIME="docker"
IMAGE_TAG="latest"

while [[ $# -gt 0 ]]; do
    case $1 in
        --tag) IMAGE_TAG="$2"; shift 2 ;;
        --finch) CONTAINER_RUNTIME="finch"; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "Building healthomics-gff3-loader:${IMAGE_TAG} for linux/amd64..."
${CONTAINER_RUNTIME} build --platform linux/amd64 -t "healthomics-gff3-loader:${IMAGE_TAG}" .
echo "Build complete."
