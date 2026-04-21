#!/usr/bin/env python3
"""
Script to load VCF or GVCF files into the variant_db tables created by schema_1.py.
This script parses VCF/GVCF files and loads the data into the three Iceberg tables:
- variants
- samples
- variant_samples
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
NAMESPACE = "variant_db"
VARIANTS_TABLE = "variants"
SAMPLES_TABLE = "samples"
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

    tables = {}
    # Check if tables exist
    for table_name in [VARIANTS_TABLE, SAMPLES_TABLE, VARIANT_SAMPLES_TABLE]:
        table_identifier = f"{NAMESPACE}.{table_name}"
        try:
            tables[table_name] = catalog.load_table(table_identifier)
        except NoSuchTableError:
            print(f"Error: Table '{table_identifier}' does not exist.")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading table {table_identifier}: {e}")
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
    sample_ids = [uuid.uuid4() for _ in samples]
    sample_id_dict = dict(zip(samples, sample_ids))

    # Create PyArrow arrays for the samples table
    sample_id_array = convert_uuids_to_arrow_array(sample_ids)
    sample_name_array = pa.array(samples, type=pa.string())

    return {
        'sample_ids': sample_id_dict,
        'arrays': {
            'sample_id': sample_id_array,
            'sample_name': sample_name_array
        }
    }


def process_vcf_batch(batch_records, sample_id_dict):
    """Process a batch of VCF records and return data for variants and variant_samples tables."""
    # Lists to hold column data for variants table
    variant_ids = []
    chrom_list = []
    pos_list = []
    vcf_id_list = []
    ref_list = []
    alt_list = []
    qual_list = []
    filter_list = []
    info_list = []

    # Lists to hold column data for variant_samples table
    vs_variant_ids = []
    vs_sample_ids = []
    vs_genotype_list = []
    vs_attributes_list = []
    vs_is_reference_block_list = []

    # Process each record in the batch
    for fields in batch_records:
        # Extract basic fields
        chrom = fields[0]
        pos = int(fields[1])
        vcf_id = fields[2]
        if vcf_id == '.':
            vcf_id = None
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

        # Generate a UUID for this variant
        variant_id = uuid.uuid4()

        # Add to variants table data
        variant_ids.append(variant_id)
        chrom_list.append(chrom)
        pos_list.append(pos)
        vcf_id_list.append(vcf_id)
        ref_list.append(ref)
        alt_list.append(alt)
        qual_list.append(qual)
        filter_list.append(filter_val)
        info_list.append(info_dict)

        # Process each sample for this variant
        format_str = fields[8] if len(fields) > 8 else None
        
        for sample_idx, (sample_name, sample_id) in enumerate(sample_id_dict.items()):
            # Parse genotype and format fields if available
            if format_str and len(fields) > 9 + sample_idx:
                sample_str = fields[9 + sample_idx]
                attributes = parse_format_field(format_str, sample_str)
                
                # Extract genotype
                genotype = attributes.get('GT', './.')
                
                # Add to variant_samples table data
                vs_variant_ids.append(variant_id)
                vs_sample_ids.append(sample_id)
                vs_genotype_list.append(genotype)
                vs_attributes_list.append(attributes)
                vs_is_reference_block_list.append(is_reference_block)
            else:
                # If no format or sample data, add with default values
                vs_variant_ids.append(variant_id)
                vs_sample_ids.append(sample_id)
                vs_genotype_list.append('./.')
                vs_attributes_list.append({})
                vs_is_reference_block_list.append(is_reference_block)

    # Convert Python lists to PyArrow arrays for variants table
    variant_id_array = convert_uuids_to_arrow_array(variant_ids)
    chrom_array = pa.array(chrom_list, type=pa.string())
    pos_array = pa.array(pos_list, type=pa.int64())
    vcf_id_array = pa.array(vcf_id_list, type=pa.string())
    ref_array = pa.array(ref_list, type=pa.string())
    alt_array = pa.array(alt_list, type=pa.string())
    qual_array = pa.array(qual_list, type=pa.float64())
    filter_array = pa.array(filter_list, type=pa.string())
    info_map_array = pa.array([{str(k): str(v) for k, v in d.items()} for d in info_list],
                              type=pa.map_(pa.string(), pa.string()))

    # Convert Python lists to PyArrow arrays for variant_samples table
    vs_variant_id_array = convert_uuids_to_arrow_array(vs_variant_ids)
    vs_sample_id_array = convert_uuids_to_arrow_array(vs_sample_ids)
    vs_genotype_array = pa.array(vs_genotype_list, type=pa.string())
    vs_attributes_map_array = pa.array([{str(k): str(v) for k, v in d.items()} for d in vs_attributes_list],
                                       type=pa.map_(pa.string(), pa.string()))
    vs_is_reference_block_array = pa.array(vs_is_reference_block_list, type=pa.bool_())

    return {
        'variants': {
            'variant_id': variant_id_array,
            'chrom': chrom_array,
            'pos': pos_array,
            'vcf_id': vcf_id_array,
            'ref': ref_array,
            'alt': alt_array,
            'qual': qual_array,
            'filter': filter_array,
            'info': info_map_array
        },
        'variant_samples': {
            'variant_id': vs_variant_id_array,
            'sample_id': vs_sample_id_array,
            'genotype': vs_genotype_array,
            'attributes': vs_attributes_map_array,
            'is_reference_block': vs_is_reference_block_array
        }
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
                sample_data['arrays']['sample_name']
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
                    # Write variants to the variants table
                    variants_table = pa.Table.from_arrays([
                        data['variants']['variant_id'],
                        data['variants']['chrom'],
                        data['variants']['pos'],
                        data['variants']['vcf_id'],
                        data['variants']['ref'],
                        data['variants']['alt'],
                        data['variants']['qual'],
                        data['variants']['filter'],
                        data['variants']['info']
                    ], schema=pyarrow_schemas[VARIANTS_TABLE])
                    
                    print(f"Writing {len(variants_table)} variants to {NAMESPACE}.{VARIANTS_TABLE}...")
                    retry_operation(
                        tables[VARIANTS_TABLE].append,
                        variants_table,
                        max_retries=5,
                        retry_condition=lambda e: "CommitFailedException" in str(e) and "branch main has changed" in str(e)
                    )
                    
                    # Write variant_samples to the variant_samples table
                    variant_samples_table = pa.Table.from_arrays([
                        data['variant_samples']['variant_id'],
                        data['variant_samples']['sample_id'],
                        data['variant_samples']['genotype'],
                        data['variant_samples']['attributes'],
                        data['variant_samples']['is_reference_block']
                    ], schema=pyarrow_schemas[VARIANT_SAMPLES_TABLE])
                    
                    print(f"Writing {len(variant_samples_table)} variant-sample associations to {NAMESPACE}.{VARIANT_SAMPLES_TABLE}...")
                    retry_operation(
                        tables[VARIANT_SAMPLES_TABLE].append,
                        variant_samples_table,
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
                # Write variants to the variants table
                variants_table = pa.Table.from_arrays([
                    data['variants']['variant_id'],
                    data['variants']['chrom'],
                    data['variants']['pos'],
                    data['variants']['vcf_id'],
                    data['variants']['ref'],
                    data['variants']['alt'],
                    data['variants']['qual'],
                    data['variants']['filter'],
                    data['variants']['info']
                ], schema=pyarrow_schemas[VARIANTS_TABLE])
                
                print(f"Writing {len(variants_table)} variants to {NAMESPACE}.{VARIANTS_TABLE}...")
                retry_operation(
                    tables[VARIANTS_TABLE].append,
                    variants_table,
                    max_retries=5,
                    retry_condition=lambda e: "CommitFailedException" in str(e) and "branch main has changed" in str(e)
                )
                
                # Write variant_samples to the variant_samples table
                variant_samples_table = pa.Table.from_arrays([
                    data['variant_samples']['variant_id'],
                    data['variant_samples']['sample_id'],
                    data['variant_samples']['genotype'],
                    data['variant_samples']['attributes'],
                    data['variant_samples']['is_reference_block']
                ], schema=pyarrow_schemas[VARIANT_SAMPLES_TABLE])
                
                print(f"Writing {len(variant_samples_table)} variant-sample associations to {NAMESPACE}.{VARIANT_SAMPLES_TABLE}...")
                retry_operation(
                    tables[VARIANT_SAMPLES_TABLE].append,
                    variant_samples_table,
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
    global bucket_arn, NAMESPACE, VARIANTS_TABLE, SAMPLES_TABLE, VARIANT_SAMPLES_TABLE, BATCH_SIZE

    parser = argparse.ArgumentParser(description='Load VCF/GVCF files into Iceberg tables using schema_1.py')
    parser.add_argument('vcf_files', nargs='+', help='VCF or GVCF file paths to load')
    parser.add_argument('--sample', help='Sample name to use (overrides sample names in VCF)')
    parser.add_argument('--bucket-arn', required=True, help='S3Tables bucket ARN')
    parser.add_argument('--namespace', default=NAMESPACE, help=f'Iceberg namespace (default: {NAMESPACE})')
    parser.add_argument('--variants-table', default=VARIANTS_TABLE, help=f'Variants table name (default: {VARIANTS_TABLE})')
    parser.add_argument('--samples-table', default=SAMPLES_TABLE, help=f'Samples table name (default: {SAMPLES_TABLE})')
    parser.add_argument('--variant-samples-table', default=VARIANT_SAMPLES_TABLE, 
                        help=f'Variant-samples table name (default: {VARIANT_SAMPLES_TABLE})')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                        help=f'Number of records to process before writing (default: {BATCH_SIZE})')

    args = parser.parse_args()
    bucket_arn = args.bucket_arn
    NAMESPACE = args.namespace
    VARIANTS_TABLE = args.variants_table
    SAMPLES_TABLE = args.samples_table
    VARIANT_SAMPLES_TABLE = args.variant_samples_table
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
