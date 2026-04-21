#!/usr/bin/env python3
"""
Generate workflow execution summary JSON.

This script accepts workflow parameters and results, calculates execution duration,
and generates a summary JSON file with all required metadata.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Dict, List, Any


def parse_timestamp(timestamp_str: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime object."""
    try:
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except ValueError as e:
        raise ValueError(f"Invalid timestamp format: {timestamp_str}. Expected ISO 8601 format.") from e


def calculate_duration(start_time: str, end_time: str) -> int:
    """Calculate duration in seconds between start and end times."""
    start_dt = parse_timestamp(start_time)
    end_dt = parse_timestamp(end_time)
    duration = (end_dt - start_dt).total_seconds()
    return int(duration)


def build_summary(
    vcf_file: str,
    schema: str,
    destination: str,
    namespace: str,
    catalog_type: str,
    tables_created: List[str],
    variants_loaded: int,
    samples_loaded: int,
    start_time: str,
    end_time: str,
    batch_size: int = 100000,
    variant_sample_associations: int = 0,
    batches_processed: int = 0,
    table_locations: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Build summary JSON structure with all required fields.
    
    Args:
        vcf_file: Input VCF file path
        schema: Schema selection (1, 2, 3, or 4)
        destination: Destination location (S3 Table Bucket ARN or S3 path)
        namespace: Iceberg namespace
        catalog_type: Catalog type ('s3tables' or 'vanilla')
        tables_created: List of table names created
        variants_loaded: Total number of variant records loaded
        samples_loaded: Total number of sample records loaded
        start_time: Workflow start timestamp (ISO 8601)
        end_time: Workflow end timestamp (ISO 8601)
        batch_size: Batch size used for processing (optional)
        variant_sample_associations: Number of variant-sample associations (optional)
        batches_processed: Number of batches processed (optional)
        table_locations: Dictionary mapping table names to their locations (optional)
    
    Returns:
        Dictionary containing the complete summary structure
    """
    duration = calculate_duration(start_time, end_time)
    
    summary = {
        "workflow": "healthomics-vcf-loader",
        "version": "1.0.0",
        "execution": {
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration
        },
        "inputs": {
            "vcf_file": vcf_file,
            "schema": schema,
            "destination": destination,
            "namespace": namespace,
            "batch_size": batch_size
        },
        "results": {
            "catalog_type": catalog_type,
            "tables_created": tables_created,
            "variants_loaded": variants_loaded,
            "samples_loaded": samples_loaded
        }
    }
    
    # Add optional fields if provided
    if variant_sample_associations > 0:
        summary["results"]["variant_sample_associations"] = variant_sample_associations
    
    if batches_processed > 0:
        summary["results"]["batches_processed"] = batches_processed
    
    if table_locations:
        summary["table_locations"] = table_locations
    
    return summary


def write_summary(summary: Dict[str, Any], output_file: str) -> None:
    """Write summary JSON to output file."""
    try:
        with open(output_file, 'w') as f:
            json.dump(summary, f, indent=2)
    except IOError as e:
        raise IOError(f"Failed to write summary to {output_file}: {e}") from e


def main():
    """Main entry point for generate_summary script."""
    parser = argparse.ArgumentParser(
        description='Generate workflow execution summary JSON'
    )
    
    # Required arguments
    parser.add_argument('--vcf-file', required=True, help='Input VCF file path')
    parser.add_argument('--schema', required=True, help='Schema selection (1, 2, 3, or 4)')
    parser.add_argument('--destination', required=True, help='Destination location')
    parser.add_argument('--namespace', required=True, help='Iceberg namespace')
    parser.add_argument('--catalog-type', required=True, help='Catalog type (s3tables or vanilla)')
    parser.add_argument('--tables-created', required=True, help='Comma-separated list of tables created')
    parser.add_argument('--variants-loaded', type=int, required=True, help='Number of variants loaded')
    parser.add_argument('--samples-loaded', type=int, required=True, help='Number of samples loaded')
    parser.add_argument('--start-time', required=True, help='Workflow start time (ISO 8601)')
    parser.add_argument('--end-time', required=True, help='Workflow end time (ISO 8601)')
    parser.add_argument('--output', required=True, help='Output file path for summary JSON')
    
    # Optional arguments
    parser.add_argument('--batch-size', type=int, default=100000, help='Batch size used for processing')
    parser.add_argument('--variant-sample-associations', type=int, default=0, 
                       help='Number of variant-sample associations')
    parser.add_argument('--batches-processed', type=int, default=0, help='Number of batches processed')
    parser.add_argument('--table-locations', help='JSON string mapping table names to locations')
    
    args = parser.parse_args()
    
    try:
        # Parse tables_created from comma-separated string
        tables_created = [t.strip() for t in args.tables_created.split(',') if t.strip()]
        
        # Parse table_locations if provided
        table_locations = None
        if args.table_locations:
            table_locations = json.loads(args.table_locations)
        
        # Build summary
        summary = build_summary(
            vcf_file=args.vcf_file,
            schema=args.schema,
            destination=args.destination,
            namespace=args.namespace,
            catalog_type=args.catalog_type,
            tables_created=tables_created,
            variants_loaded=args.variants_loaded,
            samples_loaded=args.samples_loaded,
            start_time=args.start_time,
            end_time=args.end_time,
            batch_size=args.batch_size,
            variant_sample_associations=args.variant_sample_associations,
            batches_processed=args.batches_processed,
            table_locations=table_locations
        )
        
        # Write summary to file
        write_summary(summary, args.output)
        
        # Print summary to stdout for Nextflow to capture
        print(json.dumps(summary, indent=2))
        
        return 0
        
    except Exception as e:
        print(f"Error generating summary: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
