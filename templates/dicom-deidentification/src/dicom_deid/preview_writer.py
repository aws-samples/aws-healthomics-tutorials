"""JPEG preview writer — diagnostic before/after images per instance.

Previews are an opt-in diagnostic output (CLI flag
``--emit-jpeg-previews``). They are *not* part of the de-identified
artifact set: a JPEG is lossy and tagged with no DICOM metadata, so it
must never be confused with the real output. The file naming
convention ``<sop_uid>.before.jpg`` / ``.after.jpg`` keeps them visually
distinct in any directory listing.

Window/level normalization mirrors what TextDetector uses so the
preview shows what OCR actually saw — not the raw pixel values, which
on most modalities are not directly viewable.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pydicom
from PIL import Image

from .text_detector import _get_window_level, apply_window_level

logger = logging.getLogger(__name__)

# JPEG quality setting. 85 is the conventional sweet spot for "high
# quality, small file" — higher values bloat the file without
# meaningfully improving diagnostic readability.
_JPEG_QUALITY = 85


def _first_frame_uint8(
    pixel_array: np.ndarray,
    dataset: pydicom.Dataset | None,
) -> np.ndarray:
    """Reduce *pixel_array* to a single 2-D or H×W×C uint8 image.

    For multi-frame instances, only the first frame is previewed —
    burned-in PHI is typically frame-invariant within a series, and
    writing N JPEGs per instance would explode the output directory
    on multi-frame studies.
    """
    arr = pixel_array
    if arr.ndim == 4:
        arr = arr[0]  # take first multi-frame
    elif arr.ndim == 3 and arr.shape[2] > 4:
        # N×H×W greyscale (channels-last convention used elsewhere is
        # "<= 4 channels means colour")
        arr = arr[0]

    if arr.dtype != np.uint8:
        wc, ww = _get_window_level(dataset) if dataset is not None else (None, None)
        arr = apply_window_level(arr, wc, ww)
    return arr


def write_preview(
    pixel_array: np.ndarray,
    sop_instance_uid: str,
    output_dir: Path,
    suffix: str,
    dataset: pydicom.Dataset | None = None,
) -> Path | None:
    """Write a JPEG preview of *pixel_array* for visual verification.

    Parameters
    ----------
    pixel_array:
        Decoded pixel data as returned by ``Dataset.pixel_array``.
    sop_instance_uid:
        Used as the file stem; pairs cleanly with detection_reports/
        which uses the same key.
    output_dir:
        The workflow output directory; previews live in
        ``output_dir/jpeg_previews/``.
    suffix:
        ``"before"`` or ``"after"`` — selects the file name suffix.
    dataset:
        Optional, used to read DICOM WindowCenter/WindowWidth so the
        preview matches what OCR actually saw. Min/max fallback
        otherwise.

    Returns
    -------
    Path | None
        Path written, or ``None`` on failure (errors are logged, not
        raised — preview generation must never break a de-id run).
    """
    try:
        previews_dir = output_dir / "jpeg_previews"
        previews_dir.mkdir(parents=True, exist_ok=True)
        out_path = previews_dir / f"{sop_instance_uid}.{suffix}.jpg"

        arr = _first_frame_uint8(pixel_array, dataset)
        if arr.ndim == 2:
            image = Image.fromarray(arr, mode="L")
        elif arr.ndim == 3 and arr.shape[2] == 3:
            image = Image.fromarray(arr, mode="RGB")
        elif arr.ndim == 3 and arr.shape[2] == 4:
            # Drop alpha for JPEG; we don't need transparency in a
            # diagnostic preview.
            image = Image.fromarray(arr[:, :, :3], mode="RGB")
        else:
            logger.warning(
                "Skipping JPEG preview for %s: unsupported pixel shape %s",
                sop_instance_uid,
                arr.shape,
            )
            return None

        image.save(out_path, format="JPEG", quality=_JPEG_QUALITY)
        return out_path
    except Exception as exc:  # noqa: BLE001 — preview is best-effort
        logger.warning(
            "JPEG preview write failed for %s (%s): %s",
            sop_instance_uid,
            suffix,
            exc,
        )
        return None
