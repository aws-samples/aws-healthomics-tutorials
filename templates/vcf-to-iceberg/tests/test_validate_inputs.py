#!/usr/bin/env python3
"""
Unit tests for validate_inputs module.

Tests cover:
- VCF file validation (S3 and local paths)
- Schema validation (valid and invalid values)
- Destination format validation (S3 Tables ARN and S3 path)
- Catalog type determination
"""

import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError, NoCredentialsError

# Import the module to test
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from validate_inputs import (
    parse_s3_uri,
    validate_vcf_file,
    validate_schema,
    determine_catalog_type,
    validate_destination,
    validate_inputs
)


class TestParseS3Uri:
    """Test S3 URI parsing."""
    
    def test_parse_valid_s3_uri_with_key(self):
        """Test parsing S3 URI with bucket and key."""
        bucket, key = parse_s3_uri('s3://my-bucket/path/to/file.vcf')
        assert bucket == 'my-bucket'
        assert key == 'path/to/file.vcf'
    
    def test_parse_valid_s3_uri_without_key(self):
        """Test parsing S3 URI with only bucket."""
        bucket, key = parse_s3_uri('s3://my-bucket')
        assert bucket == 'my-bucket'
        assert key == ''
    
    def test_parse_invalid_uri_format(self):
        """Test parsing non-S3 URI raises ValueError."""
        with pytest.raises(ValueError, match="Invalid S3 URI format"):
            parse_s3_uri('/local/path/file.vcf')


class TestValidateSchema:
    """Test schema validation."""
    
    def test_valid_schema_1(self):
        """Test valid schema selection: 1."""
        assert validate_schema('1') == 1
    
    def test_valid_schema_2(self):
        """Test valid schema selection: 2."""
        assert validate_schema('2') == 2
    
    def test_valid_schema_3(self):
        """Test valid schema selection: 3."""
        assert validate_schema('3') == 3
    
    def test_valid_schema_4(self):
        """Test valid schema selection: 4."""
        assert validate_schema('4') == 4
    
    def test_invalid_schema_0(self):
        """Test invalid schema selection: 0."""
        with pytest.raises(ValueError, match="Invalid schema selection: 0"):
            validate_schema('0')
    
    def test_invalid_schema_5(self):
        """Test invalid schema selection: 5."""
        with pytest.raises(ValueError, match="Invalid schema selection: 5"):
            validate_schema('5')
    
    def test_invalid_schema_negative(self):
        """Test invalid schema selection: negative number."""
        with pytest.raises(ValueError, match="Invalid schema selection: -1"):
            validate_schema('-1')
    
    def test_invalid_schema_string(self):
        """Test invalid schema selection: non-numeric string."""
        with pytest.raises(ValueError, match="Invalid schema selection: invalid"):
            validate_schema('invalid')
    
    def test_invalid_schema_none(self):
        """Test invalid schema selection: None."""
        with pytest.raises(ValueError, match="Invalid schema selection: None"):
            validate_schema(None)


class TestDetermineCatalogType:
    """Test catalog type determination."""
    
    def test_s3tables_arn_format(self):
        """Test S3 Tables ARN is identified as s3tables catalog."""
        arn = 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-table-bucket'
        assert determine_catalog_type(arn) == 's3tables'
    
    def test_s3tables_arn_different_region(self):
        """Test S3 Tables ARN with different region."""
        arn = 'arn:aws:s3tables:eu-west-1:987654321098:bucket/my-bucket'
        assert determine_catalog_type(arn) == 's3tables'
    
    def test_s3_path_format(self):
        """Test S3 path is identified as vanilla catalog."""
        path = 's3://my-bucket/path/to/data'
        assert determine_catalog_type(path) == 'vanilla'
    
    def test_s3_path_bucket_only(self):
        """Test S3 path with bucket only."""
        path = 's3://my-bucket'
        assert determine_catalog_type(path) == 'vanilla'
    
    def test_invalid_destination_local_path(self):
        """Test local path raises ValueError."""
        with pytest.raises(ValueError, match="Invalid destination format"):
            determine_catalog_type('/local/path')
    
    def test_invalid_destination_http(self):
        """Test HTTP URL raises ValueError."""
        with pytest.raises(ValueError, match="Invalid destination format"):
            determine_catalog_type('http://example.com/data')
    
    def test_invalid_destination_empty(self):
        """Test empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid destination format"):
            determine_catalog_type('')


class TestValidateVcfFile:
    """Test VCF file validation."""
    
    def test_validate_local_file_exists(self):
        """Test validation of existing local file."""
        with tempfile.NamedTemporaryFile(suffix='.vcf', delete=False) as f:
            temp_path = f.name
        
        try:
            assert validate_vcf_file(temp_path) is True
        finally:
            os.unlink(temp_path)
    
    def test_validate_local_file_not_exists(self):
        """Test validation of non-existent local file."""
        with pytest.raises(FileNotFoundError, match="VCF file not found"):
            validate_vcf_file('/nonexistent/path/file.vcf')
    
    def test_validate_local_directory_not_file(self):
        """Test validation fails for directory path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(ValueError, match="Path is not a file"):
                validate_vcf_file(temp_dir)
    
    @patch('validate_inputs.boto3.client')
    def test_validate_s3_file_exists(self, mock_boto_client):
        """Test validation of existing S3 file."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {}
        
        assert validate_vcf_file('s3://my-bucket/data/file.vcf') is True
        mock_s3.head_object.assert_called_once_with(Bucket='my-bucket', Key='data/file.vcf')
    
    @patch('validate_inputs.boto3.client')
    def test_validate_s3_file_not_found(self, mock_boto_client):
        """Test validation of non-existent S3 file."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        error_response = {'Error': {'Code': '404'}}
        mock_s3.head_object.side_effect = ClientError(error_response, 'HeadObject')
        
        with pytest.raises(FileNotFoundError, match="VCF file not found in S3"):
            validate_vcf_file('s3://my-bucket/data/file.vcf')
    
    @patch('validate_inputs.boto3.client')
    def test_validate_s3_file_access_denied(self, mock_boto_client):
        """Test validation with S3 access denied."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        error_response = {'Error': {'Code': '403'}}
        mock_s3.head_object.side_effect = ClientError(error_response, 'HeadObject')
        
        with pytest.raises(PermissionError, match="Access denied to VCF file"):
            validate_vcf_file('s3://my-bucket/data/file.vcf')
    
    @patch('validate_inputs.boto3.client')
    def test_validate_s3_file_no_credentials(self, mock_boto_client):
        """Test validation with missing AWS credentials."""
        mock_boto_client.side_effect = NoCredentialsError()
        
        with pytest.raises(RuntimeError, match="AWS credentials not found"):
            validate_vcf_file('s3://my-bucket/data/file.vcf')


class TestValidateDestination:
    """Test destination validation."""
    
    def test_validate_s3tables_arn_valid_format(self):
        """Test validation of valid S3 Tables ARN."""
        arn = 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-table-bucket'
        assert validate_destination(arn, 's3tables') is True
    
    def test_validate_s3tables_arn_invalid_format_short(self):
        """Test validation of S3 Tables ARN with too few parts."""
        arn = 'arn:aws:s3tables:us-east-1'
        with pytest.raises(ValueError, match="Invalid S3 Tables ARN format"):
            validate_destination(arn, 's3tables')
    
    def test_validate_s3tables_arn_invalid_prefix(self):
        """Test validation of ARN with wrong prefix."""
        arn = 'arn:aws:s3:us-east-1:123456789012:bucket/my-bucket'
        with pytest.raises(ValueError, match="Invalid S3 Tables ARN format"):
            validate_destination(arn, 's3tables')
    
    def test_validate_s3tables_arn_missing_region(self):
        """Test validation of S3 Tables ARN with missing region."""
        arn = 'arn:aws:s3tables::123456789012:bucket/my-table-bucket'
        with pytest.raises(ValueError, match="Invalid S3 Tables ARN: missing region"):
            validate_destination(arn, 's3tables')
    
    @patch('validate_inputs.boto3.client')
    def test_validate_vanilla_s3_bucket_exists(self, mock_boto_client):
        """Test validation of accessible S3 bucket."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_bucket.return_value = {}
        
        assert validate_destination('s3://my-bucket/path', 'vanilla') is True
        mock_s3.head_bucket.assert_called_once_with(Bucket='my-bucket')
    
    @patch('validate_inputs.boto3.client')
    def test_validate_vanilla_s3_bucket_not_found(self, mock_boto_client):
        """Test validation of non-existent S3 bucket."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        error_response = {'Error': {'Code': '404'}}
        mock_s3.head_bucket.side_effect = ClientError(error_response, 'HeadBucket')
        
        with pytest.raises(RuntimeError, match="S3 bucket not found"):
            validate_destination('s3://my-bucket/path', 'vanilla')
    
    @patch('validate_inputs.boto3.client')
    def test_validate_vanilla_s3_bucket_access_denied(self, mock_boto_client):
        """Test validation with S3 bucket access denied."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        error_response = {'Error': {'Code': '403'}}
        mock_s3.head_bucket.side_effect = ClientError(error_response, 'HeadBucket')
        
        with pytest.raises(PermissionError, match="Access denied to S3 bucket"):
            validate_destination('s3://my-bucket/path', 'vanilla')


class TestValidateInputs:
    """Test complete input validation."""
    
    @patch('validate_inputs.boto3.client')
    def test_validate_inputs_s3tables_success(self, mock_boto_client):
        """Test successful validation with S3 Tables destination."""
        # Mock S3 client for VCF file check
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {}
        
        vcf_file = 's3://my-bucket/data/sample.vcf.gz'
        schema = '1'
        destination = 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-table-bucket'
        
        result = validate_inputs(vcf_file, schema, destination)
        
        assert result['vcf_file'] == vcf_file
        assert result['schema'] == 1
        assert result['destination'] == destination
        assert result['catalog_type'] == 's3tables'
        assert result['status'] == 'valid'
    
    @patch('validate_inputs.boto3.client')
    def test_validate_inputs_vanilla_success(self, mock_boto_client):
        """Test successful validation with vanilla S3 destination."""
        # Mock S3 client for both VCF file and bucket checks
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {}
        mock_s3.head_bucket.return_value = {}
        
        vcf_file = 's3://my-bucket/data/sample.vcf.gz'
        schema = '2'
        destination = 's3://my-dest-bucket/iceberg'
        
        result = validate_inputs(vcf_file, schema, destination)
        
        assert result['vcf_file'] == vcf_file
        assert result['schema'] == 2
        assert result['destination'] == destination
        assert result['catalog_type'] == 'vanilla'
        assert result['status'] == 'valid'
    
    def test_validate_inputs_local_vcf_success(self):
        """Test successful validation with local VCF file."""
        with tempfile.NamedTemporaryFile(suffix='.vcf', delete=False) as f:
            temp_path = f.name
        
        try:
            destination = 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-table-bucket'
            result = validate_inputs(temp_path, '3', destination)
            
            assert result['vcf_file'] == temp_path
            assert result['schema'] == 3
            assert result['catalog_type'] == 's3tables'
            assert result['status'] == 'valid'
        finally:
            os.unlink(temp_path)
    
    def test_validate_inputs_invalid_schema(self):
        """Test validation fails with invalid schema."""
        with tempfile.NamedTemporaryFile(suffix='.vcf', delete=False) as f:
            temp_path = f.name
        
        try:
            destination = 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-table-bucket'
            with pytest.raises(ValueError, match="Invalid schema selection"):
                validate_inputs(temp_path, '5', destination)
        finally:
            os.unlink(temp_path)
    
    def test_validate_inputs_invalid_destination(self):
        """Test validation fails with invalid destination format."""
        with tempfile.NamedTemporaryFile(suffix='.vcf', delete=False) as f:
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError, match="Invalid destination format"):
                validate_inputs(temp_path, '1', '/local/path')
        finally:
            os.unlink(temp_path)
    
    def test_validate_inputs_vcf_not_found(self):
        """Test validation fails with non-existent VCF file."""
        destination = 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-table-bucket'
        with pytest.raises(FileNotFoundError, match="VCF file not found"):
            validate_inputs('/nonexistent/file.vcf', '1', destination)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
