"""Aggregator for discovering and organizing DICOM files into a hierarchy."""

from __future__ import annotations

import logging
from pathlib import Path

import pydicom
import pydicom.errors

from .models import DICOMHierarchy, InstanceInfo, SeriesInfo, StudyInfo

logger = logging.getLogger(__name__)


class AggregationError(Exception):
    """Raised when aggregation fails (e.g. no DICOM files found)."""


class Aggregator:
    """Discovers DICOM files and organises them into Study → Series → Instance."""

    def aggregate(self, input_dir: Path) -> DICOMHierarchy:
        """Scan *input_dir* recursively, parse DICOM headers, build hierarchy.

        Files missing Study/Series UIDs are reported as malformed.
        Raises :class:`AggregationError` if no valid DICOM files are found.
        """
        instances: list[InstanceInfo] = []
        malformed: list[tuple[Path, str]] = []

        for file_path in sorted(input_dir.rglob("*")):
            if not file_path.is_file():
                continue

            try:
                ds = pydicom.dcmread(str(file_path), stop_before_pixels=True)
            except pydicom.errors.InvalidDicomError:
                # Not a DICOM file – skip silently.
                continue
            except Exception as exc:
                # Unexpected read error (corrupt file, permissions, etc.).
                # Skip the file but log so genuine problems aren't hidden.
                logger.debug("Skipping unreadable file %s: %s", file_path, exc)
                continue

            # Validate required UIDs ----------------------------------------
            study_uid = getattr(ds, "StudyInstanceUID", None)
            series_uid = getattr(ds, "SeriesInstanceUID", None)
            sop_uid = getattr(ds, "SOPInstanceUID", None)

            missing: list[str] = []
            if not study_uid:
                missing.append("StudyInstanceUID")
            if not series_uid:
                missing.append("SeriesInstanceUID")
            if missing:
                reason = f"Missing DICOM attribute(s): {', '.join(missing)}"
                malformed.append((file_path, reason))
                continue

            # Extract remaining fields --------------------------------------
            patient_id = str(getattr(ds, "PatientID", ""))
            transfer_syntax_uid = str(
                getattr(ds.file_meta, "TransferSyntaxUID", "")
            ) if hasattr(ds, "file_meta") and ds.file_meta else ""
            file_size = file_path.stat().st_size

            instances.append(
                InstanceInfo(
                    sop_instance_uid=str(sop_uid) if sop_uid else "",
                    series_uid=str(series_uid),
                    study_uid=str(study_uid),
                    patient_id=patient_id,
                    file_path=file_path,
                    file_size_bytes=file_size,
                    transfer_syntax_uid=transfer_syntax_uid,
                )
            )

        if not instances:
            raise AggregationError(
                f"No DICOM files found in input directory: {input_dir}"
            )

        return self._build_hierarchy(instances, malformed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_hierarchy(
        instances: list[InstanceInfo],
        malformed: list[tuple[Path, str]],
    ) -> DICOMHierarchy:
        """Group flat instance list into Study → Series → Instance tree."""
        # study_uid -> series_uid -> list[InstanceInfo]
        study_map: dict[str, dict[str, list[InstanceInfo]]] = {}

        for inst in instances:
            series_map = study_map.setdefault(inst.study_uid, {})
            series_map.setdefault(inst.series_uid, []).append(inst)

        studies: list[StudyInfo] = []
        for study_uid, series_map in study_map.items():
            series_list: list[SeriesInfo] = [
                SeriesInfo(series_uid=s_uid, instances=s_instances)
                for s_uid, s_instances in series_map.items()
            ]
            # Use patient_id from the first instance in the study
            first_instance = next(iter(next(iter(series_map.values()))))
            studies.append(
                StudyInfo(
                    study_uid=study_uid,
                    patient_id=first_instance.patient_id,
                    series=series_list,
                )
            )

        return DICOMHierarchy(studies=studies, malformed_files=malformed)
