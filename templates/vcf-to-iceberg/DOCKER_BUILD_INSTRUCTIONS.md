# Docker Build Instructions

## Prerequisites

- Finch (or Docker) installed and running
- AWS credentials configured (for pushing to ECR)

**Note**: This project uses Finch instead of Docker. Finch is a container development tool that provides a Docker-compatible CLI.

## Building the Container Locally

The container is built for dual architectures:
- **amd64 (x86_64)**: Required for AWS HealthOmics
- **arm64 (aarch64)**: For local testing on Mac

### Using the Build Script (Recommended)

```bash
cd workflow
./build_container.sh
```

This script will:
1. Build the container for both amd64 and arm64 architectures
2. Test that all dependencies are installed correctly
3. Verify all Python modules can be imported

### Manual Build

```bash
cd workflow
finch build --platform linux/amd64,linux/arm64 -t healthomics-vcf-loader:latest .
```

## Testing the Container

```bash
# Test that all dependencies are installed
finch run --rm healthomics-vcf-loader:latest python -c "
import pyiceberg
import pyarrow
import boto3
print('All dependencies loaded successfully')
"

# Test that Python modules are accessible
finch run --rm healthomics-vcf-loader:latest python test_imports.py

# Interactive shell for debugging
finch run --rm -it healthomics-vcf-loader:latest /bin/bash
```

## Pushing to Amazon ECR

On Apple Silicon Macs, `finch tag` + `finch push` will default to pushing the
local arm64 image. HealthOmics requires amd64 (x86_64), so you must build the
amd64 image explicitly before pushing.

```bash
# Set your AWS account ID and region
AWS_ACCOUNT_ID=123456789012
AWS_REGION=us-east-1
ECR_REPO=healthomics-vcf-loader

# 1. Build an amd64-only image (required for HealthOmics)
finch build --platform linux/amd64 -t healthomics-vcf-loader:amd64 .

# 2. Authenticate Finch to ECR
aws ecr get-login-password --region ${AWS_REGION} | \
  finch login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# 3. Create ECR repository (if it doesn't exist)
aws ecr create-repository --repository-name ${ECR_REPO} --region ${AWS_REGION} || true

# 4. Tag the amd64 image for ECR
finch tag healthomics-vcf-loader:amd64 \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:latest

# 5. Push the amd64 image to ECR
finch push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:latest

# 6. Grant HealthOmics access to pull images from the repository
aws ecr set-repository-policy \
  --repository-name ${ECR_REPO} \
  --region ${AWS_REGION} \
  --policy-text '{
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
        ]
      }
    ]
  }'
```

**Why build amd64 separately?** A multi-arch build (`--platform linux/amd64,linux/arm64`)
produces a manifest list, but `finch tag` and `finch push` on an Apple Silicon Mac will
resolve to the arm64 variant by default. Building with `--platform linux/amd64` explicitly
ensures the pushed image is x86_64, which is what HealthOmics requires.

**Important**: The repository policy step (step 6) is required — without it, HealthOmics
cannot pull your container image.

## Container Contents

The container includes:

- **Base**: Python 3.10 slim image from AWS ECR Public
- **Architectures**: amd64 (x86_64) and arm64 (aarch64)
- **System packages**: gcc, g++ (for compiling Python extensions)
- **Python packages**:
  - pyiceberg >= 0.9.0
  - pyiceberg-core >= 0.4.0
  - boto3 >= 1.37.26
  - pyarrow >= 19.0.1
- **Application modules**:
  - schema_1.py, schema_2.py, schema_3.py, schema_4.py
  - load_vcf_schema1.py, load_vcf_schema2.py, load_vcf_schema3.py, load_vcf_schema4.py
  - utils.py
  - metadata_schema.py

## Troubleshooting

### Build fails with "gcc not found"
The Dockerfile installs gcc and g++ to compile Python extensions. If this fails, check your internet connection.

### Import errors in container
Run the test script inside the container:
```bash
finch run --rm healthomics-vcf-loader:latest python test_imports.py
```

### Container size is large
The container uses a slim base image and cleans up apt cache. Current size should be around 500-800 MB per architecture.

### Architecture mismatch
To verify the container architecture:
```bash
finch run --rm healthomics-vcf-loader:latest uname -m
```
- `aarch64` = arm64 (Mac)
- `x86_64` = amd64 (HealthOmics)

## AWS HealthOmics Compatibility

This container is designed to run in AWS HealthOmics. Key compatibility features:

- Uses public ECR base image (no authentication needed for base)
- Includes all dependencies (no external downloads during execution)
- Python 3.10 (compatible with HealthOmics runtime)
- Minimal system dependencies
- Built for amd64 (x86_64) architecture required by HealthOmics
