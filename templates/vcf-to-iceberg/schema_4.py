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
    BooleanType
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.transforms import IdentityTransform, BucketTransform

from utils import create_table, load_s3_tables_catalog
import time

# CREATE TABLE samples (
#   sample_id UUID,
#   sample_name STRING NOT NULL,
#   PRIMARY KEY (sample_id)
# )
samples_schema: Schema = Schema(
    NestedField(1, "sample_id", StringType(), required=True),
    NestedField(2, "sample_name", StringType(), required=True),
)

# CREATE TABLE variants (
#   variant_id UUID,
#   chrom STRING NOT NULL,
#   pos BIGINT NOT NULL,
#   vcf_id STRING,
#   ref STRING NOT NULL,
#   alt STRING NOT NULL,
#   qual DOUBLE,
#   filter STRING,
#   info MAP<STRING, STRING>,
#   PRIMARY KEY (variant_id)
# )
variants_schema: Schema = Schema(
    NestedField(1, "variant_id", StringType(), required=True),
    NestedField(2, "chrom", StringType(), required=True),
    NestedField(3, "pos", LongType(), required=True),
    NestedField(4, "vcf_id", StringType()),
    NestedField(5, "ref", StringType(), required=True),
    NestedField(6, "alt", StringType(), required=True),
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
                   name="chrom"),
    PartitionField(source_id=3,
                   field_id=1001,
                   transform=BucketTransform(128),
                   name="pos_bucket")
)

# CREATE TABLE variant_samples (
#   variant_id UUID NOT NULL,
#   sample_id UUID NOT NULL,
#   chrom STRING NOT NULL,
#   pos INT NOT NULL,
#   genotype STRING NOT NULL,
#   attributes MAP<STRING, STRING>,
#   is_reference_block BOOLEAN,
# )
variant_samples_schema: Schema = Schema(
    NestedField(1, "variant_id", StringType(), required=True),
    NestedField(2, "sample_id", StringType(), required=True),
    NestedField(3, "chrom", StringType(), required=True),
    NestedField(4, "pos", LongType(), required=True),
    NestedField(5, "genotype", StringType(), required=True),
    NestedField(6, "attributes", MapType(key_id=7,
                                         value_id=8,
                                         key_type=StringType(),
                                         value_type=StringType())),
    NestedField(9, "is_reference_block", BooleanType(),
                doc='Used in GVCF for non-variant sites'),
)
variant_samples_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=3,
                   field_id=1000,
                   transform=IdentityTransform(),
                   name="chrom"),
    PartitionField(source_id=4,
                   field_id=1001,
                   transform=BucketTransform(128),
                   name="pos_bucket"),
)


def create_schema_tables(catalog: Catalog, namespace: str) -> Dict[str, Table]:
    table_name_samples: str = "samples"
    table_name_variants: str = "variants"
    table_name_variant_samples: str = "variant_samples"

    print(f"Creating tables in namespace {namespace} ...")
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

    print(f"Creating {table_name_variants}")
    variants: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_variants,
        schema=variants_schema,
        partition_spec=variants_partition_spec,
        sort_order=None)
    print(f"Created {variants}")
    # sleep for 3 seconds to allow the table to be created
    time.sleep(3)

    print(f"Creating {table_name_variant_samples}")
    variant_samples: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_variant_samples,
        schema=variant_samples_schema,
        partition_spec=variant_samples_partition_spec,
        sort_order=None)
    print(f"Created {variant_samples}")

    return {
        table_name_variants: variants,
        table_name_samples: samples,
        table_name_variant_samples: variant_samples
    }


def main():
    import argparse
    from utils import create_namespace

    parser = argparse.ArgumentParser(description='Create Iceberg tables for genomic variant data (Schema 4)')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    args = parser.parse_args()

    print("Connecting to catalog ...")
    catalog = load_s3_tables_catalog(args.bucket_arn)
    print("Connected to catalog")

    print("Creating namespace ...")
    namespace: str = "variant_db_4"
    create_namespace(catalog, namespace)
    print("Namespace created")

    print("Creating tables ...")
    create_schema_tables(catalog, namespace)
    print("Tables created")


if __name__ == "__main__":
    main()
