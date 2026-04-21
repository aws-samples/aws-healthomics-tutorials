version 1.1

## HealthOmics VCF Loader Workflow
##
## Loads VCF files into Apache Iceberg tables on AWS.
## Supports S3 Tables (managed Iceberg catalog) and vanilla Iceberg with Glue catalog.
##
## NETWORKING: Both catalog types require VPC-connected workflow runs.
## Start the run with networking_mode=VPC and a HealthOmics Configuration.

workflow healthomics_vcf_loader {

    meta {
        description: "Loads VCF files into Apache Iceberg tables on AWS. Supports S3 Tables and Glue/Iceberg catalogs."
        author: "AWS HealthOmics Team"
        version: "1.1.0"
    }

    parameter_meta {
        vcf_file: "S3 URI to the input VCF file (.vcf or .vcf.gz)"
        schema: "Schema design to use: 1, 2, 3, or 4"
        destination: "Iceberg warehouse location. For Glue catalog use bucket/path format (without s3:// prefix). For S3 Tables use the full ARN."
        container: "ECR container image URI"
        namespace: "Iceberg namespace. Auto-determined by schema if omitted."
        batch_size: "Number of VCF records per processing batch (default: 100000)"
    }

    input {
        File vcf_file
        String schema
        String destination
        String container
        String? namespace
        Int batch_size = 100000
    }

    # Reconstruct full destination URI — users pass bucket/path without s3:// prefix
    # to prevent HealthOmics from treating it as a file input.
    # S3 Tables ARNs (arn:aws:s3tables:...) are passed as-is.
    String full_destination = if sub(destination, "^arn:.*", "") == "" then destination else "s3://~{destination}"

    call validate_inputs {
        input:
            vcf_file = vcf_file,
            schema = schema,
            destination = full_destination,
            container = container
    }

    call setup_catalog {
        input:
            validation_result = validate_inputs.validation_json,
            destination = full_destination,
            namespace = namespace,
            container = container
    }

    call check_connectivity {
        input:
            catalog_config = setup_catalog.catalog_json,
            container = container
    }

    call check_permissions {
        input:
            catalog_config = setup_catalog.catalog_json,
            schema = schema,
            namespace = namespace,
            container = container,
            connectivity_report = check_connectivity.connectivity_json
    }

    call initialize_tables {
        input:
            catalog_config = setup_catalog.catalog_json,
            schema = schema,
            namespace = namespace,
            container = container,
            permissions_report = check_permissions.permissions_json
    }

    call load_vcf {
        input:
            vcf_file = vcf_file,
            catalog_config = setup_catalog.catalog_json,
            init_result = initialize_tables.init_json,
            schema = schema,
            namespace = namespace,
            batch_size = batch_size,
            container = container
    }

    call generate_summary {
        input:
            vcf_file_path = vcf_file,
            schema = schema,
            destination = full_destination,
            validation_result = validate_inputs.validation_json,
            catalog_config = setup_catalog.catalog_json,
            init_result = initialize_tables.init_json,
            load_stats = load_vcf.stats_json,
            batch_size = batch_size,
            container = container
    }

    output {
        File summary = generate_summary.summary_json
        File validation_report = validate_inputs.validation_json
        File connectivity_report = check_connectivity.connectivity_json
        File permissions_report = check_permissions.permissions_json
        File table_init_report = initialize_tables.init_json
        File load_statistics = load_vcf.stats_json
    }
}


## Validates all input parameters before workflow execution.
task validate_inputs {

    meta {
        description: "Validates VCF file accessibility, schema selection, and destination format."
    }

    input {
        File vcf_file
        String schema
        String destination
        String container
    }

    command <<<
        set -eu
        python3 /app/validate_inputs.py \
            --vcf-file "~{vcf_file}" \
            --schema "~{schema}" \
            --destination "~{destination}" \
            --output validation_result.json
    >>>

    output {
        File validation_json = "validation_result.json"
    }

    runtime {
        container: container
        cpu: 2
        memory: "4 GB"
    }
}


## Configures the Iceberg catalog based on destination type.
task setup_catalog {

    meta {
        description: "Configures S3 Tables REST catalog or Glue catalog based on destination."
    }

    input {
        File validation_result
        String destination
        String? namespace
        String container
    }

    command <<<
        set -eu
        CATALOG_TYPE=$(python3 -c "import json; data=json.load(open('~{validation_result}')); print(data['catalog_type'])")

        python3 /app/setup_catalog.py \
            --catalog-type "${CATALOG_TYPE}" \
            --destination "~{destination}" \
            ~{if defined(namespace) then '--namespace "' + namespace + '"' else ''} \
            --output catalog_config.json
    >>>

    output {
        File catalog_json = "catalog_config.json"
    }

    runtime {
        container: container
        cpu: 2
        memory: "4 GB"
    }
}


## Validates network connectivity to required AWS service endpoints.
task check_connectivity {

    meta {
        description: "Checks connectivity to Glue, Lake Formation, S3 Tables, and STS endpoints. Fails fast if VPC networking is misconfigured."
    }

    input {
        File catalog_config
        String container
    }

    command <<<
        set -eu
        python3 /app/check_connectivity.py \
            --catalog-config "~{catalog_config}" \
            --output connectivity_report.json
    >>>

    output {
        File connectivity_json = "connectivity_report.json"
    }

    runtime {
        container: container
        cpu: 2
        memory: "4 GB"
    }
}


## Probes AWS permissions before table operations.
task check_permissions {

    meta {
        description: "Checks Glue access, Lake Formation governance and grants, S3 write access, or S3 Tables API access."
    }

    input {
        File catalog_config
        String schema
        String? namespace
        String container
        File connectivity_report  # ensures ordering
    }

    command <<<
        set -eu
        python3 /app/check_permissions.py \
            --catalog-config "~{catalog_config}" \
            --schema "~{schema}" \
            ~{if defined(namespace) then '--namespace "' + namespace + '"' else ''} \
            --output permissions_report.json
    >>>

    output {
        File permissions_json = "permissions_report.json"
    }

    runtime {
        container: container
        cpu: 2
        memory: "4 GB"
    }
}


## Creates Iceberg tables if they don't exist.
task initialize_tables {

    meta {
        description: "Creates namespace and tables based on schema selection. Verifies schema if tables already exist."
    }

    input {
        File catalog_config
        String schema
        String? namespace
        String container
        File permissions_report  # ensures ordering
    }

    command <<<
        set -eu
        python3 /app/initialize_tables.py \
            --catalog-config "~{catalog_config}" \
            --schema "~{schema}" \
            ~{if defined(namespace) then '--namespace "' + namespace + '"' else ''} \
            --output table_init_result.json
    >>>

    output {
        File init_json = "table_init_result.json"
    }

    runtime {
        container: container
        cpu: 2
        memory: "4 GB"
    }
}


## Loads VCF data into Iceberg tables.
task load_vcf {

    meta {
        description: "Parses VCF records in batches and writes to Iceberg tables using the selected schema."
    }

    input {
        File vcf_file
        File catalog_config
        File init_result
        String schema
        String? namespace
        Int batch_size
        String container
    }

    command <<<
        set -eu

        # Resolve namespace from init result if not provided
        if [ -z "~{select_first([namespace, ''])}" ]; then
            NAMESPACE=$(python3 -c "import json; data=json.load(open('~{init_result}')); print(data['namespace'])")
        else
            NAMESPACE="~{namespace}"
        fi

        python3 /app/load_vcf_wrapper.py \
            --vcf-file "~{vcf_file}" \
            --catalog-config "~{catalog_config}" \
            --schema "~{schema}" \
            --namespace "${NAMESPACE}" \
            --batch-size ~{batch_size} \
            --output load_stats.json
    >>>

    output {
        File stats_json = "load_stats.json"
    }

    runtime {
        container: container
        cpu: 4
        memory: "16 GB"
    }
}


## Generates a JSON summary with workflow execution metadata.
task generate_summary {

    meta {
        description: "Aggregates results from all stages into a summary JSON."
    }

    input {
        File vcf_file_path
        String schema
        String destination
        File validation_result
        File catalog_config
        File init_result
        File load_stats
        Int batch_size
        String container
    }

    command <<<
        set -eu

        CATALOG_TYPE=$(python3 -c "import json; data=json.load(open('~{validation_result}')); print(data['catalog_type'])")
        NAMESPACE=$(python3 -c "import json; data=json.load(open('~{init_result}')); print(data['namespace'])")
        TABLES_CREATED=$(python3 -c "import json; data=json.load(open('~{init_result}')); print(','.join(data['all_tables']))")
        VARIANTS_LOADED=$(python3 -c "import json; data=json.load(open('~{load_stats}')); print(data.get('variants_loaded', 0))")
        SAMPLES_LOADED=$(python3 -c "import json; data=json.load(open('~{load_stats}')); print(data.get('samples_loaded', 0))")
        VARIANT_SAMPLE_ASSOC=$(python3 -c "import json; data=json.load(open('~{load_stats}')); print(data.get('variant_sample_associations', 0))")
        BATCHES_PROCESSED=$(python3 -c "import json; data=json.load(open('~{load_stats}')); print(data.get('batches_processed', 0))")
        TABLE_LOCATIONS=$(python3 -c "import json; data=json.load(open('~{init_result}')); metadata=data.get('table_metadata', {}); locations={k: v.get('location', '') for k, v in metadata.items()}; print(json.dumps(locations))")
        START_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        END_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

        python3 /app/generate_summary.py \
            --vcf-file "~{vcf_file_path}" \
            --schema "~{schema}" \
            --destination "~{destination}" \
            --namespace "${NAMESPACE}" \
            --catalog-type "${CATALOG_TYPE}" \
            --tables-created "${TABLES_CREATED}" \
            --variants-loaded "${VARIANTS_LOADED}" \
            --samples-loaded "${SAMPLES_LOADED}" \
            --variant-sample-associations "${VARIANT_SAMPLE_ASSOC}" \
            --batches-processed "${BATCHES_PROCESSED}" \
            --batch-size ~{batch_size} \
            --start-time "${START_TIME}" \
            --end-time "${END_TIME}" \
            --table-locations "${TABLE_LOCATIONS}" \
            --output summary.json
    >>>

    output {
        File summary_json = "summary.json"
    }

    runtime {
        container: container
        cpu: 2
        memory: "4 GB"
    }
}
