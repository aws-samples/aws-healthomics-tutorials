#!/usr/bin/env python3
"""
Input validation module for HealthOmics GFF3 Annotation Loader workflow.

Validates:
- GFF3 file existence (S3 and local paths)
- Schema selection (must be 1 or 2)
- Destination format (S3 Tables ARN or S3 path)
- Catalog type determination
"""

import os
import sys
import json
import argparse
import boto3
from botocore.exceptions import ClientError, NoCredentialsError


def parse_s3_uri(s3_uri):
    if not s3_uri.startswith('s3://'):
        raise ValueError(f"Invalid S3 URI format: {s3_uri}")
    parts = s3_uri[5:].split('/', 1)
    return parts[0], parts[1] if len(parts) > 1 else ''


def validate_gff3_file(gff3_path):
    if gff3_path.startswith('s3://'):
        try:
            bucket, key = parse_s3_uri(gff3_path)
            s3 = boto3.client('s3')
            s3.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code', '')
            if code == '404':
                raise FileNotFoundError(f"GFF3 file not found in S3: {gff3_path}")
            elif code == '403':
                raise PermissionError(f"Access denied to GFF3 file: {gff3_path}")
            else:
                raise RuntimeError(f"Error accessing GFF3 file {gff3_path}: {e}")
        except NoCredentialsError:
            raise RuntimeError("AWS credentials not found.")
    else:
        if not os.path.exists(gff3_path):
            raise FileNotFoundError(f"GFF3 file not found: {gff3_path}")
        if not os.path.isfile(gff3_path):
            raise ValueError(f"Path is not a file: {gff3_path}")
        return True


def validate_schema(schema):
    try:
        schema_int = int(schema)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid schema selection: {schema}. Must be 1 or 2")
    if schema_int not in [1, 2]:
        raise ValueError(f"Invalid schema selection: {schema}. Must be 1 or 2")
    return schema_int


def determine_catalog_type(destination):
    if destination.startswith('arn:aws:s3tables:'):
        return 's3tables'
    elif destination.startswith('s3://'):
        return 'vanilla'
    else:
        raise ValueError(
            f"Invalid destination format: {destination}. "
            "Must be S3 Tables ARN (arn:aws:s3tables:...) or S3 path (s3://...)"
        )


def validate_destination(destination, catalog_type):
    if catalog_type == 's3tables':
        parts = destination.split(':')
        if len(parts) < 6 or parts[0] != 'arn' or parts[2] != 's3tables' or not parts[3]:
            raise ValueError(f"Invalid S3 Tables ARN format: {destination}")
        return True
    elif catalog_type == 'vanilla':
        try:
            bucket, _ = parse_s3_uri(destination)
            s3 = boto3.client('s3')
            s3.head_bucket(Bucket=bucket)
            return True
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code', '')
            if code == '404':
                raise RuntimeError(f"S3 bucket not found: {bucket}")
            elif code == '403':
                raise PermissionError(f"Access denied to S3 bucket: {bucket}")
            else:
                raise RuntimeError(f"Error accessing S3 bucket {bucket}: {e}")
    return True


def validate_inputs(gff3_file, schema, destination):
    schema_int = validate_schema(schema)
    catalog_type = determine_catalog_type(destination)
    validate_gff3_file(gff3_file)
    validate_destination(destination, catalog_type)
    return {
        'gff3_file': gff3_file,
        'schema': schema_int,
        'destination': destination,
        'catalog_type': catalog_type,
        'status': 'valid'
    }


def main():
    parser = argparse.ArgumentParser(description='Validate inputs for GFF3 Annotation Loader')
    parser.add_argument('--gff3-file', required=True, help='Path to GFF3 file')
    parser.add_argument('--schema', required=True, help='Schema selection (1 or 2)')
    parser.add_argument('--destination', required=True, help='Destination (S3 Tables ARN or S3 path)')
    parser.add_argument('--output', help='Output JSON file')
    args = parser.parse_args()

    try:
        result = validate_inputs(args.gff3_file, args.schema, args.destination)
        output_json = json.dumps(result, indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_json)
            print(f"Validation successful. Results written to {args.output}")
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
