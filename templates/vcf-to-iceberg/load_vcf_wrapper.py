#!/usr/bin/env python3
"""
Wrapper script to load VCF files into Iceberg tables.
This script accepts catalog configuration and delegates to the appropriate schema-specific loader.
"""

import argparse
import json
import sys
import os
from pyiceberg.catalog import load_catalog
from pyiceberg.exceptions import NoSuchTableError


def load_catalog_from_config(catalog_config):
    """Load an Iceberg catalog from configuration."""
    catalog_type = catalog_config.get('type')
    
    if catalog_type == 'rest':
        # S3 Tables catalog
        catalog = load_catalog(
            "s3tables",
            type="rest",
            warehouse=catalog_config['warehouse'],
            uri=catalog_config['uri'],
            **{k: v for k, v in catalog_config.items() if k.startswith('rest.')}
        )
    elif catalog_type == 'glue':
        # Vanilla Iceberg catalog via AWS Glue
        catalog = load_catalog(
            "glue",
            type="glue",
            warehouse=catalog_config['warehouse'],
            **{k: v for k, v in catalog_config.items() if k.startswith('client.') or k.startswith('glue.')}
        )
    else:
        raise ValueError(f"Unsupported catalog type: {catalog_type}")
    
    return catalog


def get_loader_module(schema):
    """Import and return the appropriate loader module based on schema selection."""
    if schema == '1':
        import load_vcf_schema1 as loader
        namespace = "variant_db"
        table_names = ["variants", "samples", "variant_samples"]
    elif schema == '2':
        import load_vcf_schema2 as loader
        namespace = "variant_db_2"
        table_names = ["variant_regions", "samples"]
    elif schema == '3':
        import load_vcf_schema3 as loader
        namespace = "variant_db_3"
        table_names = ["genomic_variants"]
    elif schema == '4':
        import load_vcf_schema4 as loader
        namespace = "variant_db_4"
        table_names = ["variants", "samples", "variant_samples"]
    else:
        raise ValueError(f"Invalid schema: {schema}")
    
    return loader, namespace, table_names


def load_tables(catalog, namespace, table_names):
    """Load existing tables from the catalog."""
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
    """Main function to load VCF data into Iceberg tables."""
    parser = argparse.ArgumentParser(description='Load VCF files into Iceberg tables')
    parser.add_argument('--vcf-file', required=True, help='Path to VCF file')
    parser.add_argument('--catalog-config', required=True, help='Path to catalog configuration JSON file')
    parser.add_argument('--schema', required=True, choices=['1', '2', '3', '4'], help='Schema selection (1, 2, 3, or 4)')
    parser.add_argument('--namespace', help='Iceberg namespace (optional, defaults based on schema)')
    parser.add_argument('--batch-size', type=int, default=100000, help='Batch size for processing (default: 100000)')
    parser.add_argument('--output', default='load_stats.json', help='Output file for statistics (default: load_stats.json)')
    
    args = parser.parse_args()
    
    # Load catalog configuration
    with open(args.catalog_config, 'r') as f:
        catalog_data = json.load(f)
    
    # Extract inner catalog_config if nested (setup_catalog outputs nested structure)
    if 'catalog_config' in catalog_data:
        catalog_config = catalog_data['catalog_config']
    else:
        catalog_config = catalog_data
    
    # Load the catalog
    print("Loading catalog...")
    catalog = load_catalog_from_config(catalog_config)
    
    # Get the appropriate loader module
    print(f"Loading schema {args.schema} loader module...")
    loader, default_namespace, table_names = get_loader_module(args.schema)
    
    # Use provided namespace or default
    namespace = args.namespace if args.namespace else default_namespace
    
    # Load existing tables
    print(f"Loading tables from namespace '{namespace}'...")
    tables, pyarrow_schemas = load_tables(catalog, namespace, table_names)
    
    # Override the loader's global variables if needed
    if hasattr(loader, 'NAMESPACE'):
        loader.NAMESPACE = namespace
    if hasattr(loader, 'BATCH_SIZE'):
        loader.BATCH_SIZE = args.batch_size
    
    # Track statistics by wrapping the loader's functions
    stats = {
        'vcf_file': args.vcf_file,
        'schema': args.schema,
        'namespace': namespace,
        'batch_size': args.batch_size,
        'variants_loaded': 0,
        'samples_loaded': 0,
        'variant_sample_associations': 0,
        'batches_processed': 0
    }
    
    # Create wrapper functions to track statistics
    original_append_funcs = {}
    
    def create_tracking_append(table_name, original_append):
        """Create a wrapper for table.append that tracks statistics."""
        def tracking_append(arrow_table):
            result = original_append(arrow_table)
            row_count = len(arrow_table)
            
            # Track statistics based on table name
            if table_name in ['variants', 'variant_regions', 'genomic_variants']:
                stats['variants_loaded'] += row_count
                stats['batches_processed'] += 1
            elif table_name == 'samples':
                stats['samples_loaded'] += row_count
            elif table_name == 'variant_samples':
                stats['variant_sample_associations'] += row_count
            
            return result
        return tracking_append
    
    # Wrap the append methods to track statistics
    for table_name, table in tables.items():
        original_append_funcs[table_name] = table.append
        table.append = create_tracking_append(table_name, table.append)
    
    # Process the VCF file
    print(f"Processing VCF file: {args.vcf_file}")
    try:
        # Call the loader's process_vcf_file function
        # The function signature varies by schema, but all accept vcf_path, sample_name, tables, pyarrow_schemas
        loader.process_vcf_file(
            vcf_path=args.vcf_file,
            sample_name=None,
            tables=tables,
            pyarrow_schemas=pyarrow_schemas
        )
        
        print("VCF loading completed successfully.")
        
    except Exception as e:
        print(f"Error processing VCF file: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Restore original append methods
        for table_name, table in tables.items():
            table.append = original_append_funcs[table_name]
    
    # Write statistics to output file
    with open(args.output, 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"Statistics written to {args.output}")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
