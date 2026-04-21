#!/usr/bin/env python3
"""
Unit tests for generate_summary module.

Tests cover:
- Summary JSON structure
- Required fields presence
- Timestamp formatting
- Duration calculation
- Field types
- Optional fields handling
"""

import pytest
import os
import sys
import json
import tempfile
from datetime import datetime, timedelta

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from generate_summary import (
    parse_timestamp,
    calculate_duration,
    build_summary,
    write_summary
)


class TestParseTimestamp:
    """Test timestamp parsing."""
    
    def test_parse_iso8601_with_z(self):
        """Test parsing ISO 8601 timestamp with Z suffix."""
        timestamp = '2024-01-15T10:30:00Z'
        dt = parse_timestamp(timestamp)
        assert isinstance(dt, datetime)
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.second == 0
    
    def test_parse_iso8601_with_timezone(self):
        """Test parsing ISO 8601 timestamp with timezone offset."""
        timestamp = '2024-01-15T10:30:00+00:00'
        dt = parse_timestamp(timestamp)
        assert isinstance(dt, datetime)
        assert dt.year == 2024
    
    def test_parse_iso8601_with_microseconds(self):
        """Test parsing ISO 8601 timestamp with microseconds."""
        timestamp = '2024-01-15T10:30:00.123456Z'
        dt = parse_timestamp(timestamp)
        assert isinstance(dt, datetime)
        assert dt.microsecond == 123456
    
    def test_parse_invalid_timestamp_format(self):
        """Test parsing invalid timestamp format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid timestamp format"):
            parse_timestamp('not-a-timestamp')
    
    def test_parse_empty_timestamp(self):
        """Test parsing empty timestamp raises ValueError."""
        with pytest.raises(ValueError, match="Invalid timestamp format"):
            parse_timestamp('')


class TestCalculateDuration:
    """Test duration calculation."""
    
    def test_calculate_duration_one_hour(self):
        """Test duration calculation for 1 hour."""
        start = '2024-01-15T10:00:00Z'
        end = '2024-01-15T11:00:00Z'
        duration = calculate_duration(start, end)
        assert duration == 3600
    
    def test_calculate_duration_one_minute(self):
        """Test duration calculation for 1 minute."""
        start = '2024-01-15T10:00:00Z'
        end = '2024-01-15T10:01:00Z'
        duration = calculate_duration(start, end)
        assert duration == 60
    
    def test_calculate_duration_one_day(self):
        """Test duration calculation for 1 day."""
        start = '2024-01-15T10:00:00Z'
        end = '2024-01-16T10:00:00Z'
        duration = calculate_duration(start, end)
        assert duration == 86400
    
    def test_calculate_duration_zero(self):
        """Test duration calculation for same start and end time."""
        start = '2024-01-15T10:00:00Z'
        end = '2024-01-15T10:00:00Z'
        duration = calculate_duration(start, end)
        assert duration == 0
    
    def test_calculate_duration_with_microseconds(self):
        """Test duration calculation with microseconds."""
        start = '2024-01-15T10:00:00.000000Z'
        end = '2024-01-15T10:00:00.500000Z'
        duration = calculate_duration(start, end)
        assert duration == 0  # Truncated to seconds
    
    def test_calculate_duration_15_minutes(self):
        """Test duration calculation for 15 minutes."""
        start = '2024-01-15T10:00:00Z'
        end = '2024-01-15T10:15:00Z'
        duration = calculate_duration(start, end)
        assert duration == 900


class TestBuildSummary:
    """Test summary building."""
    
    def test_build_summary_schema_1(self):
        """Test building summary for schema 1."""
        summary = build_summary(
            vcf_file='s3://bucket/sample.vcf',
            schema='1',
            destination='arn:aws:s3tables:us-east-1:123456789012:bucket/my-bucket',
            namespace='variant_db',
            catalog_type='s3tables',
            tables_created=['variants', 'samples', 'variant_samples'],
            variants_loaded=1000,
            samples_loaded=10,
            start_time='2024-01-15T10:00:00Z',
            end_time='2024-01-15T10:15:00Z'
        )
        
        assert summary['workflow'] == 'healthomics-vcf-loader'
        assert summary['version'] == '1.0.0'
        assert summary['inputs']['vcf_file'] == 's3://bucket/sample.vcf'
        assert summary['inputs']['schema'] == '1'
        assert summary['results']['catalog_type'] == 's3tables'
        assert summary['results']['tables_created'] == ['variants', 'samples', 'variant_samples']
        assert summary['results']['variants_loaded'] == 1000
        assert summary['results']['samples_loaded'] == 10
        assert summary['execution']['duration_seconds'] == 900
    
    def test_build_summary_schema_2(self):
        """Test building summary for schema 2."""
        summary = build_summary(
            vcf_file='s3://bucket/data.vcf.gz',
            schema='2',
            destination='s3://bucket/output',
            namespace='variant_db_2',
            catalog_type='vanilla',
            tables_created=['variant_regions', 'samples'],
            variants_loaded=5000,
            samples_loaded=20,
            start_time='2024-01-15T10:00:00Z',
            end_time='2024-01-15T11:00:00Z'
        )
        
        assert summary['inputs']['schema'] == '2'
        assert summary['results']['catalog_type'] == 'vanilla'
        assert summary['results']['tables_created'] == ['variant_regions', 'samples']
        assert summary['execution']['duration_seconds'] == 3600
    
    def test_build_summary_schema_3(self):
        """Test building summary for schema 3."""
        summary = build_summary(
            vcf_file='s3://bucket/variants.vcf',
            schema='3',
            destination='s3://bucket/iceberg',
            namespace='variant_db_3',
            catalog_type='vanilla',
            tables_created=['genomic_variants'],
            variants_loaded=2000,
            samples_loaded=5,
            start_time='2024-01-15T10:00:00Z',
            end_time='2024-01-15T10:30:00Z'
        )
        
        assert summary['inputs']['schema'] == '3'
        assert summary['results']['tables_created'] == ['genomic_variants']
        assert len(summary['results']['tables_created']) == 1
        assert summary['execution']['duration_seconds'] == 1800
    
    def test_build_summary_schema_4(self):
        """Test building summary for schema 4."""
        summary = build_summary(
            vcf_file='s3://bucket/test.vcf.gz',
            schema='4',
            destination='arn:aws:s3tables:eu-west-1:987654321098:bucket/test-bucket',
            namespace='variant_db_4',
            catalog_type='s3tables',
            tables_created=['variants', 'samples', 'variant_samples'],
            variants_loaded=3000,
            samples_loaded=15,
            start_time='2024-01-15T10:00:00Z',
            end_time='2024-01-15T10:45:00Z'
        )
        
        assert summary['inputs']['schema'] == '4'
        assert summary['results']['tables_created'] == ['variants', 'samples', 'variant_samples']
        assert summary['execution']['duration_seconds'] == 2700
    
    def test_build_summary_with_optional_fields(self):
        """Test building summary with optional fields."""
        summary = build_summary(
            vcf_file='s3://bucket/sample.vcf',
            schema='1',
            destination='s3://bucket/output',
            namespace='variant_db',
            catalog_type='vanilla',
            tables_created=['variants', 'samples', 'variant_samples'],
            variants_loaded=1000,
            samples_loaded=10,
            start_time='2024-01-15T10:00:00Z',
            end_time='2024-01-15T10:15:00Z',
            batch_size=50000,
            variant_sample_associations=10000,
            batches_processed=20,
            table_locations={
                'variants': 's3://bucket/output/variant_db/variants',
                'samples': 's3://bucket/output/variant_db/samples',
                'variant_samples': 's3://bucket/output/variant_db/variant_samples'
            }
        )
        
        assert summary['inputs']['batch_size'] == 50000
        assert summary['results']['variant_sample_associations'] == 10000
        assert summary['results']['batches_processed'] == 20
        assert 'table_locations' in summary
        assert len(summary['table_locations']) == 3
    
    def test_build_summary_required_fields_present(self):
        """Test that all required fields are present in summary."""
        summary = build_summary(
            vcf_file='s3://bucket/sample.vcf',
            schema='1',
            destination='s3://bucket/output',
            namespace='variant_db',
            catalog_type='vanilla',
            tables_created=['variants', 'samples', 'variant_samples'],
            variants_loaded=1000,
            samples_loaded=10,
            start_time='2024-01-15T10:00:00Z',
            end_time='2024-01-15T10:15:00Z'
        )
        
        # Top-level fields
        assert 'workflow' in summary
        assert 'version' in summary
        assert 'execution' in summary
        assert 'inputs' in summary
        assert 'results' in summary
        
        # Execution fields (Req 7.8)
        assert 'start_time' in summary['execution']
        assert 'end_time' in summary['execution']
        assert 'duration_seconds' in summary['execution']
        
        # Input fields (Req 7.7, 7.6, 7.5)
        assert 'vcf_file' in summary['inputs']
        assert 'schema' in summary['inputs']
        assert 'destination' in summary['inputs']
        assert 'namespace' in summary['inputs']
        assert 'batch_size' in summary['inputs']
        
        # Result fields (Req 7.2, 7.3, 7.4)
        assert 'catalog_type' in summary['results']
        assert 'tables_created' in summary['results']
        assert 'variants_loaded' in summary['results']
        assert 'samples_loaded' in summary['results']
    
    def test_build_summary_field_types(self):
        """Test that all fields have correct types."""
        summary = build_summary(
            vcf_file='s3://bucket/sample.vcf',
            schema='1',
            destination='s3://bucket/output',
            namespace='variant_db',
            catalog_type='vanilla',
            tables_created=['variants', 'samples', 'variant_samples'],
            variants_loaded=1000,
            samples_loaded=10,
            start_time='2024-01-15T10:00:00Z',
            end_time='2024-01-15T10:15:00Z'
        )
        
        # String fields
        assert isinstance(summary['workflow'], str)
        assert isinstance(summary['version'], str)
        assert isinstance(summary['execution']['start_time'], str)
        assert isinstance(summary['execution']['end_time'], str)
        assert isinstance(summary['inputs']['vcf_file'], str)
        assert isinstance(summary['inputs']['schema'], str)
        assert isinstance(summary['inputs']['destination'], str)
        assert isinstance(summary['inputs']['namespace'], str)
        assert isinstance(summary['results']['catalog_type'], str)
        
        # Integer fields
        assert isinstance(summary['execution']['duration_seconds'], int)
        assert isinstance(summary['inputs']['batch_size'], int)
        assert isinstance(summary['results']['variants_loaded'], int)
        assert isinstance(summary['results']['samples_loaded'], int)
        
        # List fields
        assert isinstance(summary['results']['tables_created'], list)
        for table in summary['results']['tables_created']:
            assert isinstance(table, str)
    
    def test_build_summary_zero_duration(self):
        """Test building summary with zero duration."""
        summary = build_summary(
            vcf_file='s3://bucket/sample.vcf',
            schema='1',
            destination='s3://bucket/output',
            namespace='variant_db',
            catalog_type='vanilla',
            tables_created=['variants'],
            variants_loaded=0,
            samples_loaded=0,
            start_time='2024-01-15T10:00:00Z',
            end_time='2024-01-15T10:00:00Z'
        )
        
        assert summary['execution']['duration_seconds'] == 0
    
    def test_build_summary_large_numbers(self):
        """Test building summary with large variant/sample counts."""
        summary = build_summary(
            vcf_file='s3://bucket/large.vcf.gz',
            schema='1',
            destination='s3://bucket/output',
            namespace='variant_db',
            catalog_type='vanilla',
            tables_created=['variants', 'samples', 'variant_samples'],
            variants_loaded=10000000,
            samples_loaded=1000,
            start_time='2024-01-15T10:00:00Z',
            end_time='2024-01-15T12:00:00Z'
        )
        
        assert summary['results']['variants_loaded'] == 10000000
        assert summary['results']['samples_loaded'] == 1000
        assert summary['execution']['duration_seconds'] == 7200


class TestWriteSummary:
    """Test summary writing to file."""
    
    def test_write_summary_to_file(self):
        """Test writing summary to JSON file."""
        summary = {
            'workflow': 'healthomics-vcf-loader',
            'version': '1.0.0',
            'execution': {
                'start_time': '2024-01-15T10:00:00Z',
                'end_time': '2024-01-15T10:15:00Z',
                'duration_seconds': 900
            },
            'inputs': {
                'vcf_file': 's3://bucket/sample.vcf',
                'schema': '1',
                'destination': 's3://bucket/output',
                'namespace': 'variant_db',
                'batch_size': 100000
            },
            'results': {
                'catalog_type': 'vanilla',
                'tables_created': ['variants', 'samples', 'variant_samples'],
                'variants_loaded': 1000,
                'samples_loaded': 10
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            write_summary(summary, temp_path)
            
            # Read back and verify
            with open(temp_path, 'r') as f:
                loaded = json.load(f)
            
            assert loaded == summary
            assert loaded['workflow'] == 'healthomics-vcf-loader'
            assert loaded['results']['variants_loaded'] == 1000
        finally:
            os.unlink(temp_path)
    
    def test_write_summary_creates_file(self):
        """Test that write_summary creates a new file."""
        summary = {
            'workflow': 'healthomics-vcf-loader',
            'version': '1.0.0'
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'summary.json')
            
            write_summary(summary, output_path)
            
            assert os.path.exists(output_path)
            assert os.path.isfile(output_path)
    
    def test_write_summary_invalid_path(self):
        """Test writing to invalid path raises IOError."""
        summary = {'workflow': 'test'}
        
        with pytest.raises(IOError, match="Failed to write summary"):
            write_summary(summary, '/nonexistent/directory/summary.json')
    
    def test_write_summary_json_formatting(self):
        """Test that written JSON is properly formatted."""
        summary = {
            'workflow': 'healthomics-vcf-loader',
            'results': {
                'variants_loaded': 1000
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            write_summary(summary, temp_path)
            
            # Read as text to check formatting
            with open(temp_path, 'r') as f:
                content = f.read()
            
            # Should be indented (not single line)
            assert '\n' in content
            assert '  ' in content  # Check for indentation
        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
