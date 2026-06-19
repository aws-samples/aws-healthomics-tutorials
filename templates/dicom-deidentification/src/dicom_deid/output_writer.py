"""OutputWriter for saving de-identified DICOM files."""

from __future__ import annotations

import logging
from pathlib import Path

import pydicom

logger = logging.getLogger(__name__)


class OutputWriteError(Exception):
    """Raised when writing a de-identified DICOM file fails."""


class OutputWriter:
    """Writes de-identified DICOM files preserving hierarchy."""

    def write(
        self,
        dataset: pydicom.Dataset,
        output_dir: Path,
        deidentified_study_uid: str,
        deidentified_series_uid: str,
        deidentified_sop_uid: str,
    ) -> Path:
        """Write de-identified DICOM to output_dir/study_uid/series_uid/sop_uid.dcm.

        Creates the directory structure as needed and returns the output file path.
        Raises :class:`OutputWriteError` on failure.
        """
        dest_dir = output_dir / deidentified_study_uid / deidentified_series_uid
        dest_path = dest_dir / f"{deidentified_sop_uid}.dcm"

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dataset.save_as(str(dest_path))
        except Exception as exc:
            msg = (
                f"Failed to write de-identified file for SOP {deidentified_sop_uid} "
                f"to {dest_path}: {exc}"
            )
            logger.error(msg)
            raise OutputWriteError(msg) from exc

        return dest_path
