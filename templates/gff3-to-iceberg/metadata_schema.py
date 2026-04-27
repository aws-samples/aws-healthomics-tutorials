"""
Metadata schema for GFF3 file-level directives and pragmas.

Captures GFF3 header information:
  - gff_files: Tracks loaded GFF3 files
  - sequence_regions: ##sequence-region directives
  - header_metadata: All other ## directives (species, genome-build, etc.)
"""

from typing import Dict
from pyiceberg.catalog import Catalog
from pyiceberg.schema import Schema
from pyiceberg.table import Table
from pyiceberg.types import (
    NestedField,
    StringType,
    LongType,
    UUIDType,
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.transforms import BucketTransform
from pyiceberg.table.sorting import (
    SortOrder, SortField, SortDirection, NullOrder
)
from pyiceberg.transforms import IdentityTransform
from utils import create_table, load_s3_tables_catalog


# ─── gff_files table ──────────────────────────────────────────────────────────

gff_files_schema: Schema = Schema(
    NestedField(1, "file_id", UUIDType(), required=True),
    NestedField(2, "file_name", StringType(), required=True),
    NestedField(3, "gff_version", StringType(),
                doc="GFF version from ##gff-version directive"),
    NestedField(4, "created_at", LongType(), required=True,
                doc="Epoch millis when the file was loaded"),
)

gff_files_sort_order: SortOrder = SortOrder(
    SortField(source_id=2,
              transform=IdentityTransform(),
              direction=SortDirection.ASC,
              null_order=NullOrder.NULLS_LAST),
)


# ─── sequence_regions table ───────────────────────────────────────────────────
# From ##sequence-region seqid start end

sequence_regions_schema: Schema = Schema(
    NestedField(1, "region_id", UUIDType(), required=True),
    NestedField(2, "file_id", UUIDType(), required=True),
    NestedField(3, "seqid", StringType(), required=True),
    NestedField(4, "start", LongType(), required=True),
    NestedField(5, "end", LongType(), required=True),
)

sequence_regions_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=2,
                   field_id=100,
                   transform=BucketTransform(16),
                   name="file_id_bucket"),
)


# ─── header_metadata table ────────────────────────────────────────────────────
# All other ## directives: ##species, ##genome-build, etc.

header_metadata_schema: Schema = Schema(
    NestedField(1, "metadata_id", UUIDType(), required=True),
    NestedField(2, "file_id", UUIDType(), required=True),
    NestedField(3, "directive", StringType(), required=True,
                doc="Directive name (e.g., species, genome-build)"),
    NestedField(4, "value", StringType(), required=True,
                doc="Directive value"),
)

header_metadata_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=2,
                   field_id=100,
                   transform=BucketTransform(16),
                   name="file_id_bucket"),
)


def create_schema_tables(catalog: Catalog, namespace: str) -> Dict[str, Table]:
    table_name_gff_files = "gff_files"
    table_name_sequence_regions = "sequence_regions"
    table_name_header_metadata = "header_metadata"

    print(f"Creating metadata tables in namespace {namespace} ...")

    print(f"Creating {table_name_gff_files}")
    gff_files: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_gff_files,
        schema=gff_files_schema,
        partition_spec=None,
        sort_order=gff_files_sort_order)
    print(f"Created {gff_files}")

    print(f"Creating {table_name_sequence_regions}")
    sequence_regions: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_sequence_regions,
        schema=sequence_regions_schema,
        partition_spec=sequence_regions_partition_spec,
        sort_order=None)
    print(f"Created {sequence_regions}")

    print(f"Creating {table_name_header_metadata}")
    header_metadata: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_header_metadata,
        schema=header_metadata_schema,
        partition_spec=header_metadata_partition_spec,
        sort_order=None)
    print(f"Created {header_metadata}")

    return {
        table_name_gff_files: gff_files,
        table_name_sequence_regions: sequence_regions,
        table_name_header_metadata: header_metadata,
    }


def main():
    from utils import create_namespace
    import argparse

    parser = argparse.ArgumentParser(
        description='Create metadata tables for GFF3 annotation data')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    parser.add_argument('--namespace', required=True, help='Namespace for tables')
    args = parser.parse_args()

    print("Connecting to catalog ...")
    catalog = load_s3_tables_catalog(args.bucket_arn)
    print("Connected to catalog")

    print("Creating namespace ...")
    create_namespace(catalog, args.namespace)
    print("Namespace created")

    print("Creating tables ...")
    create_schema_tables(catalog, args.namespace)
    print("Tables created")
    print("Done")


if __name__ == "__main__":
    main()
