#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Usage: ./scripts/create-tables.sh <store_type> <account_id> <store_id> <table_name> <s3_path> <region>
#
# store_type: variant | annotation_vcf | annotation_gff | annotation_tsv
# account_id: AWS account ID
# store_id:   Store identifier (used in database name)
# table_name: Iceberg table name
# s3_path:    S3 location for table data (e.g. s3://my-bucket/omics)
# region:     AWS region (e.g. us-west-2)
#
# Examples:
#   ./scripts/create-tables.sh variant 111111111111 9f86d081884c test s3://my-bucket/omics us-west-2
#   ./scripts/create-tables.sh annotation_gff 111111111111 abc123 annotations s3://my-bucket/annotations us-west-2

STORE_TYPE="${1:?Usage: $0 <store_type> <account_id> <store_id> <table_name> <s3_path> <region>}"
ACCOUNT_ID="${2:?Missing account_id}"
STORE_ID="${3:?Missing store_id}"
TABLE_NAME="${4:?Missing table_name}"
S3_PATH="${5:?Missing s3_path}"
REGION="${6:?Missing region}"

DATABASE="variant_${ACCOUNT_ID}_${STORE_ID}"
WORKGROUP="primary"

run_query() {
  local sql="$1"
  echo "Running query..."
  local execution_id
  execution_id=$(aws athena start-query-execution \
    --query-string "$sql" \
    --work-group "$WORKGROUP" \
    --region "$REGION" \
    --query "QueryExecutionId" \
    --output text)

  echo "  Execution ID: $execution_id"

  # Poll until complete
  local state="RUNNING"
  while [[ "$state" == "RUNNING" || "$state" == "QUEUED" ]]; do
    sleep 2
    state=$(aws athena get-query-execution \
      --query-execution-id "$execution_id" \
      --region "$REGION" \
      --query "QueryExecution.Status.State" \
      --output text)
    echo "  State: $state"
  done

  if [[ "$state" != "SUCCEEDED" ]]; then
    local reason
    reason=$(aws athena get-query-execution \
      --query-execution-id "$execution_id" \
      --region "$REGION" \
      --query "QueryExecution.Status.StateChangeReason" \
      --output text)
    echo "  FAILED: $reason"
    exit 1
  fi
  echo "  Done."
}

# Create database
echo "Creating database: $DATABASE"
run_query "CREATE DATABASE IF NOT EXISTS \`${DATABASE}\`;"

# Build table DDL based on store type
case "$STORE_TYPE" in
  variant|annotation_vcf)
    # VCF schema with VEP annotations (iceberg_1 format)
    DDL=$(cat <<EOF
CREATE TABLE IF NOT EXISTS \`${DATABASE}\`.\`${TABLE_NAME}\` (
  importJobId           string,
  contigname            string,
  \`start\`             bigint,
  \`end\`               bigint,
  names                 array<string>,
  referenceAllele       string,
  alternateAlleles      array<string>,
  qual                  double,
  filters               array<string>,
  splitFromMultiAllelic boolean,
  attributes            map<string, string>,
  phased                boolean,
  calls                 array<int>,
  genotypelikelihoods   array<double>,
  phredlikelihoods      array<int>,
  alleledepths          array<int>,
  conditionalquality    int,
  spl                   array<int>,
  depth                 int,
  ps                    int,
  sampleId              string,
  information           map<string, string>,
  annotations           struct<
    vep: array<struct<
      allele:string,
      consequence:array<string>,
      impact:string,
      symbol:string,
      gene:string,
      feature_type:string,
      feature:string,
      biotype:string,
      exon:struct<rank:string,total:string>,
      intron:struct<rank:string,total:string>,
      hgvsc:string,
      hgvsp:string,
      cdna_position:string,
      cds_position:string,
      protein_position:string,
      amino_acids:struct<reference:string,variant:string>,
      codons:struct<reference:string,variant:string>,
      existing_variation:array<string>,
      distance:string,
      strand:string,
      flags:array<string>,
      symbol_source:string,
      hgnc_id:string,
      extras:map<string,string>
    >>
  >
)
LOCATION '${S3_PATH}'
TBLPROPERTIES (
  'table_type' = 'ICEBERG',
  'format'     = 'parquet'
)
EOF
    )
    ;;

  annotation_gff)
    DDL=$(cat <<EOF
CREATE TABLE IF NOT EXISTS \`${DATABASE}\`.\`${TABLE_NAME}\` (
  importJobId     string,
  seqId           string,
  source          string,
  type            string,
  \`start\`       bigint,
  \`end\`         bigint,
  score           double,
  strand          string,
  phase           int,
  id              string,
  name            string,
  alias           string,
  parent          array<string>,
  target          string,
  gap             string,
  derivesFrom     string,
  note            array<string>,
  dbxref          array<string>,
  ontologyTerm    array<string>,
  \`is_circular\` boolean,
  information     map<string, string>
)
LOCATION '${S3_PATH}'
TBLPROPERTIES (
  'table_type' = 'ICEBERG',
  'format'     = 'parquet'
)
EOF
    )
    ;;

  annotation_tsv)
    echo "TSV tables require a dynamic schema. Use the Omics service API or provide the schema JSON."
    echo "This script supports: variant, annotation_vcf, annotation_gff"
    exit 1
    ;;

  *)
    echo "Unknown store type: $STORE_TYPE"
    echo "Supported: variant, annotation_vcf, annotation_gff, annotation_tsv"
    exit 1
    ;;
esac

echo "Creating table: ${DATABASE}.${TABLE_NAME}"
run_query "$DDL"

echo ""
echo "Done. Database and table created:"
echo "  Database: $DATABASE"
echo "  Table:    $TABLE_NAME"
echo "  Location: $S3_PATH"