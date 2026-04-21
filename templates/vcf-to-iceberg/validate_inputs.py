#!/usr/bin/env python3
"""
Input validation module for HealthOmics VCF Loader workflow.

This module validates workflow input parameters:
- VCF file existence (S3 and local paths)
- Schema selection (must be 1, 2, 3, or 4)
- Destination format (S3 Tables ARN or S3 path)
- Catalog type determination

Outputs validated parameters as JSON.
"""

import os
import sys
import json
import argparse
import boto3
from botocore.exceptions import ClientError, NoCredentialsError


def parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    """
    Parse an S3 URI into bucket and key components.
    
    Args:
        s3_uri: S3 URI in format s3://bucket/key
        
    Returns:
        Tuple of (bucket, key)
        
    Raises:
        ValueError: If URI format is invalid
    """
    if not s3_uri.startswith('s3://'):
        raise ValueError(f"Invalid S3 URI format: {s3_uri}")
    
    parts = s3_uri[5:].split('/', 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ''
    
    return bucket, key


def validate_vcf_file(vcf_path: str) -> bool:
    """
    Validate that a VCF file exists and is accessible.
    
    Args:
        vcf_path: Path to VCF file (S3 URI or local path)
        
    Returns:
        True if file exists and is accessible
        
    Raises:
        FileNotFoundError: If file does not exist or is not accessible
        ValueError: If S3 URI format is invalid
    """
    if vcf_path.startswith('s3://'):
        # Check S3 file exists
        try:
            bucket, key = parse_s3_uri(vcf_path)
            s3 = boto3.client('s3')
            s3.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == '404':
                raise FileNotFoundError(f"VCF file not found in S3: {vcf_path}")
            elif error_code == '403':
                raise PermissionError(f"Access denied to VCF file: {vcf_path}")
            else:
                raise RuntimeError(f"Error accessing VCF file {vcf_path}: {e}")
        except NoCredentialsError:
            raise RuntimeError("AWS credentials not found. Check AWS configuration.")
    else:
        # Check local file exists
        if not os.path.exists(vcf_path):
            raise FileNotFoundError(f"VCF file not found: {vcf_path}")
        if not os.path.isfile(vcf_path):
            raise ValueError(f"Path is not a file: {vcf_path}")
        return True


def validate_schema(schema: str) -> int:
    """
    Validate schema selection.
    
    Args:
        schema: Schema selection as string
        
    Returns:
        Schema as integer (1, 2, 3, or 4)
        
    Raises:
        ValueError: If schema is not valid
    """
    try:
        schema_int = int(schema)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid schema selection: {schema}. Must be 1, 2, 3, or 4")
    
    if schema_int not in [1, 2, 3, 4]:
        raise ValueError(f"Invalid schema selection: {schema}. Must be 1, 2, 3, or 4")
    
    return schema_int


def determine_catalog_type(destination: str) -> str:
    """
    Determine catalog type based on destination format.
    
    Args:
        destination: Destination location (S3 Tables ARN or S3 path)
        
    Returns:
        Catalog type: 's3tables' or 'vanilla'
        
    Raises:
        ValueError: If destination format is invalid
    """
    if destination.startswith('arn:aws:s3tables:'):
        return 's3tables'
    elif destination.startswith('s3://'):
        return 'vanilla'
    else:
        raise ValueError(
            f"Invalid destination format: {destination}. "
            "Must be S3 Tables ARN (arn:aws:s3tables:...) or S3 path (s3://...)"
        )


def validate_destination(destination: str, catalog_type: str) -> bool:
    """
    Validate destination is accessible.
    
    Args:
        destination: Destination location
        catalog_type: Type of catalog ('s3tables' or 'vanilla')
        
    Returns:
        True if destination is accessible
        
    Raises:
        ValueError: If destination format is invalid
        RuntimeError: If destination is not accessible
    """
    if catalog_type == 's3tables':
        # Validate S3 Tables ARN format
        # Format: arn:aws:s3tables:region:account-id:bucket/bucket-name
        parts = destination.split(':')
        if len(parts) < 6:
            raise ValueError(f"Invalid S3 Tables ARN format: {destination}")
        
        if parts[0] != 'arn' or parts[1] != 'aws' or parts[2] != 's3tables':
            raise ValueError(f"Invalid S3 Tables ARN format: {destination}")
        
        # Extract region and validate it's not empty
        region = parts[3]
        if not region:
            raise ValueError(f"Invalid S3 Tables ARN: missing region in {destination}")
        
        # Note: We don't validate S3 Tables bucket accessibility here as it requires
        # s3tables API calls which may not be available in all environments
        return True
        
    elif catalog_type == 'vanilla':
        # Validate S3 path format and check bucket accessibility
        try:
            bucket, _ = parse_s3_uri(destination)
            s3 = boto3.client('s3')
            # Check if bucket exists and is accessible
            s3.head_bucket(Bucket=bucket)
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == '404':
                raise RuntimeError(f"S3 bucket not found: {bucket}")
            elif error_code == '403':
                raise PermissionError(f"Access denied to S3 bucket: {bucket}")
            else:
                raise RuntimeError(f"Error accessing S3 bucket {bucket}: {e}")
        except NoCredentialsError:
            raise RuntimeError("AWS credentials not found. Check AWS configuration.")
    
    return True


def validate_inputs(vcf_file: str, schema: str, destination: str) -> dict:
    """
    Validate all workflow input parameters.
    
    Args:
        vcf_file: Path to VCF file
        schema: Schema selection (1, 2, 3, or 4)
        destination: Destination location
        
    Returns:
        Dictionary containing validated parameters and catalog type
        
    Raises:
        Various exceptions for validation failures
    """
    # Validate schema first (cheapest operation)
    schema_int = validate_schema(schema)
    
    # Determine catalog type
    catalog_type = determine_catalog_type(destination)
    
    # Validate VCF file exists
    validate_vcf_file(vcf_file)
    
    # Validate destination is accessible
    validate_destination(destination, catalog_type)
    
    # Return validated parameters
    return {
        'vcf_file': vcf_file,
        'schema': schema_int,
        'destination': destination,
        'catalog_type': catalog_type,
        'status': 'valid'
    }


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description='Validate input parameters for HealthOmics VCF Loader workflow'
    )
    parser.add_argument('--vcf-file', required=True, help='Path to VCF file (S3 URI or local path)')
    parser.add_argument('--schema', required=True, help='Schema selection (1, 2, 3, or 4)')
    parser.add_argument('--destination', required=True, help='Destination (S3 Tables ARN or S3 path)')
    parser.add_argument('--output', help='Output JSON file (default: stdout)')
    
    args = parser.parse_args()
    
    try:
        # Validate inputs
        result = validate_inputs(args.vcf_file, args.schema, args.destination)
        
        # Output as JSON
        output_json = json.dumps(result, indent=2)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_json)
            print(f"Validation successful. Results written to {args.output}")
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
