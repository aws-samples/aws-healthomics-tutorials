#!/usr/bin/env python3
"""
Property-based tests for summary JSON completeness.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8**

Property 12: Summary JSON Completeness
For any successful workflow execution, the generated summary JSON should contain
all required fields: vcf_file, schema, destination, namespace, catalog_type,
tables_created, variants_loaded, samples_loaded, start_time, and end_time.
"""

import pytest
import os
import sys
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, assume

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from generate_summary import build_summary


# Strategy for generating valid schema selections
schemas = st.sampled_from(['1', '2', '3', '4'])

# Strategy for generating valid catalog types
catalog_types = st.sampled_from(['s3tables', 'vanilla'])

# Strategy for generating valid AWS regions
aws_regions = st.sampled_from([
    'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
    'eu-west-1', 'eu-west-2', 'eu-central-1',
    'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1'
])

# Strategy for generating valid bucket names
bucket_names = st.text(
    alphabet=st.characters(categories=('Ll', 'Nd'), include_characters='-'),
    min_size=3,
    max_size=63
).filter(lambda x: x and x[0].isalnum() and x[-1].isalnum() and '--' not in x)

# Strategy for generating S3 paths
s3_paths = st.text(
    alphabet=st.characters(categories=('Lu', 'Ll', 'Nd'), include_characters='/-_.'),
    min_size=1,
    max_size=100
).filter(lambda x: '//' not in x)

# Strategy for generating VCF file paths
@st.composite
def vcf_file_paths(draw):
    """Generate valid VCF file paths."""
    bucket = draw(bucket_names)
    path = draw(s3_paths)
    filename = draw(st.sampled_from(['sample.vcf', 'sample.vcf.gz', 'data.vcf', 'variants.vcf.gz']))
    return f"s3://{bucket}/{path}/{filename}"

# Strategy for generating destination paths
@st.composite
def destinations(draw):
    """Generate valid destination paths (S3 Tables ARN or S3 path)."""
    catalog_type = draw(catalog_types)
    bucket = draw(bucket_names)
    
    if catalog_type == 's3tables':
        region = draw(aws_regions)
        account_id = draw(st.integers(min_value=100000000000, max_value=999999999999).map(str))
        return f"arn:aws:s3tables:{region}:{account_id}:bucket/{bucket}"
    else:
        path = draw(s3_paths)
        return f"s3://{bucket}/{path}"

# Strategy for generating namespace names
namespaces = st.sampled_from(['variant_db', 'variant_db_2', 'variant_db_3', 'variant_db_4'])

# Strategy for generating table names based on schema
@st.composite
def tables_created_for_schema(draw, schema):
    """Generate appropriate table names for a given schema."""
    schema_tables = {
        '1': ['variants', 'samples', 'variant_samples'],
        '2': ['variant_regions', 'samples'],
        '3': ['genomic_variants'],
        '4': ['variants', 'samples', 'variant_samples']
    }
    return schema_tables.get(schema, [])

# Strategy for generating positive integers
positive_ints = st.integers(min_value=0, max_value=10000000)

# Strategy for generating ISO 8601 timestamps
@st.composite
def iso_timestamps(draw):
    """Generate valid ISO 8601 timestamp strings."""
    # Generate a datetime within the last year
    days_ago = draw(st.integers(min_value=0, max_value=365))
    hours = draw(st.integers(min_value=0, max_value=23))
    minutes = draw(st.integers(min_value=0, max_value=59))
    seconds = draw(st.integers(min_value=0, max_value=59))
    
    dt = datetime.now() - timedelta(days=days_ago, hours=hours, minutes=minutes, seconds=seconds)
    return dt.isoformat() + 'Z'

# Strategy for generating start and end time pairs
@st.composite
def timestamp_pairs(draw):
    """Generate valid start and end timestamp pairs where end > start."""
    start_dt = datetime.now() - timedelta(days=draw(st.integers(min_value=0, max_value=365)))
    duration_seconds = draw(st.integers(min_value=1, max_value=86400))  # 1 second to 1 day
    end_dt = start_dt + timedelta(seconds=duration_seconds)
    
    start_time = start_dt.isoformat() + 'Z'
    end_time = end_dt.isoformat() + 'Z'
    
    return start_time, end_time


class TestSummaryJSONCompletenessProperty:
    """Property-based tests for summary JSON completeness."""
    
    @given(
        vcf_file=vcf_file_paths(),
        schema=schemas,
        destination=destinations(),
        namespace=namespaces,
        catalog_type=catalog_types,
        variants_loaded=positive_ints,
        samples_loaded=positive_ints,
        timestamps=timestamp_pairs()
    )
    def test_summary_contains_all_required_fields(
        self, vcf_file, schema, destination, namespace, catalog_type,
        variants_loaded, samples_loaded, timestamps
    ):
        """
        Property: For any valid workflow parameters, the summary JSON should contain
        all required fields.
        
        **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8**
        """
        start_time, end_time = timestamps
        
        # Generate appropriate tables for the schema
        schema_tables = {
            '1': ['variants', 'samples', 'variant_samples'],
            '2': ['variant_regions', 'samples'],
            '3': ['genomic_variants'],
            '4': ['variants', 'samples', 'variant_samples']
        }
        tables_created = schema_tables[schema]
        
        # Build summary
        summary = build_summary(
            vcf_file=vcf_file,
            schema=schema,
            destination=destination,
            namespace=namespace,
            catalog_type=catalog_type,
            tables_created=tables_created,
            variants_loaded=variants_loaded,
            samples_loaded=samples_loaded,
            start_time=start_time,
            end_time=end_time
        )
        
        # Property: Summary must be a dictionary
        assert isinstance(summary, dict), "Summary should be a dictionary"
        
        # Property: Summary must contain top-level required fields
        assert 'workflow' in summary, "Summary must contain 'workflow' field"
        assert 'version' in summary, "Summary must contain 'version' field"
        assert 'execution' in summary, "Summary must contain 'execution' field"
        assert 'inputs' in summary, "Summary must contain 'inputs' field"
        assert 'results' in summary, "Summary must contain 'results' field"
        
        # Property: Execution section must contain required fields (Req 7.8)
        assert 'start_time' in summary['execution'], "Execution must contain 'start_time'"
        assert 'end_time' in summary['execution'], "Execution must contain 'end_time'"
        assert 'duration_seconds' in summary['execution'], "Execution must contain 'duration_seconds'"
        
        # Property: Inputs section must contain required fields (Req 7.7, 7.6, 7.5)
        assert 'vcf_file' in summary['inputs'], "Inputs must contain 'vcf_file' (Req 7.7)"
        assert 'schema' in summary['inputs'], "Inputs must contain 'schema' (Req 7.6)"
        assert 'destination' in summary['inputs'], "Inputs must contain 'destination' (Req 7.5)"
        assert 'namespace' in summary['inputs'], "Inputs must contain 'namespace'"
        
        # Property: Results section must contain required fields (Req 7.2, 7.3, 7.4)
        assert 'catalog_type' in summary['results'], "Results must contain 'catalog_type'"
        assert 'tables_created' in summary['results'], "Results must contain 'tables_created' (Req 7.4)"
        assert 'variants_loaded' in summary['results'], "Results must contain 'variants_loaded' (Req 7.2)"
        assert 'samples_loaded' in summary['results'], "Results must contain 'samples_loaded' (Req 7.3)"
        
        # Property: Values must match inputs
        assert summary['inputs']['vcf_file'] == vcf_file
        assert summary['inputs']['schema'] == schema
        assert summary['inputs']['destination'] == destination
        assert summary['inputs']['namespace'] == namespace
        assert summary['results']['catalog_type'] == catalog_type
        assert summary['results']['tables_created'] == tables_created
        assert summary['results']['variants_loaded'] == variants_loaded
        assert summary['results']['samples_loaded'] == samples_loaded
        assert summary['execution']['start_time'] == start_time
        assert summary['execution']['end_time'] == end_time
    
    @given(
        vcf_file=vcf_file_paths(),
        schema=schemas,
        destination=destinations(),
        namespace=namespaces,
        catalog_type=catalog_types,
        variants_loaded=positive_ints,
        samples_loaded=positive_ints,
        timestamps=timestamp_pairs()
    )
    def test_summary_field_types_are_correct(
        self, vcf_file, schema, destination, namespace, catalog_type,
        variants_loaded, samples_loaded, timestamps
    ):
        """
        Property: All fields in the summary JSON should have the correct data types.
        
        **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8**
        """
        start_time, end_time = timestamps
        
        schema_tables = {
            '1': ['variants', 'samples', 'variant_samples'],
            '2': ['variant_regions', 'samples'],
            '3': ['genomic_variants'],
            '4': ['variants', 'samples', 'variant_samples']
        }
        tables_created = schema_tables[schema]
        
        summary = build_summary(
            vcf_file=vcf_file,
            schema=schema,
            destination=destination,
            namespace=namespace,
            catalog_type=catalog_type,
            tables_created=tables_created,
            variants_loaded=variants_loaded,
            samples_loaded=samples_loaded,
            start_time=start_time,
            end_time=end_time
        )
        
        # Property: String fields must be strings
        assert isinstance(summary['workflow'], str)
        assert isinstance(summary['version'], str)
        assert isinstance(summary['execution']['start_time'], str)
        assert isinstance(summary['execution']['end_time'], str)
        assert isinstance(summary['inputs']['vcf_file'], str)
        assert isinstance(summary['inputs']['schema'], str)
        assert isinstance(summary['inputs']['destination'], str)
        assert isinstance(summary['inputs']['namespace'], str)
        assert isinstance(summary['results']['catalog_type'], str)
        
        # Property: Integer fields must be integers
        assert isinstance(summary['execution']['duration_seconds'], int)
        assert isinstance(summary['inputs']['batch_size'], int)
        assert isinstance(summary['results']['variants_loaded'], int)
        assert isinstance(summary['results']['samples_loaded'], int)
        
        # Property: List fields must be lists
        assert isinstance(summary['results']['tables_created'], list)
        
        # Property: All items in tables_created must be strings
        for table in summary['results']['tables_created']:
            assert isinstance(table, str)
    
    @given(
        vcf_file=vcf_file_paths(),
        schema=schemas,
        destination=destinations(),
        namespace=namespaces,
        catalog_type=catalog_types,
        variants_loaded=positive_ints,
        samples_loaded=positive_ints,
        timestamps=timestamp_pairs()
    )
    def test_duration_calculation_is_correct(
        self, vcf_file, schema, destination, namespace, catalog_type,
        variants_loaded, samples_loaded, timestamps
    ):
        """
        Property: The duration_seconds field should correctly represent the time
        difference between start_time and end_time.
        
        **Validates: Requirements 7.8**
        """
        start_time, end_time = timestamps
        
        schema_tables = {
            '1': ['variants', 'samples', 'variant_samples'],
            '2': ['variant_regions', 'samples'],
            '3': ['genomic_variants'],
            '4': ['variants', 'samples', 'variant_samples']
        }
        tables_created = schema_tables[schema]
        
        summary = build_summary(
            vcf_file=vcf_file,
            schema=schema,
            destination=destination,
            namespace=namespace,
            catalog_type=catalog_type,
            tables_created=tables_created,
            variants_loaded=variants_loaded,
            samples_loaded=samples_loaded,
            start_time=start_time,
            end_time=end_time
        )
        
        # Calculate expected duration
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        expected_duration = int((end_dt - start_dt).total_seconds())
        
        # Property: Duration should match calculated value
        assert summary['execution']['duration_seconds'] == expected_duration, \
            f"Duration mismatch: expected {expected_duration}, got {summary['execution']['duration_seconds']}"
        
        # Property: Duration should be non-negative
        assert summary['execution']['duration_seconds'] >= 0, \
            "Duration should be non-negative"
    
    @given(
        schema=schemas,
        timestamps=timestamp_pairs()
    )
    def test_tables_created_matches_schema(self, schema, timestamps):
        """
        Property: The tables_created list should contain the correct tables for
        the selected schema.
        
        **Validates: Requirements 7.4**
        """
        start_time, end_time = timestamps
        
        schema_tables = {
            '1': ['variants', 'samples', 'variant_samples'],
            '2': ['variant_regions', 'samples'],
            '3': ['genomic_variants'],
            '4': ['variants', 'samples', 'variant_samples']
        }
        expected_tables = schema_tables[schema]
        
        summary = build_summary(
            vcf_file='s3://bucket/sample.vcf',
            schema=schema,
            destination='s3://bucket/output',
            namespace='variant_db',
            catalog_type='vanilla',
            tables_created=expected_tables,
            variants_loaded=100,
            samples_loaded=10,
            start_time=start_time,
            end_time=end_time
        )
        
        # Property: tables_created should match expected tables for schema
        assert summary['results']['tables_created'] == expected_tables, \
            f"Tables for schema {schema} should be {expected_tables}"
        
        # Property: Number of tables should match schema requirements
        expected_counts = {'1': 3, '2': 2, '3': 1, '4': 3}
        assert len(summary['results']['tables_created']) == expected_counts[schema], \
            f"Schema {schema} should have {expected_counts[schema]} tables"
    
    @given(
        vcf_file=vcf_file_paths(),
        schema=schemas,
        destination=destinations(),
        namespace=namespaces,
        catalog_type=catalog_types,
        variants_loaded=positive_ints,
        samples_loaded=positive_ints,
        timestamps=timestamp_pairs(),
        batch_size=st.integers(min_value=1000, max_value=1000000)
    )
    def test_optional_fields_are_included_when_provided(
        self, vcf_file, schema, destination, namespace, catalog_type,
        variants_loaded, samples_loaded, timestamps, batch_size
    ):
        """
        Property: Optional fields should be included in the summary when provided.
        
        **Validates: Requirements 7.1**
        """
        start_time, end_time = timestamps
        
        schema_tables = {
            '1': ['variants', 'samples', 'variant_samples'],
            '2': ['variant_regions', 'samples'],
            '3': ['genomic_variants'],
            '4': ['variants', 'samples', 'variant_samples']
        }
        tables_created = schema_tables[schema]
        
        summary = build_summary(
            vcf_file=vcf_file,
            schema=schema,
            destination=destination,
            namespace=namespace,
            catalog_type=catalog_type,
            tables_created=tables_created,
            variants_loaded=variants_loaded,
            samples_loaded=samples_loaded,
            start_time=start_time,
            end_time=end_time,
            batch_size=batch_size
        )
        
        # Property: batch_size should be included in inputs
        assert 'batch_size' in summary['inputs']
        assert summary['inputs']['batch_size'] == batch_size


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
