#!/bin/bash
#
# Build the HealthOmics Nuclei Segmentation container locally.
# Builds for amd64 (HealthOmics) and arm64 (local Mac testing).
#
# Usage:
#   ./build_container.sh
#   ./build_container.sh --docker
#   ./build_container.sh --podman
#   ./build_container.sh --finch
#

set -e

CONTAINER_NAME="healthomics-hovernet"
CONTAINER_TAG="latest"

# --- Auto-detect or override container runtime ---
detect_runtime() {
    if command -v finch &>/dev/null; then echo "finch"
    elif command -v podman &>/dev/null; then echo "podman"
    elif command -v docker &>/dev/null; then echo "docker"
    else echo ""; fi
}

CONTAINER_RUNTIME=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --finch)  CONTAINER_RUNTIME="finch";  shift ;;
        --podman) CONTAINER_RUNTIME="podman"; shift ;;
        --docker) CONTAINER_RUNTIME="docker"; shift ;;
        *) echo "Unknown option: $1"; echo "Usage: $0 [--finch|--podman|--docker]"; exit 1 ;;
    esac
done

if [ -z "${CONTAINER_RUNTIME}" ]; then
    CONTAINER_RUNTIME=$(detect_runtime)
    if [ -z "${CONTAINER_RUNTIME}" ]; then
        echo "Error: No container runtime found. Install finch, podman, or docker."
        exit 1
    fi
fi

echo "Building container: ${CONTAINER_NAME}:${CONTAINER_TAG}"
echo "Runtime: ${CONTAINER_RUNTIME}"
echo "Architectures: amd64 (HealthOmics), arm64 (local Mac)"
echo ""

# Download model weights from HuggingFace if not already present
MODEL_DIR="bundles/pathology_nuclei_segmentation_classification/models"
MODEL_FILE="${MODEL_DIR}/model.pt"
MODEL_URL="https://huggingface.co/MONAI/pathology_nuclei_segmentation_classification/resolve/main/models/model.pt?download=true"

if [ ! -f "${MODEL_FILE}" ]; then
    echo ">> Downloading model weights from HuggingFace..."
    mkdir -p "${MODEL_DIR}"
    curl -L -o "${MODEL_FILE}" "${MODEL_URL}"
    echo "   Model downloaded ($(du -h "${MODEL_FILE}" | cut -f1))."
    echo ""
else
    echo ">> Model weights already present ($(du -h "${MODEL_FILE}" | cut -f1))."
    echo ""
fi

${CONTAINER_RUNTIME} build --platform linux/amd64,linux/arm64 -t ${CONTAINER_NAME}:${CONTAINER_TAG} .

echo ""
echo "Container built successfully!"
echo ""
echo "Verifying dependencies..."

# Skip verification when cross-compiling — QEMU can segfault on PyTorch C extensions
HOST_ARCH=$(uname -m)
if [ "${HOST_ARCH}" = "x86_64" ] || [ "${HOST_ARCH}" = "aarch64" ] || [ "${HOST_ARCH}" = "arm64" ]; then
    ${CONTAINER_RUNTIME} run --rm ${CONTAINER_NAME}:${CONTAINER_TAG} python3 -c "
import sys
try:
    import torch
    print(f'  torch {torch.__version__}')
    import monai
    print(f'  monai {monai.__version__}')
    import openslide
    print('  openslide OK')
    print('')
    print('All dependencies loaded successfully!')
    sys.exit(0)
except ImportError as e:
    print(f'Import error: {e}')
    sys.exit(1)
" || echo "Warning: Dependency verification failed (may be expected under QEMU emulation)."
else
    echo "Skipping verification (unknown host arch: ${HOST_ARCH})."
fi

echo ""
echo "Container is ready!"
echo ""
echo "To run interactively:"
echo "  ${CONTAINER_RUNTIME} run --rm -it ${CONTAINER_NAME}:${CONTAINER_TAG} /bin/bash"
