#!/usr/bin/env python3
"""
Permissions checker for HealthOmics GFF3 Annotation Loader workflow.

Probes AWS permissions before table initialization. Checks vary by catalog type:
- Glue (vanilla S3): Glue API, Lake Formation, S3 write
- S3 Tables: s3tables API
"""

import sys
import json
import argparse
import boto3
from botocore.exceptions import ClientError


SCHEMA_NAMESPACES = {
    "1": "annotation_db",
    "2": "annotation_db_2",
}


def get_caller_identity():
    sts = boto3.client("sts")
    identity = sts.get_caller_identity()
    return {"arn": identity["Arn"], "account": identity["Account"]}


def check_glue_access(region, database):
    glue = boto3.client("glue", region_name=region)
    try:
        glue.get_database(Name=database)
        return {"check": "glue_access", "passed": True,
                "message": f"Glue database '{database}' exists and is accessible."}
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "EntityNotFoundException":
            try:
                glue.get_databases(MaxResults=1)
                return {"check": "glue_access", "passed": True,
                        "message": f"Glue database '{database}' does not exist yet but Glue API is accessible."}
            except ClientError as e2:
                return {"check": "glue_access", "passed": False, "message": f"Cannot list Glue databases: {e2}"}
        elif code == "AccessDeniedException":
            return {"check": "glue_access", "passed": False,
                    "message": f"Access denied to Glue database '{database}'."}
        return {"check": "glue_access", "passed": False, "message": f"Glue API error: {e}"}


def check_lakeformation_settings(region):
    lf = boto3.client("lakeformation", region_name=region)
    try:
        settings = lf.get_data_lake_settings()["DataLakeSettings"]
    except ClientError as e:
        return {"check": "lakeformation_settings", "passed": False,
                "message": f"Cannot read Lake Formation settings: {e}"}
    create_db = settings.get("CreateDatabaseDefaultPermissions", [{}])
    create_tbl = settings.get("CreateTableDefaultPermissions", [{}])
    iam_only = len(create_db) == 0 and len(create_tbl) == 0
    return {
        "check": "lakeformation_settings", "passed": True,
        "governed": not iam_only,
        "message": "Lake Formation is in IAM-only mode." if iam_only
                   else "Lake Formation is governing the Glue catalog."
    }


def check_s3tables_access(destination):
    parts = destination.split(":")
    region = parts[3]
    s3tables = boto3.client("s3tables", region_name=region)
    try:
        s3tables.list_namespaces(tableBucketARN=destination, maxNamespaces=1)
        return {"check": "s3tables_access", "passed": True,
                "message": "S3 Tables API is accessible for the given bucket."}
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "AccessDeniedException":
            return {"check": "s3tables_access", "passed": False,
                    "message": "Access denied to S3 Tables."}
        return {"check": "s3tables_access", "passed": False, "message": f"S3 Tables API error: {e}"}
    except Exception as e:
        return {"check": "s3tables_access", "passed": False, "message": f"S3 Tables check failed: {e}"}


def check_s3_write(destination):
    if not destination.startswith("s3://"):
        return {"check": "s3_write", "passed": True, "message": "Not an S3 path, skipped."}
    bucket = destination[5:].split("/")[0]
    prefix = destination[5:].split("/", 1)[1] if "/" in destination[5:] else ""
    test_key = f"{prefix}.healthomics-permission-check".strip("/")
    s3 = boto3.client("s3")
    try:
        s3.put_object(Bucket=bucket, Key=test_key, Body=b"")
        s3.delete_object(Bucket=bucket, Key=test_key)
        return {"check": "s3_write", "passed": True,
                "message": f"S3 write access confirmed for s3://{bucket}/{prefix}"}
    except ClientError as e:
        return {"check": "s3_write", "passed": False, "message": f"S3 write check failed: {e}"}


def check_permissions(catalog_type, destination, schema, namespace=None):
    ns = namespace or SCHEMA_NAMESPACES.get(schema, "annotation_db")
    identity = get_caller_identity()
    checks = []

    if catalog_type == "vanilla":
        session = boto3.session.Session()
        region = session.region_name or "us-east-1"
        checks.append(check_glue_access(region, ns))
        lf_settings = check_lakeformation_settings(region)
        checks.append(lf_settings)
        checks.append(check_s3_write(destination))
    elif catalog_type == "s3tables":
        checks.append(check_s3tables_access(destination))

    failures = [c for c in checks if not c["passed"]]
    return {
        "status": "passed" if not failures else "failed",
        "identity": identity, "catalog_type": catalog_type, "namespace": ns,
        "checks": checks, "passed": len(failures) == 0,
        "failures": [f["message"] for f in failures],
    }


def main():
    parser = argparse.ArgumentParser(description="Check permissions for GFF3 Annotation Loader")
    parser.add_argument("--catalog-config", required=True, help="Path to catalog_config.json")
    parser.add_argument("--schema", required=True, help="Schema selection (1 or 2)")
    parser.add_argument("--namespace", help="Iceberg namespace override")
    parser.add_argument("--output", help="Output JSON file")
    args = parser.parse_args()

    with open(args.catalog_config) as f:
        config = json.load(f)

    result = check_permissions(config["catalog_type"], config["destination"], args.schema, args.namespace)
    output_json = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)
    print(output_json)
    if not result["passed"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
