"""PixelMasker — applies black box overlays at bounding box locations in DICOM pixel data."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pydicom
from pydicom.pixels import convert_color_space

from .models import BoundingBox

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class MaskResult:
    """Result of pixel masking for a single instance."""

    status: str
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Transfer Syntax classification
# ---------------------------------------------------------------------------

# Supported Transfer Syntax UIDs
# Uncompressed / pydicom built-in
_TS_IMPLICIT_VR_LE = "1.2.840.10008.1.2"
_TS_EXPLICIT_VR_LE = "1.2.840.10008.1.2.1"
_TS_RLE_LOSSLESS = "1.2.840.10008.1.2.5"

# pylibjpeg-openjpeg (MIT)
_TS_JPEG2000_LOSSLESS = "1.2.840.10008.1.2.4.90"
_TS_JPEG2000_LOSSY = "1.2.840.10008.1.2.4.91"
_TS_HTJ2K_LOSSLESS_ONLY = "1.2.840.10008.1.2.4.201"
_TS_HTJ2K_RPCL_LOSSLESS_ONLY = "1.2.840.10008.1.2.4.202"
_TS_HTJ2K = "1.2.840.10008.1.2.4.203"

# pillow (MIT-CMU)
_TS_JPEG_BASELINE = "1.2.840.10008.1.2.4.50"
# pyjpegls (MIT)
_TS_JPEGLS_LOSSLESS = "1.2.840.10008.1.2.4.80"
_TS_JPEGLS_NEAR_LOSSLESS = "1.2.840.10008.1.2.4.81"

# JPEG XL — NOT currently supported. pydicom 3.0.2 ships no JPEG XL decoder
# and imagecodecs is not a registered pydicom decoder plugin. These UIDs are
# kept for identification only; instances using them are reported as
# "skipped_unsupported_ts" during masking.
_TS_JPEGXL_LOSSLESS = "1.2.840.10008.1.2.4.110"
_TS_JPEGXL_JPEG_RECOMPRESSION = "1.2.840.10008.1.2.4.111"
_TS_JPEGXL = "1.2.840.10008.1.2.4.112"


SUPPORTED_TRANSFER_SYNTAXES: set[str] = {
    _TS_IMPLICIT_VR_LE,
    _TS_EXPLICIT_VR_LE,
    _TS_RLE_LOSSLESS,
    _TS_JPEG2000_LOSSLESS,
    _TS_JPEG2000_LOSSY,
    _TS_HTJ2K_LOSSLESS_ONLY,
    _TS_HTJ2K_RPCL_LOSSLESS_ONLY,
    _TS_HTJ2K,
    _TS_JPEG_BASELINE,
    _TS_JPEGLS_LOSSLESS,
    _TS_JPEGLS_NEAR_LOSSLESS,
}

LOSSY_TRANSFER_SYNTAXES: set[str] = {
    _TS_JPEG_BASELINE,
    _TS_JPEG2000_LOSSY,
    _TS_JPEGLS_NEAR_LOSSLESS,
    _TS_HTJ2K,
}


# ---------------------------------------------------------------------------
# PixelMasker
# ---------------------------------------------------------------------------

class PixelMasker:
    """Apply black box overlays at bounding box locations in DICOM pixel data.

    The masker reads the Transfer Syntax UID from the dataset, decodes
    pixel data to a numpy array (pydicom handles decoder selection
    automatically when the appropriate plugins are installed), applies
    black rectangular overlays at each bounding box location, and
    re-encodes the pixel data.

    For the initial implementation, after masking on the decompressed
    array, the pixel data is re-encoded as Explicit VR Little Endian
    (uncompressed) and the Transfer Syntax UID is updated accordingly.
    This avoids the complexity of re-encoding to the original compressed
    format while still producing valid DICOM output.
    """

    def mask(
        self,
        dataset: pydicom.Dataset,
        bounding_boxes: list[BoundingBox],
        mask_lossy: bool,
        allow_unsupported_ts: bool = False,
    ) -> MaskResult:
        """Decode pixel data, apply black rectangles, re-encode.

        Parameters
        ----------
        dataset:
            A pydicom Dataset with pixel data loaded.
        bounding_boxes:
            List of BoundingBox regions to mask with black overlays.
        mask_lossy:
            If False and the instance uses lossy compression, skip masking
            and return status ``"skipped_lossy"``.
        allow_unsupported_ts:
            If True, an instance whose Transfer Syntax cannot be decoded
            (e.g. JPEG-XL) is reported as ``"skipped_unsupported_ts"``
            so the original pixel data passes through unmodified. If
            False (default), the same condition is treated as a hard
            failure (``"failed_unsupported_ts"``) so PHI cannot silently
            slip through an undetectable codec.

        Returns
        -------
        MaskResult
            Contains the masking status and optional error message.
        """
        # Read Transfer Syntax from dataset
        ts_uid = self._get_transfer_syntax(dataset)

        # Check if Transfer Syntax is supported
        if ts_uid not in SUPPORTED_TRANSFER_SYNTAXES:
            msg = f"Unsupported Transfer Syntax: {ts_uid}"
            if allow_unsupported_ts:
                logger.warning("%s — passing pixels through unmasked (opt-in).", msg)
                return MaskResult(status="skipped_unsupported_ts", error_message=msg)
            logger.error(
                "%s — refusing to pass pixels through. Set "
                "allow_unsupported_pixel_ts=true (or pass --allow-unsupported-pixel-ts) "
                "to override.",
                msg,
            )
            return MaskResult(status="failed_unsupported_ts", error_message=msg)

        # Check lossy compression handling
        is_lossy = ts_uid in LOSSY_TRANSFER_SYNTAXES
        if is_lossy and not mask_lossy:
            logger.info(
                "Skipping masking for lossy-compressed instance (mask_lossy_images=false)"
            )
            return MaskResult(status="skipped_lossy")

        # Decode pixel data
        try:
            pixel_array = dataset.pixel_array
        except Exception as exc:
            msg = f"Failed to decode pixel data (TS={ts_uid}): {exc}"
            logger.error(msg)
            return MaskResult(status="failed", error_message=msg)

        # Normalize colour space to RGB BEFORE masking and re-encode.
        # Validated against pydicom-data: uncompressed YBR_FULL and
        # JPEG-baseline-coded YBR_FULL_422 sources expose YBR-coded bytes
        # via dataset.pixel_array. _reencode_uncompressed already retags
        # the photometric to RGB, so unless we convert the BYTES too the
        # output declares RGB but contains YBR — viewers render wrong
        # colours (validated max channel diff 255 / 140 on the two
        # affected fixtures). pydicom auto-converts YBR_ICT/YBR_RCT during
        # J2K decode, so they need no fix here.
        pixel_array = self._normalize_colour_space(pixel_array, dataset)

        # Apply black rectangular overlays
        pixel_array = self._apply_masks(pixel_array, bounding_boxes)

        # Re-encode as Explicit VR Little Endian (uncompressed)
        try:
            self._reencode_uncompressed(dataset, pixel_array)
        except Exception as exc:
            msg = f"Failed to re-encode pixel data (TS={ts_uid}): {exc}"
            logger.error(msg)
            return MaskResult(status="failed", error_message=msg)

        return MaskResult(status="success")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_transfer_syntax(dataset: pydicom.Dataset) -> str:
        """Extract the Transfer Syntax UID from the dataset."""
        if hasattr(dataset, "file_meta") and dataset.file_meta is not None:
            ts = getattr(dataset.file_meta, "TransferSyntaxUID", None)
            if ts is not None:
                return str(ts)
        return ""

    @staticmethod
    def _normalize_colour_space(
        pixel_array: np.ndarray,
        dataset: pydicom.Dataset,
    ) -> np.ndarray:
        """Convert YBR-coded pixels to RGB so the rebuild matches its tag.

        Only ``YBR_FULL`` and ``YBR_FULL_422`` need conversion: pydicom
        does not auto-convert these on read. ``YBR_ICT`` / ``YBR_RCT``
        are converted by the JPEG-2000 decoder during pixel_array access,
        so the array we get is already RGB despite the photometric tag.
        ``RGB``, ``MONOCHROME1/2``, and ``PALETTE COLOR`` need no change.

        ``convert_color_space`` requires uint8 input; if the array is a
        wider dtype we leave it alone and log — uncompressed 16-bit YBR
        is exotic enough that we'd rather refuse than guess at a
        conversion. The mask still applies; the photometric retag
        downstream still happens; only the bytes are unconverted in
        that edge case.
        """
        photometric = str(getattr(dataset, "PhotometricInterpretation", ""))
        if photometric not in ("YBR_FULL", "YBR_FULL_422"):
            return pixel_array

        if pixel_array.dtype != np.uint8:
            logger.warning(
                "Cannot convert %s pixels to RGB: dtype is %s, "
                "convert_color_space requires uint8. Bytes will be "
                "rebuilt as-is and may not match the RGB tag downstream.",
                photometric,
                pixel_array.dtype,
            )
            return pixel_array

        try:
            return convert_color_space(
                pixel_array,
                current=photometric,
                desired="RGB",
            )
        except Exception as exc:
            logger.error(
                "convert_color_space(%s -> RGB) failed: %s. "
                "Falling back to unconverted bytes.",
                photometric,
                exc,
            )
            return pixel_array

    @staticmethod
    def _apply_masks(
        pixel_array: np.ndarray,
        bounding_boxes: list[BoundingBox],
    ) -> np.ndarray:
        """Apply black rectangular overlays at each bounding box location.

        Sets pixels to 0 within each bounding box region. Handles both
        single-frame (H×W or H×W×C) and multi-frame (N×H×W or N×H×W×C)
        arrays by applying masks to the correct frame based on frame_index.
        """
        ndim = pixel_array.ndim
        is_multiframe = ndim == 4 or (ndim == 3 and pixel_array.shape[2] > 4)

        for box in bounding_boxes:
            y_start = max(0, box.y)
            x_start = max(0, box.x)

            if is_multiframe:
                if ndim == 4:
                    # (N, H, W, C) multi-frame colour
                    y_end = min(pixel_array.shape[1], box.y + box.height)
                    x_end = min(pixel_array.shape[2], box.x + box.width)
                    pixel_array[box.frame_index, y_start:y_end, x_start:x_end] = 0
                else:
                    # (N, H, W) multi-frame greyscale
                    y_end = min(pixel_array.shape[1], box.y + box.height)
                    x_end = min(pixel_array.shape[2], box.x + box.width)
                    pixel_array[box.frame_index, y_start:y_end, x_start:x_end] = 0
            else:
                # Single frame (H, W) or (H, W, C)
                y_end = min(pixel_array.shape[0], box.y + box.height)
                x_end = min(pixel_array.shape[1], box.x + box.width)
                pixel_array[y_start:y_end, x_start:x_end] = 0

        return pixel_array

    @staticmethod
    def _reencode_uncompressed(
        dataset: pydicom.Dataset,
        pixel_array: np.ndarray,
    ) -> None:
        """Re-encode the modified pixel array as uncompressed Explicit VR LE.

        Updates the dataset's PixelData, Transfer Syntax UID, and all
        pixel-related attributes to match the uncompressed representation.
        pydicom's pixel_array returns data in RGB color space regardless
        of the original PhotometricInterpretation, so we update accordingly.
        """
        # Set raw pixel data bytes
        dataset.PixelData = pixel_array.tobytes()

        # Update Transfer Syntax to Explicit VR Little Endian
        if hasattr(dataset, "file_meta") and dataset.file_meta is not None:
            dataset.file_meta.TransferSyntaxUID = _TS_EXPLICIT_VR_LE

        # Update PhotometricInterpretation — pixel_array is always RGB for colour
        photometric = getattr(dataset, "PhotometricInterpretation", "")
        if photometric in ("YBR_FULL", "YBR_FULL_422", "YBR_ICT", "YBR_RCT", "YBR_PARTIAL_422"):
            dataset.PhotometricInterpretation = "RGB"

        # Ensure PlanarConfiguration is 0 (colour-by-pixel, R1G1B1 R2G2B2...)
        # which is what pixel_array.tobytes() produces
        samples = getattr(dataset, "SamplesPerPixel", 1)
        if samples > 1:
            dataset.PlanarConfiguration = 0

        # Update BitsAllocated/BitsStored/HighBit to match the array dtype
        if pixel_array.dtype == np.uint8:
            dataset.BitsAllocated = 8
            dataset.BitsStored = 8
            dataset.HighBit = 7
        elif pixel_array.dtype == np.uint16:
            dataset.BitsAllocated = 16
            dataset.BitsStored = 16
            dataset.HighBit = 15

        # Pixel data is no longer encapsulated — set definite length
        if "PixelData" in dataset:
            dataset["PixelData"].is_undefined_length = False

        # Remove any pixel data fragment sequences left over from compressed data
        # (pydicom may leave these around)
        dataset["PixelData"].VR = "OW" if dataset.BitsAllocated > 8 else "OB"
