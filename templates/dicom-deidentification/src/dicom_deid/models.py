"""Data models for the DICOM de-identification workflow."""

from dataclasses import dataclass, field
from pathlib import Path

from .enums import Action, OverrideMode, UnmatchedTextPolicy


# ---------------------------------------------------------------------------
# Status string constants
# ---------------------------------------------------------------------------

# metadata_status values
METADATA_SUCCESS = "success"
METADATA_FAILED = "failed"

# pixel_detection_status values
PIXEL_DETECTION_SUCCESS = "success"
PIXEL_DETECTION_FAILED = "failed"
PIXEL_DETECTION_NOT_REQUESTED = "not_requested"
PIXEL_DETECTION_NOT_ATTEMPTED = "not_attempted"

# pixel_masking_status values
PIXEL_MASKING_SUCCESS = "success"
PIXEL_MASKING_FAILED = "failed"
PIXEL_MASKING_SKIPPED_LOSSY = "skipped_lossy"
PIXEL_MASKING_SKIPPED_UNSUPPORTED_TS = "skipped_unsupported_ts"
PIXEL_MASKING_FAILED_UNSUPPORTED_TS = "failed_unsupported_ts"
PIXEL_MASKING_NOT_REQUESTED = "not_requested"
PIXEL_MASKING_NOT_ATTEMPTED = "not_attempted"
PIXEL_MASKING_NO_TEXT_FOUND = "no_text_found"
PIXEL_MASKING_FAILED_UNMATCHED_TEXT = "failed_unmatched_text"


# ---------------------------------------------------------------------------
# Profile configuration
# ---------------------------------------------------------------------------

@dataclass
class TagOverride:
    """A profile-supplied write to a single DICOM attribute.

    Applied AFTER all per-tag de-id actions (hash, date_shift, remove, …)
    have run, so a ``PREFIX``/``SUFFIX`` mode lands on whatever value the
    pipeline produced — not on raw PHI. The combined value is right-
    truncated to the VR's standard maximum length.
    """

    tag: str
    value: str
    mode: OverrideMode = OverrideMode.REPLACE


@dataclass
class DeidentificationProfile:
    """JSON de-identification profile configuration."""

    salt: str
    attribute_actions: dict[str, Action] = field(default_factory=dict)
    attribute_overrides: dict[str, Action] = field(default_factory=dict)
    drop_private_tags: bool = True
    drop_tags_list: list[str] = field(default_factory=list)
    max_date_shift_days: int = 365
    # User-defined writes applied AFTER all per-tag actions. Lets the
    # operator stamp a clinical-trial ID, prefix a study description,
    # etc. Each entry names a tag, a value, and a mode (replace / prefix
    # / suffix). String VRs only.
    override_tag_list: list[TagOverride] = field(default_factory=list)
    # Defaults below mirror the production-grade settings in
    # profiles/ps315_basic_tcia_v1.json. A profile that omits these
    # fields gets the same behaviour as that reference profile, so
    # callers don't need to know the dozen toggles to get sensible
    # de-id behaviour out of the box.
    enable_pixel_text_detection: bool = True
    enable_pixel_masking: bool = True
    mask_lossy_images: bool = True
    replace_uids: bool = True
    unmatched_text_policy: UnmatchedTextPolicy = UnmatchedTextPolicy.MASK
    # Allow opt-in processing of instances whose pixel data uses a Transfer
    # Syntax we cannot decode. When False (default), unsupported syntaxes
    # produce a hard failure so PHI cannot silently slip through.
    allow_unsupported_pixel_ts: bool = False
    # Inline-mode checkpointing: flush a partial manifest every N
    # processed instances.  Defends against C-level crashes losing all
    # prior work.  50 = ~10% of typical runs; 0 disables checkpointing.
    inline_checkpoint_every: int = 50
    # Run an additional OCR pass with CLAHE (Contrast-Limited Adaptive
    # Histogram Equalization) to recover gray-on-gray PHI text that
    # window/level + min/max passes miss. Adds ~1.3-1.5x OCR cost per
    # frame.
    enable_clahe: bool = True
    # CLAHE clipLimit. Higher values amplify low-contrast text more
    # aggressively but also amplify noise. 2.0 is OpenCV's mid-range
    # default; 4.0+ is "aggressive".
    clahe_clip_limit: float = 2.0
    # Upscale factor applied before OCR to recover small burned-in text.
    # CT/MR slices commonly carry 4-7 px tall annotation glyphs that fall
    # below CRAFT's reliable detection floor (~10 px); a 2x Lanczos
    # upscale puts them squarely in the detector's sweet spot.
    # Coordinates from the upscaled pass are divided by this factor
    # before merging into frame-coordinate boxes. 1 = disabled.
    ocr_upscale_factor: int = 2


# ---------------------------------------------------------------------------
# DICOM hierarchy models
# ---------------------------------------------------------------------------

@dataclass
class InstanceInfo:
    """Metadata for a single DICOM instance."""

    sop_instance_uid: str
    series_uid: str
    study_uid: str
    patient_id: str
    file_path: Path
    file_size_bytes: int
    transfer_syntax_uid: str


@dataclass
class SeriesInfo:
    """A DICOM series containing one or more instances."""

    series_uid: str
    instances: list[InstanceInfo] = field(default_factory=list)


@dataclass
class StudyInfo:
    """A DICOM study containing one or more series."""

    study_uid: str
    patient_id: str
    series: list[SeriesInfo] = field(default_factory=list)


@dataclass
class DICOMHierarchy:
    """Complete Study → Series → Instance hierarchy."""

    studies: list[StudyInfo] = field(default_factory=list)
    malformed_files: list[tuple[Path, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Processing result models
# ---------------------------------------------------------------------------

@dataclass
class BoundingBox:
    """A rectangular region enclosing detected burned-in text."""

    x: int
    y: int
    width: int
    height: int
    text: str
    frame_index: int = 0
    # OCR confidence in [0, 1]. ``None`` for boxes that bypass OCR (e.g.
    # synthetic strip masks) so callers can distinguish "unknown" from "low".
    confidence: float | None = None


@dataclass
class DetectionResult:
    """Result of pixel text detection for a single instance."""

    sop_instance_uid: str
    bounding_boxes: list[BoundingBox] = field(default_factory=list)


@dataclass
class InstanceResult:
    """Result of processing a single DICOM instance through the pipeline."""

    instance_info: InstanceInfo
    attempt_number: int
    metadata_status: str
    pixel_detection_status: str
    pixel_masking_status: str
    bounding_boxes_found: int | None = None
    deidentified_patient_id: str | None = None
    deidentified_study_uid: str | None = None
    deidentified_series_uid: str | None = None
    deidentified_sop_uid: str | None = None
    output_file_path: Path | None = None
    error_message: str | None = None
    detection_report: DetectionResult | None = None
    compressed_size: int | None = None
    decompressed_size: int | None = None
    compression_ratio: float | None = None


# ---------------------------------------------------------------------------
# Summary / reporting models
# ---------------------------------------------------------------------------

@dataclass
class WorkflowSummary:
    """Summary report of the workflow execution."""

    total_studies: int = 0
    total_series: int = 0
    total_instances: int = 0
    successful_instances: int = 0
    failed_instances: int = 0
    malformed_files: list[tuple[Path, str]] = field(default_factory=list)
    csv_mapping_written: bool = False
    masking_applied_count: int = 0
    masking_skipped_lossy_count: int = 0
    masking_skipped_unsupported_ts_count: int = 0
    masking_failed_unsupported_ts_count: int = 0
    masking_failed_unmatched_text_count: int = 0
