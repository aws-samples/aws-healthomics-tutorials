#!/usr/bin/env python3
"""
Script to load VCF or GVCF files into the variant_db_3.genomic_variants Iceberg table.
This script parses VCF/GVCF files and loads the data into the Iceberg table created by schema_3.py.
"""

import argparse
import os
import sys
import pyarrow as pa
from pyiceberg.exceptions import NoSuchTableError
from utils import load_s3_tables_catalog, retry_operation
import gzip

# Configuration
NAMESPACE = "variant_db_3"
TABLE_NAME = "genomic_variants"
BATCH_SIZE = 100000  # Number of records to process before writing to the table


def get_table():
    """Get the existing table or fail if it doesn't exist."""
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

    # Check if table exists
    table_identifier = f"{NAMESPACE}.{TABLE_NAME}"
    try:
        return catalog.load_table(table_identifier)
    except NoSuchTableError:
        print(f"Error: Table '{table_identifier}' does not exist.")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading table: {e}")
        sys.exit(1)


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


def process_vcf_batch(batch_records, samples):
    """Process a batch of VCF records and return data as PyArrow arrays."""
    # Lists to hold column data
    sample_name_list = []
    variant_name_list = []  # New list for variant_name field
    chrom_list = []
    pos_list = []
    ref_list = []
    alt_list = []
    qual_list = []
    filter_list = []
    genotype_list = []
    info_list = []
    attributes_list = []
    is_reference_block_list = []

    # Process each record in the batch
    for fields in batch_records:
        # Extract basic fields
        chrom = fields[0]
        pos = int(fields[1])
        vcf_id = fields[2]  # Now used for variant_name
        ref = fields[3]
        alt_alleles = fields[4].split(',')

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

        # Process each sample
        for sample_idx, current_sample in enumerate(samples):
            # Process all alternate alleles as a list
            # Clean up alt alleles
            clean_alt_alleles = []
            for alt in alt_alleles:
                if alt == '.':
                    alt = ''  # Handle no alternate allele
                clean_alt_alleles.append(alt)

            # Add basic variant info
            sample_name_list.append(current_sample)
            variant_name_list.append(vcf_id)  # Add variant_name from ID column
            chrom_list.append(chrom)
            pos_list.append(pos)
            ref_list.append(ref)
            alt_list.append(clean_alt_alleles)
            qual_list.append(qual)
            filter_list.append(filter_val)
            # Parse genotype and format fields if available
            if len(fields) > 8 + sample_idx:
                format_str = fields[8]
                sample_str = fields[9 + sample_idx]
                attributes = parse_format_field(format_str, sample_str)

                # Extract genotype
                genotype = attributes.get('GT', './.')
                genotype_list.append(genotype)

                # Store other format fields as attributes
                attributes_list.append(attributes)
            else:
                genotype_list.append('./.')
                attributes_list.append({})

            # Store INFO fields
            info_list.append(info_dict)
            # Store reference block status
            is_reference_block_list.append(is_reference_block)

    # Convert Python lists to PyArrow arrays
    sample_name_array = pa.array(sample_name_list, type=pa.string())
    variant_name_array = pa.array(variant_name_list, type=pa.string())  # New array for variant_name
    chrom_array = pa.array(chrom_list, type=pa.string())
    pos_array = pa.array(pos_list, type=pa.int64())
    ref_array = pa.array(ref_list, type=pa.string())
    # Create a list array for alt alleles with proper type specification
    alt_array = pa.array(alt_list, type=pa.list_(pa.string()))
    qual_array = pa.array(qual_list, type=pa.float64())
    filter_array = pa.array(filter_list, type=pa.string())
    genotype_array = pa.array(genotype_list, type=pa.string())

    # Convert dictionaries to string maps
    info_map_array = pa.array([{str(k): str(v) for k, v in d.items()} for d in info_list],
                              type=pa.map_(pa.string(), pa.string()))
    attributes_map_array = pa.array([{str(k): str(v) for k, v in d.items()} for d in attributes_list],
                                    type=pa.map_(pa.string(), pa.string()))

    is_reference_block_array = pa.array(is_reference_block_list, type=pa.bool_())

    return {
        'sample_name': sample_name_array,
        'variant_name': variant_name_array,  # Add variant_name to return dictionary
        'chrom': chrom_array,
        'pos': pos_array,
        'ref': ref_array,
        'alt': alt_array,
        'qual': qual_array,
        'filter': filter_array,
        'genotype': genotype_array,
        'info': info_map_array,
        'attributes': attributes_map_array,
        'is_reference_block': is_reference_block_array
    }


def process_vcf_file(vcf_path, sample_name=None, tables=None, pyarrow_schemas=None,
                     table=None, pyarrow_schema=None):
    """Process a VCF file in batches and write to Iceberg table."""
    # Support both dict-style (tables/pyarrow_schemas) and direct (table/pyarrow_schema) args
    if table is None and tables is not None:
        table = tables.get("genomic_variants") or next(iter(tables.values()))
    if pyarrow_schema is None and pyarrow_schemas is not None:
        pyarrow_schema = pyarrow_schemas.get("genomic_variants") or next(iter(pyarrow_schemas.values()))

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
                data_arrays = process_vcf_batch(batch_records, samples)

                if table and pyarrow_schema:
                    write_to_iceberg(table, data_arrays, pyarrow_schema)
                    records_processed += len(batch_records)
                    print(f"Processed {records_processed} records so far...")
                else:
                    return data_arrays

                # Clear the batch
                batch_records = []

        # Process any remaining records
        if batch_records:
            data_arrays = process_vcf_batch(batch_records, samples)

            if table and pyarrow_schema:
                write_to_iceberg(table, data_arrays, pyarrow_schema)
                records_processed += len(batch_records)
                print(f"Processed {records_processed} records total.")
                return None
            else:
                return data_arrays

        return None


def write_to_iceberg(table, data_arrays, pyarrow_schema):
    """Write data to the Iceberg table."""
    # Create PyArrow table schema
    arrow_table = pa.Table.from_arrays([
        data_arrays['sample_name'],
        data_arrays['variant_name'],  # Add variant_name to the table
        data_arrays['chrom'],
        data_arrays['pos'],
        data_arrays['ref'],
        data_arrays['alt'],
        data_arrays['qual'],
        data_arrays['filter'],
        data_arrays['genotype'],
        data_arrays['info'],
        data_arrays['attributes'],
        data_arrays['is_reference_block']
    ], schema=pyarrow_schema)

    print(f"Writing {len(arrow_table)} rows to Iceberg table...")
    
    # Define a condition function to check if we should retry a table.append
    def is_commit_failed_exception(e):
        return "CommitFailedException" in str(e) and "branch main has changed" in str(e)
    
    # Use the table.upsert in a retry operation function
    retry_operation(
        table.append,
        arrow_table,
        max_retries=5,
        retry_condition=is_commit_failed_exception
    )
    
    print(f"Successfully wrote {len(arrow_table)} rows to {NAMESPACE}.{TABLE_NAME}")


def main():
    """Main function to load VCF/GVCF data into the Iceberg table."""
    global bucket_arn, NAMESPACE, TABLE_NAME, BATCH_SIZE

    parser = argparse.ArgumentParser(description='Load VCF/GVCF files into Iceberg table')
    parser.add_argument('vcf_files', nargs='+', help='VCF or GVCF file paths to load')
    parser.add_argument('--sample', help='Sample name to use (overrides sample names in VCF)')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    parser.add_argument('--namespace', default=NAMESPACE, help=f'Iceberg namespace (default: {NAMESPACE})')
    parser.add_argument('--table', default=TABLE_NAME, help=f'Iceberg table name (default: {TABLE_NAME})')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                        help=f'Number of records to process from each sample before writing (default: {BATCH_SIZE})')

    args = parser.parse_args()
    bucket_arn = args.bucket_arn
    NAMESPACE = args.namespace
    TABLE_NAME = args.table
    BATCH_SIZE = args.batch_size

    print("Getting table...")
    table = get_table()
    pyarrow_schema = table.schema().as_arrow()

    # Process each VCF file
    for vcf_file in args.vcf_files:
        if not os.path.exists(vcf_file):
            print(f"Error: File not found: {vcf_file}")
            continue

        try:
            # Process the file in batches and write directly to the table
            process_vcf_file(vcf_file, args.sample, table, pyarrow_schema)
        except Exception as e:
            print(f"Error processing file {vcf_file}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
