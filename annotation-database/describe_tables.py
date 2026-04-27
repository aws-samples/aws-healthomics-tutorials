#!/usr/bin/env python3
"""
Script to describe Iceberg tables in all namespaces using PyIceberg and AWS S3Tables.
"""
import json
import traceback
from typing import Dict, List, Any
from pyiceberg.catalog import Catalog
from pyiceberg.table import Table
from utils import load_s3_tables_catalog


def describe_table(table: Table, identifier: tuple) -> Dict[str, Any]:
    """
    Generate a detailed description of an Iceberg table.
    
    Args:
        table: PyIceberg Table object
        identifier: Tuple containing namespace and table name
        
    Returns:
        Dictionary containing table details
    """
    table_info = {
        "name": identifier,
        "location": table.location(),
        "properties": table.properties,
        "schema": [],
        "current_snapshot_id": table.metadata.current_snapshot_id,
        "format_version": table.metadata.format_version,
    }
    
    # Add schema fields
    for field in table.schema().fields:
        field_info = {
            "id": field.field_id,
            "name": field.name,
            "type": str(field.field_type),
            "required": field.required,
        }
        if field.doc:
            field_info["doc"] = field.doc
        table_info["schema"].append(field_info)
    
    # Add partition information if available
    if table.spec() and table.spec().fields:
        table_info["partition_spec"] = []
        for field in table.spec().fields:
            table_info["partition_spec"].append({
                "source_id": field.source_id,
                "field_id": field.field_id,
                "name": field.name,
                "transform": str(field.transform),
            })
    
    # Add sort order if available
    if table.sort_order() and table.sort_order().fields:
        table_info["sort_order"] = []
        for field in table.sort_order().fields:
            table_info["sort_order"].append({
                "source_id": field.source_id,
                "transform": str(field.transform),
                "direction": str(field.direction),
                "null_order": str(field.null_order),
            })
    
    # Add snapshot information if available
    if table.metadata.snapshots:
        table_info["snapshots"] = []
        for snapshot in table.metadata.snapshots:
            try:
                # Create basic snapshot info with guaranteed attributes
                snapshot_info = {
                    "snapshot_id": snapshot.snapshot_id,
                    "timestamp_ms": snapshot.timestamp_ms,
                    "summary": {},
                }
                
                # Handle summary which could be a tuple, dict, or other type
                if hasattr(snapshot, 'summary') and snapshot.summary is not None:
                    if isinstance(snapshot.summary, dict):
                        # If it's a dictionary, convert values to strings
                        for key, value in snapshot.summary.items():
                            snapshot_info["summary"][key] = str(value)
                    elif isinstance(snapshot.summary, (tuple, list)):
                        # If it's a tuple or list, convert to a list of strings
                        snapshot_info["summary"]["values"] = [str(item) for item in snapshot.summary]
                    else:
                        # For any other type, just use string representation
                        snapshot_info["summary"]["value"] = str(snapshot.summary)
                
                # Handle manifest_list safely
                if hasattr(snapshot, 'manifest_list') and snapshot.manifest_list:
                    snapshot_info["manifest_list"] = str(snapshot.manifest_list)
                    
                table_info["snapshots"].append(snapshot_info)
            except Exception as e:
                # If there's an error processing a snapshot, add a placeholder with error info
                table_info["snapshots"].append({
                    "snapshot_id": getattr(snapshot, "snapshot_id", "unknown"),
                    "error": f"Error processing snapshot: {str(e)}"
                })
    
    return table_info


def list_tables(catalog: Catalog, namespace: str) -> List[str]:
    """
    List all tables in a namespace.
    
    Args:
        catalog: PyIceberg Catalog object
        namespace: Namespace to list tables from
        
    Returns:
        List of table identifiers
    """
    try:
        return catalog.list_tables(namespace)
    except Exception as e:
        print(f"Error listing tables in namespace {namespace}: {str(e)}")
        return []


def describe_tables_in_namespace(catalog: Catalog, namespace: str) -> None:
    """
    Describe all tables in a given namespace.
    
    Args:
        catalog: PyIceberg Catalog object
        namespace: Namespace to describe tables from
    """
    # List tables in the namespace
    print(f"\nListing tables in namespace: {namespace}")
    table_identifiers = list_tables(catalog, namespace)
    
    if not table_identifiers:
        print(f"No tables found in namespace {namespace}")
        return
    
    print(f"Found {len(table_identifiers)} tables in namespace {namespace}:")
    for identifier in table_identifiers:
        print(f"  - {identifier}")
    
    # Describe each table
    print("\nTable Details:")
    for identifier in table_identifiers:
        try:
            table = catalog.load_table(identifier)
            table_info = describe_table(table, identifier)
            
            print(f"\n{'-' * 80}")
            print(f"Table: {identifier}")
            print(f"{'-' * 80}")
            print(f"Location: {table_info['location']}")
            print(f"Format Version: {table_info['format_version']}")
            
            print("\nSchema:")
            for field in table_info['schema']:
                required = "required" if field['required'] else "optional"
                print(f"  - {field['name']} ({field['type']}, {required}, id={field['id']})")
                if 'doc' in field:
                    print(f"    Doc: {field['doc']}")
            
            if 'partition_spec' in table_info:
                print("\nPartition Spec:")
                for partition in table_info['partition_spec']:
                    print(f"  - {partition['name']} ({partition['transform']})")
            
            if 'sort_order' in table_info:
                print("\nSort Order:")
                for sort_field in table_info['sort_order']:
                    print(f"  - {sort_field['transform']} ({sort_field['direction']}, {sort_field['null_order']})")
            
            if 'snapshots' in table_info and table_info['snapshots']:
                for snapshot in table_info['snapshots']:
                    if 'error' in snapshot:
                        print(f"  - Error: {snapshot['error']}")
                        continue
                        
                    print(f"  - ID: {snapshot['snapshot_id']}, Time: {snapshot['timestamp_ms']}")
                    if snapshot['summary']:
                        try:
                            print(f"    Summary: {json.dumps(snapshot['summary'])}")
                        except Exception:
                            print(f"    Summary: {snapshot['summary']}")
            
            # Print record count if available in the latest snapshot
            if 'snapshots' in table_info and table_info['snapshots']:
                try:
                    latest_snapshot = table_info['snapshots'][-1]
                    if ('summary' in latest_snapshot and 
                        latest_snapshot['summary'] and 
                        'total-records' in latest_snapshot['summary']):
                        print(f"\nRecord Count: {latest_snapshot['summary']['total-records']}")
                except Exception:
                    pass  # Skip record count if there's an issue
            
        except Exception as e:
            print(f"Error describing table {identifier}: {str(e)}")
            # Uncomment for debugging
            # traceback.print_exc()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Describe all Iceberg tables in S3Tables catalog')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    args = parser.parse_args()
    
    # Load the S3Tables catalog
    print(f"Connecting to S3Tables catalog with bucket ARN: {args.bucket_arn}")
    catalog = load_s3_tables_catalog(args.bucket_arn)
    
    # List all namespaces
    print("Listing all namespaces:")
    namespaces = catalog.list_namespaces()
    
    if not namespaces:
        print("No namespaces found in the catalog")
        return
        
    for ns in namespaces:
        print(f"  - {ns}")
        
    # Iterate through each namespace and describe all tables
    for namespace in namespaces:
        # Handle both cases: when namespace is a tuple/list or when it's already a string
        if isinstance(namespace, (list, tuple)):
            namespace_str = ".".join(namespace)  # Convert namespace tuple to string
        else:
            namespace_str = str(namespace)  # Ensure it's a string
            
        print(f"\n{'=' * 80}")
        print(f"Namespace: {namespace_str}")
        print(f"{'=' * 80}")
        describe_tables_in_namespace(catalog, namespace_str)


if __name__ == "__main__":
    main()
