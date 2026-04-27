#!/usr/bin/env python3
"""
Drop (purge) all tables in a specified namespace for an AWS S3Tables catalog.

Usage:
    python drop_tables.py --bucket-arn <bucket_arn> --namespace <namespace> [--confirm]

Arguments:
    --bucket-arn: The ARN of the S3Tables bucket
    --namespace: The namespace containing tables to drop
    --confirm: If provided, tables will be dropped without confirmation prompts
"""

import argparse
import sys
from typing import List

from utils import load_s3_tables_catalog


def list_tables(bucket_arn: str, namespace: str) -> List[str]:
    """
    List all tables in the specified namespace.
    
    Args:
        bucket_arn: The ARN of the S3Tables bucket
        namespace: The namespace to list tables from
        
    Returns:
        List of table names in the namespace
    """
    catalog = load_s3_tables_catalog(bucket_arn)
    
    # Check if namespace exists
    namespaces = catalog.list_namespaces()
    namespace_exists = False
    
    for ns in namespaces:
        # Handle both string and tuple namespaces
        if isinstance(ns, tuple) and len(ns) == 1 and ns[0] == namespace:
            namespace_exists = True
            break
        elif ns == namespace:
            namespace_exists = True
            break
    
    if not namespace_exists:
        print(f"Namespace '{namespace}' does not exist.")
        return []
    
    # List tables in the namespace
    tables = catalog.list_tables(namespace)
    return [table[1] for table in tables]  # Extract table names from (namespace, table_name) tuples


def drop_tables(bucket_arn: str, namespace: str, confirm: bool = False) -> None:
    """
    Drop all tables in the specified namespace.
    
    Args:
        bucket_arn: The ARN of the S3Tables bucket
        namespace: The namespace containing tables to drop
        confirm: If True, tables will be dropped without confirmation prompts
    """
    catalog = load_s3_tables_catalog(bucket_arn)
    
    # Get list of tables
    tables = list_tables(bucket_arn, namespace)
    
    if not tables:
        print(f"No tables found in namespace '{namespace}'.")
        return
    
    print(f"Found {len(tables)} tables in namespace '{namespace}':")
    for table in tables:
        print(f"  - {namespace}.{table}")
    
    # Confirm before dropping tables
    if not confirm:
        response = input(f"\nAre you sure you want to drop all {len(tables)} tables? (y/N): ")
        if response.lower() != 'y':
            print("Operation cancelled.")
            return
    
    # Drop each table
    for table in tables:
        try:
            full_table_name = f"{namespace}.{table}"
            # Use purge_table instead of drop_table for S3Tables
            if hasattr(catalog, 'purge_table'):
                catalog.purge_table(full_table_name)
            else:
                # Fall back to drop_table if purge_table is not available
                catalog.drop_table(full_table_name)
            print(f"Dropped table: {full_table_name}")
        except Exception as e:
            print(f"Error dropping table {full_table_name}: {str(e)}")


def main():
    parser = argparse.ArgumentParser(description="Drop all tables in a specified namespace")
    parser.add_argument("--bucket-arn", required=True, help="ARN of the S3Tables bucket")
    parser.add_argument("--namespace", required=True, help="Namespace containing tables to drop")
    parser.add_argument("--confirm", action="store_true", help="Drop tables without confirmation")
    
    args = parser.parse_args()
    
    try:
        drop_tables(args.bucket_arn, args.namespace, args.confirm)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
