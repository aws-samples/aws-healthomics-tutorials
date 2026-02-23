# AwsVincentJobs

A genomics data import pipeline that runs as AWS Glue jobs. It parses and transforms genomic data files (VCF, TSV, GFF) into structured formats stored in Apache Iceberg tables on S3.

## Entry Points

The pipeline supports two import workflows, each with its own Glue job entry point:

- **VariantImportJob** — Ingests VCF files containing genomic variant data, with optional VEP annotation processing and left-normalization
- **AnnotationImportJob** — Ingests annotation data from VCF, TSV, and GFF formats

The output is a shadow (uber) JAR deployed to S3, invoked by AWS Glue with different `--classpath` values depending on the import type.

## Prerequisites

- Java 8 (source and target compatibility)
- No pre-installed Gradle needed — the project includes a Gradle 7.6.4 wrapper

## Building

```sh
# Full build: compile + test + format check + shadow JAR
./gradlew build
```

The shadow JAR is produced at `build/libs/AwsVincentJobs-super.jar`.

## Testing

```sh
# Run all tests
./gradlew test
```

## Code Formatting

Formatting is enforced via Spotless (scalafmt 3.4.3). The `test` task depends on `spotlessCheck`, so formatting issues will fail the build.

```sh
# Check formatting
./gradlew spotlessCheck

# Auto-fix formatting
./gradlew spotlessApply
```

## Deploying

Upload the shadow JAR to S3 for testing:

```sh
# Requires AWS_ACCOUNT_ID environment variable set to your account ID
export AWS_ACCOUNT_ID 123456789012
./gradlew upload
```

This uploads `build/libs/AwsVincentJobs-super.jar` to `s3://{AWS_ACCOUNT_ID}-awsvincentjobs-test-jar/`.

## Setting Up Glue Tables

Before running the pipeline, you need a Glue execution role and Iceberg tables.

### Create the Glue execution role

```sh
./scripts/create-glue-role.sh <role_name> <s3_bucket> <region>
```

For example:
```sh
./scripts/create-glue-role.sh VincentGlueRole my-data-bucket us-west-2
```

This creates an IAM role with permissions for S3, Glue catalog, Omics API, and CloudWatch Logs. The script also grants access to the JAR upload bucket (`{account_id}-awsvincentjobs-test-jar`).

### Create the Iceberg tables

The `scripts/create-tables.sh` script creates the Glue database and Iceberg table via Athena DDL.

```sh
# Variant store (with VEP annotations)
./scripts/create-tables.sh variant <account_id> <store_id> <table_name> <s3_path> <region>

# VCF annotation store
./scripts/create-tables.sh annotation_vcf <account_id> <store_id> <table_name> <s3_path> <region>

# GFF annotation store
./scripts/create-tables.sh annotation_gff <account_id> <store_id> <table_name> <s3_path> <region>
```

For example:
```sh
./scripts/create-tables.sh variant 111111111111 9f86d081884c test s3://my-bucket/omics us-west-2
```

This creates:
- A Glue database named `variant_{account_id}_{store_id}`
- An Iceberg table with the appropriate schema for the store type

TSV annotation tables require a dynamic schema and are not supported by this script.

## Running a Glue Job

Once the JAR is uploaded and tables are created, create the Glue job:

```sh
./scripts/create-glue-job.sh <job_name> <role_arn> [region]
```

For example:
```sh
./scripts/create-glue-job.sh vincent-variant-import \
  arn:aws:iam::111111111111:role/VincentGlueRole \
  us-east-1
```

This creates a Glue 3.0 ETL job pre-configured with the super JAR. Then configure `glueParameters.json` with your values and run:

```sh
./scripts/run-glue-job.sh <job_name> [region]
```

For example:
```sh
./scripts/run-glue-job.sh vincent-variant-import us-east-1
```

The Glue execution role must have permissions for S3 (read/write), Glue catalog access, and Omics API access (if using left normalization).

### Lake Formation permissions (if applicable)

If your account uses AWS Lake Formation to manage Glue catalog access, the IAM role alone is not sufficient. You also need to grant the Glue execution role permissions in Lake Formation:

```sh
# Grant database access
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier="arn:aws:iam::<account_id>:role/<role_name>" \
  --resource '{"Database":{"Name":"<database_name>"}}' \
  --permissions "ALL" \
  --region <region>

# Grant table access
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier="arn:aws:iam::<account_id>:role/<role_name>" \
  --resource '{"Table":{"DatabaseName":"<database_name>","TableWildcard":{}}}' \
  --permissions "ALL" \
  --region <region>

# Grant S3 data location access
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier="arn:aws:iam::<account_id>:role/<role_name>" \
  --resource '{"DataLocation":{"ResourceArn":"arn:aws:s3:::<bucket_name>"}}' \
  --permissions "DATA_LOCATION_ACCESS" \
  --region <region>
```

If you see `AccessDeniedException: Insufficient Lake Formation permission(s)` when running the job, these grants are needed.

## Tech Stack

- **Scala 2.12** (primary language)
- **Java 8** (source/target compatibility)
- **Gradle 7.6.4** (Kotlin DSL, via wrapper)
- **Apache Spark 3.1.1** (provided by Glue runtime)
- **Apache Iceberg 0.14.0** (provided by Glue runtime)
- **AWS SDK v2** for Omics and S3 access
- **Glow 1.2.2-SNAPSHOT** (genomics library, vendored in `lib/`)

Dependencies are resolved from Maven Central. Vendored JARs in `lib/` include Glow and the Glue assembly JAR.

## Project Structure

```
AwsVincentJobs/
├── build.gradle.kts           # Build config (shadow jar, spotless, jacoco)
├── settings.gradle.kts        # Gradle settings
├── gradlew / gradlew.bat      # Gradle wrapper scripts
├── .scalafmt.conf             # Scala formatting rules
├── lib/                       # Vendored JARs (Glow, Glue assembly)
└── src/
    ├── main/scala/.../vincent/job/
    │   ├── BaseJob.scala              # Abstract job runner (load → process → write)
    │   ├── VariantImportJob.scala     # Variant import entry point
    │   ├── AnnotationImportJob.scala  # Annotation import entry point
    │   ├── annotation/                # Format-specific import logic (GFF, TSV, VCF)
    │   ├── common/                    # Shared utilities (AWS clients, S3, validators)
    │   ├── components/                # Job composition (loader, writer, processors)
    │   └── models/                    # Data models, schemas, parameters
    └── test/scala/                    # Test classes (mirrors main structure)
```
