FROM public.ecr.aws/docker/library/python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=pyiceberg-core -r requirements.txt

COPY schema_1.py .
COPY schema_2.py .
COPY load_gff3_schema1.py .
COPY load_gff3_schema2.py .
COPY utils.py .
COPY metadata_schema.py .

COPY validate_inputs.py .
COPY setup_catalog.py .
COPY check_connectivity.py .
COPY check_permissions.py .
COPY initialize_tables.py .
COPY load_gff3_wrapper.py .
COPY generate_summary.py .

ENV PYTHONPATH=/app:${PYTHONPATH}

CMD ["/bin/bash"]
