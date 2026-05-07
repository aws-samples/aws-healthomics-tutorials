version 1.1

workflow nuclei_segmentation {

    meta {
        description: "GPU-accelerated nuclei segmentation and classification for H&E whole-slide images using HoVerNet."
        author: "AWS HealthOmics"
        version: "1.0.0"
    }

    parameter_meta {
        slide_image: "Amazon Simple Storage Service (Amazon S3) URI of the SVS whole-slide image"
        pyramid_level: "OpenSlide pyramid level (0 = highest resolution)"
        tile_size: "Square tile size in pixels (128-1024)"
        overlap: "Pixel overlap between adjacent tiles (default: tile_size/4)"
        max_tiles: "Limit number of tiles processed (for testing)"
        roi_geojson: "Optional GeoJSON file with ROI polygons for region filtering"
        container_image_uri: "Amazon Elastic Container Registry (Amazon ECR) container image URI"
    }

    input {
        File   slide_image
        Int    pyramid_level      = 0
        Int    tile_size          = 512
        Int?   overlap
        Int?   max_tiles
        File?  roi_geojson
        String container_image_uri
    }

    call segment_nuclei {
        input:
            slide_image        = slide_image,
            pyramid_level      = pyramid_level,
            tile_size          = tile_size,
            overlap            = overlap,
            max_tiles          = max_tiles,
            roi_geojson        = roi_geojson,
            container_image_uri = container_image_uri
    }

    output {
        File nuclei_geojson      = segment_nuclei.nuclei_geojson
        File tissue_mask_geojson = segment_nuclei.tissue_mask_geojson
        File task_log            = segment_nuclei.task_log
    }
}

task segment_nuclei {

    meta {
        description: "Runs HoVerNet nuclei segmentation on a whole-slide image with overlapping tiles and centroid-based stitching."
    }

    input {
        File   slide_image
        Int    pyramid_level
        Int    tile_size
        Int?   overlap
        Int?   max_tiles
        File?  roi_geojson
        String container_image_uri
    }

    command <<<
        set -euo pipefail

        LOG="task.log"
        log() { echo "[$(date +%H:%M:%S)] $1" | tee -a "$LOG"; }

        # Trap to create placeholder outputs on failure so the log gets collected
        cleanup() {
            local exit_code=$?
            if [ ! -f nuclei.geojson ]; then
                log "WARNING: nuclei.geojson missing, creating placeholder"
                echo '{"type":"FeatureCollection","features":[]}' > nuclei.geojson
            fi
            if [ ! -f nuclei_tissue_mask.geojson ]; then
                log "WARNING: nuclei_tissue_mask.geojson missing, creating placeholder"
                echo '{"type":"FeatureCollection","features":[]}' > nuclei_tissue_mask.geojson
            fi
            log "=== DONE (exit_code=$exit_code) ==="
            exit "$exit_code"
        }
        trap cleanup EXIT

        log "=== STAGE 1: Environment ==="
        log "Date: $(date)"
        log "Kernel: $(uname -a)"
        free -h 2>&1 | tee -a "$LOG" || true
        log "CPUs: $(nproc 2>&1 || echo unknown)"
        nvidia-smi 2>&1 | tee -a "$LOG" || true
        ls -la ~{slide_image} 2>&1 | tee -a "$LOG" || true
        log "=== STAGE 1 COMPLETE ==="

        log "=== STAGE 2: Python imports ==="
        python3 -c "
import sys, time
print(f'Python {sys.version}')
t0 = time.time()
print('Importing numpy...', flush=True); import numpy; print(f'  numpy {numpy.__version__} ({time.time()-t0:.1f}s)', flush=True)
print('Importing torch...', flush=True); import torch; print(f'  torch {torch.__version__}, CUDA={torch.cuda.is_available()} ({time.time()-t0:.1f}s)', flush=True)
if torch.cuda.is_available(): print(f'  GPU: {torch.cuda.get_device_name(0)}', flush=True)
print('Importing monai...', flush=True); import monai; print(f'  monai {monai.__version__} ({time.time()-t0:.1f}s)', flush=True)
print('Importing openslide...', flush=True); import openslide; print(f'  openslide OK ({time.time()-t0:.1f}s)', flush=True)
print('All imports OK', flush=True)
" 2>&1 | tee -a "$LOG"
        log "=== STAGE 2 COMPLETE ==="

        log "=== STAGE 3: Running pipeline ==="
        python3 /opt/pipeline/process_wsi.py \
            ~{slide_image} \
            --output nuclei.geojson \
            --bundle-root /opt/pipeline/bundles/pathology_nuclei_segmentation_classification \
            --level ~{pyramid_level} \
            --tile-size ~{tile_size} \
            ~{if defined(overlap) then "--overlap ~{select_first([overlap, 0])}" else ""} \
            ~{if defined(max_tiles) then "--max-tiles ~{select_first([max_tiles, 0])}" else ""} \
            ~{if defined(roi_geojson) then "--roi ~{roi_geojson}" else ""} \
            2>&1 | tee -a "$LOG"
        log "Pipeline completed successfully"
    >>>

    runtime {
        container: container_image_uri
        cpu: 8
        memory: "32 GiB"
        acceleratorCount: 1
        acceleratorType: "nvidia-t4-a10g-l4"
    }

    output {
        File nuclei_geojson      = "nuclei.geojson"
        File tissue_mask_geojson = "nuclei_tissue_mask.geojson"
        File task_log            = "task.log"
    }
}
