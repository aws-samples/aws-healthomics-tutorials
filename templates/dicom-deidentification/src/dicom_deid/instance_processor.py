"""InstanceProcessor — single-pass pipeline for each DICOM instance."""

from __future__ import annotations

import logging
from pathlib import Path

import pydicom
from pydicom.tag import Tag

from .deidentifier import Deidentifier
from .enums import HashTier, UnmatchedTextPolicy
from .models import (
    BoundingBox,
    DeidentificationProfile,
    InstanceInfo,
    InstanceResult,
    METADATA_FAILED,
    METADATA_SUCCESS,
    PIXEL_DETECTION_FAILED,
    PIXEL_DETECTION_NOT_ATTEMPTED,
    PIXEL_DETECTION_NOT_REQUESTED,
    PIXEL_DETECTION_SUCCESS,
    PIXEL_MASKING_FAILED,
    PIXEL_MASKING_FAILED_UNMATCHED_TEXT,
    PIXEL_MASKING_FAILED_UNSUPPORTED_TS,
    PIXEL_MASKING_NOT_ATTEMPTED,
    PIXEL_MASKING_NOT_REQUESTED,
    PIXEL_MASKING_NO_TEXT_FOUND,
    PIXEL_MASKING_SKIPPED_LOSSY,
    PIXEL_MASKING_SKIPPED_UNSUPPORTED_TS,
    PIXEL_MASKING_SUCCESS,
)
from .output_writer import OutputWriter

logger = logging.getLogger(__name__)

_TAG_PATIENT_ID = Tag(0x0010, 0x0020)


class InstanceProcessor:
    """Entry point for each subprocess — runs the complete single-pass pipeline.

    Pipeline: load → deidentify metadata → detect → mask → write.

    Note: ``resource.setrlimit(RLIMIT_AS)`` is already called by the
    scheduler's ``_subprocess_entry`` before this processor is invoked.

    The TextDetector is created lazily (only when pixel detection is
    enabled) to avoid import errors when EasyOCR is not installed.
    """

    def process(
        self,
        instance: InstanceInfo,
        profile: DeidentificationProfile,
        deidentifier: Deidentifier,
        output_dir: Path,
        attempt_number: int = 1,
        emit_jpeg_previews: bool = False,
        text_detector=None,
    ) -> InstanceResult:
        """Run the single-pass pipeline for one DICOM instance.

        When *text_detector* is provided, it is reused across calls —
        the OCR models load once and stay resident in GPU memory.
        Omit it only when the caller wants a fresh detector for some
        reason (e.g. a one-off ad-hoc invocation).

        Returns an :class:`InstanceResult` with all status fields populated.
        """
        # Determine pixel status defaults based on profile flags
        pixel_detection_default = (
            PIXEL_DETECTION_NOT_REQUESTED
            if not profile.enable_pixel_text_detection
            else PIXEL_DETECTION_NOT_ATTEMPTED
        )
        pixel_masking_default = (
            PIXEL_MASKING_NOT_REQUESTED
            if not profile.enable_pixel_masking
            else PIXEL_MASKING_NOT_ATTEMPTED
        )

        # --- Load DICOM dataset ---
        try:
            dataset = pydicom.dcmread(str(instance.file_path))
        except Exception as exc:
            logger.error(
                "Failed to load DICOM file %s: %s",
                instance.file_path,
                exc,
            )
            return InstanceResult(
                instance_info=instance,
                attempt_number=attempt_number,
                metadata_status=METADATA_FAILED,
                pixel_detection_status=PIXEL_DETECTION_NOT_ATTEMPTED,
                pixel_masking_status=PIXEL_MASKING_NOT_ATTEMPTED,
                error_message=f"Failed to load DICOM: {exc}",
            )

        # --- Record compressed size (file size on disk) ---
        compressed_size = instance.file_size_bytes

        # --- Record decompressed size (pixel data size after decompression) ---
        decompressed_size: int | None = None
        try:
            if hasattr(dataset, "PixelData") and dataset.PixelData is not None:
                pixel_array = dataset.pixel_array
                decompressed_size = pixel_array.nbytes
        except Exception:
            # If we can't decompress pixel data, that's okay for metadata-only
            # processing — just use file size as fallback
            decompressed_size = compressed_size

        if decompressed_size is None:
            decompressed_size = compressed_size

        compression_ratio: float | None = None
        if compressed_size > 0:
            compression_ratio = decompressed_size / compressed_size

        # --- Metadata de-identification ---
        try:
            dataset = deidentifier.deidentify(dataset, instance)
        except Exception as exc:
            logger.error(
                "Metadata de-identification failed for %s: %s",
                instance.sop_instance_uid,
                exc,
            )
            return InstanceResult(
                instance_info=instance,
                attempt_number=attempt_number,
                metadata_status=METADATA_FAILED,
                pixel_detection_status=PIXEL_DETECTION_NOT_ATTEMPTED,
                pixel_masking_status=PIXEL_MASKING_NOT_ATTEMPTED,
                error_message=f"Metadata de-identification failed: {exc}",
                compressed_size=compressed_size,
                decompressed_size=decompressed_size,
                compression_ratio=compression_ratio,
            )

        # --- Retrieve de-identified UIDs ---
        if profile.replace_uids:
            deid_study_uid = deidentifier.generate_uid(instance.study_uid)
            deid_series_uid = deidentifier.generate_uid(instance.series_uid)
            deid_sop_uid = deidentifier.generate_uid(instance.sop_instance_uid)
        else:
            deid_study_uid = instance.study_uid
            deid_series_uid = instance.series_uid
            deid_sop_uid = instance.sop_instance_uid

        # Report the PatientID exactly as written to the de-identified dataset
        # so the CSV mapping stays consistent even when an attribute_override
        # changes the PatientID action (e.g. a different hash tier or remove).
        # If the tag is absent (rare; the dataset wouldn't have parsed without
        # it in normal cases) fall back to a HASH_16 over the original — a
        # safety floor so the CSV never carries plaintext PHI.
        if _TAG_PATIENT_ID in dataset:
            deid_patient_id = str(dataset[_TAG_PATIENT_ID].value)
        else:
            deid_patient_id = deidentifier.hash_attribute(
                instance.patient_id, HashTier.HASH_16
            )

        # --- Pixel text detection (Phase 2) ---
        pixel_detection_status = pixel_detection_default
        bounding_boxes_found: int | None = None
        detection_report = None
        pixel_array = None  # populated below; reused for masking + strip fallback
        unsupported_ts_failure = False

        if profile.enable_pixel_text_detection:
            # Up-front Transfer Syntax check. We refuse to silently pass
            # pixels through when the codec is unknown — pydicom would
            # raise inside the try/except below, get caught as a generic
            # detection failure, and the file would be written with
            # original PHI-bearing pixels.
            from .pixel_masker import SUPPORTED_TRANSFER_SYNTAXES

            if (
                instance.transfer_syntax_uid not in SUPPORTED_TRANSFER_SYNTAXES
                and not profile.allow_unsupported_pixel_ts
            ):
                logger.error(
                    "Unsupported Transfer Syntax for %s: %s — refusing to pass "
                    "pixels through (set allow_unsupported_pixel_ts=true to override).",
                    instance.sop_instance_uid,
                    instance.transfer_syntax_uid,
                )
                pixel_detection_status = PIXEL_DETECTION_FAILED
                unsupported_ts_failure = True
            else:
                try:
                    # Decompress pixel data for detection
                    pixel_array = dataset.pixel_array

                    # --- Diagnostic JPEG preview: BEFORE masking ---
                    # Snapshot now, before the masker mutates the array
                    # in-place. Failures inside the preview are logged
                    # but never bubble up to the caller — previews must
                    # not break a de-id run.
                    if emit_jpeg_previews:
                        from .preview_writer import write_preview

                        write_preview(
                            pixel_array=pixel_array,
                            sop_instance_uid=instance.sop_instance_uid,
                            output_dir=output_dir,
                            suffix="before",
                            dataset=dataset,
                        )

                    # Update decompressed size from actual pixel data
                    decompressed_size = pixel_array.nbytes
                    if compressed_size > 0:
                        compression_ratio = decompressed_size / compressed_size

                    # Reuse the caller-provided TextDetector when given
                    # (the inline path) so the heavy OCR weights load
                    # only once. Otherwise lazily create one — needed
                    # for the subprocess path where each child fork
                    # can't share parent state. Lazy import keeps the
                    # rest of the codebase usable without easyocr.
                    if text_detector is None:
                        from .text_detector import TextDetector
                        detector = TextDetector(
                            enable_clahe=profile.enable_clahe,
                            clahe_clip_limit=profile.clahe_clip_limit,
                            upscale_factor=profile.ocr_upscale_factor,
                        )
                    else:
                        detector = text_detector
                    detection_report = detector.detect(
                        pixel_array, instance.sop_instance_uid, dataset=dataset
                    )
                    bounding_boxes_found = len(detection_report.bounding_boxes)
                    pixel_detection_status = PIXEL_DETECTION_SUCCESS

                    # Write Instance Detection Report JSON. Import is
                    # local because the inline path may have skipped
                    # the lazy import branch above.
                    from .text_detector import TextDetector
                    TextDetector.write_detection_report(detection_report, output_dir)

                except Exception as exc:
                    logger.error(
                        "Pixel text detection failed for %s: %s",
                        instance.sop_instance_uid,
                        exc,
                    )
                    pixel_detection_status = PIXEL_DETECTION_FAILED

        # --- Pixel masking (Phase 3) ---
        pixel_masking_status = pixel_masking_default

        unmatched_failure_message: str | None = None

        # Up-front unsupported TS rejection: detection skipped this instance
        # because we refuse to decode it. Surface the failure now so masking
        # status reflects the codec-level block rather than a generic failure.
        if unsupported_ts_failure and profile.enable_pixel_masking:
            pixel_masking_status = PIXEL_MASKING_FAILED_UNSUPPORTED_TS

        if profile.enable_pixel_masking and pixel_detection_status == PIXEL_DETECTION_SUCCESS:
            if detection_report is not None and len(detection_report.bounding_boxes) > 0:
                try:
                    # Classify detected text as PHI or non-PHI
                    from .phi_classifier import PHIClassifier

                    classifier = PHIClassifier()
                    # Load PHI values from the ORIGINAL dataset (before de-id)
                    # We need to re-read the original to get unmodified PHI values
                    original_ds = pydicom.dcmread(str(instance.file_path), stop_before_pixels=True)
                    classifier.load_phi_from_dataset(original_ds)

                    # Partition boxes:
                    #   phi_boxes        — fuzzy-matched a known PHI value
                    #   unmatched_boxes  — text that matched nothing (operator-typed
                    #                      free text or low-confidence OCR)
                    phi_boxes: list[BoundingBox] = []
                    unmatched_boxes: list[BoundingBox] = []
                    for box in detection_report.bounding_boxes:
                        result = classifier.classify(box.text)
                        if result.is_phi:
                            phi_boxes.append(box)
                            # PHI text is NEVER logged — only the
                            # match score and bbox geometry, which are
                            # operationally useful and non-revealing.
                            logger.info(
                                "PHI match in instance %s at (%d,%d,%d,%d) score=%.1f",
                                instance.sop_instance_uid,
                                box.x, box.y, box.width, box.height,
                                result.match_score,
                            )
                            continue
                        # Safe-token / safe-pattern hits are intentionally
                        # excluded from "unmatched" because we have positive
                        # evidence they're not PHI. Don't log the text —
                        # safe-pattern is a safety classification, not a
                        # PHI guarantee, and we treat all OCR output as
                        # potentially sensitive in logs.
                        if result.reason in ("safe_token", "safe_pattern", "too_short"):
                            logger.debug(
                                "Non-PHI text skipped (reason=%s) in %s",
                                result.reason, instance.sop_instance_uid,
                            )
                            continue
                        unmatched_boxes.append(box)
                        logger.debug(
                            "Unmatched text in %s (reason=%s, conf=%s)",
                            instance.sop_instance_uid, result.reason, box.confidence,
                        )

                    # Apply unmatched-text policy.
                    extra_phi_boxes: list[BoundingBox] = []
                    if unmatched_boxes:
                        if profile.unmatched_text_policy == UnmatchedTextPolicy.FAIL:
                            # Failure message and log line both name only
                            # COUNTS and bbox geometry — never the OCR
                            # text itself. The text is potentially PHI
                            # and propagates into manifests/CSV/logs.
                            unmatched_failure_message = (
                                f"{len(unmatched_boxes)} unmatched text region(s) "
                                f"(policy=fail)"
                            )
                            logger.error(
                                "Unmatched text in %s under fail policy: %s",
                                instance.sop_instance_uid,
                                unmatched_failure_message,
                            )
                        elif profile.unmatched_text_policy == UnmatchedTextPolicy.MASK:
                            extra_phi_boxes.extend(unmatched_boxes)
                            logger.info(
                                "Masking %d unmatched text region(s) under mask policy",
                                len(unmatched_boxes),
                            )
                        # KEEP: nothing to do — leave them in place.

                    if unmatched_failure_message is not None:
                        pixel_masking_status = PIXEL_MASKING_FAILED_UNMATCHED_TEXT
                    else:
                        boxes_to_mask = phi_boxes + extra_phi_boxes
                        if boxes_to_mask:
                            from .pixel_masker import PixelMasker

                            masker = PixelMasker()
                            mask_result = masker.mask(
                                dataset=dataset,
                                bounding_boxes=boxes_to_mask,
                                mask_lossy=profile.mask_lossy_images,
                                allow_unsupported_ts=profile.allow_unsupported_pixel_ts,
                            )

                            if mask_result.status == "success":
                                pixel_masking_status = PIXEL_MASKING_SUCCESS
                            elif mask_result.status == "skipped_lossy":
                                pixel_masking_status = PIXEL_MASKING_SKIPPED_LOSSY
                            elif mask_result.status == "skipped_unsupported_ts":
                                pixel_masking_status = PIXEL_MASKING_SKIPPED_UNSUPPORTED_TS
                                logger.warning(
                                    "Pixel masking skipped for %s (unsupported TS): %s",
                                    instance.sop_instance_uid,
                                    mask_result.error_message,
                                )
                            elif mask_result.status == "failed_unsupported_ts":
                                pixel_masking_status = PIXEL_MASKING_FAILED_UNSUPPORTED_TS
                                logger.error(
                                    "Pixel masking failed for %s (unsupported TS, "
                                    "no opt-in): %s",
                                    instance.sop_instance_uid,
                                    mask_result.error_message,
                                )
                            else:
                                pixel_masking_status = PIXEL_MASKING_FAILED
                                logger.warning(
                                    "Pixel masking issue for %s: %s",
                                    instance.sop_instance_uid,
                                    mask_result.error_message,
                                )
                        else:
                            # Text detected but none classified as PHI and no
                            # extra boxes from unmatched/strip policies.
                            pixel_masking_status = PIXEL_MASKING_NO_TEXT_FOUND
                except Exception as exc:
                    logger.error(
                        "Pixel masking failed for %s: %s",
                        instance.sop_instance_uid,
                        exc,
                    )
                    pixel_masking_status = PIXEL_MASKING_FAILED
            else:
                # Detection succeeded but no text found — nothing to mask
                pixel_masking_status = PIXEL_MASKING_NO_TEXT_FOUND

        # --- Refuse to write output when pixel PHI may remain ---
        # When masking fails on policy (unmatched text / unsupported codec),
        # the file on disk would have de-identified metadata but original
        # pixels — exactly the silent leak we're guarding against. Surface
        # the failure instead of writing a dangerous artifact.
        if pixel_masking_status in (
            PIXEL_MASKING_FAILED_UNMATCHED_TEXT,
            PIXEL_MASKING_FAILED_UNSUPPORTED_TS,
        ):
            return InstanceResult(
                instance_info=instance,
                attempt_number=attempt_number,
                metadata_status=METADATA_FAILED,
                pixel_detection_status=pixel_detection_status,
                pixel_masking_status=pixel_masking_status,
                bounding_boxes_found=bounding_boxes_found,
                error_message=(
                    unmatched_failure_message
                    if pixel_masking_status == PIXEL_MASKING_FAILED_UNMATCHED_TEXT
                    else f"Unsupported pixel Transfer Syntax: {instance.transfer_syntax_uid}"
                ),
                compressed_size=compressed_size,
                decompressed_size=decompressed_size,
                compression_ratio=compression_ratio,
                detection_report=detection_report,
            )

        # --- Write de-identified file ---
        try:
            writer = OutputWriter()
            output_path = writer.write(
                dataset=dataset,
                output_dir=output_dir,
                deidentified_study_uid=deid_study_uid,
                deidentified_series_uid=deid_series_uid,
                deidentified_sop_uid=deid_sop_uid,
            )

            # --- Diagnostic JPEG preview: AFTER masking ---
            # Mirrors the "before" snapshot above. We always write
            # both halves of the pair when previews are enabled — even
            # if no masking happened — so a directory listing of
            # ``jpeg_previews/`` always pairs cleanly. When before ==
            # after the comparison itself is informative.
            if emit_jpeg_previews:
                from .preview_writer import write_preview

                try:
                    final_array = dataset.pixel_array
                    write_preview(
                        pixel_array=final_array,
                        sop_instance_uid=instance.sop_instance_uid,
                        output_dir=output_dir,
                        suffix="after",
                        dataset=dataset,
                    )
                except Exception as exc:  # noqa: BLE001
                    # Read-back of the just-written pixels can fail on
                    # some Transfer Syntaxes; never let it break the run.
                    logger.warning(
                        "After-preview decode failed for %s: %s",
                        instance.sop_instance_uid,
                        exc,
                    )
        except Exception as exc:
            logger.error(
                "Failed to write de-identified file for %s: %s",
                instance.sop_instance_uid,
                exc,
            )
            return InstanceResult(
                instance_info=instance,
                attempt_number=attempt_number,
                metadata_status=METADATA_FAILED,
                pixel_detection_status=PIXEL_DETECTION_NOT_ATTEMPTED,
                pixel_masking_status=PIXEL_MASKING_NOT_ATTEMPTED,
                error_message=f"Output write failed: {exc}",
                compressed_size=compressed_size,
                decompressed_size=decompressed_size,
                compression_ratio=compression_ratio,
            )

        return InstanceResult(
            instance_info=instance,
            attempt_number=attempt_number,
            metadata_status=METADATA_SUCCESS,
            pixel_detection_status=pixel_detection_status,
            pixel_masking_status=pixel_masking_status,
            bounding_boxes_found=bounding_boxes_found,
            deidentified_patient_id=deid_patient_id,
            deidentified_study_uid=deid_study_uid,
            deidentified_series_uid=deid_series_uid,
            deidentified_sop_uid=deid_sop_uid,
            output_file_path=output_path,
            compressed_size=compressed_size,
            decompressed_size=decompressed_size,
            compression_ratio=compression_ratio,
            detection_report=detection_report,
        )


