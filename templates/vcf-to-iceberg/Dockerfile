# Dockerfile for HealthOmics VCF Loader
# Python 3.10 base image with AWS HealthOmics compatibility
FROM public.ecr.aws/docker/library/python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
# Use --only-binary for pyiceberg-core to avoid Rust compilation under QEMU
RUN pip install --no-cache-dir --only-binary=pyiceberg-core -r requirements.txt

# Copy Python modules — schema definitions and loaders
COPY schema_1.py .
COPY schema_2.py .
COPY schema_3.py .
COPY schema_4.py .
COPY load_vcf_schema1.py .
COPY load_vcf_schema2.py .
COPY load_vcf_schema3.py .
COPY load_vcf_schema4.py .
COPY utils.py .
COPY metadata_schema.py .
COPY test_imports.py .

# Copy workflow orchestration scripts (referenced by main.nf via ${projectDir}/)
COPY validate_inputs.py .
COPY setup_catalog.py .
COPY check_connectivity.py .
COPY check_permissions.py .
COPY initialize_tables.py .
COPY load_vcf_wrapper.py .
COPY generate_summary.py .

# Set Python path
ENV PYTHONPATH=/app:$PYTHONPATH

# Default command
CMD ["/bin/bash"]
