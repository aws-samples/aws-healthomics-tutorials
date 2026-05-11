"""
Schema 2: Denormalized schema for GFF3 annotation data.

Single table in namespace `annotation_db_2`:

1. genomic_annotations - All feature data with parent info embedded

Partitioning:
  - by seqid (chromosome) and type_bucket (128 buckets on feature type)
  - sorted by start position

This design favors fast single-region queries without joins. Parent IDs are
stored as a list directly on each feature row. Trade-off is that source
metadata is duplicated across rows.
"""

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
    ListType,
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.transforms import IdentityTransform, BucketTransform
from pyiceberg.table.sorting import (
    SortOrder, SortField, SortDirection, NullOrder
)
from utils import create_table, load_s3_tables_catalog


genomic_annotations_schema: Schema = Schema(
    NestedField(1, "feature_id", StringType(), required=True,
                doc="GFF3 ID attribute — unique identifier for this feature"),
    NestedField(2, "seqid", StringType(), required=True,
                doc="Landmark / chromosome identifier (GFF3 column 1)"),
    NestedField(3, "source", StringType(), required=True,
                doc="Source of the annotation (GFF3 column 2)"),
    NestedField(4, "type", StringType(), required=True,
                doc="Feature type / SO term (GFF3 column 3)"),
    NestedField(5, "start", LongType(), required=True,
                doc="Start position, 1-based inclusive (GFF3 column 4)"),
    NestedField(6, "end", LongType(), required=True,
                doc="End position, 1-based inclusive (GFF3 column 5)"),
    NestedField(7, "score", DoubleType(),
                doc="Score value (GFF3 column 6), null if '.'"),
    NestedField(8, "strand", StringType(),
                doc="Strand: +, -, ., or ? (GFF3 column 7)"),
    NestedField(9, "phase", StringType(),
                doc="CDS phase: 0, 1, 2, or . (GFF3 column 8)"),
    NestedField(10, "name", StringType(),
                doc="GFF3 Name attribute — display name"),
    NestedField(11, "parent_ids", ListType(element_id=1000,
                                           element_type=StringType(),
                                           element_required=True),
                doc="GFF3 Parent attribute — list of parent feature IDs"),
    NestedField(12, "dbxref", StringType(),
                doc="GFF3 Dbxref attribute — database cross-references (comma-separated)"),
    NestedField(13, "ontology_term", StringType(),
                doc="GFF3 Ontology_term attribute (comma-separated)"),
    NestedField(14, "is_circular", BooleanType(),
                doc="GFF3 Is_circular attribute"),
    NestedField(15, "attributes", MapType(key_id=16,
                                          value_id=17,
                                          key_type=StringType(),
                                          value_type=StringType()),
                doc="All remaining GFF3 column 9 attributes as key-value pairs"),
    identifier_field_ids=[1, 2, 4, 5]
)

genomic_annotations_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=2,
                   field_id=1001,
                   transform=IdentityTransform(),
                   name="seqid"),
    PartitionField(source_id=4,
                   field_id=1002,
                   transform=BucketTransform(128),
                   name="type_bucket"),
)

genomic_annotations_sort_order: SortOrder = SortOrder(
    SortField(source_id=2,
              transform=IdentityTransform(),
              direction=SortDirection.ASC,
              null_order=NullOrder.NULLS_LAST),
    SortField(source_id=5,
              transform=IdentityTransform(),
              direction=SortDirection.ASC,
              null_order=NullOrder.NULLS_LAST),
)


def create_schema_tables(catalog: Catalog, namespace: str) -> Dict[str, Table]:
    table_name = "genomic_annotations"

    print(f"Creating tables in namespace {namespace} ...")
    print(f"Creating {table_name}")
    genomic_annotations: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name,
        schema=genomic_annotations_schema,
        partition_spec=genomic_annotations_partition_spec,
        sort_order=genomic_annotations_sort_order)
    print(f"Created {genomic_annotations}")

    return {
        table_name: genomic_annotations,
    }


def main():
    import argparse
    from utils import create_namespace

    parser = argparse.ArgumentParser(
        description='Create Iceberg table for GFF3 annotation data (Schema 2 — denormalized)')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    args = parser.parse_args()

    print("Connecting to catalog ...")
    catalog = load_s3_tables_catalog(args.bucket_arn)
    print("Connected to catalog")

    namespace = "annotation_db_2"
    print("Creating namespace ...")
    create_namespace(catalog, namespace)
    print("Namespace created")

    print("Creating tables ...")
    create_schema_tables(catalog, namespace)
    print("Tables created")
    print("Done")


if __name__ == "__main__":
    main()
