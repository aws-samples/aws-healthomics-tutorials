#!/usr/bin/env python3
"""
Load GFF3 files into the annotation_db tables created by schema_1.py.

Parses GFF3 files and loads data into three Iceberg tables:
  - features
  - sources
  - feature_relationships
"""

import argparse
import os
import sys
import gzip
import pyarrow as pa
from urllib.parse import unquote
from pyiceberg.exceptions import NoSuchTableError
from utils import load_s3_tables_catalog, retry_operation
import boto3
from io import TextIOWrapper

# Configuration
NAMESPACE = "annotation_db"
FEATURES_TABLE = "features"
SOURCES_TABLE = "sources"
RELATIONSHIPS_TABLE = "feature_relationships"
BATCH_SIZE = 100000


def parse_s3_uri(s3_uri):
    """Parse S3 URI and return bucket and key."""
    if not s3_uri.startswith('s3://'):
        raise ValueError(f"Invalid S3 URI format: {s3_uri}")
    s3_parts = s3_uri[5:].split('/', 1)
    if len(s3_parts) != 2 or not s3_parts[0] or not s3_parts[1]:
        raise ValueError(f"Invalid S3 URI — missing bucket or key: {s3_uri}")
    return s3_parts[0], s3_parts[1]


def get_tables():
    """Get the existing tables or fail if they don't exist."""
    catalog = load_s3_tables_catalog(bucket_arn)

    try:
        namespaces = [ns[0] for ns in catalog.list_namespaces()]
        if NAMESPACE not in namespaces:
            print(f"Error: Namespace '{NAMESPACE}' does not exist.")
            sys.exit(1)
    except Exception as e:
        print(f"Error checking namespaces: {e}")
        sys.exit(1)

    tables = {}
    for table_name in [FEATURES_TABLE, SOURCES_TABLE, RELATIONSHIPS_TABLE]:
        table_identifier = f"{NAMESPACE}.{table_name}"
        try:
            tables[table_name] = catalog.load_table(table_identifier)
        except NoSuchTableError:
            print(f"Error: Table '{table_identifier}' does not exist.")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading table {table_identifier}: {e}")
            sys.exit(1)

    return tables


def open_gff3_file(file_path):
    """Open a GFF3 file, handling local files, S3 URIs, and gzip."""
    if file_path.startswith('s3://'):
        bucket, key = parse_s3_uri(file_path)
        s3_client = boto3.client('s3')
        response = s3_client.get_object(Bucket=bucket, Key=key)
        if file_path.endswith('.gz'):
            return TextIOWrapper(gzip.GzipFile(fileobj=response['Body']))
        else:
            return TextIOWrapper(response['Body'])
    else:
        if file_path.endswith('.gz'):
            return gzip.open(file_path, 'rt')
        else:
            return open(file_path, 'r')


# Reserved GFF3 attributes that get extracted into dedicated columns
RESERVED_ATTRIBUTES = {'ID', 'Name', 'Parent', 'Dbxref', 'Ontology_term', 'Is_circular'}


def parse_gff3_attributes(attr_str):
    """Parse GFF3 column 9 attributes with URL-decoding.

    Returns a dict of all attributes. Reserved keys are included
    so callers can extract them before storing the remainder.
    """
    if attr_str == '.' or not attr_str.strip():
        return {}

    attrs = {}
    for item in attr_str.split(';'):
        item = item.strip()
        if not item:
            continue
        if '=' in item:
            key, value = item.split('=', 1)
            attrs[unquote(key)] = unquote(value)
        else:
            attrs[unquote(item)] = 'true'
    return attrs


def parse_gff3_header(gff3_file):
    """Parse GFF3 header directives. Returns (directives, first_data_line).

    directives is a list of (key, value) tuples for ## lines.
    first_data_line is the first non-comment, non-empty line (or None).
    """
    directives = []
    first_data_line = None

    for line in gff3_file:
        line = line.rstrip('\n\r')
        if not line or line.startswith('###'):
            continue
        if line.startswith('##'):
            parts = line[2:].strip().split(None, 1)
            key = parts[0] if parts else ''
            value = parts[1] if len(parts) > 1 else ''
            directives.append((key, value))
            continue
        if line.startswith('#'):
            continue
        # First data line
        first_data_line = line
        break

    return directives, first_data_line


def process_gff3_batch(batch_lines):
    """Process a batch of GFF3 data lines.

    Returns dicts of PyArrow arrays for features and feature_relationships,
    plus a set of source names encountered.
    """
    # Features columns
    feature_id_list = []
    seqid_list = []
    source_list = []
    type_list = []
    start_list = []
    end_list = []
    score_list = []
    strand_list = []
    phase_list = []
    name_list = []
    dbxref_list = []
    ontology_term_list = []
    is_circular_list = []
    attributes_list = []

    # Relationships columns
    rel_child_id_list = []
    rel_parent_id_list = []
    rel_seqid_list = []
    rel_child_type_list = []
    rel_parent_type_list = []

    # Track sources and parent types for relationship enrichment
    sources_seen = set()
    feature_types = {}  # feature_id -> type, built during this batch

    for line in batch_lines:
        fields = line.split('\t')
        if len(fields) < 9:
            print(f"Warning: Skipping malformed GFF3 line (< 9 fields): {line[:80]}")
            continue

        seqid = unquote(fields[0])
        source = unquote(fields[1])
        feat_type = unquote(fields[2])

        try:
            start = int(fields[3])
            end = int(fields[4])
        except ValueError:
            print(f"Warning: Invalid start/end in GFF3 line: {line[:80]}")
            continue

        score = None
        if fields[5] != '.':
            try:
                score = float(fields[5])
            except ValueError:
                pass

        strand = fields[6] if fields[6] != '.' else None
        phase = fields[7] if fields[7] != '.' else None

        # Parse attributes
        attrs = parse_gff3_attributes(fields[8])

        feature_id = attrs.get('ID', f"{seqid}:{feat_type}:{start}-{end}")
        name = attrs.get('Name')
        parent_str = attrs.get('Parent')
        dbxref = attrs.get('Dbxref')
        ontology_term = attrs.get('Ontology_term')
        is_circular = attrs.get('Is_circular', '').lower() == 'true' if 'Is_circular' in attrs else None

        # Build remaining attributes map (exclude reserved keys)
        remaining_attrs = {k: v for k, v in attrs.items() if k not in RESERVED_ATTRIBUTES}

        # Track
        sources_seen.add(source)
        feature_types[feature_id] = feat_type

        # Append feature data
        feature_id_list.append(feature_id)
        seqid_list.append(seqid)
        source_list.append(source)
        type_list.append(feat_type)
        start_list.append(start)
        end_list.append(end)
        score_list.append(score)
        strand_list.append(strand)
        phase_list.append(phase)
        name_list.append(name)
        dbxref_list.append(dbxref)
        ontology_term_list.append(ontology_term)
        is_circular_list.append(is_circular)
        attributes_list.append(remaining_attrs)

        # Build relationship rows (one per parent)
        if parent_str:
            parent_ids = [p.strip() for p in parent_str.split(',')]
            for pid in parent_ids:
                rel_child_id_list.append(feature_id)
                rel_parent_id_list.append(pid)
                rel_seqid_list.append(seqid)
                rel_child_type_list.append(feat_type)
                rel_parent_type_list.append(feature_types.get(pid))

    # Convert to PyArrow arrays
    features_arrays = {
        'feature_id': pa.array(feature_id_list, type=pa.string()),
        'seqid': pa.array(seqid_list, type=pa.string()),
        'source': pa.array(source_list, type=pa.string()),
        'type': pa.array(type_list, type=pa.string()),
        'start': pa.array(start_list, type=pa.int64()),
        'end': pa.array(end_list, type=pa.int64()),
        'score': pa.array(score_list, type=pa.float64()),
        'strand': pa.array(strand_list, type=pa.string()),
        'phase': pa.array(phase_list, type=pa.string()),
        'name': pa.array(name_list, type=pa.string()),
        'dbxref': pa.array(dbxref_list, type=pa.string()),
        'ontology_term': pa.array(ontology_term_list, type=pa.string()),
        'is_circular': pa.array(is_circular_list, type=pa.bool_()),
        'attributes': pa.array(
            [{str(k): str(v) for k, v in d.items()} for d in attributes_list],
            type=pa.map_(pa.string(), pa.string())),
    }

    relationships_arrays = None
    if rel_child_id_list:
        relationships_arrays = {
            'child_id': pa.array(rel_child_id_list, type=pa.string()),
            'parent_id': pa.array(rel_parent_id_list, type=pa.string()),
            'seqid': pa.array(rel_seqid_list, type=pa.string()),
            'child_type': pa.array(rel_child_type_list, type=pa.string()),
            'parent_type': pa.array(rel_parent_type_list, type=pa.string()),
        }

    return features_arrays, relationships_arrays, sources_seen


def write_to_iceberg(table, data_arrays, pyarrow_schema, table_name):
    """Write data arrays to an Iceberg table with retry logic."""
    columns = [data_arrays[field.name] for field in pyarrow_schema]
    arrow_table = pa.Table.from_arrays(columns, schema=pyarrow_schema)

    print(f"Writing {len(arrow_table)} rows to {NAMESPACE}.{table_name}...")

    def is_commit_failed(e):
        return "CommitFailedException" in str(e) and "branch main has changed" in str(e)

    retry_operation(
        table.append,
        arrow_table,
        max_retries=5,
        retry_condition=is_commit_failed,
    )
    print(f"Successfully wrote {len(arrow_table)} rows to {NAMESPACE}.{table_name}")


def process_gff3_file(gff3_path, tables=None, pyarrow_schemas=None):
    """Process a GFF3 file in batches and write to Iceberg tables."""
    print(f"Processing GFF3 file: {gff3_path}")

    all_sources = set()

    with open_gff3_file(gff3_path) as gff3_file:
        directives, first_line = parse_gff3_header(gff3_file)

        # Log directives
        for key, value in directives:
            print(f"  Directive: ##{key} {value}")

        # Process data lines in batches
        batch_lines = []
        if first_line:
            batch_lines.append(first_line)

        records_processed = 0

        for line in gff3_file:
            line = line.rstrip('\n\r')
            if not line or line.startswith('#'):
                continue
            # FASTA section terminates GFF3 features
            if line.startswith('>'):
                break

            batch_lines.append(line)

            if len(batch_lines) >= BATCH_SIZE:
                feat_arrays, rel_arrays, sources = process_gff3_batch(batch_lines)
                all_sources.update(sources)

                if tables and pyarrow_schemas:
                    write_to_iceberg(tables[FEATURES_TABLE], feat_arrays,
                                     pyarrow_schemas[FEATURES_TABLE], FEATURES_TABLE)
                    if rel_arrays:
                        write_to_iceberg(tables[RELATIONSHIPS_TABLE], rel_arrays,
                                         pyarrow_schemas[RELATIONSHIPS_TABLE], RELATIONSHIPS_TABLE)

                records_processed += len(batch_lines)
                print(f"Processed {records_processed} records so far...")
                batch_lines = []

        # Remaining records
        if batch_lines:
            feat_arrays, rel_arrays, sources = process_gff3_batch(batch_lines)
            all_sources.update(sources)

            if tables and pyarrow_schemas:
                write_to_iceberg(tables[FEATURES_TABLE], feat_arrays,
                                 pyarrow_schemas[FEATURES_TABLE], FEATURES_TABLE)
                if rel_arrays:
                    write_to_iceberg(tables[RELATIONSHIPS_TABLE], rel_arrays,
                                     pyarrow_schemas[RELATIONSHIPS_TABLE], RELATIONSHIPS_TABLE)

            records_processed += len(batch_lines)

        # Write sources
        if all_sources and tables and pyarrow_schemas:
            sources_arrays = {
                'source_name': pa.array(sorted(all_sources), type=pa.string()),
                'description': pa.array([None] * len(all_sources), type=pa.string()),
            }
            write_to_iceberg(tables[SOURCES_TABLE], sources_arrays,
                             pyarrow_schemas[SOURCES_TABLE], SOURCES_TABLE)

        print(f"Processed {records_processed} records total from {gff3_path}")


def main():
    global bucket_arn, NAMESPACE, BATCH_SIZE

    parser = argparse.ArgumentParser(description='Load GFF3 files into Iceberg tables (Schema 1)')
    parser.add_argument('gff3_files', nargs='+', help='GFF3 file paths to load (local or s3://)')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    parser.add_argument('--namespace', default=NAMESPACE, help=f'Iceberg namespace (default: {NAMESPACE})')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                        help=f'Records per batch (default: {BATCH_SIZE})')
    args = parser.parse_args()

    bucket_arn = args.bucket_arn
    NAMESPACE = args.namespace
    BATCH_SIZE = args.batch_size

    print("Getting tables...")
    tables = get_tables()
    pyarrow_schemas = {
        table_name: table.schema().as_arrow()
        for table_name, table in tables.items()
    }

    for gff3_file in args.gff3_files:
        file_exists = True
        if gff3_file.startswith('s3://'):
            try:
                bucket, key = parse_s3_uri(gff3_file)
                s3_client = boto3.client('s3')
                s3_client.head_object(Bucket=bucket, Key=key)
            except Exception as e:
                file_exists = False
                print(f"Error: S3 file not found: {gff3_file} — {e}")
        else:
            file_exists = os.path.exists(gff3_file)
            if not file_exists:
                print(f"Error: Local file not found: {gff3_file}")

        if not file_exists:
            continue

        try:
            process_gff3_file(gff3_file, tables, pyarrow_schemas)
        except Exception as e:
            print(f"Error processing file {gff3_file}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
