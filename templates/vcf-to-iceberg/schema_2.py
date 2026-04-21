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
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.transforms import IdentityTransform, BucketTransform
from pyiceberg.table.sorting import (
    SortOrder, SortField, SortDirection, NullOrder
)
from utils import create_table, load_s3_tables_catalog
import time

# CREATE TABLE samples (
#   sample_id UUID,
#   sample_name STRING NOT NULL,
# )

samples_schema: Schema = Schema(
    NestedField(1, "sample_id", StringType(), required=True),
    NestedField(2, "sample_name", StringType(), required=True),
    NestedField(3, "metadata", MapType(key_id=4,
                                       value_id=5,
                                       key_type=StringType(),
                                       value_type=StringType())),
)

# CREATE TABLE variant_regions (
#   chrom STRING NOT NULL,
#   pos BIGINT NOT NULL,
#   ref STRING NOT NULL,
#   alt STRING NOT NULL,
#   qual DOUBLE,
#   filter STRING,
#   info MAP<STRING, STRING>,
#   sample_ids ARRAY<UUID>,
#   sample_genotypes MAP<UUID, STRING>,
#   is_reference_block BOOLEAN,
# )
variant_regions_schema: Schema = Schema(
    NestedField(1, "chrom", StringType(), required=True),
    NestedField(2, "pos", LongType(), required=True),
    NestedField(4, "ref", StringType(), required=True),
    NestedField(5, "alt", StringType(), required=True),
    NestedField(6, "qual", DoubleType()),
    NestedField(7, "filter", StringType()),
    NestedField(8, "info", MapType(key_id=9,
                                   value_id=10,
                                   key_type=StringType(),
                                   value_type=StringType())),
    NestedField(11, "sample_ids", MapType(key_id=12,
                                          value_id=13,
                                          key_type=StringType(),
                                          value_type=StringType())),
    NestedField(14, "sample_genotypes", MapType(key_id=15,
                                                value_id=16,
                                                key_type=StringType(),
                                                value_type=StringType())),
    NestedField(17, "is_reference_block", BooleanType(),
                doc='Used in GVCF for non-variant sites'),
)
variant_regions_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=1,
                   field_id=1000,
                   transform=IdentityTransform(),
                   name="chrom"),
    PartitionField(source_id=2,
                   field_id=1001,
                   transform=BucketTransform(128),
                   name="pos_bucket"),
)
variant_regions_sort_order: SortOrder = SortOrder(
    # sort by position
    SortField(source_id=2,
              transform=IdentityTransform(),
              direction=SortDirection.ASC,
              null_order=NullOrder.NULLS_LAST),
)


def create_schema_tables(catalog: Catalog, namespace: str) -> Dict[str, Table]:
    table_name_variant_regions: str = "variant_regions"
    table_name_samples: str = "samples"

    print(f"Creating tables in namespace {namespace} ...")
    print(f"Creating {table_name_variant_regions}")
    variant_regions: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_variant_regions,
        schema=variant_regions_schema,
        partition_spec=variant_regions_partition_spec,
        sort_order=variant_regions_sort_order)
    print(f"Created {variant_regions}")

    # sleep for 3 seconds to allow the table to be created
    time.sleep(3)

    print(f"Creating {table_name_samples}")
    samples = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_samples,
        schema=samples_schema,
        partition_spec=None,
        sort_order=None
    )
    print(f"Created {samples}")

    return {
        table_name_variant_regions: variant_regions,
        table_name_samples: samples
    }


def main():
    import argparse
    from utils import create_namespace

    parser = argparse.ArgumentParser(description='Create Iceberg tables for genomic variant data (Schema 2)')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    args = parser.parse_args()

    print("Connecting to catalog ...")
    catalog = load_s3_tables_catalog(args.bucket_arn)
    print("Connected to catalog")

    print("Creating namespace ...")
    namespace: str = "variant_db_2"
    create_namespace(catalog, namespace)
    print("Namespace created")

    print("Creating tables ...")
    create_schema_tables(catalog, namespace)
    print("Tables created")


if __name__ == "__main__":
    main()
