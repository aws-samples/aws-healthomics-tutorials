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
from pyiceberg.transforms import IdentityTransform, BucketTransform
from pyiceberg.table.sorting import (
    SortOrder, SortField, SortDirection, NullOrder
)
from utils import create_table, load_s3_tables_catalog
import time

# CREATE TABLE variants (
#     variant_id UUID,
#     chrom STRING,
#     pos BIGINT,
#     vcf_id STRING,
#     ref STRING,
#     alt STRING,
#     qual DOUBLE,
#     filter STRING,
#     info MAP<STRING, STRING>
# )

variants_schema: Schema = Schema(
    # NestedField(1, "variant_id", UUIDType(), required=True),
    NestedField(1, "variant_id", StringType(), required=True),
    NestedField(2, "chrom", StringType()),
    NestedField(3, "pos", LongType()),
    NestedField(4, "vcf_id", StringType()),
    NestedField(5, "ref", StringType()),
    NestedField(6, "alt", StringType()),
    NestedField(7, "qual", DoubleType()),
    NestedField(8, "filter", StringType()),
    NestedField(9, "info", MapType(key_id=10,
                                   value_id=11,
                                   key_type=StringType(),
                                   value_type=StringType())),
)

variants_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=2,
                   field_id=1000,
                   transform=IdentityTransform(),
                   name="chrom")
)

variants_sort_order: SortOrder = SortOrder(
    # sort by position
    SortField(source_id=3,
              transform=IdentityTransform(),
              direction=SortDirection.ASC,
              null_order=NullOrder.NULLS_LAST)
)

# CREATE TABLE samples (
#     sample_id UUID,
#     sample_name STRING,
# )
samples_schema: Schema = Schema(
    # NestedField(1, "sample_id", UUIDType(), required=True),
    NestedField(1, "sample_id", StringType(), required=True),
    NestedField(2, "sample_name", StringType()),
)

# -- Create the VariantSamples table (junction table)
# CREATE TABLE variant_samples (
#     variant_id UUID,
#     sample_id UUID,
#     genotype STRING,
#     attributes MAP<STRING, STRING>,
#     is_reference_block BOOLEAN       -- Used in GVCF for non-variant sites
# )
variant_samples_schema: Schema = Schema(
    # NestedField(1, "variant_id", UUIDType(), required=True),
    # NestedField(2, "sample_id", UUIDType(), required=True),
    NestedField(1, "variant_id", StringType(), required=True),
    NestedField(2, "sample_id", StringType(), required=True),
    NestedField(3, "genotype", StringType()),
    NestedField(4, "attributes", MapType(key_id=5,
                                         value_id=6,
                                         key_type=StringType(),
                                         value_type=StringType())),
    NestedField(5, "is_reference_block", BooleanType(),
                doc='Used in GVCF for non-variant sites'),
)
variant_samples_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=1,
                   field_id=1000,
                   transform=BucketTransform(32),
                   name="variant_id_bucket")
)
variant_samples_sort_order: SortOrder = SortOrder(
    # sort by sample_id
    SortField(source_id=2,
              transform=IdentityTransform(),
              direction=SortDirection.ASC,
              null_order=NullOrder.NULLS_LAST)
)


def create_schema_tables(catalog: Catalog, namespace: str) -> Dict[str, Table]:
    table_name_variants: str = "variants"
    table_name_samples: str = "samples"
    table_name_variant_samples: str = "variant_samples"

    print(f"Creating tables in namespace {namespace} ...")
    print(f"Creating {table_name_variants}")
    variants: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_variants,
        schema=variants_schema,
        partition_spec=variants_partition_spec,
        sort_order=variants_sort_order)
    print(f"Created {variants}")

    # sleep for 3 seconds to allow the table to be created
    time.sleep(3)

    print(f"Creating {table_name_samples}")
    samples: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_samples,
        schema=samples_schema,
        partition_spec=None,
        sort_order=None)
    print(f"Created {samples}")

    # sleep for 3 seconds to allow the table to be created
    time.sleep(3)

    print(f"Creating {table_name_variant_samples}")
    variant_samples: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_variant_samples,
        schema=variant_samples_schema,
        partition_spec=variant_samples_partition_spec,
        sort_order=variant_samples_sort_order)
    print(f"Created {variant_samples}")

    # sleep for 3 seconds to allow the table to be created
    time.sleep(3)

    return {
        table_name_variants: variants,
        table_name_samples: samples,
        table_name_variant_samples: variant_samples
    }


def main():
    import argparse
    from utils import create_namespace

    parser = argparse.ArgumentParser(description='Create Iceberg tables for genomic variant data (Schema 1)')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    args = parser.parse_args()

    print("Connecting to catalog ...")
    catalog = load_s3_tables_catalog(args.bucket_arn)
    print("Connected to catalog")

    print("Creating namespace ...")
    namespace: str = "variant_db"
    create_namespace(catalog, namespace)
    print("Namespace created")

    print("Creating tables ...")
    create_schema_tables(catalog, namespace)
    print("Tables created")


if __name__ == "__main__":
    main()
