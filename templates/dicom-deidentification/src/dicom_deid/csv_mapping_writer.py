"""CSVMappingWriter — produces the CSV mapping file with full traceability."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from .models import InstanceResult

logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "original_patient_id",
    "deidentified_patient_id",
    "original_study_uid",
    "deidentified_study_uid",
    "original_series_uid",
    "deidentified_series_uid",
    "original_sop_instance_uid",
    "deidentified_sop_instance_uid",
    "original_file_path",
    "output_file_path",
    "metadata_status",
    "pixel_detection_status",
    "pixel_masking_status",
    "bounding_boxes_found",
]


class CSVWriteError(Exception):
    """Raised when writing the CSV mapping file fails."""


class CSVMappingWriter:
    """Writes the CSV mapping file with one row per processed instance."""

    def write(self, results: list[InstanceResult], output_dir: Path) -> Path:
        """Write CSV with header row and one row per instance.

        De-identified columns are left empty for failed/skipped instances.
        Returns the output file path.
        Raises :class:`CSVWriteError` on failure.
        """
        dest_path = output_dir / "csv_mapping.csv"

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()

                for result in results:
                    info = result.instance_info
                    is_success = result.metadata_status == "success"

                    row = {
                        "original_patient_id": info.patient_id,
                        "deidentified_patient_id": result.deidentified_patient_id or "" if is_success else "",
                        "original_study_uid": info.study_uid,
                        "deidentified_study_uid": result.deidentified_study_uid or "" if is_success else "",
                        "original_series_uid": info.series_uid,
                        "deidentified_series_uid": result.deidentified_series_uid or "" if is_success else "",
                        "original_sop_instance_uid": info.sop_instance_uid,
                        "deidentified_sop_instance_uid": result.deidentified_sop_uid or "" if is_success else "",
                        "original_file_path": str(info.file_path),
                        "output_file_path": str(result.output_file_path) if is_success and result.output_file_path else "",
                        "metadata_status": result.metadata_status,
                        "pixel_detection_status": result.pixel_detection_status,
                        "pixel_masking_status": result.pixel_masking_status,
                        "bounding_boxes_found": result.bounding_boxes_found if result.bounding_boxes_found is not None else "",
                    }
                    writer.writerow(row)
        except Exception as exc:
            msg = f"Failed to write CSV mapping file to {dest_path}: {exc}"
            logger.error(msg)
            raise CSVWriteError(msg) from exc

        return dest_path
