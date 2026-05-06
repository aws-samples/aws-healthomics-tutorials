# Docker Build Instructions

## Prerequisites

- A container runtime installed: [Finch](https://github.com/runfinch/finch), [Podman](https://podman.io/), or [Docker](https://www.docker.com/)
- AWS CLI configured (for pushing to Amazon Elastic Container Registry (Amazon ECR))

The build scripts auto-detect which runtime is available (checking finch → podman → docker). You can override with `--finch`, `--podman`, or `--docker`.

## Building the Container Locally

The container is built for dual architectures:
- **amd64 (x86_64)**: Required for AWS HealthOmics
- **arm64 (aarch64)**: For local testing on Apple Silicon Macs

### Using the Build Script (Recommended)

```bash
./build_container.sh
```

This script will:
1. Auto-detect your container runtime (finch, podman, or docker)
2. Build the container for both amd64 and arm64 architectures
3. Verify that PyTorch, MONAI, and OpenSlide are installed correctly

To force a specific runtime:

```bash
./build_container.sh --docker
```

### Manual Build

```bash
# Replace 'finch' with your container runtime
finch build --platform linux/amd64,linux/arm64 -t healthomics-hovernet:latest .
```

## Testing the Container

```bash
# Verify dependencies
finch run --rm healthomics-hovernet:latest python3 -c "
import torch; import monai; import openslide
print(f'torch {torch.__version__}, monai {monai.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print('All dependencies OK')
"

# Interactive shell for debugging
finch run --rm -it healthomics-hovernet:latest /bin/bash
```

## Pushing to Amazon ECR

### Using the Push Script (Recommended)

```bash
./build_and_push_container.sh \
  --account-id 123456789012 \
  --region us-east-1 \
  --repo healthomics-hovernet
```

This script will:
1. Build an amd64 image (required for HealthOmics)
2. Authenticate to ECR
3. Create the ECR repository if it doesn't exist (with scan-on-push enabled)
4. Set the repository policy to grant HealthOmics pull access
5. Tag and push the image

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--account-id` | (required) | AWS account ID |
| `--region` | (required) | AWS region |
| `--repo` | `healthomics-hovernet` | ECR repository name |
| `--tag` | `latest` | Image tag |
| `--skip-build` | — | Skip build, only tag and push |
| `--finch` / `--podman` / `--docker` | auto-detect | Force container runtime |

### Manual Push

```bash
AWS_ACCOUNT_ID=123456789012
AWS_REGION=us-east-1
ECR_REPO=healthomics-hovernet

# 1. Build amd64 image (required for HealthOmics)
finch build --platform linux/amd64 -t healthomics-hovernet:latest .

# 2. Authenticate to ECR
aws ecr get-login-password --region ${AWS_REGION} | \
  finch login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# 3. Create ECR repository (if needed)
aws ecr create-repository --repository-name ${ECR_REPO} --region ${AWS_REGION} || true

# 4. Grant HealthOmics pull access
aws ecr set-repository-policy \
  --repository-name ${ECR_REPO} \
  --region ${AWS_REGION} \
  --policy-text '{
    "Version": "2012-10-17",
    "Statement": [{
      "Sid": "AllowHealthOmicsAccess",
      "Effect": "Allow",
      "Principal": { "Service": "omics.amazonaws.com" },
      "Action": [
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:BatchCheckLayerAvailability"
      ],
      "Condition": {
        "StringEquals": { "aws:SourceAccount": "'${AWS_ACCOUNT_ID}'" }
      }
    }]
  }'

# 5. Tag and push
finch tag healthomics-hovernet:latest \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:latest
finch push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:latest
```

**Important**: The repository policy (step 4) is required — without it, HealthOmics cannot pull your container image.

**Why build amd64 separately?** On Apple Silicon Macs, a multi-arch build produces a manifest list, but `tag` and `push` resolve to the local arm64 variant by default. Building with `--platform linux/amd64` explicitly ensures the pushed image is x86_64.

## Container Contents

- **Base**: Ubuntu 22.04
- **System packages**: Python 3.10, OpenSlide (libopenslide0)
- **Python packages**: PyTorch 2.1.2, TorchVision 0.16.2, MONAI 1.3.1, OpenSlide-Python 1.3.1, SciPy, scikit-image, NumPy, Pillow, tqdm
- **Application**: `process_wsi.py` pipeline script
- **Model weights**: HoVerNet (fast mode) from MONAI Model Zoo v0.2.8 (~144 MB)

## Troubleshooting

### Build fails with OpenSlide errors
The Dockerfile installs `libopenslide0` and `libopenslide-dev` from apt. If this fails, check your internet connection or base image availability.

### Import errors in container
Run an interactive shell and test imports manually:
```bash
finch run --rm -it healthomics-hovernet:latest python3 -c "import torch; import monai; import openslide; print('OK')"
```

### Container size is large
The container includes PyTorch and MONAI with CUDA support, plus model weights. Expected size is 3-5 GB. This is normal for GPU ML containers.

### Architecture mismatch
Verify the container architecture:
```bash
finch run --rm healthomics-hovernet:latest uname -m
```
- `aarch64` = arm64 (Mac)
- `x86_64` = amd64 (HealthOmics)

### Cross-compilation verification skipped
When building amd64 on an ARM Mac, dependency verification is skipped because QEMU emulation can segfault on PyTorch's CUDA extensions. The container runs natively on HealthOmics (x86_64) so this is safe.

## HealthOmics Compatibility

- Uses Ubuntu 22.04 base image
- All dependencies bundled (no external downloads at runtime)
- Model weights baked into the image
- Python 3.10 compatible with HealthOmics runtime
- Built for amd64 (x86_64) architecture required by HealthOmics
- GPU-enabled: requires `acceleratorType: "nvidia-t4-a10g-l4"` in WDL runtime
