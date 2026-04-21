#!/usr/bin/env python3
"""
Property-based tests for vanilla Iceberg catalog configuration.

**Validates: Requirements 6.2**

Property 3: Vanilla Catalog Configuration
For any S3 path destination, the catalog configuration should use the "glue" type
with the warehouse set to the S3 path and client.region set appropriately.
"""

import pytest
import os
import sys
from hypothesis import given, strategies as st
from unittest.mock import patch, MagicMock

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from setup_catalog import setup_vanilla_catalog, extract_region_from_s3_path


# Strategy for generating valid AWS regions
aws_regions = st.sampled_from([
    'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
    'eu-west-1', 'eu-west-2', 'eu-central-1',
    'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1',
    'ap-south-1', 'ca-central-1', 'sa-east-1'
])

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


class TestVanillaCatalogConfigurationProperty:
    """Property-based tests for vanilla Iceberg catalog configuration."""
    
    @given(s3_paths_strategy(), aws_regions)
    def test_glue_catalog_type_always_set(self, s3_path, region):
        """
        Property: For any S3 path, the catalog configuration should have type 'glue'.
        
        **Validates: Requirements 6.2**
        """
        with patch('setup_catalog.boto3.session.Session') as mock_session:
            mock_session_instance = MagicMock()
            mock_session_instance.region_name = region
            mock_session.return_value = mock_session_instance
            
            catalog_config = setup_vanilla_catalog(s3_path)
            
            assert catalog_config['type'] == 'glue', \
                f"Expected catalog type 'glue' for S3 path {s3_path}, got {catalog_config.get('type')}"
    
    @given(s3_paths_strategy(), aws_regions)
    def test_warehouse_matches_s3_path(self, s3_path, region):
        """
        Property: For any S3 path, the warehouse should be set to the S3 path.
        
        **Validates: Requirements 6.2**
        """
        with patch('setup_catalog.boto3.session.Session') as mock_session:
            mock_session_instance = MagicMock()
            mock_session_instance.region_name = region
            mock_session.return_value = mock_session_instance
            
            catalog_config = setup_vanilla_catalog(s3_path)
            
            assert catalog_config['warehouse'] == s3_path, \
                f"Expected warehouse to be {s3_path}, got {catalog_config.get('warehouse')}"
    
    @given(s3_paths_strategy(), aws_regions)
    def test_client_region_includes_region(self, s3_path, region):
        """
        Property: For any S3 path, the client.region should match the session region.
        
        **Validates: Requirements 6.2**
        """
        with patch('setup_catalog.boto3.session.Session') as mock_session:
            mock_session_instance = MagicMock()
            mock_session_instance.region_name = region
            mock_session.return_value = mock_session_instance
            
            catalog_config = setup_vanilla_catalog(s3_path)
            
            assert catalog_config['client.region'] == region, \
                f"Expected client.region {region}, got {catalog_config.get('client.region')}"
    
    @given(s3_paths_strategy(), aws_regions)
    def test_all_required_fields_present(self, s3_path, region):
        """
        Property: For any S3 path, all required configuration fields should be present.
        
        **Validates: Requirements 6.2**
        """
        with patch('setup_catalog.boto3.session.Session') as mock_session:
            mock_session_instance = MagicMock()
            mock_session_instance.region_name = region
            mock_session.return_value = mock_session_instance
            
            catalog_config = setup_vanilla_catalog(s3_path)
            
            required_fields = [
                'type',
                'warehouse',
                'client.region'
            ]
            
            for field in required_fields:
                assert field in catalog_config, \
                    f"Required field '{field}' missing from catalog config for S3 path {s3_path}"
    
    @given(s3_paths_strategy(), aws_regions)
    def test_configuration_is_deterministic(self, s3_path, region):
        """
        Property: For any S3 path, calling setup_vanilla_catalog multiple times
        should produce identical configurations (with same region).
        
        **Validates: Requirements 6.2**
        """
        with patch('setup_catalog.boto3.session.Session') as mock_session:
            mock_session_instance = MagicMock()
            mock_session_instance.region_name = region
            mock_session.return_value = mock_session_instance
            
            config1 = setup_vanilla_catalog(s3_path)
            config2 = setup_vanilla_catalog(s3_path)
            
            assert config1 == config2, \
                f"Configuration should be deterministic for S3 path {s3_path}"
    
    @given(
        bucket=bucket_names,
        path=s3_paths,
        region=aws_regions
    )
    def test_s3_path_components_preserved(self, bucket, path, region):
        """
        Property: For any valid bucket and path components, the warehouse should
        preserve the complete S3 path.
        
        **Validates: Requirements 6.2**
        """
        if path:
            s3_uri = f"s3://{bucket}/{path}"
        else:
            s3_uri = f"s3://{bucket}"
        
        with patch('setup_catalog.boto3.session.Session') as mock_session:
            mock_session_instance = MagicMock()
            mock_session_instance.region_name = region
            mock_session.return_value = mock_session_instance
            
            catalog_config = setup_vanilla_catalog(s3_uri)
            
            assert catalog_config['warehouse'] == s3_uri, \
                f"Expected warehouse to preserve S3 path {s3_uri}"
    
    @given(s3_paths_strategy())
    def test_default_region_when_no_session_region(self, s3_path):
        """
        Property: For any S3 path, when no region is configured in boto3 session,
        the configuration should default to 'us-east-1'.
        
        **Validates: Requirements 6.2**
        """
        with patch('setup_catalog.boto3.session.Session') as mock_session:
            mock_session_instance = MagicMock()
            mock_session_instance.region_name = None
            mock_session.return_value = mock_session_instance
            
            catalog_config = setup_vanilla_catalog(s3_path)
            
            assert catalog_config['client.region'] == 'us-east-1', \
                f"Expected default region 'us-east-1' when no session region configured"
    
    @given(s3_paths_strategy(), aws_regions)
    def test_no_rest_catalog_fields_present(self, s3_path, region):
        """
        Property: For any S3 path, the vanilla catalog configuration should NOT
        contain REST catalog fields (uri, rest.sigv4-enabled, etc.).
        
        **Validates: Requirements 6.2**
        """
        with patch('setup_catalog.boto3.session.Session') as mock_session:
            mock_session_instance = MagicMock()
            mock_session_instance.region_name = region
            mock_session.return_value = mock_session_instance
            
            catalog_config = setup_vanilla_catalog(s3_path)
            
            rest_fields = [
                'uri',
                'rest.sigv4-enabled',
                'rest.signing-name',
                'rest.signing-region'
            ]
            
            for field in rest_fields:
                assert field not in catalog_config, \
                    f"REST catalog field '{field}' should not be present in vanilla catalog config"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
