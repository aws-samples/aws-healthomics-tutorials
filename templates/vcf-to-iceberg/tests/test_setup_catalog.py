#!/usr/bin/env python3
"""
Unit tests for setup_catalog module.

Tests cover:
- S3 Tables catalog configuration for different regions
- Vanilla catalog configuration
- Region extraction from ARN
- Error handling for invalid inputs
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from setup_catalog import (
    extract_region_from_arn,
    extract_region_from_s3_path,
    setup_s3tables_catalog,
    setup_vanilla_catalog,
    setup_catalog
)


class TestExtractRegionFromArn:
    """Test region extraction from S3 Tables ARN."""
    
    def test_extract_region_us_east_1(self):
        """Test extracting us-east-1 region from ARN."""
        arn = 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-table-bucket'
        region = extract_region_from_arn(arn)
        assert region == 'us-east-1'
    
    def test_extract_region_eu_west_1(self):
        """Test extracting eu-west-1 region from ARN."""
        arn = 'arn:aws:s3tables:eu-west-1:987654321098:bucket/my-bucket'
        region = extract_region_from_arn(arn)
        assert region == 'eu-west-1'
    
    def test_extract_region_ap_southeast_2(self):
        """Test extracting ap-southeast-2 region from ARN."""
        arn = 'arn:aws:s3tables:ap-southeast-2:111111111111:bucket/test-bucket'
        region = extract_region_from_arn(arn)
        assert region == 'ap-southeast-2'
    
    def test_extract_region_us_west_2(self):
        """Test extracting us-west-2 region from ARN."""
        arn = 'arn:aws:s3tables:us-west-2:222222222222:bucket/data-bucket'
        region = extract_region_from_arn(arn)
        assert region == 'us-west-2'
    
    def test_invalid_arn_too_few_parts(self):
        """Test error when ARN has too few parts."""
        arn = 'arn:aws:s3tables:us-east-1'
        with pytest.raises(ValueError, match="Invalid S3 Tables ARN format"):
            extract_region_from_arn(arn)
    
    def test_invalid_arn_wrong_prefix(self):
        """Test error when ARN has wrong service prefix."""
        arn = 'arn:aws:s3:us-east-1:123456789012:bucket/my-bucket'
        with pytest.raises(ValueError, match="Invalid S3 Tables ARN format"):
            extract_region_from_arn(arn)
    
    def test_invalid_arn_missing_region(self):
        """Test error when ARN has empty region field."""
        arn = 'arn:aws:s3tables::123456789012:bucket/my-table-bucket'
        with pytest.raises(ValueError, match="Invalid S3 Tables ARN: missing region"):
            extract_region_from_arn(arn)
    
    def test_invalid_arn_not_arn_prefix(self):
        """Test error when string doesn't start with 'arn'."""
        arn = 's3://my-bucket/path'
        with pytest.raises(ValueError, match="Invalid S3 Tables ARN format"):
            extract_region_from_arn(arn)


class TestExtractRegionFromS3Path:
    """Test region extraction from S3 path."""
    
    @patch('setup_catalog.boto3.session.Session')
    def test_extract_region_from_session(self, mock_session_class):
        """Test extracting region from boto3 session."""
        mock_session = MagicMock()
        mock_session.region_name = 'us-west-1'
        mock_session_class.return_value = mock_session
        
        region = extract_region_from_s3_path('s3://my-bucket/path')
        assert region == 'us-west-1'
    
    @patch('setup_catalog.boto3.session.Session')
    def test_extract_region_defaults_to_us_east_1(self, mock_session_class):
        """Test default region when session has no region configured."""
        mock_session = MagicMock()
        mock_session.region_name = None
        mock_session_class.return_value = mock_session
        
        region = extract_region_from_s3_path('s3://my-bucket/path')
        assert region == 'us-east-1'


class TestSetupS3TablesCatalog:
    """Test S3 Tables catalog configuration."""
    
    def test_s3tables_catalog_us_east_1(self):
        """Test S3 Tables catalog config for us-east-1."""
        arn = 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-table-bucket'
        config = setup_s3tables_catalog(arn)
        
        assert config['type'] == 'rest'
        assert config['warehouse'] == arn
        assert config['uri'] == 'https://s3tables.us-east-1.amazonaws.com/iceberg'
        assert config['rest.sigv4-enabled'] == 'true'
        assert config['rest.signing-name'] == 's3tables'
        assert config['rest.signing-region'] == 'us-east-1'
        assert config['region'] == 'us-east-1'
    
    def test_s3tables_catalog_eu_west_1(self):
        """Test S3 Tables catalog config for eu-west-1."""
        arn = 'arn:aws:s3tables:eu-west-1:987654321098:bucket/my-bucket'
        config = setup_s3tables_catalog(arn)
        
        assert config['type'] == 'rest'
        assert config['warehouse'] == arn
        assert config['uri'] == 'https://s3tables.eu-west-1.amazonaws.com/iceberg'
        assert config['rest.sigv4-enabled'] == 'true'
        assert config['rest.signing-name'] == 's3tables'
        assert config['rest.signing-region'] == 'eu-west-1'
        assert config['region'] == 'eu-west-1'
    
    def test_s3tables_catalog_ap_southeast_2(self):
        """Test S3 Tables catalog config for ap-southeast-2."""
        arn = 'arn:aws:s3tables:ap-southeast-2:111111111111:bucket/test-bucket'
        config = setup_s3tables_catalog(arn)
        
        assert config['type'] == 'rest'
        assert config['warehouse'] == arn
        assert config['uri'] == 'https://s3tables.ap-southeast-2.amazonaws.com/iceberg'
        assert config['rest.sigv4-enabled'] == 'true'
        assert config['rest.signing-name'] == 's3tables'
        assert config['rest.signing-region'] == 'ap-southeast-2'
        assert config['region'] == 'ap-southeast-2'
    
    def test_s3tables_catalog_us_west_2(self):
        """Test S3 Tables catalog config for us-west-2."""
        arn = 'arn:aws:s3tables:us-west-2:222222222222:bucket/data-bucket'
        config = setup_s3tables_catalog(arn)
        
        assert config['type'] == 'rest'
        assert config['warehouse'] == arn
        assert config['uri'] == 'https://s3tables.us-west-2.amazonaws.com/iceberg'
        assert config['rest.sigv4-enabled'] == 'true'
        assert config['rest.signing-name'] == 's3tables'
        assert config['rest.signing-region'] == 'us-west-2'
        assert config['region'] == 'us-west-2'
    
    def test_s3tables_catalog_invalid_arn(self):
        """Test error with invalid ARN format."""
        arn = 'arn:aws:s3:us-east-1:123456789012:bucket/my-bucket'
        with pytest.raises(ValueError, match="Invalid S3 Tables ARN format"):
            setup_s3tables_catalog(arn)


class TestSetupVanillaCatalog:
    """Test vanilla Iceberg catalog configuration."""
    
    @patch('setup_catalog.boto3.session.Session')
    def test_vanilla_catalog_with_path(self, mock_session_class):
        """Test vanilla catalog config with S3 path."""
        mock_session = MagicMock()
        mock_session.region_name = 'us-east-1'
        mock_session_class.return_value = mock_session
        
        s3_path = 's3://my-bucket/iceberg/warehouse'
        config = setup_vanilla_catalog(s3_path)
        
        assert config['type'] == 'glue'
        assert config['warehouse'] == s3_path
        assert config['client.region'] == 'us-east-1'
    
    @patch('setup_catalog.boto3.session.Session')
    def test_vanilla_catalog_bucket_only(self, mock_session_class):
        """Test vanilla catalog config with bucket only."""
        mock_session = MagicMock()
        mock_session.region_name = 'eu-west-1'
        mock_session_class.return_value = mock_session
        
        s3_path = 's3://my-bucket'
        config = setup_vanilla_catalog(s3_path)
        
        assert config['type'] == 'glue'
        assert config['warehouse'] == s3_path
        assert config['client.region'] == 'eu-west-1'
    
    @patch('setup_catalog.boto3.session.Session')
    def test_vanilla_catalog_default_region(self, mock_session_class):
        """Test vanilla catalog config defaults to us-east-1 when no region configured."""
        mock_session = MagicMock()
        mock_session.region_name = None
        mock_session_class.return_value = mock_session
        
        s3_path = 's3://my-bucket/data'
        config = setup_vanilla_catalog(s3_path)
        
        assert config['type'] == 'glue'
        assert config['warehouse'] == s3_path
        assert config['client.region'] == 'us-east-1'


class TestSetupCatalog:
    """Test complete catalog setup function."""
    
    def test_setup_s3tables_catalog_without_namespace(self):
        """Test setting up S3 Tables catalog without namespace."""
        arn = 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-table-bucket'
        result = setup_catalog('s3tables', arn)
        
        assert result['catalog_type'] == 's3tables'
        assert result['destination'] == arn
        assert result['status'] == 'configured'
        assert 'catalog_config' in result
        assert result['catalog_config']['type'] == 'rest'
        assert result['catalog_config']['warehouse'] == arn
        assert 'namespace' not in result['catalog_config']
    
    def test_setup_s3tables_catalog_with_namespace(self):
        """Test setting up S3 Tables catalog with namespace."""
        arn = 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-table-bucket'
        namespace = 'variant_db'
        result = setup_catalog('s3tables', arn, namespace)
        
        assert result['catalog_type'] == 's3tables'
        assert result['destination'] == arn
        assert result['status'] == 'configured'
        assert result['catalog_config']['namespace'] == namespace
    
    @patch('setup_catalog.boto3.session.Session')
    def test_setup_vanilla_catalog_without_namespace(self, mock_session_class):
        """Test setting up vanilla catalog without namespace."""
        mock_session = MagicMock()
        mock_session.region_name = 'us-west-2'
        mock_session_class.return_value = mock_session
        
        s3_path = 's3://my-bucket/iceberg'
        result = setup_catalog('vanilla', s3_path)
        
        assert result['catalog_type'] == 'vanilla'
        assert result['destination'] == s3_path
        assert result['status'] == 'configured'
        assert 'catalog_config' in result
        assert result['catalog_config']['type'] == 'glue'
        assert result['catalog_config']['warehouse'] == s3_path
        assert 'namespace' not in result['catalog_config']
    
    @patch('setup_catalog.boto3.session.Session')
    def test_setup_vanilla_catalog_with_namespace(self, mock_session_class):
        """Test setting up vanilla catalog with namespace."""
        mock_session = MagicMock()
        mock_session.region_name = 'us-west-2'
        mock_session_class.return_value = mock_session
        
        s3_path = 's3://my-bucket/iceberg'
        namespace = 'variant_db_2'
        result = setup_catalog('vanilla', s3_path, namespace)
        
        assert result['catalog_type'] == 'vanilla'
        assert result['destination'] == s3_path
        assert result['status'] == 'configured'
        assert result['catalog_config']['namespace'] == namespace
    
    def test_setup_catalog_invalid_type(self):
        """Test error with invalid catalog type."""
        with pytest.raises(ValueError, match="Invalid catalog type"):
            setup_catalog('invalid', 's3://my-bucket')
    
    def test_setup_catalog_empty_type(self):
        """Test error with empty catalog type."""
        with pytest.raises(ValueError, match="Invalid catalog type"):
            setup_catalog('', 's3://my-bucket')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
