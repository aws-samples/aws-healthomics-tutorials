#!/usr/bin/env python3
"""
Script to load VCF or GVCF files into the variant_db_2 tables created by schema_2.py.
This script parses VCF/GVCF files and loads the data into the two Iceberg tables:
- samples
- variant_regions
"""

import argparse
import os
import sys
import uuid
import pyarrow as pa
from pyiceberg.exceptions import NoSuchTableError
from utils import load_s3_tables_catalog, retry_operation, convert_uuids_to_arrow_array
import gzip

# Configuration
NAMESPACE = "variant_db_2"
SAMPLES_TABLE = "samples"
VARIANT_REGIONS_TABLE = "variant_regions"
BATCH_SIZE = 100000  # Number of records to process before writing to the table


def get_tables():
    """Get the existing tables or fail if they don't exist."""
    # Load the catalog using the utility function
    catalog = load_s3_tables_catalog(bucket_arn)
    tables = {}

    # Check if namespace exists
    try:
        namespaces = [ns[0] for ns in catalog.list_namespaces()]
        if NAMESPACE not in namespaces:
            raise ValueError(f"Namespace '{NAMESPACE}' does not exist.")
    except Exception as e:
        print(f"Error checking namespaces: {e}")
        raise  # Re-raise the exception instead of sys.exit(1)

    # Check if tables exist
    for table_name in [SAMPLES_TABLE, VARIANT_REGIONS_TABLE]:
        table_identifier = f"{NAMESPACE}.{table_name}"
        try:
            tables[table_name] = catalog.load_table(table_identifier)
        except NoSuchTableError:
            raise ValueError(f"Table '{table_identifier}' does not exist.")
        except Exception as e:
            print(f"Error loading table {table_identifier}: {e}")
            raise  # Re-raise the exception instead of sys.exit(1)

    return tables


def open_vcf_file(file_path):
    """Open a VCF file, handling gzipped files automatically."""
    if file_path.endswith('.gz') or file_path.endswith('.bgz'):
        return gzip.open(file_path, 'rt', encoding='utf-8', errors='replace')
    else:
        return open(file_path, 'r', encoding='utf-8', errors='replace')


def parse_vcf_header(vcf_file):
    """Parse the VCF header to extract format and sample information."""
    samples = []
    info_fields = {}
    format_fields = {}

    for line in vcf_file:
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # End of header
        if line.startswith('#CHROM'):
            # Extract sample names from the header line
            header_fields = line.split('\t')
            if len(header_fields) > 9:  # VCF has samples
                samples = header_fields[9:]
            break

        # Parse INFO field definitions
        elif line.startswith('##INFO='):
            info_def = line[8:-1]  # Remove ##INFO=< and >
            info_parts = info_def.split(',', 3)
            info_id = info_parts[0].split('=')[1]
            info_fields[info_id] = {
                'id': info_id,
                'type': info_parts[2].split('=')[1]
            }

        # Parse FORMAT field definitions
        elif line.startswith('##FORMAT='):
            format_def = line[10:-1]  # Remove ##FORMAT=< and >
            format_parts = format_def.split(',', 3)
            format_id = format_parts[0].split('=')[1]
            format_fields[format_id] = {
                'id': format_id,
                'type': format_parts[2].split('=')[1]
            }

    return samples, info_fields, format_fields


def parse_info_field(info_str):
    """Parse the INFO field from a VCF record."""
    if info_str == '.':
        return {}

    info_dict = {}
    for item in info_str.split(';'):
        if '=' in item:
            key, value = item.split('=', 1)
            info_dict[key] = value
        else:
            info_dict[item] = 'true'

    return info_dict


def parse_format_field(format_str, sample_str):
    """Parse the FORMAT and sample fields from a VCF record."""
    if format_str == '.' or sample_str == '.':
        return {}

    format_keys = format_str.split(':')
    sample_values = sample_str.split(':')

    # Handle cases where sample values might be missing
    if len(sample_values) < len(format_keys):
        sample_values.extend(['.' for _ in range(len(format_keys) - len(sample_values))])

    return dict(zip(format_keys, sample_values))


def process_samples(samples, sample_name=None):
    """Process samples and return data for the samples table."""
    # If sample_name is provided, use it instead of samples from VCF
    if sample_name and sample_name not in samples:
        samples = [sample_name]
    elif not samples:
        # If no samples in VCF and none provided, use a default
        sample_name = "unknown_sample"
        samples = [sample_name]

    # Generate UUIDs for each sample
    sample_ids = [str(uuid.uuid4()) for _ in samples]
    sample_id_dict = dict(zip(samples, sample_ids))

    # Create PyArrow arrays for the samples table
    sample_id_array = pa.array(sample_ids, type=pa.string())
    sample_name_array = pa.array(samples, type=pa.string())
    # Empty metadata for now
    metadata_array = pa.array([{} for _ in samples], type=pa.map_(pa.string(), pa.string()))

    return {
        'sample_ids': sample_id_dict,
        'arrays': {
            'sample_id': sample_id_array,
            'sample_name': sample_name_array,
            'metadata': metadata_array
        }
    }


def process_vcf_batch(batch_records, sample_id_dict):
    """Process a batch of VCF records and return data for variant_regions table."""
    # Lists to hold column data for variant_regions table
    chrom_list = []
    pos_list = []
    ref_list = []
    alt_list = []
    qual_list = []
    filter_list = []
    info_list = []
    sample_ids_list = []
    sample_genotypes_list = []
    is_reference_block_list = []

    # Process each record in the batch
    for fields in batch_records:
        # Extract basic fields
        chrom = fields[0]
        pos = int(fields[1])
        ref = fields[3]
        alt = fields[4]
        if alt == '.':
            alt = ''  # Handle no alternate allele

        # Handle quality
        qual = None
        if fields[5] != '.':
            try:
                qual = float(fields[5])
            except ValueError:
                print(f"Warning: Invalid quality value: {fields[5]}")

        # Handle filter
        filter_val = fields[6]
        if filter_val == '.':
            filter_val = None

        # Parse INFO field
        info_dict = parse_info_field(fields[7])

        # Determine if this is a reference block (used in GVCFs)
        is_reference_block = 'END' in info_dict

        # Create sample_ids and sample_genotypes maps
        sample_ids_map = {}
        sample_genotypes_map = {}
        
        # Process each sample for this variant
        format_str = fields[8] if len(fields) > 8 else None
        
        for sample_idx, (sample_name, sample_id) in enumerate(sample_id_dict.items()):
            # Parse genotype and format fields if available
            if format_str and len(fields) > 9 + sample_idx:
                sample_str = fields[9 + sample_idx]
                attributes = parse_format_field(format_str, sample_str)
                
                # Extract genotype
                genotype = attributes.get('GT', './.')
                
                # Add to maps
                sample_ids_map[sample_id] = sample_name
                sample_genotypes_map[sample_id] = genotype
            else:
                # If no format or sample data, add with default values
                sample_ids_map[sample_id] = sample_name
                sample_genotypes_map[sample_id] = './.'

        # Add to variant_regions table data
        chrom_list.append(chrom)
        pos_list.append(pos)
        ref_list.append(ref)
        alt_list.append(alt)
        qual_list.append(qual)
        filter_list.append(filter_val)
        info_list.append(info_dict)
        sample_ids_list.append(sample_ids_map)
        sample_genotypes_list.append(sample_genotypes_map)
        is_reference_block_list.append(is_reference_block)

    # Convert Python lists to PyArrow arrays for variant_regions table
    chrom_array = pa.array(chrom_list, type=pa.string())
    pos_array = pa.array(pos_list, type=pa.int64())
    ref_array = pa.array(ref_list, type=pa.string())
    alt_array = pa.array(alt_list, type=pa.string())
    qual_array = pa.array(qual_list, type=pa.float64())
    filter_array = pa.array(filter_list, type=pa.string())
    info_map_array = pa.array([{str(k): str(v) for k, v in d.items()} for d in info_list],
                              type=pa.map_(pa.string(), pa.string()))
    sample_ids_map_array = pa.array([{str(k): str(v) for k, v in d.items()} for d in sample_ids_list],
                                    type=pa.map_(pa.string(), pa.string()))
    sample_genotypes_map_array = pa.array([{str(k): str(v) for k, v in d.items()} for d in sample_genotypes_list],
                                          type=pa.map_(pa.string(), pa.string()))
    is_reference_block_array = pa.array(is_reference_block_list, type=pa.bool_())

    return {
        'chrom': chrom_array,
        'pos': pos_array,
        'ref': ref_array,
        'alt': alt_array,
        'qual': qual_array,
        'filter': filter_array,
        'info': info_map_array,
        'sample_ids': sample_ids_map_array,
        'sample_genotypes': sample_genotypes_map_array,
        'is_reference_block': is_reference_block_array
    }


def process_vcf_file(vcf_path, sample_name=None, tables=None, pyarrow_schemas=None):
    """Process a VCF file in batches and write to Iceberg tables."""
    print(f"Processing VCF file: {vcf_path}")

    # Open and parse the VCF file
    with open_vcf_file(vcf_path) as vcf_file:
        # Parse header to get samples
        samples, info_fields, format_fields = parse_vcf_header(vcf_file)

        # If sample_name is provided but not in VCF, handle appropriately
        if sample_name and sample_name not in samples:
            print(f"Warning: Sample '{sample_name}' not found in VCF. Available samples: {samples}")
            if not samples:
                print("No samples found in VCF. Using provided sample name.")
                samples = [sample_name]
            else:
                print(f"Using first sample: {samples[0]}")
                sample_name = samples[0]
        elif not samples:
            # If no samples in VCF and none provided, use filename as sample name
            sample_name = os.path.basename(vcf_path).split('.')[0]
            print(f"No samples found in VCF. Using filename as sample name: {sample_name}")
            samples = [sample_name]

        # Process samples first
        sample_data = process_samples(samples, sample_name)
        
        # Write samples to the samples table if tables are provided
        if tables and pyarrow_schemas:
            samples_table = pa.Table.from_arrays([
                sample_data['arrays']['sample_id'],
                sample_data['arrays']['sample_name'],
                sample_data['arrays']['metadata']
            ], schema=pyarrow_schemas[SAMPLES_TABLE])
            
            print(f"Writing {len(samples_table)} samples to {NAMESPACE}.{SAMPLES_TABLE}...")
            retry_operation(
                tables[SAMPLES_TABLE].append,
                samples_table,
                max_retries=5,
                retry_condition=lambda e: "CommitFailedException" in str(e) and "branch main has changed" in str(e)
            )
            print(f"Successfully wrote samples to {NAMESPACE}.{SAMPLES_TABLE}")

        # Process VCF records in batches
        batch_records = []
        records_processed = 0

        for line in vcf_file:
            if line.startswith('#'):
                continue
            fields = line.strip().split('\t')
            if len(fields) < 8:
                print(f"Warning: Invalid VCF record (not enough fields): {line}")
                continue

            batch_records.append(fields)

            # When batch size is reached, process the batch
            if len(batch_records) >= BATCH_SIZE:
                data = process_vcf_batch(batch_records, sample_data['sample_ids'])

                if tables and pyarrow_schemas:
                    # Write variant regions to the variant_regions table
                    variant_regions_table = pa.Table.from_arrays([
                        data['chrom'],
                        data['pos'],
                        data['ref'],
                        data['alt'],
                        data['qual'],
                        data['filter'],
                        data['info'],
                        data['sample_ids'],
                        data['sample_genotypes'],
                        data['is_reference_block']
                    ], schema=pyarrow_schemas[VARIANT_REGIONS_TABLE])
                    
                    print(f"Writing {len(variant_regions_table)} variant regions to {NAMESPACE}.{VARIANT_REGIONS_TABLE}...")
                    retry_operation(
                        tables[VARIANT_REGIONS_TABLE].append,
                        variant_regions_table,
                        max_retries=5,
                        retry_condition=lambda e: "CommitFailedException" in str(e) and "branch main has changed" in str(e)
                    )
                    
                    records_processed += len(batch_records)
                    print(f"Processed {records_processed} records so far...")
                else:
                    return data, sample_data

                # Clear the batch
                batch_records = []

        # Process any remaining records
        if batch_records:
            data = process_vcf_batch(batch_records, sample_data['sample_ids'])

            if tables and pyarrow_schemas:
                # Write variant regions to the variant_regions table
                variant_regions_table = pa.Table.from_arrays([
                    data['chrom'],
                    data['pos'],
                    data['ref'],
                    data['alt'],
                    data['qual'],
                    data['filter'],
                    data['info'],
                    data['sample_ids'],
                    data['sample_genotypes'],
                    data['is_reference_block']
                ], schema=pyarrow_schemas[VARIANT_REGIONS_TABLE])
                
                print(f"Writing {len(variant_regions_table)} variant regions to {NAMESPACE}.{VARIANT_REGIONS_TABLE}...")
                retry_operation(
                    tables[VARIANT_REGIONS_TABLE].append,
                    variant_regions_table,
                    max_retries=5,
                    retry_condition=lambda e: "CommitFailedException" in str(e) and "branch main has changed" in str(e)
                )
                
                records_processed += len(batch_records)
                print(f"Processed {records_processed} records total.")
                return None
            else:
                return data, sample_data

        return None


def main():
    """Main function to load VCF/GVCF data into the Iceberg tables."""
    global bucket_arn, NAMESPACE, SAMPLES_TABLE, VARIANT_REGIONS_TABLE, BATCH_SIZE

    parser = argparse.ArgumentParser(description='Load VCF/GVCF files into Iceberg tables using schema_2.py')
    parser.add_argument('vcf_files', nargs='+', help='VCF or GVCF file paths to load')
    parser.add_argument('--sample', help='Sample name to use (overrides sample names in VCF)')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    parser.add_argument('--namespace', default=NAMESPACE, help=f'Iceberg namespace (default: {NAMESPACE})')
    parser.add_argument('--samples-table', default=SAMPLES_TABLE, help=f'Samples table name (default: {SAMPLES_TABLE})')
    parser.add_argument('--variant-regions-table', default=VARIANT_REGIONS_TABLE, 
                        help=f'Variant regions table name (default: {VARIANT_REGIONS_TABLE})')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                        help=f'Number of records to process before writing (default: {BATCH_SIZE})')

    args = parser.parse_args()
    bucket_arn = args.bucket_arn
    NAMESPACE = args.namespace
    SAMPLES_TABLE = args.samples_table
    VARIANT_REGIONS_TABLE = args.variant_regions_table
    BATCH_SIZE = args.batch_size

    print("Getting tables...")
    tables = get_tables()
    pyarrow_schemas = {
        table_name: table.schema().as_arrow() 
        for table_name, table in tables.items()
    }

    # Process each VCF file
    for vcf_file in args.vcf_files:
        if not os.path.exists(vcf_file):
            print(f"Error: File not found: {vcf_file}")
            continue

        try:
            # Process the file in batches and write directly to the tables
            process_vcf_file(vcf_file, args.sample, tables, pyarrow_schemas)
        except Exception as e:
            print(f"Error processing file {vcf_file}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
