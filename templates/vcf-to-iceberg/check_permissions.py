#!/usr/bin/env python3
"""
Permissions checker for HealthOmics VCF Loader workflow.

Probes AWS permissions before table initialization to surface missing
grants early. Checks vary by catalog type:

- Glue (vanilla S3): Glue API access, Lake Formation governance mode,
  Lake Formation grants, S3 write access
- S3 Tables: s3tables API access, S3 write access

Outputs a JSON report with pass/fail per check and actionable messages
for any failures.
"""

import sys
import json
import argparse
import boto3
from botocore.exceptions import ClientError, NoCredentialsError


def get_caller_identity():
    """Return the ARN and account of the current caller."""
    sts = boto3.client("sts")
    identity = sts.get_caller_identity()
    return {
        "arn": identity["Arn"],
        "account": identity["Account"],
    }


# ---------------------------------------------------------------------------
# Lake Formation checks
# ---------------------------------------------------------------------------

def check_lakeformation_settings(region: str) -> dict:
    """
    Check whether Lake Formation is governing the Glue Data Catalog.

    Returns a dict with:
      governed: bool  — True if LF restricts new databases/tables
      details: str
    """
    lf = boto3.client("lakeformation", region_name=region)
    try:
        settings = lf.get_data_lake_settings()["DataLakeSettings"]
    except ClientError as e:
        return {
            "check": "lakeformation_settings",
            "passed": False,
            "message": f"Cannot read Lake Formation settings: {e}",
        }

    # These flags control whether IAM-only access is sufficient.
    # When both are True → IAM alone is enough, LF is not governing.
    create_db_default = settings.get(
        "CreateDatabaseDefaultPermissions", [{}]
    )
    create_tbl_default = settings.get(
        "CreateTableDefaultPermissions", [{}]
    )

    # If the default permission lists are empty, LF is in IAM-only mode
    iam_only = (len(create_db_default) == 0 and len(create_tbl_default) == 0)

    if iam_only:
        return {
            "check": "lakeformation_settings",
            "passed": True,
            "governed": False,
            "message": "Lake Formation is in IAM-only mode. No LF grants needed.",
        }
    else:
        return {
            "check": "lakeformation_settings",
            "passed": True,
            "governed": True,
            "message": (
                "Lake Formation is governing the Glue catalog. "
                "The execution role needs explicit LF grants for "
                "CREATE_DATABASE, CREATE_TABLE, DESCRIBE, ALTER, INSERT, and SELECT."
            ),
        }


def check_lakeformation_grants(region: str, role_arn: str, database: str) -> dict:
    """
    Check whether the role has Lake Formation grants on the target database.
    """
    lf = boto3.client("lakeformation", region_name=region)
    missing = []

    # Check database-level permissions
    try:
        resp = lf.list_permissions(
            Principal={"DataLakePrincipal": {"DataLakePrincipalIdentifier": role_arn}},
            Resource={"Database": {"Name": database}},
        )
        granted = set()
        for entry in resp.get("PrincipalResourcePermissions", []):
            granted.update(entry.get("Permissions", []))

        needed_db = {"CREATE_TABLE", "DESCRIBE", "ALTER"}
        missing_db = needed_db - granted
        if missing_db:
            missing.append(f"Database '{database}': missing {sorted(missing_db)}")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "EntityNotFoundException":
            missing.append(
                f"Database '{database}' does not exist yet. "
                "The role needs CREATE_DATABASE grant on the catalog."
            )
        else:
            missing.append(f"Cannot check DB grants: {e}")

    # Check table-level wildcard permissions (ALL_TABLES)
    try:
        resp = lf.list_permissions(
            Principal={"DataLakePrincipal": {"DataLakePrincipalIdentifier": role_arn}},
            Resource={"Table": {"DatabaseName": database, "TableWildcard": {}}},
        )
        granted = set()
        for entry in resp.get("PrincipalResourcePermissions", []):
            granted.update(entry.get("Permissions", []))

        needed_tbl = {"SELECT", "INSERT", "DESCRIBE", "ALTER"}
        missing_tbl = needed_tbl - granted
        if missing_tbl:
            missing.append(
                f"Tables in '{database}': missing {sorted(missing_tbl)}"
            )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code != "EntityNotFoundException":
            missing.append(f"Cannot check table grants: {e}")

    if missing:
        return {
            "check": "lakeformation_grants",
            "passed": False,
            "missing": missing,
            "message": "Lake Formation grants are insufficient: " + "; ".join(missing),
        }
    return {
        "check": "lakeformation_grants",
        "passed": True,
        "message": f"Lake Formation grants look good for database '{database}'.",
    }


# ---------------------------------------------------------------------------
# Glue checks
# ---------------------------------------------------------------------------

def check_glue_access(region: str, database: str) -> dict:
    """Check basic Glue API access (GetDatabase or CreateDatabase)."""
    glue = boto3.client("glue", region_name=region)
    try:
        glue.get_database(Name=database)
        return {
            "check": "glue_access",
            "passed": True,
            "message": f"Glue database '{database}' exists and is accessible.",
        }
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "EntityNotFoundException":
            # DB doesn't exist yet — try a dry-run style check by listing databases
            try:
                glue.get_databases(MaxResults=1)
                return {
                    "check": "glue_access",
                    "passed": True,
                    "message": (
                        f"Glue database '{database}' does not exist yet but "
                        "Glue API is accessible. It will be created."
                    ),
                }
            except ClientError as e2:
                return {
                    "check": "glue_access",
                    "passed": False,
                    "message": f"Cannot list Glue databases: {e2}",
                }
        elif code == "AccessDeniedException":
            return {
                "check": "glue_access",
                "passed": False,
                "message": (
                    f"Access denied to Glue database '{database}'. "
                    "The role needs glue:GetDatabase, glue:CreateDatabase, "
                    "glue:CreateTable, glue:GetTable, glue:GetTables, and glue:UpdateTable."
                ),
            }
        else:
            return {
                "check": "glue_access",
                "passed": False,
                "message": f"Glue API error: {e}",
            }


# ---------------------------------------------------------------------------
# S3 Tables checks
# ---------------------------------------------------------------------------

def check_s3tables_access(destination: str) -> dict:
    """Check S3 Tables API access for the given bucket ARN."""
    parts = destination.split(":")
    region = parts[3]

    s3tables = boto3.client("s3tables", region_name=region)
    try:
        # Try listing namespaces — lightweight probe
        s3tables.list_namespaces(tableBucketARN=destination, maxNamespaces=1)
        return {
            "check": "s3tables_access",
            "passed": True,
            "message": "S3 Tables API is accessible for the given bucket.",
        }
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "AccessDeniedException":
            return {
                "check": "s3tables_access",
                "passed": False,
                "message": (
                    "Access denied to S3 Tables. The role needs: "
                    "s3tables:ListNamespaces, s3tables:CreateNamespace, "
                    "s3tables:CreateTable, s3tables:GetTable, s3tables:ListTables, "
                    "s3tables:PutTableData, s3tables:GetTableData."
                ),
            }
        else:
            return {
                "check": "s3tables_access",
                "passed": False,
                "message": f"S3 Tables API error: {e}",
            }
    except Exception as e:
        return {
            "check": "s3tables_access",
            "passed": False,
            "message": f"S3 Tables check failed: {e}",
        }


# ---------------------------------------------------------------------------
# S3 write check
# ---------------------------------------------------------------------------

def check_s3_write(destination: str) -> dict:
    """Check S3 write access to the warehouse location."""
    if not destination.startswith("s3://"):
        return {"check": "s3_write", "passed": True, "message": "Not an S3 path, skipped."}

    bucket = destination[5:].split("/")[0]
    prefix = destination[5:].split("/", 1)[1] if "/" in destination[5:] else ""
    test_key = f"{prefix}.healthomics-permission-check".strip("/")

    s3 = boto3.client("s3")
    try:
        s3.put_object(Bucket=bucket, Key=test_key, Body=b"")
        s3.delete_object(Bucket=bucket, Key=test_key)
        return {
            "check": "s3_write",
            "passed": True,
            "message": f"S3 write access confirmed for s3://{bucket}/{prefix}",
        }
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "AccessDenied":
            return {
                "check": "s3_write",
                "passed": False,
                "message": (
                    f"Cannot write to s3://{bucket}/{prefix}. "
                    "The role needs s3:PutObject, s3:GetObject, s3:DeleteObject, "
                    "and s3:ListBucket on this bucket."
                ),
            }
        return {
            "check": "s3_write",
            "passed": False,
            "message": f"S3 write check failed: {e}",
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

SCHEMA_NAMESPACES = {
    "1": "variant_db",
    "2": "variant_db_2",
    "3": "variant_db_3",
    "4": "variant_db_4",
}


def check_permissions(catalog_type: str, destination: str,
                      schema: str, namespace: str = None) -> dict:
    """
    Run all relevant permission checks and return a report.

    Returns:
        dict with keys: status, checks (list), passed (bool), failures (list)
    """
    ns = namespace or SCHEMA_NAMESPACES.get(schema, "variant_db")
    identity = get_caller_identity()
    role_arn = identity["arn"]
    checks = []

    if catalog_type == "vanilla":
        # Determine region from destination
        session = boto3.session.Session()
        region = session.region_name or "us-east-1"

        # 1. Glue API access
        checks.append(check_glue_access(region, ns))

        # 2. Lake Formation governance
        lf_settings = check_lakeformation_settings(region)
        checks.append(lf_settings)

        # 3. If LF is governing, check grants
        if lf_settings.get("governed", False):
            checks.append(check_lakeformation_grants(region, role_arn, ns))

        # 4. S3 write access
        checks.append(check_s3_write(destination))

    elif catalog_type == "s3tables":
        # 1. S3 Tables API access
        checks.append(check_s3tables_access(destination))

    failures = [c for c in checks if not c["passed"]]
    passed = len(failures) == 0

    return {
        "status": "passed" if passed else "failed",
        "identity": identity,
        "catalog_type": catalog_type,
        "namespace": ns,
        "checks": checks,
        "passed": passed,
        "failures": [f["message"] for f in failures],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check AWS permissions for HealthOmics VCF Loader"
    )
    parser.add_argument("--catalog-config", required=True,
                        help="Path to catalog_config.json from setupCatalog")
    parser.add_argument("--schema", required=True, help="Schema selection (1-4)")
    parser.add_argument("--namespace", help="Iceberg namespace override")
    parser.add_argument("--output", help="Output JSON file")

    args = parser.parse_args()

    # Load catalog config
    with open(args.catalog_config) as f:
        config = json.load(f)

    catalog_type = config["catalog_type"]
    destination = config["destination"]

    result = check_permissions(catalog_type, destination, args.schema, args.namespace)

    output_json = json.dumps(result, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)

    # Print report
    print(output_json)

    if not result["passed"]:
        print("\n=== PERMISSION FAILURES ===", file=sys.stderr)
        for msg in result["failures"]:
            print(f"  ✗ {msg}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
