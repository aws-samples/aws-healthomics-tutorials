"""TextDetector — EasyOCR-based burned-in text detection for DICOM pixel data.

Uses EasyOCR for text detection and recognition, with DICOM-aware
window/level normalization to handle the wide range of pixel value
representations found in medical images (8-bit ultrasound, 12/16-bit
CT/MR, etc.).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pydicom

from .models import BoundingBox, DetectionResult

logger = logging.getLogger(__name__)


def upscale_for_ocr(image: np.ndarray, factor: int) -> np.ndarray:
    """Lanczos-upscale *image* by an integer *factor* for OCR.

    Lanczos preserves text edges better than bicubic at small font
    sizes — the alternative would be cv2.INTER_CUBIC which softens
    glyph boundaries and can cause CRAFT to merge adjacent characters.

    For ``factor <= 1`` the input is returned unchanged.
    """
    if factor <= 1:
        return image

    import cv2  # type: ignore[import-untyped]

    new_w = image.shape[1] * factor
    new_h = image.shape[0] * factor
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)


def apply_clahe(
    image: np.ndarray,
    clip_limit: float = 2.0,
    tile_grid_size: tuple[int, int] = (8, 8),
) -> np.ndarray:
    """Apply Contrast-Limited Adaptive Histogram Equalization.

    Used as a *third* OCR pass for cases where neither the DICOM
    window/level nor strip-local min/max produce enough contrast for
    OCR — typically gray-text-on-gray-background overlays where the
    text and the surrounding anatomy share a similar brightness band.
    CLAHE redistributes the histogram inside small tiles, so a faint
    text region gets locally amplified into a visible range without
    blowing out the rest of the image.

    Operates on uint8 input only; callers should normalize first.
    Colour images are converted via the LAB L-channel so chroma stays
    untouched.
    """
    import cv2  # type: ignore[import-untyped]

    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)

    if image.ndim == 2:
        return clahe.apply(image)

    if image.ndim == 3 and image.shape[2] in (3, 4):
        rgb = image[:, :, :3] if image.shape[2] == 4 else image
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)

    # Multi-frame or unusual shape: caller should slice frames first.
    return image


def apply_window_level(
    pixel_array: np.ndarray,
    window_center: float | None = None,
    window_width: float | None = None,
) -> np.ndarray:
    """Apply DICOM window/level normalization to produce a uint8 image.

    If *window_center* and *window_width* are provided (from DICOM
    attributes ``WindowCenter`` / ``WindowWidth``), the standard DICOM
    VOI LUT transform is applied.  Otherwise the pixel min/max are used
    to stretch the full dynamic range to 0-255.

    Parameters
    ----------
    pixel_array:
        Raw pixel data (any numeric dtype, 2-D or 3-D).
    window_center:
        DICOM WindowCenter value, or ``None`` to auto-compute.
    window_width:
        DICOM WindowWidth value, or ``None`` to auto-compute.

    Returns
    -------
    np.ndarray
        uint8 image normalized to 0-255.
    """
    arr = pixel_array.astype(np.float64)

    if window_center is not None and window_width is not None and window_width > 0:
        low = window_center - window_width / 2
        high = window_center + window_width / 2
    else:
        low = float(arr.min())
        high = float(arr.max())

    if high <= low:
        return np.zeros_like(pixel_array, dtype=np.uint8)

    arr = (arr - low) / (high - low) * 255.0
    arr = np.clip(arr, 0, 255)
    return arr.astype(np.uint8)


def _get_window_level(dataset: pydicom.Dataset) -> tuple[float | None, float | None]:
    """Extract WindowCenter and WindowWidth from a DICOM dataset.

    Handles the case where these attributes are multi-valued (returns
    the first value) or absent (returns ``None, None``). pydicom returns
    multi-valued elements as ``MultiValue`` — a ``MutableSequence``
    subclass that is NOT a ``list`` or ``tuple``, so a naive
    ``isinstance(value, (list, tuple))`` check misses it and falls
    through to ``float(MultiValue(...))`` which raises and silently
    disables OCR for the whole instance. We instead detect any
    non-string sequence.
    """

    def _first_numeric(value) -> float | None:
        if value is None:
            return None
        if not isinstance(value, (str, bytes)) and hasattr(value, "__iter__"):
            try:
                first = next(iter(value))
            except StopIteration:
                return None
            return float(first)
        return float(value)

    wc = _first_numeric(getattr(dataset, "WindowCenter", None))
    ww = _first_numeric(getattr(dataset, "WindowWidth", None))

    return wc, ww


class TextDetector:
    """Detect burned-in text in DICOM pixel data using EasyOCR.

    The OCR reader is initialised once and reused across frames / instances
    within the same subprocess.  GPU availability is detected at runtime.

    Before running OCR, pixel data is normalized using DICOM window/level
    attributes (or min/max fallback) to produce a well-contrasted uint8
    image suitable for text detection.

    Burned-in PHI is recovered by running OCR over the full frame in up
    to three passes: window/level (or min/max), CLAHE, and Lanczos
    upscale.  Each later pass is merged into the previous result and
    deduped by IoU so the final box list is the union of everything any
    pass found.

    EasyOCR is imported lazily so that the rest of the codebase can be
    used (and tested) without having EasyOCR installed.
    """

    def __init__(
        self,
        enable_clahe: bool = False,
        clahe_clip_limit: float = 2.0,
        upscale_factor: int = 1,
    ) -> None:
        try:
            import easyocr  # type: ignore[import-untyped]
        except ImportError as exc:
            # Include the underlying message — at runtime EasyOCR's own
            # import can fail because of a missing transitive (e.g. libGL,
            # CUDA shim, PyTorch arch mismatch) and the bare "not
            # installed" string sent us chasing the wrong fix in HealthOmics.
            raise ImportError(
                f"EasyOCR import failed: {type(exc).__name__}: {exc}. "
                "If easyocr was installed, check transitive native deps "
                "(libGL, libglib, CUDA runtime). To install: pip install easyocr."
            ) from exc

        # EasyOCR auto-detects GPU; gpu=True will fall back to CPU if CUDA
        # unavailable. Point it at the model directory the Dockerfile
        # pre-downloads to (/opt/easyocr/model). When the env var is
        # missing (e.g. local dev outside the container), EasyOCR's
        # default ~/.EasyOCR/ behavior takes over.
        import os
        model_dir = os.environ.get("EASYOCR_MODULE_PATH")
        reader_kwargs: dict = {"gpu": True}
        if model_dir:
            reader_kwargs["model_storage_directory"] = f"{model_dir}/model"
            reader_kwargs["user_network_directory"] = f"{model_dir}/user_network"
            reader_kwargs["download_enabled"] = False
        self._reader = easyocr.Reader(["en"], **reader_kwargs)
        self._enable_clahe = enable_clahe
        self._clahe_clip_limit = clahe_clip_limit
        self._upscale_factor = max(1, int(upscale_factor))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        pixel_array: np.ndarray,
        sop_instance_uid: str,
        dataset: pydicom.Dataset | None = None,
    ) -> DetectionResult:
        """Run text detection on *pixel_array* and return a DetectionResult.

        Parameters
        ----------
        pixel_array:
            A numpy array as returned by ``pydicom.Dataset.pixel_array``.
            May be 2-D (single frame), 3-D (H×W×C colour or N×H×W
            multi-frame greyscale), or 4-D (N×H×W×C multi-frame colour).
        sop_instance_uid:
            The SOP Instance UID used to tag the result.
        dataset:
            Optional pydicom Dataset used to read WindowCenter/WindowWidth
            for proper normalization.  If ``None``, min/max normalization
            is used.

        Returns
        -------
        DetectionResult
            Contains the SOP Instance UID and a (possibly empty) list of
            ``BoundingBox`` objects.
        """
        # Extract window/level from DICOM attributes if available
        wc, ww = _get_window_level(dataset) if dataset is not None else (None, None)

        frames = self._extract_frames(pixel_array)
        all_boxes: list[BoundingBox] = []

        for frame_index, frame in enumerate(frames):
            boxes = self._detect_single_frame(frame, frame_index, wc, ww)
            all_boxes.extend(boxes)

        return DetectionResult(
            sop_instance_uid=sop_instance_uid,
            bounding_boxes=all_boxes,
        )

    # ------------------------------------------------------------------
    # Instance Detection Report writing
    # ------------------------------------------------------------------

    @staticmethod
    def write_detection_report(
        detection_result: DetectionResult,
        output_dir: Path,
    ) -> Path:
        """Write a per-instance detection report JSON file.

        The report is written to
        ``output_dir/detection_reports/{sop_instance_uid}.json``
        and always includes the bounding-box count and list — even when
        no text was detected (count=0, empty list).

        Returns the path to the written report file.
        """
        reports_dir = output_dir / "detection_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_path = reports_dir / f"{detection_result.sop_instance_uid}.json"

        report_data = {
            "sop_instance_uid": detection_result.sop_instance_uid,
            "bounding_boxes_count": len(detection_result.bounding_boxes),
            "bounding_boxes": [
                {
                    "x": box.x,
                    "y": box.y,
                    "width": box.width,
                    "height": box.height,
                    "text": box.text,
                    "frame_index": box.frame_index,
                    "confidence": box.confidence,
                }
                for box in detection_result.bounding_boxes
            ],
        }

        report_path.write_text(json.dumps(report_data, indent=2))
        return report_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_frames(pixel_array: np.ndarray) -> list[np.ndarray]:
        """Split a pixel array into individual 2-D (or H×W×C) frames.

        EasyOCR expects a single image per call, so multi-frame
        instances must be iterated frame-by-frame.
        """
        ndim = pixel_array.ndim

        if ndim == 2:
            return [pixel_array]

        if ndim == 3:
            if pixel_array.shape[2] <= 4:
                return [pixel_array]
            return [pixel_array[i] for i in range(pixel_array.shape[0])]

        if ndim == 4:
            return [pixel_array[i] for i in range(pixel_array.shape[0])]

        return [pixel_array]

    def _detect_single_frame(
        self,
        frame: np.ndarray,
        frame_index: int = 0,
        window_center: float | None = None,
        window_width: float | None = None,
    ) -> list[BoundingBox]:
        """Run EasyOCR on a single frame and return all detected boxes.

        Up to three normalization variants over the full frame:

        1. **Window/level** — DICOM WC/WW (or min/max fallback). Catches
           text overlapping anatomy or on bright backgrounds.
        2. **CLAHE** *(when enable_clahe=True)* — local contrast
           equalization. Catches gray-on-gray text where min/max can't
           separate text from background.
        3. **Lanczos upscale** *(when upscale_factor > 1)* — small
           annotation glyphs (4–7 px) become detectable by CRAFT.

        Boxes from later passes are deduped against earlier ones by
        IoU ≥0.5. Earlier passes win on overlap.
        """
        # --- Normalize once for use as the first OCR pass and as the
        # base for the CLAHE pass.
        if frame.dtype != np.uint8:
            full_frame = apply_window_level(frame, window_center, window_width)
        else:
            full_frame = frame

        # --- Pass 1: full-frame OCR with the supplied window/level ---
        merged = self._readtext_to_boxes(full_frame, frame_index)

        # --- Pass 2: full-frame CLAHE (optional) ---
        if self._enable_clahe:
            clahe_full = apply_clahe(full_frame, clip_limit=self._clahe_clip_limit)
            merged = self._merge_dedupe(
                merged,
                self._readtext_to_boxes(clahe_full, frame_index),
            )

        # --- Pass 2b: upscaled full-frame (optional) ---
        # Lanczos-upscale before OCR so 4-7 px CT/MR annotation glyphs
        # land in CRAFT's reliable detection range. Coordinates from
        # the upscaled image are divided by the factor before merging.
        # We upscale the WL-normalized frame (not the CLAHE one) so
        # this pass is orthogonal to CLAHE and either can be enabled
        # alone or together.
        if self._upscale_factor > 1:
            up_full = upscale_for_ocr(full_frame, self._upscale_factor)
            up_boxes = self._readtext_to_boxes(up_full, frame_index)
            merged = self._merge_dedupe(
                merged,
                self._scale_down(up_boxes, self._upscale_factor),
            )

        return merged

    @staticmethod
    def _scale_down(boxes: list[BoundingBox], factor: int) -> list[BoundingBox]:
        """Map OCR results from the upscaled image back to original coords.

        The naive approach — floor-divide ``x``, ``y``, ``width``,
        ``height`` independently — leaks PHI: when the upscaled box
        ends on an odd boundary, dividing the *width* throws away the
        trailing half-pixel and the rightmost original-coord pixel of
        the glyph stays unmasked. Instead we floor the start and ceil
        the end, then derive the dimensions from the difference, so
        the resulting box always *covers* every original pixel that
        any upscaled pixel of the box mapped to.

        Worst-case slack: up to ``factor - 1`` pixels on the right and
        bottom edges, which masks one extra original-coord pixel — far
        better than missing one.
        """
        if factor <= 1:
            return boxes
        out: list[BoundingBox] = []
        for b in boxes:
            new_x = b.x // factor
            new_y = b.y // factor
            # ceil-div via -(-a // b); avoids importing math.ceil
            new_x_end = -(-(b.x + b.width) // factor)
            new_y_end = -(-(b.y + b.height) // factor)
            out.append(
                BoundingBox(
                    x=new_x,
                    y=new_y,
                    width=max(1, new_x_end - new_x),
                    height=max(1, new_y_end - new_y),
                    text=b.text,
                    frame_index=b.frame_index,
                    confidence=b.confidence,
                )
            )
        return out

    @staticmethod
    def _merge_dedupe(
        existing: list[BoundingBox],
        new: list[BoundingBox],
    ) -> list[BoundingBox]:
        """Return ``existing + new`` with new boxes that overlap any
        existing box (IoU ≥0.5) suppressed. Existing boxes win on
        overlap so coordinates we already trust aren't perturbed."""
        if not existing:
            return list(new)
        out = list(existing)
        for nbox in new:
            if not any(_iou(nbox, ebox) >= 0.5 for ebox in existing):
                out.append(nbox)
        return out

    def _readtext_to_boxes(
        self,
        image: np.ndarray,
        frame_index: int,
    ) -> list[BoundingBox]:
        """Run EasyOCR on a uint8 image and convert results to BoundingBox list."""
        results = self._reader.readtext(image)
        if not results:
            return []

        boxes: list[BoundingBox] = []
        for bbox, text, confidence in results:
            box = self._easyocr_bbox_to_bounding_box(
                bbox, text, frame_index, float(confidence)
            )
            if box is not None:
                boxes.append(box)
        return boxes

    @staticmethod
    def _easyocr_bbox_to_bounding_box(
        bbox: list[list[float]],
        text: str,
        frame_index: int = 0,
        confidence: float | None = None,
    ) -> BoundingBox | None:
        """Convert an EasyOCR bounding box to a BoundingBox.

        EasyOCR returns bounding boxes as
        ``[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]`` (4 corner points).
        We take min/max of x and y to get an axis-aligned rectangle.
        """
        if not bbox or len(bbox) < 4:
            return None

        xs = [float(pt[0]) for pt in bbox]
        ys = [float(pt[1]) for pt in bbox]

        x_min = int(min(xs))
        y_min = int(min(ys))
        x_max = int(max(xs))
        y_max = int(max(ys))

        width = x_max - x_min
        height = y_max - y_min

        if width <= 0 or height <= 0:
            return None

        return BoundingBox(
            x=x_min,
            y=y_min,
            width=width,
            height=height,
            text=text,
            frame_index=frame_index,
            confidence=confidence,
        )


def _iou(a: BoundingBox, b: BoundingBox) -> float:
    """Intersection-over-union for two ``BoundingBox`` objects.

    Used to suppress strip-pass boxes that duplicate text already
    found by the full-frame pass.
    """
    if a.frame_index != b.frame_index:
        return 0.0
    ax0, ay0, ax1, ay1 = a.x, a.y, a.x + a.width, a.y + a.height
    bx0, by0, bx1, by1 = b.x, b.y, b.x + b.width, b.y + b.height
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    if inter == 0:
        return 0.0
    a_area = max(1, (ax1 - ax0) * (ay1 - ay0))
    b_area = max(1, (bx1 - bx0) * (by1 - by0))
    return inter / (a_area + b_area - inter)
