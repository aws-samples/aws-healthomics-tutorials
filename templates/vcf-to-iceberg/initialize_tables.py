#!/usr/bin/env python3
"""
Table initialization module for HealthOmics VCF Loader workflow.

This module creates Iceberg tables if they don't exist based on the selected schema.
It handles:
- Loading the appropriate schema module (schema_1, schema_2, schema_3, or schema_4)
- Connecting to the catalog using provided configuration
- Creating namespace if it doesn't exist
- Checking if tables exist
- Creating tables if they don't exist
- Verifying schema matches expected schema if tables exist
- Returning list of tables created and metadata as JSON

Outputs table initialization results as JSON.
"""

import sys
import json
import argparse
import importlib
from typing import Dict, List, Any
from pyiceberg.catalog import Catalog, load_catalog
from pyiceberg.table import Table
from pyiceberg.schema import Schema
from pyiceberg.partitioning import PartitionSpec
from pyiceberg.table.sorting import SortOrder
from utils import create_namespace


# Namespace mapping for each schema
SCHEMA_NAMESPACES = {
    '1': 'variant_db',
    '2': 'variant_db_2',
    '3': 'variant_db_3',
    '4': 'variant_db_4'
}


def load_schema_module(schema: str):
    """
    Load the appropriate schema module based on schema selection.
    
    Args:
        schema: Schema selection ('1', '2', '3', or '4')
        
    Returns:
        Imported schema module
        
    Raises:
        ValueError: If schema is invalid
        ImportError: If schema module cannot be loaded
    """
    if schema not in ['1', '2', '3', '4']:
        raise ValueError(f"Invalid schema: {schema}. Must be 1, 2, 3, or 4")
    
    module_name = f"schema_{schema}"
    
    try:
        schema_module = importlib.import_module(module_name)
        return schema_module
    except ImportError as e:
        raise ImportError(f"Failed to load schema module {module_name}: {e}")


def connect_to_catalog(catalog_config: dict) -> Catalog:
    """
    Connect to Iceberg catalog using provided configuration.
    
    Args:
        catalog_config: Dictionary containing catalog configuration
        
    Returns:
        Connected Catalog instance
        
    Raises:
        Exception: If catalog connection fails
    """
    catalog_type = catalog_config.get('type')
    
    if not catalog_type:
        raise ValueError("Catalog configuration missing 'type' field")
    
    # Extract catalog configuration parameters
    config_params = {k: v for k, v in catalog_config.items() if k != 'namespace'}
    
    try:
        # Load catalog with appropriate name based on type
        catalog_name = 's3tables' if catalog_type == 'rest' else 'glue'
        catalog = load_catalog(catalog_name, **config_params)
        return catalog
    except Exception as e:
        raise Exception(f"Failed to connect to catalog: {e}")


def get_table_schema_info(table: Table) -> dict:
    """
    Extract schema information from a table for comparison.
    
    Args:
        table: Iceberg Table instance
        
    Returns:
        Dictionary containing schema information
    """
    schema = table.schema()
    partition_spec = table.spec()
    sort_order = table.sort_order()
    
    return {
        'fields': [{'id': field.field_id, 'name': field.name, 'type': str(field.field_type)} 
                   for field in schema.fields],
        'partition_fields': [{'source_id': field.source_id, 'name': field.name, 
                             'transform': str(field.transform)} 
                            for field in partition_spec.fields] if partition_spec else [],
        'sort_fields': [{'source_id': field.source_id, 'direction': str(field.direction)} 
                       for field in sort_order.fields] if sort_order else []
    }


def compare_schemas(existing_schema_info: dict, expected_schema: Schema, 
                   expected_partition_spec: PartitionSpec = None,
                   expected_sort_order: SortOrder = None) -> tuple[bool, List[str]]:
    """
    Compare existing table schema with expected schema.
    
    Args:
        existing_schema_info: Schema information from existing table
        expected_schema: Expected Schema object
        expected_partition_spec: Expected PartitionSpec object (optional)
        expected_sort_order: Expected SortOrder object (optional)
        
    Returns:
        Tuple of (matches: bool, differences: List[str])
    """
    differences = []
    
    # Compare fields
    existing_fields = {f['name']: f for f in existing_schema_info['fields']}
    expected_fields = {field.name: field for field in expected_schema.fields}
    
    # Check for missing or extra fields
    existing_names = set(existing_fields.keys())
    expected_names = set(expected_fields.keys())
    
    if existing_names != expected_names:
        missing = expected_names - existing_names
        extra = existing_names - expected_names
        if missing:
            differences.append(f"Missing fields: {missing}")
        if extra:
            differences.append(f"Extra fields: {extra}")
    
    # Compare field types for common fields
    for name in existing_names & expected_names:
        existing_type = existing_fields[name]['type']
        expected_type = str(expected_fields[name].field_type)
        if existing_type != expected_type:
            differences.append(f"Field '{name}' type mismatch: {existing_type} vs {expected_type}")
    
    # Compare partition specs
    if expected_partition_spec:
        existing_partitions = {p['name']: p for p in existing_schema_info['partition_fields']}
        expected_partitions = {field.name: field for field in expected_partition_spec.fields}
        
        existing_partition_names = set(existing_partitions.keys())
        expected_partition_names = set(expected_partitions.keys())
        
        if existing_partition_names != expected_partition_names:
            differences.append(f"Partition spec mismatch: {existing_partition_names} vs {expected_partition_names}")
    
    # Compare sort orders
    if expected_sort_order and expected_sort_order.fields:
        if len(existing_schema_info['sort_fields']) != len(expected_sort_order.fields):
            differences.append(f"Sort order field count mismatch: {len(existing_schema_info['sort_fields'])} vs {len(expected_sort_order.fields)}")
    
    return (len(differences) == 0, differences)


def initialize_tables(catalog_config: dict, schema: str, namespace: str = None) -> dict:
    """
    Initialize Iceberg tables based on schema selection.
    
    Args:
        catalog_config: Dictionary containing catalog configuration
        schema: Schema selection ('1', '2', '3', or '4')
        namespace: Optional namespace override (uses default if not provided)
        
    Returns:
        Dictionary containing initialization results
        
    Raises:
        ValueError: If schema is invalid or configuration is missing
        Exception: If table creation or verification fails
    """
    # Load schema module
    schema_module = load_schema_module(schema)
    
    # Determine namespace
    if not namespace:
        namespace = SCHEMA_NAMESPACES.get(schema)
        if not namespace:
            raise ValueError(f"No default namespace for schema {schema}")
    
    # Connect to catalog
    catalog = connect_to_catalog(catalog_config)
    
    # Create namespace if it doesn't exist
    try:
        create_namespace(catalog, namespace)
    except Exception as e:
        # Log but don't fail if namespace already exists
        print(f"Namespace creation: {e}")
    
    # Get expected table definitions from schema module
    # Each schema module has a create_schema_tables function that returns a dict of tables
    # We need to check what tables should exist
    
    # Determine expected tables based on schema
    if schema == '1':
        expected_tables = ['variants', 'samples', 'variant_samples']
        table_schemas = {
            'variants': (schema_module.variants_schema, 
                        schema_module.variants_partition_spec, 
                        schema_module.variants_sort_order),
            'samples': (schema_module.samples_schema, None, None),
            'variant_samples': (schema_module.variant_samples_schema,
                              schema_module.variant_samples_partition_spec,
                              schema_module.variant_samples_sort_order)
        }
    elif schema == '2':
        expected_tables = ['variant_regions', 'samples']
        table_schemas = {
            'variant_regions': (schema_module.variant_regions_schema,
                              schema_module.variant_regions_partition_spec,
                              schema_module.variant_regions_sort_order),
            'samples': (schema_module.samples_schema, None, None)
        }
    elif schema == '3':
        expected_tables = ['genomic_variants']
        table_schemas = {
            'genomic_variants': (schema_module.genomic_variants_schema,
                               schema_module.genomic_variants_partition_spec,
                               schema_module.genomic_variants_sort_order)
        }
    elif schema == '4':
        expected_tables = ['variants', 'samples', 'variant_samples']
        table_schemas = {
            'variants': (schema_module.variants_schema,
                        schema_module.variants_partition_spec,
                        None),
            'samples': (schema_module.samples_schema, None, None),
            'variant_samples': (schema_module.variant_samples_schema,
                              schema_module.variant_samples_partition_spec,
                              None)
        }
    else:
        raise ValueError(f"Invalid schema: {schema}")
    
    # Check which tables exist and which need to be created
    tables_created = []
    tables_existing = []
    tables_verified = []
    table_metadata = {}
    schema_mismatches = []
    
    for table_name in expected_tables:
        table_identifier = f"{namespace}.{table_name}"
        
        if catalog.table_exists(table_identifier):
            # Table exists - verify schema
            print(f"Table {table_identifier} already exists, verifying schema...")
            tables_existing.append(table_name)
            
            try:
                table = catalog.load_table(table_identifier)
                existing_schema_info = get_table_schema_info(table)
                
                expected_schema, expected_partition_spec, expected_sort_order = table_schemas[table_name]
                
                matches, differences = compare_schemas(
                    existing_schema_info,
                    expected_schema,
                    expected_partition_spec,
                    expected_sort_order
                )
                
                if matches:
                    print(f"Table {table_identifier} schema matches expected schema")
                    tables_verified.append(table_name)
                    table_metadata[table_name] = {
                        'location': table.location(),
                        'status': 'verified',
                        'schema_match': True
                    }
                else:
                    print(f"WARNING: Table {table_identifier} schema mismatch: {differences}")
                    schema_mismatches.append({
                        'table': table_name,
                        'differences': differences
                    })
                    table_metadata[table_name] = {
                        'location': table.location(),
                        'status': 'schema_mismatch',
                        'schema_match': False,
                        'differences': differences
                    }
            except Exception as e:
                print(f"Error verifying table {table_identifier}: {e}")
                table_metadata[table_name] = {
                    'status': 'verification_error',
                    'error': str(e)
                }
        else:
            # Table doesn't exist - will be created
            print(f"Table {table_identifier} does not exist")
    
    # If any schema mismatches, fail with error
    if schema_mismatches:
        error_msg = "Schema mismatch detected for existing tables:\n"
        for mismatch in schema_mismatches:
            error_msg += f"  {mismatch['table']}: {mismatch['differences']}\n"
        raise Exception(error_msg)
    
    # Create tables that don't exist
    if len(tables_existing) < len(expected_tables):
        print(f"Creating missing tables in namespace {namespace}...")
        created_tables = schema_module.create_schema_tables(catalog, namespace)
        
        for table_name, table in created_tables.items():
            if table_name not in tables_existing:
                tables_created.append(table_name)
                table_metadata[table_name] = {
                    'location': table.location(),
                    'status': 'created',
                    'schema_match': True
                }
    
    # Build result
    result = {
        'status': 'success',
        'schema': schema,
        'namespace': namespace,
        'tables_created': tables_created,
        'tables_existing': tables_existing,
        'tables_verified': tables_verified,
        'table_metadata': table_metadata,
        'all_tables': expected_tables
    }
    
    return result


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description='Initialize Iceberg tables for HealthOmics VCF Loader workflow'
    )
    parser.add_argument('--catalog-config', required=True,
                       help='Path to catalog configuration JSON file')
    parser.add_argument('--schema', required=True,
                       choices=['1', '2', '3', '4'],
                       help='Schema selection (1, 2, 3, or 4)')
    parser.add_argument('--namespace',
                       help='Iceberg namespace (optional, uses default if not provided)')
    parser.add_argument('--output',
                       help='Output JSON file (default: stdout)')
    
    args = parser.parse_args()
    
    try:
        # Load catalog configuration
        with open(args.catalog_config, 'r') as f:
            catalog_data = json.load(f)
        
        # Extract catalog_config from the result
        if 'catalog_config' in catalog_data:
            catalog_config = catalog_data['catalog_config']
        else:
            catalog_config = catalog_data
        
        # Initialize tables
        result = initialize_tables(catalog_config, args.schema, args.namespace)
        
        # Output as JSON
        output_json = json.dumps(result, indent=2)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_json)
            print(f"Table initialization successful. Results written to {args.output}")
        else:
            print(output_json)
        
        sys.exit(0)
        
    except Exception as e:
        error_result = {
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__
        }
        
        output_json = json.dumps(error_result, indent=2)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_json)
        
        print(output_json, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
