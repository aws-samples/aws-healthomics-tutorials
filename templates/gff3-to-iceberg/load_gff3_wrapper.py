#!/usr/bin/env python3
"""
Wrapper script to load GFF3 files into Iceberg tables.
Accepts catalog configuration and delegates to the appropriate schema-specific loader.
"""

import argparse
import json
import sys
from pyiceberg.catalog import load_catalog
from pyiceberg.exceptions import NoSuchTableError


def load_catalog_from_config(catalog_config):
    catalog_type = catalog_config.get('type')
    if catalog_type == 'rest':
        catalog = load_catalog(
            "s3tables", type="rest",
            warehouse=catalog_config['warehouse'],
            uri=catalog_config['uri'],
            **{k: v for k, v in catalog_config.items() if k.startswith('rest.')}
        )
    elif catalog_type == 'glue':
        catalog = load_catalog(
            "glue", type="glue",
            warehouse=catalog_config['warehouse'],
            **{k: v for k, v in catalog_config.items() if k.startswith('client.') or k.startswith('glue.')}
        )
    else:
        raise ValueError(f"Unsupported catalog type: {catalog_type}")
    return catalog


def get_loader_module(schema):
    if schema == '1':
        import load_gff3_schema1 as loader
        namespace = "annotation_db"
        table_names = ["features", "sources", "feature_relationships"]
    elif schema == '2':
        import load_gff3_schema2 as loader
        namespace = "annotation_db_2"
        table_names = ["genomic_annotations"]
    else:
        raise ValueError(f"Invalid schema: {schema}")
    return loader, namespace, table_names


def load_tables(catalog, namespace, table_names):
    tables = {}
    pyarrow_schemas = {}
    for table_name in table_names:
        table_identifier = f"{namespace}.{table_name}"
        try:
            table = catalog.load_table(table_identifier)
            tables[table_name] = table
            pyarrow_schemas[table_name] = table.schema().as_arrow()
        except NoSuchTableError:
            print(f"Error: Table '{table_identifier}' does not exist.")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading table {table_identifier}: {e}")
            sys.exit(1)
    return tables, pyarrow_schemas


def main():
    parser = argparse.ArgumentParser(description='Load GFF3 files into Iceberg tables')
    parser.add_argument('--gff3-file', required=True, help='Path to GFF3 file')
    parser.add_argument('--catalog-config', required=True, help='Path to catalog configuration JSON')
    parser.add_argument('--schema', required=True, choices=['1', '2'], help='Schema selection')
    parser.add_argument('--namespace', help='Iceberg namespace override')
    parser.add_argument('--batch-size', type=int, default=100000, help='Batch size (default: 100000)')
    parser.add_argument('--output', default='load_stats.json', help='Output stats file')
    args = parser.parse_args()

    with open(args.catalog_config, 'r') as f:
        catalog_data = json.load(f)
    catalog_config = catalog_data.get('catalog_config', catalog_data)

    print("Loading catalog...")
    catalog = load_catalog_from_config(catalog_config)

    print(f"Loading schema {args.schema} loader module...")
    loader, default_namespace, table_names = get_loader_module(args.schema)
    namespace = args.namespace if args.namespace else default_namespace

    print(f"Loading tables from namespace '{namespace}'...")
    tables, pyarrow_schemas = load_tables(catalog, namespace, table_names)

    if hasattr(loader, 'NAMESPACE'):
        loader.NAMESPACE = namespace
    if hasattr(loader, 'BATCH_SIZE'):
        loader.BATCH_SIZE = args.batch_size

    stats = {
        'gff3_file': args.gff3_file, 'schema': args.schema,
        'namespace': namespace, 'batch_size': args.batch_size,
        'features_loaded': 0, 'sources_loaded': 0,
        'relationships_loaded': 0, 'batches_processed': 0,
    }

    original_append_funcs = {}

    def create_tracking_append(table_name, original_append):
        def tracking_append(arrow_table):
            result = original_append(arrow_table)
            row_count = len(arrow_table)
            if table_name in ['features', 'genomic_annotations']:
                stats['features_loaded'] += row_count
                stats['batches_processed'] += 1
            elif table_name == 'sources':
                stats['sources_loaded'] += row_count
            elif table_name == 'feature_relationships':
                stats['relationships_loaded'] += row_count
            return result
        return tracking_append

    for table_name, table in tables.items():
        original_append_funcs[table_name] = table.append
        table.append = create_tracking_append(table_name, table.append)

    print(f"Processing GFF3 file: {args.gff3_file}")
    try:
        if args.schema == '1':
            loader.process_gff3_file(
                gff3_path=args.gff3_file, tables=tables, pyarrow_schemas=pyarrow_schemas)
        elif args.schema == '2':
            loader.process_gff3_file(
                gff3_path=args.gff3_file, table=tables['genomic_annotations'],
                pyarrow_schema=pyarrow_schemas['genomic_annotations'])
        print("GFF3 loading completed successfully.")
    except Exception as e:
        print(f"Error processing GFF3 file: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        for table_name, table in tables.items():
            table.append = original_append_funcs[table_name]

    with open(args.output, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"Statistics written to {args.output}")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
