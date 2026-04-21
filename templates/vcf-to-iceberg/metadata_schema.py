from typing import Dict
from pyiceberg.catalog import Catalog
from pyiceberg.schema import Schema
from pyiceberg.table import Table
from pyiceberg.types import (
    NestedField,
    StringType,
    LongType,
    DoubleType,
    MapType,
    BooleanType,
    UUIDType
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.transforms import YearTransform, IdentityTransform, BucketTransform
from pyiceberg.table.sorting import (
    SortOrder, SortField, SortDirection, NullOrder
)
from utils import create_table, load_s3_tables_catalog

# -- VCF Files table
# CREATE TABLE vcf_files (
#   file_id BIGINT,
#   file_name STRING,
#   file_format STRING,
#   created_at TIMESTAMP
# )

vcf_files_schema: Schema = Schema(
    NestedField(1, "file_id", UUIDType(), required=True),
    NestedField(2, "file_name", StringType(), required=True),
    NestedField(3, "file_format", StringType(), required=True),
    NestedField(4, "created_at", LongType(), required=True),
)
vcf_files_sort_order: SortOrder = SortOrder(
    # sort by file_name
    SortField(source_id=2,
              transform=IdentityTransform(),
              direction=SortDirection.ASC,
              null_order=NullOrder.NULLS_LAST),
)

# -- Contigs table
# CREATE TABLE contigs (
#   contig_id BIGINT,
#   file_id BIGINT,
#   name STRING,
#   length BIGINT
# ) USING iceberg
# PARTITIONED BY (file_id)

contigs_schema: Schema = Schema(
    NestedField(1, "contig_id", UUIDType(), required=True),
    NestedField(2, "file_id", UUIDType(), required=True),
    NestedField(3, "name", StringType(), required=True),
    NestedField(4, "length", LongType(), required=True),
)
contigs_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=2,
                   field_id=100,
                   transform=BucketTransform(16),
                   name="file_id_bucket"),
)

# -- Filters table
# CREATE TABLE filters (
#   filter_id BIGINT,
#   file_id BIGINT,
#   name STRING,
#   description STRING
# ) USING iceberg
# PARTITIONED BY (file_id)
# TBLPROPERTIES (
#   'format-version' = '2',
#   'write.format.default' = 'parquet',
#   'write.parquet.compression-codec' = 'snappy'
# );
filters_schema: Schema = Schema(
    NestedField(1, "filter_id", UUIDType(), required=True),
    NestedField(2, "file_id", UUIDType(), required=True),
    NestedField(3, "name", StringType(), required=True),
    NestedField(4, "description", StringType()),
)
filters_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=2,
                   field_id=100,
                   transform=BucketTransform(16),
                   name="file_id_bucket"),
)

# -- INFO fields table
# CREATE TABLE info_fields (
#   info_id BIGINT,
#   file_id BIGINT,
#   name STRING,
#   number_type STRING,
#   value_type STRING,
#   description STRING
# ) USING iceberg
# PARTITIONED BY (file_id)
# TBLPROPERTIES (
#   'format-version' = '2',
#   'write.format.default' = 'parquet',
#   'write.parquet.compression-codec' = 'snappy'
# );
info_fields_schema: Schema = Schema(
    NestedField(1, "info_id", UUIDType(), required=True),
    NestedField(2, "file_id", UUIDType(), required=True),
    NestedField(3, "name", StringType(), required=True),
    NestedField(4, "number_type", StringType()),
    NestedField(5, "value_type", StringType(), required=True),
    NestedField(6, "description", StringType()),
)
info_fields_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=2,
                   field_id=100,
                   transform=BucketTransform(16),
                   name="file_id_bucket"),
)

# -- FORMAT fields table
# CREATE TABLE format_fields (
#   format_id BIGINT,
#   file_id BIGINT,
#   name STRING,
#   number_type STRING,
#   value_type STRING,
#   description STRING
# ) USING iceberg
# PARTITIONED BY (file_id)
# TBLPROPERTIES (
#   'format-version' = '2',
#   'write.format.default' = 'parquet',
#   'write.parquet.compression-codec' = 'snappy'
# );
format_fields_schema: Schema = Schema(
    NestedField(1, "format_id", UUIDType(), required=True),
    NestedField(2, "file_id", UUIDType(), required=True),
    NestedField(3, "name", StringType(), required=True),
    NestedField(4, "number_type", StringType()),
    NestedField(5, "value_type", StringType(), required=True),
    NestedField(6, "description", StringType()),
)
format_fields_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=2,
                   field_id=100,
                   transform=BucketTransform(16),
                   name="file_id_bucket"),
)

# -- Samples table
# CREATE TABLE samples (
#   sample_id BIGINT,
#   file_id BIGINT,
#   name STRING,
#   position INT
# ) USING iceberg
# PARTITIONED BY (file_id)

samples_schema: Schema = Schema(
    NestedField(1, "sample_id", UUIDType(), required=True),
    NestedField(2, "file_id", UUIDType(), required=True),
    NestedField(3, "name", StringType(), required=True),
    NestedField(4, "position", LongType(), required=True,
                doc='the ordinal of the sample in the file'),
)
samples_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=2,
                   field_id=100,
                   transform=BucketTransform(16),
                   name="file_id_bucket"),
)

# -- Header metadata table
# CREATE TABLE header_metadata (
#   metadata_id BIGINT,
#   file_id BIGINT,
#   meta_key STRING,
#   meta_value STRING
# ) USING iceberg
# PARTITIONED BY (file_id)
# TBLPROPERTIES (
#   'format-version' = '2',
#   'write.format.default' = 'parquet',
#   'write.parquet.compression-codec' = 'snappy'
# );

header_metadata_schema: Schema = Schema(
    NestedField(1, "metadata_id", UUIDType(), required=True),
    NestedField(2, "file_id", UUIDType(), required=True),
    NestedField(3, "meta_key", StringType(), required=True),
    NestedField(4, "meta_value", StringType(), required=True),
)
header_metadata_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=2,
                   field_id=100,
                   transform=BucketTransform(16),
                   name="file_id_bucket"),
)


def create_schema_tables(catalog: Catalog, namespace: str) -> Dict[str, Table]:
    table_name_vcf_files: str = "vcf_files"
    table_name_contigs: str = "contigs"
    table_name_filters: str = "filters"
    table_name_info_fields: str = "info_fields"
    table_name_format_fields: str = "format_fields"
    table_name_samples: str = "samples"
    table_name_header_metadata: str = "header_metadata"

    print(f"Creating tables in namespace {namespace} ...")
    print(f"Creating {table_name_vcf_files}")
    vcf_files: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_vcf_files,
        schema=vcf_files_schema,
        partition_spec=None,
        sort_order=vcf_files_sort_order)
    print(f"Created {vcf_files}")

    print(f"Creating {table_name_contigs}")
    contigs: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_contigs,
        schema=contigs_schema,
        partition_spec=contigs_partition_spec,
        sort_order=None)
    print(f"Created {contigs}")

    print(f"Creating {table_name_filters}")
    filters: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_filters,
        schema=filters_schema,
        partition_spec=filters_partition_spec,
        sort_order=None)
    print(f"Created {filters}")

    print(f"Creating {table_name_info_fields}")
    info_fields: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_info_fields,
        schema=info_fields_schema,
        partition_spec=info_fields_partition_spec,
        sort_order=None)
    print(f"Created {info_fields}")

    print(f"Creating {table_name_format_fields}")
    format_fields: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_format_fields,
        schema=format_fields_schema,
        partition_spec=format_fields_partition_spec,
        sort_order=None)
    print(f"Created {format_fields}")

    print(f"Creating {table_name_samples}")
    samples: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_samples,
        schema=samples_schema,
        partition_spec=samples_partition_spec,
        sort_order=None)
    print(f"Created {samples}")

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
        table_name_vcf_files: vcf_files,
        table_name_contigs: contigs,
        table_name_filters: filters,
        table_name_info_fields: info_fields,
        table_name_format_fields: format_fields,
        table_name_samples: samples,
        table_name_header_metadata: header_metadata
    }


def main():
    from utils import create_namespace
    import os
    import argparse

    # Set up command line argument parsing
    parser = argparse.ArgumentParser()
    parser.add_argument('--bucket-arn', help='S3 bucket ARN')
    parser.add_argument('--namespace', help='Namespace for tables')
    args = parser.parse_args()

    # Get values from command line args or environment variables
    bucket_arn = args.bucket_arn or os.environ.get('BUCKET_ARN')
    namespace = args.namespace or os.environ.get('NAMESPACE')

    if not bucket_arn:
        raise ValueError("bucket_arn must be provided via --bucket-arn argument or BUCKET_ARN environment variable")
    if not namespace:
        raise ValueError("namespace must be provided via --namespace argument or NAMESPACE environment variable")

    print("Connecting to catalog ...")
    catalog = load_s3_tables_catalog(bucket_arn)
    print("Connected to catalog")

    print("Creating namespace ...")
    create_namespace(catalog, namespace)
    print("Namespace created")

    print("Creating tables ...")
    create_schema_tables(catalog, namespace)
    print("Tables created")
    print("Done")


if __name__ == "__main__":
    main()
