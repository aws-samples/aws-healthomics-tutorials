version development

workflow dicom_deidentification {
    input {
        Directory dicom_input_prefix
        File deidentification_profile
        Boolean emit_jpeg_previews = false
        String container
    }

    call deidentify_task {
        input:
            dicom_input = dicom_input_prefix,
            profile = deidentification_profile,
            emit_jpeg_previews = emit_jpeg_previews,
            container = container
    }

    output {
        Directory deidentified_output = deidentify_task.output_dir
        File csv_mapping = deidentify_task.csv_mapping_file
        File job_manifest = deidentify_task.job_output_manifest
    }

    meta {
        description: "DICOM de-identification workflow for AWS HealthOmics. Processes DICOM files through metadata de-identification, optional pixel text detection, and optional pixel masking in a single-pass pipeline."
        author: "DICOM De-identification Team"
    }

    parameter_meta {
        dicom_input_prefix: {
            description: "S3 prefix containing DICOM files. HealthOmics localizes the prefix into a directory before the task runs (Directory type from WDL development; HealthOmics handles staging end-to-end)."
        }
        deidentification_profile: {
            description: "S3 path to the JSON de-identification profile configuration file."
        }
        emit_jpeg_previews: {
            description: "When true, the task writes a <sop_uid>.before.jpg / .after.jpg pair per instance to <output>/jpeg_previews/ for visual verification of mask placement. Diagnostic only; defaults to false to keep production runs lean."
        }
        container: {
            description: "ECR container image URI. Build and push the image with `build_and_push_container.sh` and pass the resulting URI here. No default — operators register the workflow once and supply the URI per run."
        }
    }
}

task deidentify_task {
    input {
        Directory dicom_input
        File profile
        Boolean emit_jpeg_previews = false
        String container
    }

    command <<<
        set -euo pipefail
        # HealthOmics' miniwdl engine requires task outputs to live INSIDE
        # the task's working directory. An absolute /output path was
        # rejected with `OutputError: task outputs attempted to use a
        # path outside its working directory`. We use a relative
        # `output` directory which miniwdl resolves to the task workdir
        # it created (e.g. /mnt/workflow/<run-id>/call-deidentify_task/work/output).
        mkdir -p output
        python3 -m dicom_deid.main \
            --input-dir ~{dicom_input} \
            --profile ~{profile} \
            --output-dir output \
            ~{if emit_jpeg_previews then "--emit-jpeg-previews" else ""}
    >>>

    runtime {
        container: container
        cpu: 16
        memory: "64 GB"
        # HealthOmics requires a SPECIFIC GPU type, not the generic
        # "nvidia". us-east-1 supports: nvidia-tesla-t4, nvidia-tesla-a10g,
        # nvidia-tesla-t4-a10g, nvidia-l4, nvidia-l40s, nvidia-l4-a10g,
        # nvidia-t4-a10g-l4. T4 is the cheapest and plenty for EasyOCR.
        acceleratorCount: 1
        acceleratorType: "nvidia-tesla-t4"
    }

    output {
        Directory output_dir = "output"
        File csv_mapping_file = "output/csv_mapping.csv"
        File job_output_manifest = "output/job_output_manifest.json"
    }

    meta {
        description: "Single-task DICOM de-identification pipeline: metadata de-identification with optional pixel text detection and pixel masking."
    }

    parameter_meta {
        dicom_input: {
            description: "Local directory containing staged DICOM files (HealthOmics-managed)."
        }
        profile: {
            description: "Local path to the JSON de-identification profile."
        }
        emit_jpeg_previews: {
            description: "Pass --emit-jpeg-previews through to the de-id CLI. See the workflow-level field of the same name."
        }
        container: {
            description: "ECR image URI used as runtime { container: ... }. Forwarded from the workflow input."
        }
    }
}
