#!/usr/bin/env python3
"""
Table initialization module for HealthOmics GFF3 Annotation Loader workflow.

Creates Iceberg tables if they don't exist based on the selected schema.
"""

import sys
import json
import argparse
import importlib
from pyiceberg.catalog import load_catalog
from utils import create_namespace


SCHEMA_NAMESPACES = {
    '1': 'annotation_db',
    '2': 'annotation_db_2',
}


def load_schema_module(schema):
    if schema not in ['1', '2']:
        raise ValueError(f"Invalid schema: {schema}. Must be 1 or 2")
    return importlib.import_module(f"schema_{schema}")


def connect_to_catalog(catalog_config):
    catalog_type = catalog_config.get('type')
    if not catalog_type:
        raise ValueError("Catalog configuration missing 'type' field")
    config_params = {k: v for k, v in catalog_config.items() if k != 'namespace'}
    catalog_name = 's3tables' if catalog_type == 'rest' else 'glue'
    return load_catalog(catalog_name, **config_params)


def initialize_tables(catalog_config, schema, namespace=None):
    schema_module = load_schema_module(schema)

    if not namespace:
        namespace = SCHEMA_NAMESPACES.get(schema)
        if not namespace:
            raise ValueError(f"No default namespace for schema {schema}")

    catalog = connect_to_catalog(catalog_config)

    try:
        create_namespace(catalog, namespace)
    except Exception as e:
        print(f"Namespace creation: {e}")

    # Determine expected tables
    if schema == '1':
        expected_tables = ['features', 'sources', 'feature_relationships']
    elif schema == '2':
        expected_tables = ['genomic_annotations']
    else:
        raise ValueError(f"Invalid schema: {schema}")

    tables_created = []
    tables_existing = []
    table_metadata = {}

    for table_name in expected_tables:
        table_identifier = f"{namespace}.{table_name}"
        if catalog.table_exists(table_identifier):
            print(f"Table {table_identifier} already exists.")
            tables_existing.append(table_name)
            table = catalog.load_table(table_identifier)
            table_metadata[table_name] = {
                'location': table.location(), 'status': 'existing'
            }

    if len(tables_existing) < len(expected_tables):
        print(f"Creating missing tables in namespace {namespace}...")
        created_tables = schema_module.create_schema_tables(catalog, namespace)
        for table_name, table in created_tables.items():
            if table_name not in tables_existing:
                tables_created.append(table_name)
                table_metadata[table_name] = {
                    'location': table.location(), 'status': 'created'
                }

    return {
        'status': 'success', 'schema': schema, 'namespace': namespace,
        'tables_created': tables_created, 'tables_existing': tables_existing,
        'table_metadata': table_metadata, 'all_tables': expected_tables,
    }


def main():
    parser = argparse.ArgumentParser(description='Initialize Iceberg tables for GFF3 Annotation Loader')
    parser.add_argument('--catalog-config', required=True, help='Path to catalog configuration JSON')
    parser.add_argument('--schema', required=True, choices=['1', '2'], help='Schema selection')
    parser.add_argument('--namespace', help='Iceberg namespace override')
    parser.add_argument('--output', help='Output JSON file')
    args = parser.parse_args()

    try:
        with open(args.catalog_config, 'r') as f:
            catalog_data = json.load(f)
        catalog_config = catalog_data.get('catalog_config', catalog_data)
        result = initialize_tables(catalog_config, args.schema, args.namespace)
        output_json = json.dumps(result, indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_json)
            print(f"Table initialization successful. Results written to {args.output}")
        else:
            print(output_json)
        sys.exit(0)
    except Exception as e:
        error_result = {'status': 'error', 'error': str(e), 'error_type': type(e).__name__}
        output_json = json.dumps(error_result, indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_json)
        print(output_json, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
