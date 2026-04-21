#!/usr/bin/env python3
"""
Property-based tests for catalog type determination.

**Validates: Requirements 2.4, 2.5, 6.5**

Property 1: Catalog Type Determination
For any destination parameter, the workflow should correctly determine the catalog type:
- If the destination starts with "arn:aws:s3tables:", the catalog type should be "s3tables"
- Otherwise, if it starts with "s3://", the catalog type should be "vanilla"
"""

import pytest
import os
import sys
from hypothesis import given, strategies as st, assume

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from validate_inputs import determine_catalog_type


# Strategy for generating valid AWS regions
aws_regions = st.sampled_from([
    'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
    'eu-west-1', 'eu-west-2', 'eu-central-1',
    'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1'
])

# Strategy for generating valid AWS account IDs (12 digits)
aws_account_ids = st.integers(min_value=100000000000, max_value=999999999999).map(str)

# Strategy for generating valid bucket names
# S3 bucket names: 3-63 chars, lowercase letters, numbers, hyphens
bucket_names = st.text(
    alphabet=st.characters(categories=('Ll', 'Nd'), include_characters='-'),
    min_size=3,
    max_size=63
).filter(lambda x: x and x[0].isalnum() and x[-1].isalnum() and '--' not in x)

# Strategy for generating valid S3 paths (keys)
s3_paths = st.text(
    alphabet=st.characters(categories=('Lu', 'Ll', 'Nd'), include_characters='/-_.'),
    min_size=0,
    max_size=100
).filter(lambda x: '//' not in x)


# Strategy for generating S3 Tables ARNs
@st.composite
def s3tables_arns(draw):
    """Generate valid S3 Tables ARN strings."""
    region = draw(aws_regions)
    account_id = draw(aws_account_ids)
    bucket_name = draw(bucket_names)
    
    return f"arn:aws:s3tables:{region}:{account_id}:bucket/{bucket_name}"


# Strategy for generating S3 paths
@st.composite
def s3_paths_strategy(draw):
    """Generate valid S3 path strings."""
    bucket = draw(bucket_names)
    path = draw(s3_paths)
    
    if path:
        return f"s3://{bucket}/{path}"
    else:
        return f"s3://{bucket}"


class TestCatalogTypeDeterminationProperty:
    """Property-based tests for catalog type determination."""
    
    @given(s3tables_arns())
    def test_s3tables_arn_always_returns_s3tables(self, arn):
        """
        Property: Any destination starting with 'arn:aws:s3tables:' should return 's3tables'.
        
        **Validates: Requirements 2.4, 2.5, 6.5**
        """
        # The ARN should start with the expected prefix
        assert arn.startswith('arn:aws:s3tables:')
        
        # Determine catalog type
        catalog_type = determine_catalog_type(arn)
        
        # Property: catalog type should always be 's3tables'
        assert catalog_type == 's3tables', \
            f"Expected 's3tables' for ARN {arn}, got {catalog_type}"
    
    @given(s3_paths_strategy())
    def test_s3_path_always_returns_vanilla(self, s3_path):
        """
        Property: Any destination starting with 's3://' should return 'vanilla'.
        
        **Validates: Requirements 2.4, 2.5, 6.5**
        """
        # The path should start with the expected prefix
        assert s3_path.startswith('s3://')
        
        # Determine catalog type
        catalog_type = determine_catalog_type(s3_path)
        
        # Property: catalog type should always be 'vanilla'
        assert catalog_type == 'vanilla', \
            f"Expected 'vanilla' for S3 path {s3_path}, got {catalog_type}"
    
    @given(st.text(min_size=1, max_size=200))
    def test_invalid_destination_raises_error(self, destination):
        """
        Property: Any destination that doesn't start with 'arn:aws:s3tables:' or 's3://'
        should raise a ValueError.
        
        **Validates: Requirements 2.4, 2.5, 6.5**
        """
        # Assume the destination is not a valid format
        assume(not destination.startswith('arn:aws:s3tables:'))
        assume(not destination.startswith('s3://'))
        
        # Property: should raise ValueError for invalid destinations
        with pytest.raises(ValueError, match="Invalid destination format"):
            determine_catalog_type(destination)
    
    @given(
        region=aws_regions,
        account_id=aws_account_ids,
        bucket=bucket_names
    )
    def test_s3tables_arn_components_preserved(self, region, account_id, bucket):
        """
        Property: S3 Tables ARN with any valid region, account ID, and bucket name
        should be correctly identified as 's3tables'.
        
        **Validates: Requirements 2.4, 2.5, 6.5**
        """
        arn = f"arn:aws:s3tables:{region}:{account_id}:bucket/{bucket}"
        
        catalog_type = determine_catalog_type(arn)
        
        assert catalog_type == 's3tables', \
            f"Expected 's3tables' for ARN with region={region}, account={account_id}, bucket={bucket}"
    
    @given(
        bucket=bucket_names,
        path=s3_paths
    )
    def test_s3_path_components_preserved(self, bucket, path):
        """
        Property: S3 path with any valid bucket and path should be correctly
        identified as 'vanilla'.
        
        **Validates: Requirements 2.4, 2.5, 6.5**
        """
        if path:
            s3_uri = f"s3://{bucket}/{path}"
        else:
            s3_uri = f"s3://{bucket}"
        
        catalog_type = determine_catalog_type(s3_uri)
        
        assert catalog_type == 'vanilla', \
            f"Expected 'vanilla' for S3 path with bucket={bucket}, path={path}"
    
    @given(s3tables_arns(), s3_paths_strategy())
    def test_catalog_types_are_distinct(self, s3tables_arn, s3_path):
        """
        Property: S3 Tables ARNs and S3 paths should always produce different catalog types.
        
        **Validates: Requirements 2.4, 2.5, 6.5**
        """
        s3tables_type = determine_catalog_type(s3tables_arn)
        vanilla_type = determine_catalog_type(s3_path)
        
        assert s3tables_type == 's3tables'
        assert vanilla_type == 'vanilla'
        assert s3tables_type != vanilla_type, \
            "S3 Tables and vanilla catalogs should have different types"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
