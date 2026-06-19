"""Entry point for the DICOM de-identification workflow task.

Parses CLI arguments, orchestrates the full pipeline:
  profile load → aggregation → scheduling → CSV → manifest → summary.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .aggregator import Aggregator, AggregationError
from .csv_mapping_writer import CSVMappingWriter, CSVWriteError
from .deidentifier import Deidentifier
from .instance_processor import InstanceProcessor
from .manifest_writer import ManifestWriter
from .models import (
    DeidentificationProfile,
    InstanceInfo,
    InstanceResult,
)
from .profile_loader import ProfileLoader, ProfileValidationError
from .summary_reporter import SummaryReporter

logger = logging.getLogger(__name__)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DICOM de-identification workflow task entry point.",
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        type=Path,
        help="Local directory containing staged DICOM files.",
    )
    parser.add_argument(
        "--profile",
        required=True,
        type=Path,
        help="Path to the JSON de-identification profile.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Local directory for de-identified output.",
    )
    parser.add_argument(
        "--allow-unsupported-pixel-ts",
        action="store_true",
        help=(
            "Allow instances whose pixel Transfer Syntax cannot be decoded "
            "(e.g. JPEG-XL) to pass through unmasked. Without this flag (the "
            "default), such instances are treated as a hard failure so PHI "
            "cannot silently slip through an undetectable codec. Overrides "
            "the profile's allow_unsupported_pixel_ts field when set."
        ),
    )
    parser.add_argument(
        "--emit-jpeg-previews",
        action="store_true",
        help=(
            "Write per-instance JPEG previews of the first frame: "
            "<sop_uid>.before.jpg (original windowed pixels) and "
            "<sop_uid>.after.jpg (de-identified pixels). Off by "
            "default — these previews are diagnostic, not part of "
            "the de-identified artifact set. Useful for visually "
            "verifying that masking landed where expected."
        ),
    )
    return parser


def _process_inline(
    instances: list[InstanceInfo],
    profile: DeidentificationProfile,
    output_dir: Path,
    emit_jpeg_previews: bool,
    checkpoint_every: int,
    hierarchy,
) -> list[InstanceResult]:
    """Process every instance in the orchestrator process.

    The OCR Reader is constructed once and reused across all
    instances — the dominant cost of a fork-per-instance approach
    was reloading the EasyOCR weights (~5–8 sec each) which on a
    480-instance run added up to ~40 min of pure overhead.

    Crash isolation comes from a per-instance try/except: anything
    raised by ``processor.process(...)`` becomes a FAILED InstanceResult
    for that instance and the loop continues. Only C-level segfaults
    (rare in practice) take down the whole task — and HealthOmics' own
    retry handles that case.

    *checkpoint_every* > 0 flushes a partial manifest every N processed
    instances so a hard crash doesn't lose all prior work.
    """
    deidentifier = Deidentifier(profile)
    processor = InstanceProcessor()

    # Build the persistent TextDetector once when pixel detection is on.
    # When OCR is disabled we leave it None — the processor short-circuits
    # without touching it.
    detector = None
    if profile.enable_pixel_text_detection:
        from .text_detector import TextDetector
        detector = TextDetector(
            enable_clahe=profile.enable_clahe,
            clahe_clip_limit=profile.clahe_clip_limit,
            upscale_factor=profile.ocr_upscale_factor,
        )
        logger.info("TextDetector loaded once, reused across %d instances", len(instances))

    results: list[InstanceResult] = []
    total = len(instances)
    for idx, instance in enumerate(instances, start=1):
        try:
            result = processor.process(
                instance=instance,
                profile=profile,
                deidentifier=deidentifier,
                output_dir=output_dir,
                attempt_number=1,
                emit_jpeg_previews=emit_jpeg_previews,
                text_detector=detector,
            )
        except Exception as exc:  # noqa: BLE001
            # Layer 1 isolation: any Python-surfaced failure becomes a
            # per-instance failure record. The pipeline keeps going.
            logger.exception(
                "Pipeline crashed on %s (continuing): %s",
                instance.sop_instance_uid, exc,
            )
            result = InstanceResult(
                instance_info=instance,
                attempt_number=1,
                metadata_status="failed",
                pixel_detection_status="not_attempted",
                pixel_masking_status="not_attempted",
                error_message=f"{type(exc).__name__}: {exc}",
            )
        results.append(result)

        # Per-instance audit line. Counts only — never the actual text
        # OCR found — so the run log is safe to ship to operators.
        # Format intentionally compact so 480 lines aren't overwhelming.
        logger.info(
            "[%d/%d] %s metadata=%s detection=%s masking=%s phi_boxes=%s",
            idx,
            total,
            instance.sop_instance_uid,
            result.metadata_status,
            result.pixel_detection_status,
            result.pixel_masking_status,
            result.bounding_boxes_found if result.bounding_boxes_found is not None else "-",
        )

        # Layer 2 insurance: periodic checkpoint manifest. Costs a few
        # ms per N instances; lets a hard crash recover prior work.
        if checkpoint_every > 0 and idx % checkpoint_every == 0:
            _write_checkpoint(results, hierarchy, output_dir, idx, total)

    return results


def _write_checkpoint(
    results: list[InstanceResult],
    hierarchy,
    output_dir: Path,
    processed: int,
    total: int,
) -> None:
    """Best-effort partial manifest write. Failure here is non-fatal."""
    try:
        ManifestWriter().write(
            results=results,
            hierarchy=hierarchy,
            output_dir=output_dir,
        )
        logger.info("Checkpointed manifest at %d/%d instances", processed, total)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Checkpoint write failed at %d/%d: %s", processed, total, exc)


def _log_startup_environment() -> None:
    """Emit a one-shot diagnostic block describing the runtime environment.

    Intended for HealthOmics workflow logs where the actual instance
    type, driver version and library combo are otherwise opaque. Logs:
    - host platform / kernel
    - CPU count, total memory
    - Python and key library versions (torch, numpy, easyocr)
    - GPU details if any (count, name, VRAM)
    - NVIDIA driver version + CUDA runtime + nvidia-smi output

    Best-effort: any individual probe that fails is logged at WARNING
    and the function continues. We never raise from here.
    """
    import platform
    import shutil
    import subprocess

    logger.info("=" * 60)
    logger.info("Runtime environment")
    logger.info("=" * 60)
    logger.info("Platform: %s %s (%s)", platform.system(), platform.release(), platform.machine())
    logger.info("Python: %s", platform.python_version())
    logger.info("CPU count: %d", os.cpu_count() or 0)

    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    logger.info("Memory: %s", line.split(":", 1)[1].strip())
                    break
    except OSError:
        pass

    # Library versions — each in its own try since one missing dep
    # shouldn't suppress the others.
    for lib_name in ("torch", "numpy", "easyocr", "pydicom", "cv2"):
        try:
            mod = __import__(lib_name)
            ver = getattr(mod, "__version__", "?")
            logger.info("%s: %s", lib_name, ver)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: import failed: %s", lib_name, exc)

    # GPU probe via torch. Single-process inline orchestration means
    # there's no fork after this point, so initializing CUDA here is
    # safe — the EasyOCR Reader will initialize it anyway as soon as
    # TextDetector is constructed.
    try:
        import torch
        logger.info("CUDA available (torch): %s", torch.cuda.is_available())
        if torch.cuda.is_available():
            logger.info("CUDA runtime (torch): %s", torch.version.cuda)
            logger.info("cuDNN: %s", torch.backends.cudnn.version())
            n = torch.cuda.device_count()
            logger.info("GPU count: %d", n)
            for i in range(n):
                p = torch.cuda.get_device_properties(i)
                logger.info(
                    "  [%d] %s, %.1f GB, compute %d.%d",
                    i, p.name, p.total_memory / 1e9, p.major, p.minor,
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("torch GPU probe failed: %s", exc)

    # nvidia-smi for driver version + utilization. The CUDA driver lives
    # outside torch; this surfaces it directly.
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi",
                 "--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu",
                 "--format=csv,noheader"],
                timeout=5, stderr=subprocess.DEVNULL,
            ).decode().strip()
            for line in out.splitlines():
                logger.info("nvidia-smi: %s", line)
        except Exception as exc:  # noqa: BLE001
            logger.warning("nvidia-smi probe failed: %s", exc)
    else:
        logger.info("nvidia-smi: not available (no GPU runtime?)")

    # HealthOmics-injected env vars — useful for cross-referencing
    # logs with run/task IDs in the AWS console.
    for env in ("AWS_OMICS_RUN_ID", "AWS_OMICS_TASK_ID", "AWS_REGION"):
        val = os.environ.get(env)
        if val:
            logger.info("%s: %s", env, val)

    logger.info("=" * 60)


def main(argv: list[str] | None = None) -> int:
    """Run the DICOM de-identification pipeline. Returns exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _log_startup_environment()

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    input_dir: Path = args.input_dir
    profile_path: Path = args.profile
    output_dir: Path = args.output_dir

    # --- Load profile ---
    try:
        profile = ProfileLoader().load(profile_path)
    except ProfileValidationError as exc:
        logger.error("Profile validation failed: %s", exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # CLI flag overrides the profile field when present. We deliberately
    # only allow the CLI to *enable* the opt-in (not disable it) — the
    # safer default wins on conflict.
    if args.allow_unsupported_pixel_ts:
        profile.allow_unsupported_pixel_ts = True

    # --- Aggregate DICOM hierarchy ---
    try:
        hierarchy = Aggregator().aggregate(input_dir)
    except AggregationError as exc:
        logger.error("Aggregation failed: %s", exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # --- Flatten instances ---
    all_instances: list[InstanceInfo] = []
    for study in hierarchy.studies:
        for series in study.series:
            all_instances.extend(series.instances)

    logger.info("Starting de-identification: %d instances", len(all_instances))

    results = _process_inline(
        instances=all_instances,
        profile=profile,
        output_dir=output_dir,
        emit_jpeg_previews=args.emit_jpeg_previews,
        checkpoint_every=profile.inline_checkpoint_every,
        hierarchy=hierarchy,
    )

    # --- Write CSV mapping ---
    csv_written = False
    try:
        CSVMappingWriter().write(results, output_dir)
        csv_written = True
    except CSVWriteError as exc:
        logger.error("CSV mapping write failed: %s", exc)

    # --- Write manifest ---
    try:
        ManifestWriter().write(
            results=results,
            hierarchy=hierarchy,
            output_dir=output_dir,
        )
    except Exception as exc:
        logger.error("Manifest write failed: %s", exc)

    # --- Generate and print summary ---
    reporter = SummaryReporter()
    summary = reporter.generate(
        results=results,
        hierarchy=hierarchy,
        csv_mapping_written=csv_written,
    )
    report_text = reporter.format_report(summary)
    print(report_text)

    # --- Determine exit code ---
    successful = sum(1 for r in results if r.metadata_status == "success")
    if successful >= 1:
        logger.info("Workflow completed successfully (%d instances succeeded).", successful)
        return 0

    logger.error("Workflow failed: zero instances succeeded.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
