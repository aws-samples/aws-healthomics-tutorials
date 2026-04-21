# HealthOmics VCF Loader Workflow

A WDL workflow that loads VCF (Variant Call Format) files into Apache Iceberg tables on AWS. Runs exclusively in AWS HealthOmics and supports both S3 Tables (managed Iceberg catalog) and vanilla Iceberg with Glue catalog and S3 storage.

> **VPC Connectivity Required:** Both catalog types require VPC-connected workflow runs in HealthOmics. The default RESTRICTED networking mode only provides same-region S3 and ECR access, which is not sufficient for Glue, Lake Formation, or S3 Tables API calls. See [HealthOmics VPC Setup](#healthomics-vpc-setup) for details.

## Quick Start

1. Build and push the container to ECR (see [Building the Container](#building-and-deploying-the-container))
2. Deploy the workflow to HealthOmics using `main.wdl`
3. Start a VPC-connected run with your parameters

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `vcf_file` | File | Yes | — | S3 URI to VCF file. Supports `.vcf` and `.vcf.gz` |
| `schema` | String | Yes | — | Schema design to use: `1`, `2`, `3`, or `4` |
| `destination` | String | Yes | — | For Glue catalog: `bucket/path` (no `s3://` prefix). For S3 Tables: full ARN |
| `container` | String | No | `public.ecr.aws/aws-genomics/healthomics-vcf-loader:v1.1.4` | Container image URI |
| `namespace` | String | No | Auto | Iceberg namespace. Auto-determined by schema if not set |
| `batch_size` | Int | No | `100000` | Number of VCF records per processing batch |

### Destination Format

The `destination` parameter is a `String` type in WDL (not a `File`) to prevent HealthOmics from treating it as an S3 input to stage.

- **Glue catalog (vanilla Iceberg):** Pass `bucket/path` without the `s3://` prefix. The workflow prepends `s3://` internally.
  Example: `my-iceberg-bucket/warehouse`
- **S3 Tables:** Pass the full ARN as-is.
  Example: `arn:aws:s3tables:us-east-1:123456789012:bucket/my-table-bucket`

## Schema Selection Guide

| Schema | Tables | Best For | Trade-offs |
|--------|--------|----------|------------|
| **1** | `variants`, `samples`, `variant_samples` | Data integrity, minimal redundancy | Requires joins for most queries |
| **2** | `variant_regions`, `samples` | Variant-centric queries | Some data duplication |
| **3** | `genomic_variants` | Single-sample queries, simplicity | High duplication for multi-sample VCFs |
| **4** | `variants`, `samples`, `variant_samples` | Genomic region queries | Similar to schema 1 with position partitioning |

### Default Namespaces

- Schema 1: `variant_db`
- Schema 2: `variant_db_2`
- Schema 3: `variant_db_3`
- Schema 4: `variant_db_4`

## Destination Types

### S3 Tables (Managed Iceberg Catalog)

Provide an S3 Table Bucket ARN:

```
arn:aws:s3tables:<region>:<account-id>:bucket/<bucket-name>
```

The workflow configures a REST catalog with SigV4 authentication pointing to the S3 Tables service. This mode does not use AWS Glue or Lake Formation — table metadata is managed entirely by the S3 Tables API.

### Vanilla Iceberg (Glue Catalog + S3 Storage)

Provide a bucket and path without the `s3://` prefix:

```
my-bucket/path/to/warehouse
```

The workflow configures an Iceberg catalog using AWS Glue Data Catalog for table metadata and S3 as the storage backend. If Lake Formation governance is enabled in your account, the execution role also needs explicit Lake Formation grants (see [AWS Permissions](#aws-permissions)).

## Workflow Stages

1. **Validate Inputs** — Checks VCF file accessibility, validates schema selection, determines catalog type
2. **Setup Catalog** — Configures the Iceberg catalog (S3 Tables REST or Glue)
3. **Check Connectivity** — Validates network access to required AWS service endpoints (Glue, Lake Formation, S3 Tables, STS). Fails fast with actionable guidance if VPC networking is misconfigured
4. **Check Permissions** — Probes AWS permissions (Glue access, Lake Formation governance, S3 write access, S3 Tables API access)
5. **Initialize Tables** — Creates tables if they don't exist, verifies schema if they do
6. **Load VCF** — Parses VCF records in batches and writes to Iceberg tables
7. **Generate Summary** — Produces a JSON summary with execution metadata and statistics

## Output

The workflow produces the following output files:

- `summary` — JSON summary with execution metadata and loading statistics
- `validation_report` — Input validation results
- `connectivity_report` — Network connectivity check results
- `permissions_report` — AWS permissions check results
- `table_init_report` — Table initialization results
- `load_statistics` — VCF loading statistics

### Summary JSON Structure

```json
{
  "workflow": "healthomics-vcf-loader",
  "version": "1.1.0",
  "execution": {
    "start_time": "2026-01-15T10:30:00Z",
    "end_time": "2026-01-15T10:45:00Z",
    "duration_seconds": 900
  },
  "inputs": {
    "vcf_file": "s3://my-bucket/data/sample.vcf.gz",
    "schema": "1",
    "destination": "s3://my-bucket/iceberg-warehouse",
    "namespace": "variant_db",
    "batch_size": 100000
  },
  "results": {
    "catalog_type": "s3tables",
    "tables_created": ["variants", "samples", "variant_samples"],
    "variants_loaded": 1500000,
    "samples_loaded": 10
  }
}
```

## AWS Permissions

### IAM Service Role

The HealthOmics service role needs the following permissions. The exact set depends on which destination type you use.

### S3 Tables Destination

Uses the S3 Tables REST API directly. Does not require Glue or Lake Formation access.

- `s3tables:CreateTable`, `s3tables:GetTable`, `s3tables:CreateNamespace`
- `s3tables:ListNamespaces`, `s3tables:ListTables`
- `s3tables:PutTableData`, `s3tables:GetTableData`
- `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, `s3:ListBucket` (for Iceberg data files)

### Vanilla S3 Destination

Uses AWS Glue Data Catalog for table metadata. Lake Formation read access is always needed to check governance mode.

**Glue (always required):**
- `glue:GetDatabase`, `glue:GetDatabases`, `glue:CreateDatabase`
- `glue:GetTable`, `glue:CreateTable`, `glue:UpdateTable`, `glue:GetTables`
- `glue:DeleteTable` (for table management)

Scope these to your Glue catalog, database, and table ARNs:
```
arn:aws:glue:<region>:<account>:catalog
arn:aws:glue:<region>:<account>:database/*
arn:aws:glue:<region>:<account>:table/*/*
```

**Lake Formation (always required for governance check):**
- `lakeformation:GetDataLakeSettings` — needed to detect whether LF governance is enabled
- `lakeformation:ListPermissions` — needed to check if the role has sufficient grants

Even when Lake Formation reports "IAM-only mode" (empty default permissions), the role may still need explicit Lake Formation grants to access Glue resources if `SET_CONTEXT` is enabled in your account. Grant the following via the Lake Formation console or CLI:
- Catalog level: `CREATE_DATABASE`
- Data location: `DATA_LOCATION_ACCESS` on the S3 warehouse bucket

**Lake Formation grants (only if LF governance is enabled):**

The workflow's permission checker probes Lake Formation settings automatically. If governance is not enabled, no LF grants are needed. Otherwise the execution role needs explicit grants via the Lake Formation console:
- Database level: `CREATE_TABLE`, `DESCRIBE`, `ALTER`
- Table level: `SELECT`, `INSERT`, `DESCRIBE`, `ALTER`

**S3 (always required):**
- `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, `s3:ListBucket`

### Common Permissions (both destination types)

- `s3:GetObject` on the VCF input file bucket
- `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` (HealthOmics logging)
- `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage` (container image access)

### Example IAM Policy for Vanilla Iceberg

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GlueAccess",
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase", "glue:GetDatabases", "glue:CreateDatabase",
        "glue:GetTable", "glue:CreateTable", "glue:UpdateTable",
        "glue:GetTables", "glue:DeleteTable"
      ],
      "Resource": [
        "arn:aws:glue:*:ACCOUNT_ID:catalog",
        "arn:aws:glue:*:ACCOUNT_ID:database/*",
        "arn:aws:glue:*:ACCOUNT_ID:table/*/*"
      ]
    },
    {
      "Sid": "LakeFormationAccess",
      "Effect": "Allow",
      "Action": [
        "lakeformation:GetDataLakeSettings",
        "lakeformation:ListPermissions"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::YOUR_BUCKET",
        "arn:aws:s3:::YOUR_BUCKET/*"
      ]
    }
  ]
}
```

### Example IAM Policy for S3 Tables

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3TablesAccess",
      "Effect": "Allow",
      "Action": [
        "s3tables:CreateTable", "s3tables:GetTable",
        "s3tables:CreateNamespace", "s3tables:ListNamespaces",
        "s3tables:ListTables", "s3tables:PutTableData",
        "s3tables:GetTableData"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::YOUR_BUCKET",
        "arn:aws:s3:::YOUR_BUCKET/*"
      ]
    }
  ]
}
```

## Building and Deploying the Container

### Build Locally

```bash
cd workflow
./build_container.sh
```

### Push to ECR

```bash
./build_and_push_container.sh \
  --account-id 123456789012 \
  --region us-east-1 \
  --repo healthomics-vcf-loader
```

See [DOCKER_BUILD_INSTRUCTIONS.md](DOCKER_BUILD_INSTRUCTIONS.md) for detailed instructions.

## Directory Structure

```
workflow/
├── main.wdl                   # WDL workflow definition
├── Dockerfile                 # Container definition
├── requirements.txt           # Python dependencies
├── build_container.sh         # Local container build script
├── build_and_push_container.sh # Build + ECR push script
├── validate_inputs.py         # Input validation module
├── setup_catalog.py           # Catalog configuration module
├── check_connectivity.py      # Network connectivity checker (VPC validation)
├── check_permissions.py       # AWS permissions checker
├── initialize_tables.py       # Table initialization module
├── load_vcf_wrapper.py        # VCF loading wrapper
├── generate_summary.py        # Summary generation module
├── schema_1.py … schema_4.py  # Schema definitions
├── load_vcf_schema1.py … 4.py # Schema-specific VCF loaders
├── utils.py                   # Shared utilities
├── metadata_schema.py         # Metadata schema
├── examples/                  # Example parameter files
│   ├── params-s3tables-schema1.json
│   ├── params-vanilla-schema1.json
│   └── ...
└── tests/                     # Unit and property-based tests
```

## HealthOmics VPC Setup

Both catalog types (S3 Tables and vanilla Glue) require VPC-connected workflow runs in HealthOmics. The default `RESTRICTED` networking mode only provides same-region S3 and ECR access.

### Why VPC is Required

| Catalog Type | Endpoints Needed | Why RESTRICTED Mode Fails |
|---|---|---|
| **S3 Tables** | `s3tables.{region}.amazonaws.com` (REST API) | S3 Tables REST endpoint is not S3 — it's a separate service |
| **Vanilla (Glue)** | Glue API, Lake Formation API, STS | Glue and LF are not accessible in RESTRICTED mode |

### Setup Steps

1. **Create or identify a VPC** with private subnets in Availability Zones where HealthOmics operates
2. **Configure a NAT Gateway** in a public subnet, with private subnet route tables routing `0.0.0.0/0` to the NAT Gateway
3. **Configure security groups** allowing outbound HTTPS (TCP 443)
4. **Optionally add VPC endpoints** to reduce NAT Gateway costs:
   - `com.amazonaws.{region}.s3` (Gateway type) — recommended
   - `com.amazonaws.{region}.glue` (Interface type) — for vanilla Iceberg
   - `com.amazonaws.{region}.lakeformation` (Interface type) — if LF governance is enabled
   - `com.amazonaws.{region}.sts` (Interface type) — for credential validation
5. **Create a HealthOmics Configuration** with your subnet and security group IDs
6. **Start the run** with `networking_mode=VPC` and `configuration_name=<your-config>`

### Example: Starting a VPC-Connected Run

```json
{
  "workflow_id": "8609916",
  "role_arn": "arn:aws:iam::123456789012:role/OmicsServiceRole",
  "output_uri": "s3://omics-outputs/",
  "storage_type": "DYNAMIC",
  "networking_mode": "VPC",
  "configuration_name": "my-vpc-config",
  "name": "vcf-loader-run",
  "parameters": {
    "vcf_file": "s3://my-bucket/data/sample.vcf.gz",
    "schema": "1",
    "destination": "my-iceberg-bucket/warehouse",
    "container": "123456789012.dkr.ecr.us-east-1.amazonaws.com/healthomics-vcf-loader:v1.1.0"
  }
}
```

## Troubleshooting

### "VCF file not found or not accessible"
- Verify the S3 URI is correct
- Ensure the execution role has `s3:GetObject` permission on the bucket

### "Invalid destination format"
- Glue catalog: Pass `bucket/path` without `s3://` prefix
- S3 Tables: Pass the full ARN starting with `arn:aws:s3tables:`

### Table creation fails with "schema mismatch"
- Tables already exist with a different schema than selected
- Either drop existing tables or use the matching schema number

### Connectivity check fails (Cannot reach Glue/S3 Tables/STS)
- Ensure you started the run with `networking_mode=VPC` and a valid `configuration_name`
- Verify the HealthOmics Configuration is `ACTIVE` with private subnets
- Verify private subnets route `0.0.0.0/0` to a NAT Gateway
- Verify the security group allows outbound HTTPS (TCP 443)

### Lake Formation permission errors
- The workflow automatically detects whether LF governance is enabled
- If governed, the execution role needs explicit LF grants — see [AWS Permissions](#aws-permissions)

### Out of memory during VCF loading
- Reduce `batch_size` (e.g., `10000`)
- The load_vcf task defaults to 16 GB memory
