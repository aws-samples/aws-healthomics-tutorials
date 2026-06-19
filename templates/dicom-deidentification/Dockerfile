# Base image: ubuntu:22.04
#   - CUDA driver paths pre-configured in ldconfig
#   - python3.10 (Ubuntu 22.04 default) — matches HealthOmics runtime
#
# Why not python:3.X-slim: bookworm-slim images don't include the
# CUDA runtime package paths in their linker config, so the libcuda.so
# that HealthOmics' NVIDIA Container Toolkit injects at a system path
# isn't discovered by the dynamic linker. Torch then "imports" but
# `cudaGetDeviceCount()` fails with the misleading
# `Error 2: out of memory`.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# System packages:
#   python3.10 + python3-pip — runtime + package manager
#   libgl1, libglib2.0-0     — opencv-python-headless (CLAHE, resize)
#   libgomp1                  — numpy / scipy / opencv parallel kernels
RUN set -eu && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.10 \
        python3-pip \
        libgl1 \
        libglib2.0-0 \
        libgomp1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# CUDA-bundled torch from PyTorch's CUDA-12.1 wheel index.
#
# Why 2.4.1 specifically:
# - torch < 2.2 was built against numpy 1.x; with modern pip resolving
#   numpy>=2.0, easyocr fails at runtime with "Numpy is not available"
#   because torch's tensor-numpy bridge can't find _ARRAY_API in the
#   new numpy.
# - 2.2+ rebuilt against numpy 2.0 ABI, fixing that.
# - cu121 wheel is published for torch 2.2 through 2.5; 2.6+ dropped it.
# - 2.4.1 is a stable middle pick: numpy-2 compatible, cu121 available,
#   Python 3.10 wheels published.
#
# Pinned BEFORE other packages so easyocr's unconstrained `torch` dep
# is satisfied without pip resolving to a default-index wheel with a
# newer CUDA version that may not match HealthOmics' host driver.
RUN set -eu && \
    pip3 install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cu121 \
        "torch==2.4.1" "torchvision==0.19.1"

# Pixel decode plugins (all permissive licenses, no GPL):
#   - pylibjpeg-openjpeg (MIT): JPEG 2000 / HTJ2K
#   - pyjpegls (MIT):           JPEG-LS lossless / near-lossless
#   - pillow (MIT-CMU):         JPEG Baseline
# pylibjpeg-libjpeg (GPLv3) was deliberately excluded.
#
# opencv-python-headless is required by TextDetector's CLAHE + upscale
# passes (cv2.createCLAHE, cv2.resize); listing it explicitly insulates
# us from EasyOCR dropping the dep in a future release.
RUN set -eu && \
    pip3 install --no-cache-dir \
        pydicom \
        pylibjpeg \
        pylibjpeg-openjpeg \
        pyjpegls \
        pillow \
        numpy \
        opencv-python-headless \
        rapidfuzz \
        easyocr

# Pre-download EasyOCR model weights at build time. The first Reader()
# call would otherwise pull ~70 MB from jaided.ai + GitHub at runtime —
# which fails in HealthOmics tasks that run with no outbound internet
# (only S3/ECR endpoints are reachable). EASYOCR_MODULE_PATH is read at
# Reader() init by TextDetector to set download_enabled=False on the
# baked-in path.
ENV EASYOCR_MODULE_PATH=/opt/easyocr
RUN set -eu && \
    mkdir -p /opt/easyocr && \
    python3 -c "import easyocr; easyocr.Reader(['en'], gpu=False, model_storage_directory='/opt/easyocr/model', user_network_directory='/opt/easyocr/user_network')" && \
    ls -la /opt/easyocr/model

# Copy application code as an importable package so relative imports work
COPY src/dicom_deid/ /opt/dicom-deid/dicom_deid/
ENV PYTHONPATH=/opt/dicom-deid

ENTRYPOINT ["python3", "-m", "dicom_deid.main"]
