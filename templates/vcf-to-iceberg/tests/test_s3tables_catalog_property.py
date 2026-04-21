#!/usr/bin/env python3
"""
Property-based tests for S3 Tables catalog configuration.

**Validates: Requirements 6.1, 6.3**

Property 2: S3 Tables Catalog Configuration
For any S3 Table Bucket ARN destination, the catalog configuration should include
a REST endpoint pointing to the S3 Tables service in the correct region, with
SigV4 authentication enabled.
"""

import pytest
import os
import sys
from hypothesis import given, strategies as st

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from setup_catalog import setup_s3tables_catalog, extract_region_from_arn


# Strategy for generating valid AWS regions
aws_regions = st.sampled_from([
    'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
    'eu-west-1', 'eu-west-2', 'eu-central-1',
    'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1',
    'ap-south-1', 'ca-central-1', 'sa-east-1'
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


# Strategy for generating S3 Tables ARNs
@st.composite
def s3tables_arns(draw):
    """Generate valid S3 Tables ARN strings."""
    region = draw(aws_regions)
    account_id = draw(aws_account_ids)
    bucket_name = draw(bucket_names)
    
    return f"arn:aws:s3tables:{region}:{account_id}:bucket/{bucket_name}", region


class TestS3TablesCatalogConfigurationProperty:
    """Property-based tests for S3 Tables catalog configuration."""
    
    @given(s3tables_arns())
    def test_rest_catalog_type_always_set(self, arn_and_region):
        """
        Property: For any S3 Tables ARN, the catalog configuration should have type 'rest'.
        
        **Validates: Requirements 6.1**
        """
        arn, expected_region = arn_and_region
        
        # Setup catalog
        catalog_config = setup_s3tables_catalog(arn)
        
        # Property: catalog type should always be 'rest'
        assert catalog_config['type'] == 'rest', \
            f"Expected catalog type 'rest' for ARN {arn}, got {catalog_config.get('type')}"
    
    @given(s3tables_arns())
    def test_warehouse_matches_arn(self, arn_and_region):
        """
        Property: For any S3 Tables ARN, the warehouse should be set to the ARN.
        
        **Validates: Requirements 6.1**
        """
        arn, expected_region = arn_and_region
        
        # Setup catalog
        catalog_config = setup_s3tables_catalog(arn)
        
        # Property: warehouse should match the input ARN
        assert catalog_config['warehouse'] == arn, \
            f"Expected warehouse to be {arn}, got {catalog_config.get('warehouse')}"
    
    @given(s3tables_arns())
    def test_rest_endpoint_includes_correct_region(self, arn_and_region):
        """
        Property: For any S3 Tables ARN, the REST endpoint should include the correct region.
        
        **Validates: Requirements 6.1, 6.3**
        """
        arn, expected_region = arn_and_region
        
        # Setup catalog
        catalog_config = setup_s3tables_catalog(arn)
        
        # Property: URI should contain the correct region
        expected_uri = f"https://s3tables.{expected_region}.amazonaws.com/iceberg"
        assert catalog_config['uri'] == expected_uri, \
            f"Expected URI {expected_uri}, got {catalog_config.get('uri')}"
    
    @given(s3tables_arns())
    def test_sigv4_authentication_enabled(self, arn_and_region):
        """
        Property: For any S3 Tables ARN, SigV4 authentication should be enabled.
        
        **Validates: Requirements 6.3**
        """
        arn, expected_region = arn_and_region
        
        # Setup catalog
        catalog_config = setup_s3tables_catalog(arn)
        
        # Property: SigV4 should be enabled
        assert catalog_config['rest.sigv4-enabled'] == 'true', \
            f"Expected SigV4 to be enabled for ARN {arn}"
    
    @given(s3tables_arns())
    def test_signing_name_is_s3tables(self, arn_and_region):
        """
        Property: For any S3 Tables ARN, the signing name should be 's3tables'.
        
        **Validates: Requirements 6.3**
        """
        arn, expected_region = arn_and_region
        
        # Setup catalog
        catalog_config = setup_s3tables_catalog(arn)
        
        # Property: signing name should be 's3tables'
        assert catalog_config['rest.signing-name'] == 's3tables', \
            f"Expected signing name 's3tables' for ARN {arn}, got {catalog_config.get('rest.signing-name')}"
    
    @given(s3tables_arns())
    def test_signing_region_matches_arn_region(self, arn_and_region):
        """
        Property: For any S3 Tables ARN, the signing region should match the region in the ARN.
        
        **Validates: Requirements 6.3**
        """
        arn, expected_region = arn_and_region
        
        # Setup catalog
        catalog_config = setup_s3tables_catalog(arn)
        
        # Property: signing region should match the ARN region
        assert catalog_config['rest.signing-region'] == expected_region, \
            f"Expected signing region {expected_region} for ARN {arn}, got {catalog_config.get('rest.signing-region')}"
    
    @given(s3tables_arns())
    def test_region_field_matches_arn_region(self, arn_and_region):
        """
        Property: For any S3 Tables ARN, the region field should match the region in the ARN.
        
        **Validates: Requirements 6.1**
        """
        arn, expected_region = arn_and_region
        
        # Setup catalog
        catalog_config = setup_s3tables_catalog(arn)
        
        # Property: region field should match the ARN region
        assert catalog_config['region'] == expected_region, \
            f"Expected region {expected_region} for ARN {arn}, got {catalog_config.get('region')}"
    
    @given(s3tables_arns())
    def test_all_required_fields_present(self, arn_and_region):
        """
        Property: For any S3 Tables ARN, all required configuration fields should be present.
        
        **Validates: Requirements 6.1, 6.3**
        """
        arn, expected_region = arn_and_region
        
        # Setup catalog
        catalog_config = setup_s3tables_catalog(arn)
        
        # Property: all required fields should be present
        required_fields = [
            'type',
            'warehouse',
            'uri',
            'rest.sigv4-enabled',
            'rest.signing-name',
            'rest.signing-region',
            'region'
        ]
        
        for field in required_fields:
            assert field in catalog_config, \
                f"Required field '{field}' missing from catalog config for ARN {arn}"
    
    @given(
        region=aws_regions,
        account_id=aws_account_ids,
        bucket=bucket_names
    )
    def test_region_extraction_is_consistent(self, region, account_id, bucket):
        """
        Property: For any S3 Tables ARN components, region extraction should be consistent
        with the region used in the catalog configuration.
        
        **Validates: Requirements 6.1, 6.3**
        """
        arn = f"arn:aws:s3tables:{region}:{account_id}:bucket/{bucket}"
        
        # Extract region
        extracted_region = extract_region_from_arn(arn)
        
        # Setup catalog
        catalog_config = setup_s3tables_catalog(arn)
        
        # Property: extracted region should match the region in all config fields
        assert extracted_region == region
        assert catalog_config['region'] == region
        assert catalog_config['rest.signing-region'] == region
        assert f"s3tables.{region}.amazonaws.com" in catalog_config['uri']
    
    @given(s3tables_arns())
    def test_configuration_is_deterministic(self, arn_and_region):
        """
        Property: For any S3 Tables ARN, calling setup_s3tables_catalog multiple times
        should produce identical configurations.
        
        **Validates: Requirements 6.1, 6.3**
        """
        arn, expected_region = arn_and_region
        
        # Setup catalog twice
        config1 = setup_s3tables_catalog(arn)
        config2 = setup_s3tables_catalog(arn)
        
        # Property: configurations should be identical
        assert config1 == config2, \
            f"Configuration should be deterministic for ARN {arn}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
