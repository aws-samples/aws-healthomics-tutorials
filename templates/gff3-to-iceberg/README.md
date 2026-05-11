# HealthOmics GFF3 Annotation Loader Workflow

A WDL workflow that loads GFF3 (Generic Feature Format version 3) files into Apache Iceberg tables on AWS. Runs in AWS HealthOmics and supports both S3 Tables (managed Iceberg catalog) and vanilla Iceberg with Glue catalog and S3 storage.

> **VPC Connectivity Required:** Both catalog types require VPC-connected workflow runs.

## Quick Start

1. Build and push the container to ECR (see below)
2. Deploy the workflow to HealthOmics using `main.wdl`
3. Start a VPC-connected run with your parameters

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `gff3_file` | File | Yes | — | S3 URI to GFF3 file (`.gff3` or `.gff3.gz`) |
| `schema` | String | Yes | — | Schema design: `1` (normalized) or `2` (denormalized) |
| `destination` | String | Yes | — | S3 Tables ARN or `bucket/path` (no `s3://` prefix) |
| `container` | String | Yes | — | Container image URI |
| `namespace` | String | No | Auto | Iceberg namespace |
| `batch_size` | Int | No | `100000` | Records per processing batch |

## Schema Selection

| Schema | Tables | Best For |
|--------|--------|----------|
| **1** | `features`, `sources`, `feature_relationships` | Data integrity, hierarchy traversal |
| **2** | `genomic_annotations` | Fast region queries, simplicity |

### Default Namespaces

- Schema 1: `annotation_db`
- Schema 2: `annotation_db_2`

## Workflow Stages

1. **Validate Inputs** — Checks GFF3 file, schema, destination
2. **Setup Catalog** — Configures S3 Tables REST or Glue catalog
3. **Check Connectivity** — Validates VPC network access
4. **Check Permissions** — Probes AWS permissions
5. **Initialize Tables** — Creates tables if they don't exist
6. **Load GFF3** — Parses features in batches, writes to Iceberg
7. **Generate Summary** — Produces JSON summary

## Building the Container

```bash
# Build locally
./build_container.sh

# Build and push to ECR
./build_and_push_container.sh \
  --account-id 123456789012 \
  --region us-east-1 \
  --repo healthomics-gff3-loader \
  --tag v1.0.0 \
  --docker
```

## AWS Permissions

Same as the VCF loader — see the variant-database workflow README for IAM policy examples for S3 Tables and Glue catalog destinations.
