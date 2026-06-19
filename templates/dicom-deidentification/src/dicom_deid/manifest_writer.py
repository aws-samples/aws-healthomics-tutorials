"""ManifestWriter — produces the hierarchical Job Output Manifest JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import (
    DICOMHierarchy,
    InstanceResult,
    METADATA_SUCCESS,
)

logger = logging.getLogger(__name__)


class ManifestWriter:
    """Produces the hierarchical Job Output Manifest JSON."""

    def write(
        self,
        results: list[InstanceResult],
        hierarchy: DICOMHierarchy,
        output_dir: Path,
    ) -> Path:
        """Compute statuses, build manifest, write JSON to output_dir/job_output_manifest.json."""
        # Build lookup: sop_instance_uid -> InstanceResult
        result_map: dict[str, InstanceResult] = {}
        for r in results:
            result_map[r.instance_info.sop_instance_uid] = r

        studies_json: list[dict] = []
        all_study_statuses: list[str] = []
        all_series_statuses: list[str] = []
        total_instances = 0
        instance_outcomes: dict[str, int] = {"success": 0, "skipped": 0, "failed": 0}

        for study in hierarchy.studies:
            series_json_list: list[dict] = []
            study_series_statuses: list[str] = []

            for series in study.series:
                instances_json: list[dict] = []
                series_instance_statuses: list[str] = []

                for inst in series.instances:
                    total_instances += 1
                    result = result_map.get(inst.sop_instance_uid)

                    if result is None:
                        # No result — treat as failed
                        combined = "failed"
                        instances_json.append({
                            "original_sop_instance_uid": inst.sop_instance_uid,
                            "deidentified_sop_instance_uid": "",
                            "metadata_status": "failed",
                            "pixel_detection_status": "not_attempted",
                            "pixel_masking_status": "not_attempted",
                        })
                    else:
                        combined = self._compute_instance_status(result)
                        instances_json.append({
                            "original_sop_instance_uid": inst.sop_instance_uid,
                            "deidentified_sop_instance_uid": result.deidentified_sop_uid or "",
                            "metadata_status": result.metadata_status,
                            "pixel_detection_status": result.pixel_detection_status,
                            "pixel_masking_status": result.pixel_masking_status,
                        })

                    series_instance_statuses.append(combined)
                    if combined == "success":
                        instance_outcomes["success"] += 1
                    elif "skipped" in (result.metadata_status if result else ""):
                        instance_outcomes["skipped"] += 1
                    else:
                        instance_outcomes["failed"] += 1

                series_status = self.compute_series_status(series_instance_statuses)
                study_series_statuses.append(series_status)
                all_series_statuses.append(series_status)

                series_json_list.append({
                    "original_series_uid": series.series_uid,
                    "deidentified_series_uid": self._get_deid_series_uid(series.series_uid, result_map, series.instances),
                    "series_status": series_status,
                    "instances": instances_json,
                })

            study_status = self.compute_study_status(study_series_statuses)
            all_study_statuses.append(study_status)

            studies_json.append({
                "original_study_uid": study.study_uid,
                "deidentified_study_uid": self._get_deid_study_uid(study.study_uid, result_map, study),
                "study_status": study_status,
                "series": series_json_list,
            })

        # Overall workflow status
        workflow_status = "success" if instance_outcomes["success"] >= 1 else "failed"

        # Study/series status counts
        studies_by_status = {"success": 0, "partial": 0, "failed": 0}
        for s in all_study_statuses:
            studies_by_status[s] = studies_by_status.get(s, 0) + 1

        series_by_status = {"success": 0, "partial": 0, "failed": 0}
        for s in all_series_statuses:
            series_by_status[s] = series_by_status.get(s, 0) + 1

        manifest = {
            "workflow_status": workflow_status,
            "summary": {
                "total_studies": len(hierarchy.studies),
                "total_series": sum(len(st.series) for st in hierarchy.studies),
                "total_instances": total_instances,
                "studies_by_status": studies_by_status,
                "series_by_status": series_by_status,
                "instances_by_outcome": instance_outcomes,
            },
            "studies": studies_json,
        }

        dest_path = output_dir / "job_output_manifest.json"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "w") as f:
                json.dump(manifest, f, indent=2)
        except Exception as exc:
            logger.error("Failed to write manifest to %s: %s", dest_path, exc)
            raise

        return dest_path

    @staticmethod
    def _compute_instance_status(result: InstanceResult) -> str:
        """Compute combined instance status.

        An instance is "success" only if ALL requested steps succeeded.
        """
        if result.metadata_status != METADATA_SUCCESS:
            return "failed"

        # Check pixel detection if it was requested
        if result.pixel_detection_status not in ("success", "not_requested"):
            return "failed"

        # Check pixel masking if it was requested
        if result.pixel_masking_status not in (
            "success",
            "skipped_lossy",
            "skipped_unsupported_ts",
            "not_requested",
            "no_text_found",
        ):
            return "failed"

        return "success"

    @staticmethod
    def compute_series_status(instance_statuses: list[str]) -> str:
        """Compute series status from instance combined statuses.

        "success" if all succeeded, "failed" if all failed, "partial" otherwise.
        """
        if not instance_statuses:
            return "failed"

        all_success = all(s == "success" for s in instance_statuses)
        all_failed = all(s == "failed" for s in instance_statuses)

        if all_success:
            return "success"
        if all_failed:
            return "failed"
        return "partial"

    @staticmethod
    def compute_study_status(series_statuses: list[str]) -> str:
        """Compute study status from series statuses.

        "success" if all succeeded, "failed" if all failed, "partial" otherwise.
        """
        if not series_statuses:
            return "failed"

        all_success = all(s == "success" for s in series_statuses)
        all_failed = all(s == "failed" for s in series_statuses)

        if all_success:
            return "success"
        if all_failed:
            return "failed"
        return "partial"

    @staticmethod
    def _get_deid_study_uid(study_uid, result_map, study):
        """Get de-identified study UID from any successful instance in the study."""
        for series in study.series:
            for inst in series.instances:
                r = result_map.get(inst.sop_instance_uid)
                if r and r.deidentified_study_uid:
                    return r.deidentified_study_uid
        return ""

    @staticmethod
    def _get_deid_series_uid(series_uid, result_map, instances):
        """Get de-identified series UID from any successful instance in the series."""
        for inst in instances:
            r = result_map.get(inst.sop_instance_uid)
            if r and r.deidentified_series_uid:
                return r.deidentified_series_uid
        return ""
