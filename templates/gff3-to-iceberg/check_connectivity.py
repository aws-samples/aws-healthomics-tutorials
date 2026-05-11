#!/usr/bin/env python3
"""
Network connectivity checker for HealthOmics VCF Loader workflow.

Validates that the workflow run has network access to the AWS service
endpoints required by the selected catalog type. This catches VPC
networking misconfigurations early with clear, actionable error messages.

Required connectivity by catalog type:

  Vanilla (Glue catalog):
    - AWS STS (credential validation)
    - AWS Glue API
    - AWS Lake Formation API (if governance is enabled)
    - Amazon S3 (data read/write)

  S3 Tables (REST catalog):
    - AWS STS (credential validation)
    - S3 Tables REST API (https://s3tables.{region}.amazonaws.com)
    - Amazon S3 (data read/write)

Both catalog types require VPC-connected workflow runs in HealthOmics.
The default RESTRICTED networking mode only provides same-region S3 and
ECR access, which is NOT sufficient for Glue, Lake Formation, S3 Tables,
or STS API calls.

Outputs a JSON report with pass/fail per endpoint and remediation guidance.
"""

import sys
import json
import argparse
import socket
import ssl
import urllib.request
import urllib.error
import boto3
from botocore.exceptions import ClientError, EndpointConnectionError, ConnectTimeoutError


# Timeout for connectivity probes (seconds)
CONNECT_TIMEOUT = 10


def check_sts_connectivity() -> dict:
    """
    Check connectivity to AWS STS by calling GetCallerIdentity.

    STS is required for all catalog types to validate credentials and
    determine the caller's identity and account.
    """
    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        return {
            "endpoint": "sts",
            "passed": True,
            "message": f"STS reachable. Caller: {identity['Arn']}",
        }
    except (EndpointConnectionError, ConnectTimeoutError) as e:
        return {
            "endpoint": "sts",
            "passed": False,
            "message": (
                f"Cannot reach AWS STS: {e}. "
                "This workflow requires VPC-connected runs in HealthOmics. "
                "Ensure the run uses networking_mode=VPC with a configuration "
                "that has private subnets routed through a NAT Gateway, or add "
                "a com.amazonaws.{region}.sts VPC interface endpoint."
            ),
        }
    except Exception as e:
        return {
            "endpoint": "sts",
            "passed": False,
            "message": f"STS connectivity check failed: {e}",
        }


def check_glue_connectivity(region: str) -> dict:
    """
    Check connectivity to AWS Glue API.

    Glue is the catalog backend for vanilla Iceberg. The workflow needs
    Glue to create databases, create/update tables, and read table metadata.
    """
    try:
        glue = boto3.client("glue", region_name=region)
        # Lightweight probe — list databases with limit 1
        glue.get_databases(MaxResults=1)
        return {
            "endpoint": "glue",
            "passed": True,
            "message": f"Glue API reachable in {region}.",
        }
    except ClientError:
        # Access denied still means the endpoint is reachable
        return {
            "endpoint": "glue",
            "passed": True,
            "message": f"Glue API reachable in {region} (permissions checked separately).",
        }
    except (EndpointConnectionError, ConnectTimeoutError) as e:
        return {
            "endpoint": "glue",
            "passed": False,
            "message": (
                f"Cannot reach AWS Glue in {region}: {e}. "
                "Ensure the run uses networking_mode=VPC with NAT Gateway access, "
                "or add a com.amazonaws.{region}.glue VPC interface endpoint."
            ),
        }
    except Exception as e:
        return {
            "endpoint": "glue",
            "passed": False,
            "message": f"Glue connectivity check failed: {e}",
        }


def check_lakeformation_connectivity(region: str) -> dict:
    """
    Check connectivity to AWS Lake Formation API.

    Lake Formation is required when Glue Data Catalog governance is enabled.
    Even when not governing, the workflow probes LF settings to determine
    whether explicit grants are needed.
    """
    try:
        lf = boto3.client("lakeformation", region_name=region)
        lf.get_data_lake_settings()
        return {
            "endpoint": "lakeformation",
            "passed": True,
            "message": f"Lake Formation API reachable in {region}.",
        }
    except ClientError:
        # Access denied still means the endpoint is reachable
        return {
            "endpoint": "lakeformation",
            "passed": True,
            "message": f"Lake Formation API reachable in {region} (permissions checked separately).",
        }
    except (EndpointConnectionError, ConnectTimeoutError) as e:
        return {
            "endpoint": "lakeformation",
            "passed": False,
            "message": (
                f"Cannot reach Lake Formation in {region}: {e}. "
                "Ensure the run uses networking_mode=VPC with NAT Gateway access, "
                "or add a com.amazonaws.{region}.lakeformation VPC interface endpoint."
            ),
        }
    except Exception as e:
        return {
            "endpoint": "lakeformation",
            "passed": False,
            "message": f"Lake Formation connectivity check failed: {e}",
        }


def check_s3tables_connectivity(region: str) -> dict:
    """
    Check connectivity to the S3 Tables REST API endpoint.

    S3 Tables uses a dedicated REST endpoint at
    https://s3tables.{region}.amazonaws.com/iceberg for Iceberg catalog
    operations. This endpoint is NOT accessible in HealthOmics RESTRICTED
    networking mode.
    """
    endpoint = f"s3tables.{region}.amazonaws.com"
    try:
        # TCP connectivity check on port 443
        sock = socket.create_connection((endpoint, 443), timeout=CONNECT_TIMEOUT)
        sock.close()
        return {
            "endpoint": "s3tables",
            "passed": True,
            "message": f"S3 Tables REST endpoint reachable at {endpoint}.",
        }
    except (socket.timeout, socket.gaierror, OSError) as e:
        return {
            "endpoint": "s3tables",
            "passed": False,
            "message": (
                f"Cannot reach S3 Tables endpoint {endpoint}: {e}. "
                "S3 Tables requires VPC-connected workflow runs. "
                "Ensure the run uses networking_mode=VPC with a configuration "
                "that has private subnets routed through a NAT Gateway."
            ),
        }


def check_s3_connectivity(region: str) -> dict:
    """
    Check connectivity to Amazon S3.

    S3 is required for reading VCF input files and writing Iceberg data files.
    In HealthOmics RESTRICTED mode, same-region S3 is accessible by default.
    In VPC mode, S3 access goes through the VPC — use a Gateway endpoint for
    best performance and cost.
    """
    try:
        s3 = boto3.client("s3", region_name=region)
        # Lightweight probe — list buckets (limit 1)
        s3.list_buckets(MaxBuckets=1)
        return {
            "endpoint": "s3",
            "passed": True,
            "message": f"S3 reachable in {region}.",
        }
    except ClientError:
        # Access denied still means the endpoint is reachable
        return {
            "endpoint": "s3",
            "passed": True,
            "message": f"S3 reachable in {region} (permissions checked separately).",
        }
    except (EndpointConnectionError, ConnectTimeoutError) as e:
        return {
            "endpoint": "s3",
            "passed": False,
            "message": (
                f"Cannot reach S3 in {region}: {e}. "
                "Add a com.amazonaws.{region}.s3 Gateway VPC endpoint for "
                "best performance and cost."
            ),
        }
    except Exception as e:
        return {
            "endpoint": "s3",
            "passed": False,
            "message": f"S3 connectivity check failed: {e}",
        }


def check_connectivity(catalog_config: dict) -> dict:
    """
    Run all connectivity checks relevant to the catalog type.

    Args:
        catalog_config: Full catalog configuration dict (from setup_catalog output)

    Returns:
        dict with keys: status, catalog_type, checks, passed, failures, guidance
    """
    catalog_type = catalog_config.get("catalog_type", "")
    inner_config = catalog_config.get("catalog_config", catalog_config)
    region = inner_config.get("region") or inner_config.get("client.region", "us-east-1")

    checks = []

    # STS is always required
    checks.append(check_sts_connectivity())

    if catalog_type == "vanilla":
        checks.append(check_glue_connectivity(region))
        checks.append(check_lakeformation_connectivity(region))
        checks.append(check_s3_connectivity(region))
    elif catalog_type == "s3tables":
        checks.append(check_s3tables_connectivity(region))
        checks.append(check_s3_connectivity(region))
    else:
        # Unknown type — check everything
        checks.append(check_glue_connectivity(region))
        checks.append(check_s3tables_connectivity(region))
        checks.append(check_s3_connectivity(region))

    failures = [c for c in checks if not c["passed"]]
    passed = len(failures) == 0

    guidance = None
    if not passed:
        guidance = (
            "This workflow requires VPC-connected runs in AWS HealthOmics. "
            "When starting the run, set networking_mode=VPC and provide a "
            "configuration_name that references an ACTIVE HealthOmics Configuration "
            "with private subnets routed through a NAT Gateway. "
            "See the HealthOmics VPC documentation for setup instructions."
        )

    return {
        "status": "passed" if passed else "failed",
        "catalog_type": catalog_type,
        "region": region,
        "checks": checks,
        "passed": passed,
        "failures": [f["message"] for f in failures],
        "guidance": guidance,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check network connectivity for HealthOmics VCF Loader"
    )
    parser.add_argument(
        "--catalog-config", required=True,
        help="Path to catalog_config.json from setupCatalog"
    )
    parser.add_argument("--output", help="Output JSON file")

    args = parser.parse_args()

    # Load catalog config
    with open(args.catalog_config) as f:
        config = json.load(f)

    result = check_connectivity(config)

    output_json = json.dumps(result, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)

    # Print report
    print(output_json)

    if not result["passed"]:
        print("\n=== CONNECTIVITY FAILURES ===", file=sys.stderr)
        for msg in result["failures"]:
            print(f"  ✗ {msg}", file=sys.stderr)
        if result.get("guidance"):
            print(f"\n  ℹ {result['guidance']}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
