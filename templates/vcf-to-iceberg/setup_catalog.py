#!/usr/bin/env python3
"""
Catalog configuration module for HealthOmics VCF Loader workflow.

This module configures the appropriate Iceberg catalog based on destination type:
- S3 Tables catalog: REST catalog with SigV4 authentication
- Vanilla Iceberg catalog: Glue-based catalog with S3 storage

Outputs catalog configuration as JSON.
"""

import sys
import json
import argparse
import re
import boto3


def extract_region_from_arn(arn: str) -> str:
    """
    Extract AWS region from an S3 Tables ARN.
    
    Args:
        arn: S3 Tables ARN in format arn:aws:s3tables:region:account-id:bucket/bucket-name
        
    Returns:
        AWS region string
        
    Raises:
        ValueError: If ARN format is invalid or region cannot be extracted
    """
    # ARN format: arn:aws:s3tables:region:account-id:bucket/bucket-name
    parts = arn.split(':')
    
    if len(parts) < 6:
        raise ValueError(f"Invalid S3 Tables ARN format: {arn}")
    
    if parts[0] != 'arn' or parts[1] != 'aws' or parts[2] != 's3tables':
        raise ValueError(f"Invalid S3 Tables ARN format: {arn}")
    
    region = parts[3]
    
    if not region:
        raise ValueError(f"Invalid S3 Tables ARN: missing region in {arn}")
    
    return region


def extract_region_from_s3_path(s3_path: str) -> str:
    """
    Extract or determine AWS region from an S3 path.
    
    For vanilla Iceberg catalogs, we use the current boto3 session region
    or default to us-east-1.
    
    Args:
        s3_path: S3 path in format s3://bucket/path
        
    Returns:
        AWS region string
    """
    session = boto3.session.Session()
    region = session.region_name
    
    if not region:
        # Default to us-east-1 if no region is configured
        region = 'us-east-1'
    
    return region


def setup_s3tables_catalog(destination: str) -> dict:
    """
    Configure S3 Tables REST catalog with SigV4 authentication.
    
    Args:
        destination: S3 Tables bucket ARN
        
    Returns:
        Dictionary containing catalog configuration
        
    Raises:
        ValueError: If ARN format is invalid
    """
    # Extract region from ARN
    region = extract_region_from_arn(destination)
    
    # Build catalog configuration
    catalog_config = {
        "type": "rest",
        "warehouse": destination,
        "uri": f"https://s3tables.{region}.amazonaws.com/iceberg",
        "rest.sigv4-enabled": "true",
        "rest.signing-name": "s3tables",
        "rest.signing-region": region,
        "region": region
    }
    
    return catalog_config


def setup_vanilla_catalog(destination: str) -> dict:
    """
    Configure vanilla Iceberg catalog with S3 storage using AWS Glue as the catalog.
    
    Glue is the standard managed Iceberg catalog on AWS. It requires no extra
    dependencies beyond what PyIceberg ships with, and works natively in
    HealthOmics environments.
    
    Args:
        destination: S3 path for warehouse location
        
    Returns:
        Dictionary containing catalog configuration
    """
    # Determine region
    region = extract_region_from_s3_path(destination)
    
    catalog_config = {
        "type": "glue",
        "warehouse": destination,
        "client.region": region
    }
    
    return catalog_config


def setup_catalog(catalog_type: str, destination: str, namespace: str = None) -> dict:
    """
    Configure the appropriate Iceberg catalog based on catalog type.
    
    Args:
        catalog_type: Type of catalog ('s3tables' or 'vanilla')
        destination: Destination location (S3 Tables ARN or S3 path)
        namespace: Optional Iceberg namespace
        
    Returns:
        Dictionary containing catalog configuration and metadata
        
    Raises:
        ValueError: If catalog_type is invalid or configuration fails
    """
    if catalog_type == 's3tables':
        catalog_config = setup_s3tables_catalog(destination)
    elif catalog_type == 'vanilla':
        catalog_config = setup_vanilla_catalog(destination)
    else:
        raise ValueError(f"Invalid catalog type: {catalog_type}. Must be 's3tables' or 'vanilla'")
    
    # Add namespace if provided
    if namespace:
        catalog_config['namespace'] = namespace
    
    # Add metadata
    result = {
        'catalog_type': catalog_type,
        'destination': destination,
        'catalog_config': catalog_config,
        'status': 'configured'
    }
    
    return result


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description='Configure Iceberg catalog for HealthOmics VCF Loader workflow'
    )
    parser.add_argument('--catalog-type', required=True, 
                       choices=['s3tables', 'vanilla'],
                       help='Type of catalog (s3tables or vanilla)')
    parser.add_argument('--destination', required=True, 
                       help='Destination location (S3 Tables ARN or S3 path)')
    parser.add_argument('--namespace', 
                       help='Iceberg namespace (optional)')
    parser.add_argument('--output', 
                       help='Output JSON file (default: stdout)')
    
    args = parser.parse_args()
    
    try:
        # Setup catalog
        result = setup_catalog(args.catalog_type, args.destination, args.namespace)
        
        # Output as JSON
        output_json = json.dumps(result, indent=2)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_json)
            print(f"Catalog configuration successful. Results written to {args.output}")
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
