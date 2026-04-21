#!/bin/bash

# Build script for HealthOmics VCF Loader Docker container
# This script builds dual architecture containers (amd64 and arm64)
# - amd64: Required for AWS HealthOmics
# - arm64: For local testing on Mac

set -e

CONTAINER_NAME="healthomics-vcf-loader"
CONTAINER_TAG="latest"

echo "Building dual architecture Docker container: ${CONTAINER_NAME}:${CONTAINER_TAG}"
echo "Architectures: amd64 (HealthOmics), arm64 (local Mac)"
echo ""

# Build for both architectures
finch build --platform linux/amd64,linux/arm64 -t ${CONTAINER_NAME}:${CONTAINER_TAG} .

echo ""
echo "Container built successfully for both architectures!"
echo ""
echo "Testing container dependencies..."
finch run --rm ${CONTAINER_NAME}:${CONTAINER_TAG} python -c "
import sys
try:
    import pyiceberg
    print('✓ PyIceberg imported successfully')
    import pyarrow
    print('✓ PyArrow imported successfully')
    import boto3
    print('✓ boto3 imported successfully')
    print('')
    print('All dependencies loaded successfully!')
    sys.exit(0)
except ImportError as e:
    print(f'✗ Import error: {e}')
    sys.exit(1)
"

echo ""
echo "Container is ready for use!"
echo ""
echo "To run the container:"
echo "  finch run --rm -it ${CONTAINER_NAME}:${CONTAINER_TAG} /bin/bash"
echo ""
echo "Note: Container supports both amd64 (HealthOmics) and arm64 (local Mac) architectures"
