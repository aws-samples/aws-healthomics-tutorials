#!/usr/bin/env python3
"""Generate workflow execution summary JSON for GFF3 Annotation Loader."""

import argparse
import json
import sys
from datetime import datetime


def parse_timestamp(ts):
    try:
        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except ValueError as e:
        raise ValueError(f"Invalid timestamp: {ts}") from e


def calculate_duration(start, end):
    return int((parse_timestamp(end) - parse_timestamp(start)).total_seconds())


def build_summary(gff3_file, schema, destination, namespace, catalog_type,
                  tables_created, features_loaded, sources_loaded,
                  start_time, end_time, batch_size=100000,
                  relationships_loaded=0, batches_processed=0, table_locations=None):
    duration = calculate_duration(start_time, end_time)
    summary = {
        "workflow": "healthomics-gff3-loader",
        "version": "1.0.0",
        "execution": {
            "start_time": start_time, "end_time": end_time,
            "duration_seconds": duration,
        },
        "inputs": {
            "gff3_file": gff3_file, "schema": schema,
            "destination": destination, "namespace": namespace,
            "batch_size": batch_size,
        },
        "results": {
            "catalog_type": catalog_type, "tables_created": tables_created,
            "features_loaded": features_loaded, "sources_loaded": sources_loaded,
        },
    }
    if relationships_loaded > 0:
        summary["results"]["relationships_loaded"] = relationships_loaded
    if batches_processed > 0:
        summary["results"]["batches_processed"] = batches_processed
    if table_locations:
        summary["table_locations"] = table_locations
    return summary


def main():
    parser = argparse.ArgumentParser(description='Generate GFF3 loader summary')
    parser.add_argument('--gff3-file', required=True)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--catalog-type', required=True)
    parser.add_argument('--tables-created', required=True)
    parser.add_argument('--features-loaded', type=int, required=True)
    parser.add_argument('--sources-loaded', type=int, required=True)
    parser.add_argument('--start-time', required=True)
    parser.add_argument('--end-time', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--batch-size', type=int, default=100000)
    parser.add_argument('--relationships-loaded', type=int, default=0)
    parser.add_argument('--batches-processed', type=int, default=0)
    parser.add_argument('--table-locations', help='JSON string of table locations')
    args = parser.parse_args()

    try:
        tables_created = [t.strip() for t in args.tables_created.split(',') if t.strip()]
        table_locations = json.loads(args.table_locations) if args.table_locations else None
        summary = build_summary(
            args.gff3_file, args.schema, args.destination, args.namespace,
            args.catalog_type, tables_created, args.features_loaded,
            args.sources_loaded, args.start_time, args.end_time,
            args.batch_size, args.relationships_loaded, args.batches_processed,
            table_locations)
        with open(args.output, 'w') as f:
            json.dump(summary, f, indent=2)
        print(json.dumps(summary, indent=2))
        return 0
    except Exception as e:
        print(f"Error generating summary: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
