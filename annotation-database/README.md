# Creating and Loading Iceberg Tables with GFF3 Annotation Data

This project demonstrates how to use PyIceberg to connect to an AWS S3Tables catalog, create Iceberg tables for storing genomic annotation data, and load GFF3 files into these tables.

## Prerequisites

- AWS account with appropriate permissions
- Python 3.8+
- AWS credentials configured (CLI, environment variables, IAM role, etc.)

## Installation

```bash
python -m venv venv
./setup.sh

# Or manually:
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Update the `--bucket-arn` argument with your S3Tables bucket ARN:

```
arn:aws:s3tables:us-east-1:YOUR_ACCOUNT_ID:bucket/YOUR_BUCKET_NAME
```

## Project Structure

- `utils.py` — Utility functions for S3Tables and Iceberg operations
- `schema_1.py` — Normalized schema: features, sources, feature_relationships
- `schema_2.py` — Denormalized schema: single genomic_annotations table
- `metadata_schema.py` — Schema for GFF3 file-level directives and pragmas
- `load_gff3_schema1.py` — Load GFF3 files into Schema 1 tables
- `load_gff3_schema2.py` — Load GFF3 files into Schema 2 table
- `describe_tables.py` — Describe existing Iceberg tables
- `drop_tables.py` — Drop tables from a namespace

## Usage

### Creating Tables

```bash
python schema_1.py --bucket-arn <bucket_arn>  # Creates tables in namespace annotation_db
python schema_2.py --bucket-arn <bucket_arn>  # Creates tables in namespace annotation_db_2
```

### Loading GFF3 Data

```bash
# Load into Schema 1 (normalized)
python load_gff3_schema1.py --bucket-arn <bucket_arn> path/to/annotations.gff3.gz ...

# Load into Schema 2 (denormalized)
python load_gff3_schema2.py --bucket-arn <bucket_arn> path/to/annotations.gff3.gz ...

# Load from S3
python load_gff3_schema1.py --bucket-arn <bucket_arn> s3://bucket/annotations.gff3.gz
```

### Describing Tables

```bash
python describe_tables.py --bucket-arn <bucket_arn>
```

### Dropping Tables

```bash
python drop_tables.py --bucket-arn <bucket_arn> --namespace annotation_db --confirm
```

## Schema Designs

### Schema 1 — Normalized (`schema_1.py`)

Three tables in namespace `annotation_db`:

1. **features** — Core annotation features
   - `feature_id` (String, primary key) — GFF3 `ID` attribute
   - `seqid` (String) — Chromosome / landmark
   - `source` (String) — Annotation source program
   - `type` (String) — Feature type / SO term (gene, mRNA, exon, CDS, etc.)
   - `start` (Long) — Start position, 1-based inclusive
   - `end` (Long) — End position, 1-based inclusive
   - `score` (Double) — Score value
   - `strand` (String) — +, -, ., or ?
   - `phase` (String) — CDS phase: 0, 1, or 2
   - `name` (String) — GFF3 `Name` attribute
   - `dbxref` (String) — Database cross-references
   - `ontology_term` (String) — Ontology terms
   - `is_circular` (Boolean) — Circular feature flag
   - `attributes` (Map<String, String>) — All remaining GFF3 attributes
   - Partitioned by: `seqid` + `type_bucket` (128 buckets)
   - Sorted by: `start` (ascending)

2. **sources** — Distinct annotation sources
   - `source_name` (String)
   - `description` (String)

3. **feature_relationships** — Parent-child hierarchy
   - `child_id` (String) — Child feature ID
   - `parent_id` (String) — Parent feature ID
   - `seqid` (String) — Chromosome (for partition-aligned joins)
   - `child_type` (String) — e.g., exon, CDS
   - `parent_type` (String) — e.g., gene, mRNA
   - Partitioned by: `seqid`
   - Sorted by: `parent_id` (ascending)

### Schema 2 — Denormalized (`schema_2.py`)

Single table in namespace `annotation_db_2`:

1. **genomic_annotations** — All feature data with embedded parent references
   - Same columns as Schema 1 features, plus:
   - `parent_ids` (List<String>) — GFF3 `Parent` attribute as a list
   - Partitioned by: `seqid` + `type_bucket` (128 buckets)
   - Sorted by: `seqid` and `start` (ascending)

## GFF3 Parsing Details

- **URL decoding**: GFF3 requires percent-encoding for special characters; the parser handles this automatically
- **Reserved attributes**: `ID`, `Name`, `Parent`, `Dbxref`, `Ontology_term`, `Is_circular` are extracted into dedicated columns
- **Remaining attributes**: Stored in a `Map<String, String>` column
- **Multi-value Parent**: `Parent=mRNA00001,mRNA00002` produces multiple relationship rows (Schema 1) or a list (Schema 2)
- **FASTA section**: The parser stops at `>` lines (inline FASTA sequences are skipped)
- **Directives**: `##` header lines are logged; use `metadata_schema.py` to persist them

## Performance Considerations

- **Schema 1**: Normalized — good for data integrity, enables tree traversal queries via the relationship table, requires joins
- **Schema 2**: Denormalized — fastest for region-based queries, parent info embedded, some source duplication

## Required AWS Permissions

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3tables:CreateTable",
                "s3tables:GetTable",
                "s3tables:ListNamespaces",
                "s3tables:CreateNamespace",
                "s3tables:ListTables",
                "s3tables:DeleteTable",
                "s3tables:PutTableData",
                "s3tables:GetTableData"
            ],
            "Resource": [
                "arn:aws:s3tables:*:*:bucket/*"
            ]
        }
    ]
}
```

## Resources

- [GFF3 Specification](https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md)
- [AWS S3Tables Documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables-integrating-open-source.html)
- [PyIceberg Documentation](https://py.iceberg.apache.org/)
