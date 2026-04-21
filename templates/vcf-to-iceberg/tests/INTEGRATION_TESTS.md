# Integration Tests for HealthOmics VCF Loader Workflow

This document describes the integration tests for the WDL workflow and how to run them.

## Overview

The integration tests validate end-to-end workflow execution including:
- Input validation
- Catalog configuration (S3 Tables and vanilla Iceberg)
- Table initialization for all schema types (1, 2, 3, 4)
- VCF data loading
- Summary generation
- Error handling

**OCI Runtime Detection:** The tests automatically detect and use the available OCI container runtime on your system (docker, finch, or podman). No manual configuration needed!

## Test Structure

### Component Tests (`TestWDLWorkflowComponents`)

These tests validate individual workflow components in isolation:
- Input validation with various scenarios
- Invalid schema detection
- Missing file detection

**Requirements:** Python 3.10+, pytest

**Run:**
```bash
cd workflow
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowComponents -v
```

### Full Integration Tests (`TestWDLWorkflowIntegration`)

These tests run the complete WDL workflow end-to-end. They require additional setup.

**Requirements:**
1. miniwdl or Cromwell installed
2. OCI container runtime (docker, finch, or podman) - automatically detected
3. AWS credentials (for S3 tests)
4. S3 bucket access (for vanilla S3 tests)
5. S3 Tables bucket (for S3 Tables tests)

## Setup Instructions

### 1. Install a WDL Runner

```bash
# Option A: miniwdl (recommended)
pip install miniwdl

# Verify installation
miniwdl --version
```

### 2. Install OCI Container Runtime

The tests automatically detect which container runtime you have installed. Choose one:

#### Option A: Docker
```bash
# macOS
brew install docker

# Linux
sudo apt-get install docker.io
```

#### Option B: Finch (Recommended for macOS)
```bash
# macOS
brew install finch
finch vm init
```

#### Option C: Podman
```bash
# macOS
brew install podman

# Linux
sudo apt-get install podman
```

The tests will automatically detect and use whichever runtime is available.

### 3. Build Container

```bash
cd workflow
./build_container.sh
```

This builds the container image with all required dependencies (Python, PyIceberg, PyArrow, boto3).

### 3. Configure AWS Credentials

For S3 and S3 Tables tests, configure AWS credentials:

```bash
# Option 1: AWS CLI configuration
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1

# Option 3: AWS Profile
export AWS_PROFILE=your-profile
```

### 4. Create Test S3 Bucket (Optional)

For vanilla S3 tests, create a test bucket:

```bash
aws s3 mb s3://your-test-bucket-name
```

### 5. Create S3 Tables Bucket (Optional)

For S3 Tables tests, create an S3 Tables bucket:

```bash
aws s3tables create-table-bucket \
    --name your-table-bucket-name \
    --region us-east-1
```

## Running Integration Tests

### Run All Component Tests

```bash
cd workflow
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowComponents -v
```

### Run Specific Integration Test

#### Test with Schema 1 (Vanilla S3)

```bash
cd workflow
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowIntegration::test_workflow_schema_1_vanilla_s3 -v -s
```

#### Test with Schema 2 (Vanilla S3)

```bash
cd workflow
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowIntegration::test_workflow_schema_2_vanilla_s3 -v -s
```

#### Test Error Handling

```bash
cd workflow
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowIntegration::test_workflow_error_invalid_schema -v -s
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowIntegration::test_workflow_error_missing_vcf_file -v -s
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowIntegration::test_workflow_error_invalid_destination -v -s
```

#### Test Custom Parameters

```bash
cd workflow
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowIntegration::test_workflow_custom_namespace -v -s
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowIntegration::test_workflow_custom_batch_size -v -s
```

#### Test Idempotency

```bash
cd workflow
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowIntegration::test_workflow_idempotent_execution -v -s
```

### Run All Integration Tests

**Note:** This requires a WDL runner, Docker, and may take several minutes:

```bash
cd workflow
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowIntegration -v -s
```

### Run S3 Tables Test

The S3 Tables test is skipped by default. To run it:

1. Create an S3 Tables bucket
2. Update the ARN in the test
3. Remove the `@pytest.mark.skip` decorator
4. Run:

```bash
cd workflow
python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowIntegration::test_workflow_s3tables_destination -v -s
```

## Test Data

The tests use VCF files from the `test-data/` directory:
- `spec-v4.3.vcf.gz` - Small VCF file for quick tests
- `sample1-bcbio-cancer.vcf.gz` - Cancer sample VCF
- `sample2-bcbio-cancer.vcf.gz` - Another cancer sample VCF

## Troubleshooting

### WDL Runner Not Found

```
Error: miniwdl: command not found
```

**Solution:** Install miniwdl (`pip install miniwdl`) or add it to your PATH.

### No Container Runtime Found

```
Error: No OCI runtime (docker, finch, podman) found on system
```

**Solution:** Install one of the supported container runtimes:
- Docker: `brew install docker` (macOS) or `sudo apt-get install docker.io` (Linux)
- Finch: `brew install finch` (macOS)
- Podman: `brew install podman` (macOS) or `sudo apt-get install podman` (Linux)

The tests will automatically detect and use whichever runtime is available.

### Container Runtime Not Running

```
Error: Cannot connect to the container runtime
```

**Solution:** 
- For Docker: Start Docker Desktop or Docker daemon
- For Finch: Run `finch vm start`
- For Podman: Start the Podman machine with `podman machine start`

### AWS Credentials Not Found

```
Error: AWS credentials not found
```

**Solution:** Configure AWS credentials using `aws configure` or environment variables.

### S3 Bucket Access Denied

```
Error: Access denied to S3 bucket
```

**Solution:** Ensure your AWS credentials have the required permissions:
- `s3:PutObject`
- `s3:GetObject`
- `s3:ListBucket`
- `s3:HeadBucket`

### Container Build Failed

```
Error: Docker build failed
```

**Solution:** Check Docker is running and you have internet access to pull base images.

## Test Coverage

The integration tests validate:

### Requirements Coverage

- **1.1**: Workflow execution in HealthOmics environment
- **2.1**: VCF file path parameter
- **2.2**: Schema selection parameter
- **2.3**: Destination location parameter
- **4.1**: Table creation based on schema
- **5.1**: VCF data loading
- **7.1**: Summary JSON generation
- **8.1**: Invalid schema error handling
- **8.2**: Missing VCF file error handling
- **8.3**: Invalid destination error handling

### Test Scenarios

1. **Schema 1 with Vanilla S3**: Tests normalized schema (3 tables)
2. **Schema 2 with Vanilla S3**: Tests partially denormalized schema (2 tables)
3. **S3 Tables Destination**: Tests S3 Tables catalog configuration
4. **Error Handling**: Tests validation and error messages
5. **Custom Parameters**: Tests namespace and batch size customization
6. **Idempotency**: Tests running workflow multiple times

## Continuous Integration

For CI/CD pipelines, use the component tests which don't require a WDL runner or AWS:

```yaml
# Example GitHub Actions workflow
- name: Run Component Tests
  run: |
    cd workflow
    python3 -m pytest tests/test_wdl_integration.py::TestWDLWorkflowComponents -v
```

For full integration tests in CI, use mocked S3 or LocalStack:

```yaml
# Example with LocalStack
- name: Start LocalStack
  run: docker run -d -p 4566:4566 localstack/localstack

- name: Run Integration Tests
  run: |
    export AWS_ENDPOINT_URL=http://localhost:4566
    cd workflow
    python3 -m pytest tests/test_wdl_integration.py -v
```

## Additional Resources

- [WDL Specification](https://github.com/openwdl/wdl)
- [miniwdl Documentation](https://miniwdl.readthedocs.io/)
- [PyIceberg Documentation](https://py.iceberg.apache.org/)
- [AWS S3 Tables Documentation](https://docs.aws.amazon.com/s3/latest/userguide/s3-tables.html)
- [Workflow README](../README.md)
