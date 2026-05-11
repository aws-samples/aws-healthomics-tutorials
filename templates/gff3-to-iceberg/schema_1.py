"""
Schema 1: Normalized schema for GFF3 annotation data.

Three tables in namespace `annotation_db`:

1. features       - Core annotation features (gene, mRNA, exon, CDS, etc.)
2. sources        - Annotation sources/programs that produced features
3. feature_relationships - Parent-child relationships between features

Partitioning:
  - features: by seqid (chromosome) and type_bucket (128 buckets on feature type)
  - sources: unpartitioned (small cardinality)
  - feature_relationships: by seqid (chromosome)

This design favors data integrity and minimal redundancy. Joins are required
to traverse the feature hierarchy (gene -> mRNA -> exon/CDS).
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
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.transforms import IdentityTransform, BucketTransform
from pyiceberg.table.sorting import (
    SortOrder, SortField, SortDirection, NullOrder
)
from utils import create_table, load_s3_tables_catalog
import time


# ─── features table ───────────────────────────────────────────────────────────
# One row per GFF3 feature line.
# Reserved GFF3 attributes (ID, Name, Dbxref, Ontology_term, Is_circular)
# are extracted into dedicated columns. Remaining attributes go into the map.

features_schema: Schema = Schema(
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
    NestedField(11, "dbxref", StringType(),
                doc="GFF3 Dbxref attribute — database cross-references (comma-separated)"),
    NestedField(12, "ontology_term", StringType(),
                doc="GFF3 Ontology_term attribute (comma-separated)"),
    NestedField(13, "is_circular", BooleanType(),
                doc="GFF3 Is_circular attribute"),
    NestedField(14, "attributes", MapType(key_id=15,
                                          value_id=16,
                                          key_type=StringType(),
                                          value_type=StringType()),
                doc="All remaining GFF3 column 9 attributes as key-value pairs"),
)

features_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=2,
                   field_id=1000,
                   transform=IdentityTransform(),
                   name="seqid"),
    PartitionField(source_id=4,
                   field_id=1001,
                   transform=BucketTransform(128),
                   name="type_bucket"),
)

features_sort_order: SortOrder = SortOrder(
    SortField(source_id=5,
              transform=IdentityTransform(),
              direction=SortDirection.ASC,
              null_order=NullOrder.NULLS_LAST),
)


# ─── sources table ────────────────────────────────────────────────────────────
# Distinct annotation sources encountered across loaded GFF3 files.

sources_schema: Schema = Schema(
    NestedField(1, "source_name", StringType(), required=True,
                doc="Unique source/program name from GFF3 column 2"),
    NestedField(2, "description", StringType(),
                doc="Optional description of the source"),
)


# ─── feature_relationships table ──────────────────────────────────────────────
# Parent-child edges derived from the GFF3 Parent attribute.
# A feature with Parent=mRNA00001,mRNA00002 produces two rows.

feature_relationships_schema: Schema = Schema(
    NestedField(1, "child_id", StringType(), required=True,
                doc="Feature ID of the child"),
    NestedField(2, "parent_id", StringType(), required=True,
                doc="Feature ID of the parent"),
    NestedField(3, "seqid", StringType(), required=True,
                doc="Chromosome — denormalized for partition-aligned joins"),
    NestedField(4, "child_type", StringType(),
                doc="Feature type of the child (e.g., exon, CDS)"),
    NestedField(5, "parent_type", StringType(),
                doc="Feature type of the parent (e.g., gene, mRNA)"),
)

feature_relationships_partition_spec: PartitionSpec = PartitionSpec(
    PartitionField(source_id=3,
                   field_id=1000,
                   transform=IdentityTransform(),
                   name="seqid"),
)

feature_relationships_sort_order: SortOrder = SortOrder(
    SortField(source_id=2,
              transform=IdentityTransform(),
              direction=SortDirection.ASC,
              null_order=NullOrder.NULLS_LAST),
)


def create_schema_tables(catalog: Catalog, namespace: str) -> Dict[str, Table]:
    table_name_features = "features"
    table_name_sources = "sources"
    table_name_relationships = "feature_relationships"

    print(f"Creating tables in namespace {namespace} ...")

    print(f"Creating {table_name_features}")
    features: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_features,
        schema=features_schema,
        partition_spec=features_partition_spec,
        sort_order=features_sort_order)
    print(f"Created {features}")

    time.sleep(3)

    print(f"Creating {table_name_sources}")
    sources: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_sources,
        schema=sources_schema,
        partition_spec=None,
        sort_order=None)
    print(f"Created {sources}")

    time.sleep(3)

    print(f"Creating {table_name_relationships}")
    relationships: Table = create_table(
        catalog=catalog,
        namespace=namespace,
        table_name=table_name_relationships,
        schema=feature_relationships_schema,
        partition_spec=feature_relationships_partition_spec,
        sort_order=feature_relationships_sort_order)
    print(f"Created {relationships}")

    time.sleep(3)

    return {
        table_name_features: features,
        table_name_sources: sources,
        table_name_relationships: relationships,
    }


def main():
    import argparse
    from utils import create_namespace

    parser = argparse.ArgumentParser(
        description='Create Iceberg tables for GFF3 annotation data (Schema 1 — normalized)')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    args = parser.parse_args()

    print("Connecting to catalog ...")
    catalog = load_s3_tables_catalog(args.bucket_arn)
    print("Connected to catalog")

    namespace = "annotation_db"
    print("Creating namespace ...")
    create_namespace(catalog, namespace)
    print("Namespace created")

    print("Creating tables ...")
    create_schema_tables(catalog, namespace)
    print("Tables created")


if __name__ == "__main__":
    main()
