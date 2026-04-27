version 1.1

## HealthOmics GFF3 Annotation Loader Workflow
##
## Loads GFF3 files into Apache Iceberg tables on AWS.
## Supports S3 Tables (managed Iceberg catalog) and vanilla Iceberg with Glue catalog.
##
## NETWORKING: Both catalog types require VPC-connected workflow runs.

workflow healthomics_gff3_loader {

    meta {
        description: "Loads GFF3 annotation files into Apache Iceberg tables on AWS."
        author: "AWS HealthOmics"
        version: "1.0.0"
    }

    parameter_meta {
        gff3_file: "S3 URI to the input GFF3 file (.gff3 or .gff3.gz)"
        schema: "Schema design to use: 1 (normalized) or 2 (denormalized)"
        destination: "For Glue catalog use bucket/path (no s3:// prefix). For S3 Tables use the full ARN."
        container: "ECR container image URI"
        namespace: "Iceberg namespace. Auto-determined by schema if omitted."
        batch_size: "Number of GFF3 records per processing batch (default: 100000)"
    }

    input {
        File gff3_file
        String schema
        String destination
        String container
        String? namespace
        Int batch_size = 100000
    }

    String full_destination = if sub(destination, "^arn:.*", "") == "" then destination else "s3://~{destination}"

    call validate_inputs {
        input:
            gff3_file = gff3_file,
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

    call load_gff3 {
        input:
            gff3_file = gff3_file,
            catalog_config = setup_catalog.catalog_json,
            init_result = initialize_tables.init_json,
            schema = schema,
            namespace = namespace,
            batch_size = batch_size,
            container = container
    }

    call generate_summary {
        input:
            gff3_file_path = gff3_file,
            schema = schema,
            destination = full_destination,
            validation_result = validate_inputs.validation_json,
            catalog_config = setup_catalog.catalog_json,
            init_result = initialize_tables.init_json,
            load_stats = load_gff3.stats_json,
            batch_size = batch_size,
            container = container
    }

    output {
        File summary = generate_summary.summary_json
        File validation_report = validate_inputs.validation_json
        File connectivity_report = check_connectivity.connectivity_json
        File permissions_report = check_permissions.permissions_json
        File table_init_report = initialize_tables.init_json
        File load_statistics = load_gff3.stats_json
    }
}


task validate_inputs {
    input {
        File gff3_file
        String schema
        String destination
        String container
    }
    command <<<
        set -eu
        python3 /app/validate_inputs.py \
            --gff3-file "~{gff3_file}" \
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


task setup_catalog {
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


task check_connectivity {
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


task check_permissions {
    input {
        File catalog_config
        String schema
        String? namespace
        String container
        File connectivity_report
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


task initialize_tables {
    input {
        File catalog_config
        String schema
        String? namespace
        String container
        File permissions_report
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


task load_gff3 {
    input {
        File gff3_file
        File catalog_config
        File init_result
        String schema
        String? namespace
        Int batch_size
        String container
    }
    command <<<
        set -eu
        if [ -z "~{select_first([namespace, ''])}" ]; then
            NAMESPACE=$(python3 -c "import json; data=json.load(open('~{init_result}')); print(data['namespace'])")
        else
            NAMESPACE="~{namespace}"
        fi
        python3 /app/load_gff3_wrapper.py \
            --gff3-file "~{gff3_file}" \
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


task generate_summary {
    input {
        File gff3_file_path
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
        FEATURES_LOADED=$(python3 -c "import json; data=json.load(open('~{load_stats}')); print(data.get('features_loaded', 0))")
        SOURCES_LOADED=$(python3 -c "import json; data=json.load(open('~{load_stats}')); print(data.get('sources_loaded', 0))")
        RELATIONSHIPS_LOADED=$(python3 -c "import json; data=json.load(open('~{load_stats}')); print(data.get('relationships_loaded', 0))")
        BATCHES_PROCESSED=$(python3 -c "import json; data=json.load(open('~{load_stats}')); print(data.get('batches_processed', 0))")
        TABLE_LOCATIONS=$(python3 -c "import json; data=json.load(open('~{init_result}')); metadata=data.get('table_metadata', {}); locations={k: v.get('location', '') for k, v in metadata.items()}; print(json.dumps(locations))")
        START_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        END_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

        python3 /app/generate_summary.py \
            --gff3-file "~{gff3_file_path}" \
            --schema "~{schema}" \
            --destination "~{destination}" \
            --namespace "${NAMESPACE}" \
            --catalog-type "${CATALOG_TYPE}" \
            --tables-created "${TABLES_CREATED}" \
            --features-loaded "${FEATURES_LOADED}" \
            --sources-loaded "${SOURCES_LOADED}" \
            --relationships-loaded "${RELATIONSHIPS_LOADED}" \
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
