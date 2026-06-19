"""SummaryReporter — produces the workflow execution summary report."""

from __future__ import annotations

import logging

from .models import (
    DICOMHierarchy,
    InstanceResult,
    WorkflowSummary,
    METADATA_FAILED,
    METADATA_SUCCESS,
    PIXEL_MASKING_FAILED_UNMATCHED_TEXT,
    PIXEL_MASKING_FAILED_UNSUPPORTED_TS,
    PIXEL_MASKING_SKIPPED_LOSSY,
    PIXEL_MASKING_SKIPPED_UNSUPPORTED_TS,
    PIXEL_MASKING_SUCCESS,
)

logger = logging.getLogger(__name__)


class SummaryReporter:
    """Generates the workflow execution summary."""

    def generate(
        self,
        results: list[InstanceResult],
        hierarchy: DICOMHierarchy,
        csv_mapping_written: bool = False,
    ) -> WorkflowSummary:
        """Generate summary with counts and malformed files."""
        total_studies = len(hierarchy.studies)
        total_series = sum(len(st.series) for st in hierarchy.studies)
        total_instances = len(results)

        successful = sum(1 for r in results if r.metadata_status == METADATA_SUCCESS)
        failed = sum(1 for r in results if r.metadata_status == METADATA_FAILED)

        masking_applied = sum(
            1 for r in results if r.pixel_masking_status == PIXEL_MASKING_SUCCESS
        )
        masking_skipped_lossy = sum(
            1 for r in results if r.pixel_masking_status == PIXEL_MASKING_SKIPPED_LOSSY
        )
        masking_skipped_unsupported_ts = sum(
            1
            for r in results
            if r.pixel_masking_status == PIXEL_MASKING_SKIPPED_UNSUPPORTED_TS
        )
        masking_failed_unsupported_ts = sum(
            1
            for r in results
            if r.pixel_masking_status == PIXEL_MASKING_FAILED_UNSUPPORTED_TS
        )
        masking_failed_unmatched_text = sum(
            1
            for r in results
            if r.pixel_masking_status == PIXEL_MASKING_FAILED_UNMATCHED_TEXT
        )

        return WorkflowSummary(
            total_studies=total_studies,
            total_series=total_series,
            total_instances=total_instances,
            successful_instances=successful,
            failed_instances=failed,
            malformed_files=list(hierarchy.malformed_files),
            csv_mapping_written=csv_mapping_written,
            masking_applied_count=masking_applied,
            masking_skipped_lossy_count=masking_skipped_lossy,
            masking_skipped_unsupported_ts_count=masking_skipped_unsupported_ts,
            masking_failed_unsupported_ts_count=masking_failed_unsupported_ts,
            masking_failed_unmatched_text_count=masking_failed_unmatched_text,
        )

    def format_report(self, summary: WorkflowSummary) -> str:
        """Format the summary as a human-readable string."""
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("DICOM De-identification Workflow Summary")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Studies processed:    {summary.total_studies}")
        lines.append(f"Series processed:     {summary.total_series}")
        lines.append(f"Instances processed:  {summary.total_instances}")
        lines.append(f"  Successful:         {summary.successful_instances}")
        lines.append(f"  Failed:             {summary.failed_instances}")
        lines.append("")

        if summary.malformed_files:
            lines.append("Malformed/Failed Files:")
            for path, reason in summary.malformed_files:
                lines.append(f"  {path}: {reason}")
            lines.append("")

        csv_status = "Yes" if summary.csv_mapping_written else "No"
        lines.append(f"CSV Mapping Written:  {csv_status}")

        # Pixel masking stats (only show if any masking activity occurred)
        if (
            summary.masking_applied_count > 0
            or summary.masking_skipped_lossy_count > 0
            or summary.masking_skipped_unsupported_ts_count > 0
            or summary.masking_failed_unsupported_ts_count > 0
            or summary.masking_failed_unmatched_text_count > 0
        ):
            lines.append("")
            lines.append("Pixel Masking Stats:")
            lines.append(f"  Masking applied:          {summary.masking_applied_count}")
            lines.append(f"  Skipped (lossy):          {summary.masking_skipped_lossy_count}")
            lines.append(f"  Skipped (unsupported TS): {summary.masking_skipped_unsupported_ts_count}")
            lines.append(f"  Failed (unsupported TS):  {summary.masking_failed_unsupported_ts_count}")
            lines.append(f"  Failed (unmatched text):  {summary.masking_failed_unmatched_text_count}")

        lines.append("=" * 60)

        return "\n".join(lines)
