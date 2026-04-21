#!/usr/bin/env python3
"""
Script to load VCF or GVCF files into the variant_db_4 Iceberg tables.
This script parses VCF/GVCF files and loads the data into the Iceberg tables created by schema_4.py.
"""

import argparse
import os
import sys
import uuid
import pyarrow as pa
from pyiceberg.exceptions import NoSuchTableError
from utils import load_s3_tables_catalog, retry_operation
import gzip

# Configuration
NAMESPACE = "variant_db_4"
SAMPLES_TABLE = "samples"
VARIANTS_TABLE = "variants"
VARIANT_SAMPLES_TABLE = "variant_samples"
BATCH_SIZE = 100000  # Number of records to process before writing to the table


def get_tables():
    """Get the existing tables or fail if they don't exist."""
    # Load the catalog using the utility function
    catalog = load_s3_tables_catalog(bucket_arn)

    # Check if namespace exists
    try:
        namespaces = [ns[0] for ns in catalog.list_namespaces()]
        if NAMESPACE not in namespaces:
            print(f"Error: Namespace '{NAMESPACE}' does not exist.")
            sys.exit(1)
    except Exception as e:
        print(f"Error checking namespaces: {e}")
        sys.exit(1)

    # Check if tables exist
    tables = {}
    for table_name in [SAMPLES_TABLE, VARIANTS_TABLE, VARIANT_SAMPLES_TABLE]:
        table_identifier = f"{NAMESPACE}.{table_name}"
        try:
            tables[table_name] = catalog.load_table(table_identifier)
        except NoSuchTableError:
            print(f"Error: Table '{table_identifier}' does not exist.")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading table: {e}")
            sys.exit(1)

    return tables


def open_vcf_file(file_path):
    """Open a VCF file, handling gzipped files automatically."""
    if file_path.endswith('.gz'):
        return gzip.open(file_path, 'rt')
    else:
        return open(file_path, 'r')


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


def register_samples(samples, tables):
    """Register samples in the samples table and return a mapping of sample names to IDs."""
    sample_table = tables[SAMPLES_TABLE]
    sample_schema = sample_table.schema().as_arrow()
    
    # Generate UUIDs for each sample
    sample_ids = [str(uuid.uuid4()) for _ in samples]
    sample_name_array = pa.array(samples, type=pa.string())
    sample_id_array = pa.array(sample_ids, type=pa.string())
    
    # Create PyArrow table
    arrow_table = pa.Table.from_arrays([
        sample_id_array,
        sample_name_array
    ], schema=sample_schema)
    
    print(f"Registering {len(samples)} samples in the samples table...")
    
    # Define a condition function to check if we should retry a table.append
    def is_commit_failed_exception(e):
        return "CommitFailedException" in str(e) and "branch main has changed" in str(e)
    
    # Use the table.append in a retry operation function
    retry_operation(
        sample_table.append,
        arrow_table,
        max_retries=5,
        retry_condition=is_commit_failed_exception
    )
    
    print(f"Successfully registered {len(samples)} samples")
    
    # Return mapping of sample names to IDs
    return dict(zip(samples, sample_ids))


def process_vcf_batch(batch_records, samples, sample_id_map):
    """Process a batch of VCF records and return data for variants and variant_samples tables."""
    # Lists to hold column data for variants table
    variant_ids = []
    variant_chrom_list = []
    variant_pos_list = []
    variant_vcf_id_list = []
    variant_ref_list = []
    variant_alt_list = []
    variant_qual_list = []
    variant_filter_list = []
    variant_info_list = []
    
    # Lists to hold column data for variant_samples table
    vs_variant_id_list = []
    vs_sample_id_list = []
    vs_chrom_list = []
    vs_pos_list = []
    vs_genotype_list = []
    vs_attributes_list = []
    vs_is_reference_block_list = []

    # Process each record in the batch
    for fields in batch_records:
        # Extract basic fields
        chrom = fields[0]
        pos = int(fields[1])
        vcf_id = fields[2] if fields[2] != '.' else None
        ref = fields[3]
        alt_alleles = fields[4].split(',')
        
        # Generate a variant ID
        variant_id = str(uuid.uuid4())
        
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

        # For each alt allele, create a variant record
        for alt_idx, alt in enumerate(alt_alleles):
            if alt == '.':
                alt = ''  # Handle no alternate allele
                
            # Add to variants table data
            variant_ids.append(variant_id)
            variant_chrom_list.append(chrom)
            variant_pos_list.append(pos)
            variant_vcf_id_list.append(vcf_id)
            variant_ref_list.append(ref)
            variant_alt_list.append(alt)
            variant_qual_list.append(qual)
            variant_filter_list.append(filter_val)
            variant_info_list.append(info_dict)
            
            # Process each sample for this variant
            for sample_idx, sample_name in enumerate(samples):
                sample_id = sample_id_map[sample_name]
                
                # Parse genotype and format fields if available
                if len(fields) > 8 + sample_idx:
                    format_str = fields[8]
                    sample_str = fields[9 + sample_idx]
                    attributes = parse_format_field(format_str, sample_str)

                    # Extract genotype
                    genotype = attributes.get('GT', './.')
                    
                    # Add to variant_samples table data
                    vs_variant_id_list.append(variant_id)
                    vs_sample_id_list.append(sample_id)
                    vs_chrom_list.append(chrom)
                    vs_pos_list.append(pos)
                    vs_genotype_list.append(genotype)
                    vs_attributes_list.append(attributes)
                    vs_is_reference_block_list.append(is_reference_block)
                else:
                    # If no format or sample data, add with default values
                    vs_variant_id_list.append(variant_id)
                    vs_sample_id_list.append(sample_id)
                    vs_chrom_list.append(chrom)
                    vs_pos_list.append(pos)
                    vs_genotype_list.append('./.')
                    vs_attributes_list.append({})
                    vs_is_reference_block_list.append(is_reference_block)

    # Convert Python lists to PyArrow arrays for variants table
    variant_data = {
        'variant_id': pa.array(variant_ids, type=pa.string()),
        'chrom': pa.array(variant_chrom_list, type=pa.string()),
        'pos': pa.array(variant_pos_list, type=pa.int64()),
        'vcf_id': pa.array(variant_vcf_id_list, type=pa.string()),
        'ref': pa.array(variant_ref_list, type=pa.string()),
        'alt': pa.array(variant_alt_list, type=pa.string()),
        'qual': pa.array(variant_qual_list, type=pa.float64()),
        'filter': pa.array(variant_filter_list, type=pa.string()),
        'info': pa.array([{str(k): str(v) for k, v in d.items()} for d in variant_info_list],
                         type=pa.map_(pa.string(), pa.string()))
    }
    
    # Convert Python lists to PyArrow arrays for variant_samples table
    variant_samples_data = {
        'variant_id': pa.array(vs_variant_id_list, type=pa.string()),
        'sample_id': pa.array(vs_sample_id_list, type=pa.string()),
        'chrom': pa.array(vs_chrom_list, type=pa.string()),
        'pos': pa.array(vs_pos_list, type=pa.int64()),
        'genotype': pa.array(vs_genotype_list, type=pa.string()),
        'attributes': pa.array([{str(k): str(v) for k, v in d.items()} for d in vs_attributes_list],
                              type=pa.map_(pa.string(), pa.string())),
        'is_reference_block': pa.array(vs_is_reference_block_list, type=pa.bool_())
    }

    return variant_data, variant_samples_data


def process_vcf_file(vcf_path, sample_name=None, tables=None, pyarrow_schemas=None):
    """Process a VCF file in batches and write to Iceberg tables."""
    print(f"Processing VCF file: {vcf_path}")

    # Open and parse the VCF file
    with open_vcf_file(vcf_path) as vcf_file:
        # Parse header to get samples
        samples, info_fields, format_fields = parse_vcf_header(vcf_file)

        # If sample_name is not provided, use all samples from the VCF
        if sample_name:
            if sample_name not in samples:
                print(f"Warning: Sample '{sample_name}' not found in VCF. Available samples: {samples}")
                if not samples:
                    print("No samples found in VCF. Using provided sample name anyway.")
                    samples = [sample_name]
                else:
                    print(f"Using first sample: {samples[0]}")
                    sample_name = samples[0]
            else:
                samples = [sample_name]
        elif not samples:
            # If no samples in VCF and none provided, use a default
            sample_name = os.path.basename(vcf_path).split('.')[0]
            print(f"No samples found in VCF. Using filename as sample name: {sample_name}")
            samples = [sample_name]
            
        # Register samples and get sample ID mapping
        sample_id_map = register_samples(samples, tables)

        # Get PyArrow schemas for the tables
        variants_schema = tables[VARIANTS_TABLE].schema().as_arrow()
        variant_samples_schema = tables[VARIANT_SAMPLES_TABLE].schema().as_arrow()

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
                variant_data, variant_samples_data = process_vcf_batch(batch_records, samples, sample_id_map)

                # Write to Iceberg tables
                write_to_variants_table(tables[VARIANTS_TABLE], variant_data, variants_schema)
                write_to_variant_samples_table(tables[VARIANT_SAMPLES_TABLE], variant_samples_data, variant_samples_schema)
                
                records_processed += len(batch_records)
                print(f"Processed {records_processed} records so far...")

                # Clear the batch
                batch_records = []

        # Process any remaining records
        if batch_records:
            variant_data, variant_samples_data = process_vcf_batch(batch_records, samples, sample_id_map)

            # Write to Iceberg tables
            write_to_variants_table(tables[VARIANTS_TABLE], variant_data, variants_schema)
            write_to_variant_samples_table(tables[VARIANT_SAMPLES_TABLE], variant_samples_data, variant_samples_schema)
            
            records_processed += len(batch_records)
            print(f"Processed {records_processed} records total.")


def write_to_variants_table(table, data, pyarrow_schema):
    """Write data to the variants Iceberg table."""
    # Create PyArrow table
    arrow_table = pa.Table.from_arrays([
        data['variant_id'],
        data['chrom'],
        data['pos'],
        data['vcf_id'],
        data['ref'],
        data['alt'],
        data['qual'],
        data['filter'],
        data['info']
    ], schema=pyarrow_schema)

    print(f"Writing {len(arrow_table)} rows to variants table...")
    
    # Define a condition function to check if we should retry a table.append
    def is_commit_failed_exception(e):
        return "CommitFailedException" in str(e) and "branch main has changed" in str(e)
    
    # Use the table.append in a retry operation function
    retry_operation(
        table.append,
        arrow_table,
        max_retries=5,
        retry_condition=is_commit_failed_exception
    )
    
    print(f"Successfully wrote {len(arrow_table)} rows to variants table")


def write_to_variant_samples_table(table, data, pyarrow_schema):
    """Write data to the variant_samples Iceberg table."""
    # Create PyArrow table
    arrow_table = pa.Table.from_arrays([
        data['variant_id'],
        data['sample_id'],
        data['chrom'],
        data['pos'],
        data['genotype'],
        data['attributes'],
        data['is_reference_block']
    ], schema=pyarrow_schema)

    print(f"Writing {len(arrow_table)} rows to variant_samples table...")
    
    # Define a condition function to check if we should retry a table.append
    def is_commit_failed_exception(e):
        return "CommitFailedException" in str(e) and "branch main has changed" in str(e)
    
    # Use the table.append in a retry operation function
    retry_operation(
        table.append,
        arrow_table,
        max_retries=5,
        retry_condition=is_commit_failed_exception
    )
    
    print(f"Successfully wrote {len(arrow_table)} rows to variant_samples table")


def main():
    """Main function to load VCF/GVCF data into the Iceberg tables."""
    global bucket_arn, NAMESPACE, SAMPLES_TABLE, VARIANTS_TABLE, VARIANT_SAMPLES_TABLE, BATCH_SIZE

    parser = argparse.ArgumentParser(description='Load VCF/GVCF files into Iceberg tables')
    parser.add_argument('vcf_files', nargs='+', help='VCF or GVCF file paths to load')
    parser.add_argument('--sample', help='Sample name to use (overrides sample names in VCF)')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    parser.add_argument('--namespace', default=NAMESPACE, help=f'Iceberg namespace (default: {NAMESPACE})')
    parser.add_argument('--samples-table', default=SAMPLES_TABLE, help=f'Samples table name (default: {SAMPLES_TABLE})')
    parser.add_argument('--variants-table', default=VARIANTS_TABLE, help=f'Variants table name (default: {VARIANTS_TABLE})')
    parser.add_argument('--variant-samples-table', default=VARIANT_SAMPLES_TABLE, 
                        help=f'Variant samples table name (default: {VARIANT_SAMPLES_TABLE})')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                        help=f'Number of records to process before writing (default: {BATCH_SIZE})')

    args = parser.parse_args()
    bucket_arn = args.bucket_arn
    NAMESPACE = args.namespace
    SAMPLES_TABLE = args.samples_table
    VARIANTS_TABLE = args.variants_table
    VARIANT_SAMPLES_TABLE = args.variant_samples_table
    BATCH_SIZE = args.batch_size

    print("Getting tables...")
    tables = get_tables()

    # Process each VCF file
    for vcf_file in args.vcf_files:
        if not os.path.exists(vcf_file):
            print(f"Error: File not found: {vcf_file}")
            continue

        try:
            # Process the file in batches and write directly to the tables
            process_vcf_file(vcf_file, args.sample, tables)
        except Exception as e:
            print(f"Error processing file {vcf_file}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
