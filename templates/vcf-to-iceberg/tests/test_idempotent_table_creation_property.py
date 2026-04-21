#!/usr/bin/env python3
"""
Property-based test for idempotent table creation.

**Property 11: Idempotent Table Creation**
**Validates: Requirements 4.1**

For any schema selection and destination where tables already exist with the correct schema,
the table initialization process should skip creation and successfully load the existing tables
without errors.
"""

import pytest
import os
import sys
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from initialize_tables import initialize_tables, SCHEMA_NAMESPACES


# Expected tables for each schema
EXPECTED_TABLES = {
    '1': ['variants', 'samples', 'variant_samples'],
    '2': ['variant_regions', 'samples'],
    '3': ['genomic_variants'],
    '4': ['variants', 'samples', 'variant_samples']
}


@given(schema=st.sampled_from(['1', '2', '3', '4']))
@settings(max_examples=100, deadline=None)
def test_idempotent_table_creation_property(schema):
    """
    Property test: For any schema selection, when tables already exist with correct schema,
    the initialization process should skip creation and load existing tables without errors.
    
    **Validates: Requirements 4.1**
    """
    # Mock catalog
    mock_catalog = MagicMock()
    
    # Mock catalog.table_exists to return True (tables already exist)
    mock_catalog.table_exists.return_value = True
    
    # Expected tables for this schema
    expected_tables = EXPECTED_TABLES[schema]
    
    # Mock existing tables with correct schema
    mock_tables = {}
    for table_name in expected_tables:
        mock_table = MagicMock()
        mock_table.location.return_value = f"s3://test-bucket/{table_name}"
        
        # Mock schema that matches expected schema
        mock_schema = MagicMock()
        if schema == '1':
            if table_name == 'variants':
                mock_schema.fields = [
                    MagicMock(field_id=1, name='variant_id', field_type='string'),
                    MagicMock(field_id=2, name='chrom', field_type='string'),
                    MagicMock(field_id=3, name='pos', field_type='long')
                ]
            elif table_name == 'samples':
                mock_schema.fields = [
                    MagicMock(field_id=1, name='sample_id', field_type='string'),
                    MagicMock(field_id=2, name='sample_name', field_type='string')
                ]
            elif table_name == 'variant_samples':
                mock_schema.fields = [
                    MagicMock(field_id=1, name='variant_id', field_type='string'),
                    MagicMock(field_id=2, name='sample_id', field_type='string')
                ]
        elif schema == '2':
            if table_name == 'variant_regions':
                mock_schema.fields = [
                    MagicMock(field_id=1, name='chrom', field_type='string'),
                    MagicMock(field_id=2, name='pos', field_type='long')
                ]
            elif table_name == 'samples':
                mock_schema.fields = [
                    MagicMock(field_id=1, name='sample_id', field_type='string'),
                    MagicMock(field_id=2, name='sample_name', field_type='string')
                ]
        elif schema == '3':
            if table_name == 'genomic_variants':
                mock_schema.fields = [
                    MagicMock(field_id=1, name='sample_id', field_type='string'),
                    MagicMock(field_id=2, name='chrom', field_type='string'),
                    MagicMock(field_id=3, name='pos', field_type='long')
                ]
        elif schema == '4':
            if table_name == 'variants':
                mock_schema.fields = [
                    MagicMock(field_id=1, name='variant_id', field_type='string'),
                    MagicMock(field_id=2, name='chrom', field_type='string'),
                    MagicMock(field_id=3, name='pos', field_type='long')
                ]
            elif table_name == 'samples':
                mock_schema.fields = [
                    MagicMock(field_id=1, name='sample_id', field_type='string'),
                    MagicMock(field_id=2, name='sample_name', field_type='string')
                ]
            elif table_name == 'variant_samples':
                mock_schema.fields = [
                    MagicMock(field_id=1, name='variant_id', field_type='string'),
                    MagicMock(field_id=2, name='sample_id', field_type='string')
                ]
        
        mock_table.schema.return_value = mock_schema
        
        # Mock partition spec (empty for simplicity, will be validated by compare_schemas)
        mock_partition_spec = MagicMock()
        mock_partition_spec.fields = []
        mock_table.spec.return_value = mock_partition_spec
        
        # Mock sort order (empty for simplicity)
        mock_sort_order = MagicMock()
        mock_sort_order.fields = []
        mock_table.sort_order.return_value = mock_sort_order
        
        mock_tables[table_name] = mock_table
    
    # Configure mock catalog to return existing tables
    def mock_load_table(table_identifier):
        table_name = table_identifier.split('.')[-1]
        return mock_tables[table_name]
    
    mock_catalog.load_table.side_effect = mock_load_table
    
    # Mock schema module
    mock_schema_module = MagicMock()
    
    # Patch the necessary functions
    with patch('initialize_tables.connect_to_catalog', return_value=mock_catalog), \
         patch('initialize_tables.create_namespace'), \
         patch('initialize_tables.load_schema_module') as mock_load_schema, \
         patch('initialize_tables.compare_schemas', return_value=(True, [])):
        
        # Configure the mock schema module
        mock_load_schema.return_value = mock_schema_module
        
        # Create catalog config
        catalog_config = {
            'type': 'hadoop',
            'warehouse': 's3://test-bucket/iceberg',
            'region': 'us-east-1'
        }
        
        # Initialize tables (should be idempotent)
        result = initialize_tables(catalog_config, schema)
        
        # Verify the result
        assert result['status'] == 'success'
        assert result['schema'] == schema
        assert result['namespace'] == SCHEMA_NAMESPACES[schema]
        
        # Verify that NO tables were created (all should be existing)
        assert len(result['tables_created']) == 0
        assert set(result['tables_existing']) == set(expected_tables)
        assert set(result['tables_verified']) == set(expected_tables)
        
        # Verify that create_schema_tables was NOT called (idempotent behavior)
        mock_schema_module.create_schema_tables.assert_not_called()
        
        # Verify table metadata shows all tables as verified
        for table_name in expected_tables:
            assert table_name in result['table_metadata']
            assert result['table_metadata'][table_name]['status'] == 'verified'
            assert result['table_metadata'][table_name]['schema_match'] is True


@given(schema=st.sampled_from(['1', '2', '3', '4']))
@settings(max_examples=100, deadline=None)
def test_idempotent_table_creation_multiple_calls(schema):
    """
    Property test: For any schema selection, calling initialize_tables multiple times
    should produce the same result without errors (true idempotency).
    
    **Validates: Requirements 4.1**
    """
    # Mock catalog
    mock_catalog = MagicMock()
    
    # Expected tables for this schema
    expected_tables = EXPECTED_TABLES[schema]
    
    # Track call count
    call_count = {'count': 0}
    
    # Mock table_exists to return False on first call, True on subsequent calls
    def mock_table_exists(table_identifier):
        if call_count['count'] == 0:
            return False
        return True
    
    mock_catalog.table_exists.side_effect = mock_table_exists
    
    # Mock tables
    mock_tables = {}
    for table_name in expected_tables:
        mock_table = MagicMock()
        mock_table.location.return_value = f"s3://test-bucket/{table_name}"
        
        # Mock schema
        mock_schema = MagicMock()
        mock_schema.fields = [
            MagicMock(field_id=1, name='field1', field_type='string')
        ]
        mock_table.schema.return_value = mock_schema
        
        # Mock partition spec
        mock_partition_spec = MagicMock()
        mock_partition_spec.fields = []
        mock_table.spec.return_value = mock_partition_spec
        
        # Mock sort order
        mock_sort_order = MagicMock()
        mock_sort_order.fields = []
        mock_table.sort_order.return_value = mock_sort_order
        
        mock_tables[table_name] = mock_table
    
    # Configure mock catalog to return tables
    def mock_load_table(table_identifier):
        table_name = table_identifier.split('.')[-1]
        return mock_tables[table_name]
    
    mock_catalog.load_table.side_effect = mock_load_table
    
    # Mock schema module
    mock_schema_module = MagicMock()
    mock_schema_module.create_schema_tables.return_value = mock_tables
    
    # Patch the necessary functions
    with patch('initialize_tables.connect_to_catalog', return_value=mock_catalog), \
         patch('initialize_tables.create_namespace'), \
         patch('initialize_tables.load_schema_module', return_value=mock_schema_module), \
         patch('initialize_tables.compare_schemas', return_value=(True, [])):
        
        # Create catalog config
        catalog_config = {
            'type': 'hadoop',
            'warehouse': 's3://test-bucket/iceberg',
            'region': 'us-east-1'
        }
        
        # First call - should create tables
        result1 = initialize_tables(catalog_config, schema)
        call_count['count'] += 1
        
        assert result1['status'] == 'success'
        assert len(result1['tables_created']) == len(expected_tables)
        
        # Second call - should be idempotent (no creation)
        result2 = initialize_tables(catalog_config, schema)
        call_count['count'] += 1
        
        assert result2['status'] == 'success'
        assert len(result2['tables_created']) == 0
        assert len(result2['tables_existing']) == len(expected_tables)
        assert len(result2['tables_verified']) == len(expected_tables)
        
        # Third call - should still be idempotent
        result3 = initialize_tables(catalog_config, schema)
        call_count['count'] += 1
        
        assert result3['status'] == 'success'
        assert len(result3['tables_created']) == 0
        assert len(result3['tables_existing']) == len(expected_tables)
        assert len(result3['tables_verified']) == len(expected_tables)


@given(
    schema=st.sampled_from(['1', '2', '3', '4']),
    custom_namespace=st.text(min_size=1, max_size=20, alphabet=st.characters(categories=('Ll', 'Lu', 'Nd'), include_characters='_'))
)
@settings(max_examples=100, deadline=None)
def test_idempotent_table_creation_with_custom_namespace(schema, custom_namespace):
    """
    Property test: For any schema selection and custom namespace, when tables exist,
    initialization should be idempotent regardless of namespace.
    
    **Validates: Requirements 4.1**
    """
    # Mock catalog
    mock_catalog = MagicMock()
    mock_catalog.table_exists.return_value = True
    
    # Expected tables for this schema
    expected_tables = EXPECTED_TABLES[schema]
    
    # Mock existing tables
    mock_tables = {}
    for table_name in expected_tables:
        mock_table = MagicMock()
        mock_table.location.return_value = f"s3://test-bucket/{custom_namespace}/{table_name}"
        
        # Mock schema
        mock_schema = MagicMock()
        mock_schema.fields = [
            MagicMock(field_id=1, name='field1', field_type='string')
        ]
        mock_table.schema.return_value = mock_schema
        
        # Mock partition spec
        mock_partition_spec = MagicMock()
        mock_partition_spec.fields = []
        mock_table.spec.return_value = mock_partition_spec
        
        # Mock sort order
        mock_sort_order = MagicMock()
        mock_sort_order.fields = []
        mock_table.sort_order.return_value = mock_sort_order
        
        mock_tables[table_name] = mock_table
    
    # Configure mock catalog
    def mock_load_table(table_identifier):
        table_name = table_identifier.split('.')[-1]
        return mock_tables[table_name]
    
    mock_catalog.load_table.side_effect = mock_load_table
    
    # Mock schema module
    mock_schema_module = MagicMock()
    
    # Patch the necessary functions
    with patch('initialize_tables.connect_to_catalog', return_value=mock_catalog), \
         patch('initialize_tables.create_namespace'), \
         patch('initialize_tables.load_schema_module', return_value=mock_schema_module), \
         patch('initialize_tables.compare_schemas', return_value=(True, [])):
        
        # Create catalog config
        catalog_config = {
            'type': 'hadoop',
            'warehouse': 's3://test-bucket/iceberg',
            'region': 'us-east-1'
        }
        
        # Initialize tables with custom namespace
        result = initialize_tables(catalog_config, schema, namespace=custom_namespace)
        
        # Verify the result
        assert result['status'] == 'success'
        assert result['namespace'] == custom_namespace
        assert len(result['tables_created']) == 0
        assert set(result['tables_existing']) == set(expected_tables)
        assert set(result['tables_verified']) == set(expected_tables)
        
        # Verify that create_schema_tables was NOT called
        mock_schema_module.create_schema_tables.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
