// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

nextflow.enable.dsl=2

process VALIDATE_QUERY_JSON {
    container 'openfoldconsortium/openfold3:latest'
    cpus 2
    memory 4.GB

    input:
    path query_json

    output:
    path query_json

    script:
    """
    #!/usr/bin/env python3
    import json, sys
    try:
        with open("${query_json}") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in query file: {e}", file=sys.stderr)
        sys.exit(1)
    if "queries" not in data:
        print("ERROR: Query JSON missing required 'queries' key", file=sys.stderr)
        sys.exit(1)
    print("Query JSON validation passed")
    """
}

process OPENFOLD_PREDICT {
    container 'openfoldconsortium/openfold3:latest'
    cpus 4
    memory 32.GB
    accelerator 1, type: 'nvidia-l40s'
    publishDir '/mnt/workflow/pubdir/', mode: 'copy'

    input:
    path query_json
    path model_params
    path runner_yml
    val use_msa_server
    val extra_args

    output:
    path "output/**"

    script:
    def msa_flag = use_msa_server ? '--use-msa-server=True' : '--use-msa-server=False'
    def runner_flag = runner_yml.name != 'NO_RUNNER' ? "--runner-config ${runner_yml}" : ''
    def extra = extra_args ?: ''
    """
    export TORCH_CUDA_ARCH_LIST="8.0;8.9"

    mkdir -p /root/.openfold3
    cp ${model_params} /root/.openfold3/

    run_openfold predict \
        --query-json ${query_json} \
        ${msa_flag} \
        --output-dir output/ \
        ${runner_flag} \
        ${extra}
    """
}

workflow {
    // Resolve query JSON — fail fast if file does not exist
    query_json = file(params.query_json, checkIfExists: true)

    // Handle optional runner YAML — sentinel file when not provided
    runner_yml = params.runner_yml
        ? file(params.runner_yml, checkIfExists: true)
        : file("NO_RUNNER")

    // Resolve model parameters (local path or S3 URI, Nextflow stages automatically)
    model_params = file(params.params, checkIfExists: true)

    // Validate query JSON then run inference
    VALIDATE_QUERY_JSON(query_json)
    OPENFOLD_PREDICT(
        VALIDATE_QUERY_JSON.out,
        model_params,
        runner_yml,
        params.use_msa_server,
        params.extra_args
    )
}
