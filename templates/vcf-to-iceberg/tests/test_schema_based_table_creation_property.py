#!/usr/bin/env python3
"""
Property-based test for schema-based table creation.

**Property 9: Schema-Based Table Creation**
**Validates: Requirements 4.1**

For any schema selection (1, 2, 3, or 4) and empty destination, creating tables 
should result in the correct set of tables as defined in the corresponding schema module.
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
def test_schema_based_table_creation_property(schema):
    """
    Property test: For any schema selection (1, 2, 3, or 4), creating tables 
    should result in the correct set of tables as defined in the schema module.
    
    **Validates: Requirements 4.1**
    """
    # Mock catalog
    mock_catalog = MagicMock()
    
    # Mock catalog.table_exists to return False (tables don't exist)
    mock_catalog.table_exists.return_value = False
    
    # Mock schema module's create_schema_tables function
    expected_tables = EXPECTED_TABLES[schema]
    mock_tables = {}
    for table_name in expected_tables:
        mock_table = MagicMock()
        mock_table.location.return_value = f"s3://test-bucket/{table_name}"
        mock_tables[table_name] = mock_table
    
    # Patch the necessary functions
    with patch('initialize_tables.connect_to_catalog', return_value=mock_catalog), \
         patch('initialize_tables.create_namespace'), \
         patch('initialize_tables.load_schema_module') as mock_load_schema:
        
        # Configure the mock schema module
        mock_schema_module = MagicMock()
        mock_schema_module.create_schema_tables.return_value = mock_tables
        mock_load_schema.return_value = mock_schema_module
        
        # Create catalog config
        catalog_config = {
            'type': 'hadoop',
            'warehouse': 's3://test-bucket/iceberg',
            'region': 'us-east-1'
        }
        
        # Initialize tables
        result = initialize_tables(catalog_config, schema)
        
        # Verify the result
        assert result['status'] == 'success'
        assert result['schema'] == schema
        assert result['namespace'] == SCHEMA_NAMESPACES[schema]
        
        # Verify that the correct tables were created
        assert set(result['tables_created']) == set(expected_tables)
        assert set(result['all_tables']) == set(expected_tables)
        
        # Verify that create_schema_tables was called
        mock_schema_module.create_schema_tables.assert_called_once_with(
            mock_catalog, 
            SCHEMA_NAMESPACES[schema]
        )
        
        # Verify table metadata
        for table_name in expected_tables:
            assert table_name in result['table_metadata']
            assert result['table_metadata'][table_name]['status'] == 'created'
            assert result['table_metadata'][table_name]['schema_match'] is True


@given(schema=st.sampled_from(['1', '2', '3', '4']))
@settings(max_examples=100, deadline=None)
def test_schema_based_table_creation_with_custom_namespace(schema):
    """
    Property test: For any schema selection with a custom namespace, 
    tables should be created in the specified namespace.
    
    **Validates: Requirements 4.1**
    """
    # Mock catalog
    mock_catalog = MagicMock()
    mock_catalog.table_exists.return_value = False
    
    # Mock schema module's create_schema_tables function
    expected_tables = EXPECTED_TABLES[schema]
    mock_tables = {}
    for table_name in expected_tables:
        mock_table = MagicMock()
        mock_table.location.return_value = f"s3://test-bucket/{table_name}"
        mock_tables[table_name] = mock_table
    
    # Custom namespace
    custom_namespace = f"custom_namespace_{schema}"
    
    # Patch the necessary functions
    with patch('initialize_tables.connect_to_catalog', return_value=mock_catalog), \
         patch('initialize_tables.create_namespace'), \
         patch('initialize_tables.load_schema_module') as mock_load_schema:
        
        # Configure the mock schema module
        mock_schema_module = MagicMock()
        mock_schema_module.create_schema_tables.return_value = mock_tables
        mock_load_schema.return_value = mock_schema_module
        
        # Create catalog config
        catalog_config = {
            'type': 'hadoop',
            'warehouse': 's3://test-bucket/iceberg',
            'region': 'us-east-1'
        }
        
        # Initialize tables with custom namespace
        result = initialize_tables(catalog_config, schema, namespace=custom_namespace)
        
        # Verify the result uses custom namespace
        assert result['status'] == 'success'
        assert result['namespace'] == custom_namespace
        
        # Verify that create_schema_tables was called with custom namespace
        mock_schema_module.create_schema_tables.assert_called_once_with(
            mock_catalog, 
            custom_namespace
        )


@given(schema=st.sampled_from(['1', '2', '3', '4']))
@settings(max_examples=100, deadline=None)
def test_schema_based_table_count_property(schema):
    """
    Property test: For any schema selection, the number of tables created 
    should match the expected count for that schema.
    
    **Validates: Requirements 4.1**
    """
    # Mock catalog
    mock_catalog = MagicMock()
    mock_catalog.table_exists.return_value = False
    
    # Mock schema module's create_schema_tables function
    expected_tables = EXPECTED_TABLES[schema]
    expected_count = len(expected_tables)
    
    mock_tables = {}
    for table_name in expected_tables:
        mock_table = MagicMock()
        mock_table.location.return_value = f"s3://test-bucket/{table_name}"
        mock_tables[table_name] = mock_table
    
    # Patch the necessary functions
    with patch('initialize_tables.connect_to_catalog', return_value=mock_catalog), \
         patch('initialize_tables.create_namespace'), \
         patch('initialize_tables.load_schema_module') as mock_load_schema:
        
        # Configure the mock schema module
        mock_schema_module = MagicMock()
        mock_schema_module.create_schema_tables.return_value = mock_tables
        mock_load_schema.return_value = mock_schema_module
        
        # Create catalog config
        catalog_config = {
            'type': 'hadoop',
            'warehouse': 's3://test-bucket/iceberg',
            'region': 'us-east-1'
        }
        
        # Initialize tables
        result = initialize_tables(catalog_config, schema)
        
        # Verify the table count
        assert len(result['tables_created']) == expected_count
        assert len(result['all_tables']) == expected_count
        
        # Verify specific table counts for each schema
        if schema == '1':
            assert len(result['tables_created']) == 3  # variants, samples, variant_samples
        elif schema == '2':
            assert len(result['tables_created']) == 2  # variant_regions, samples
        elif schema == '3':
            assert len(result['tables_created']) == 1  # genomic_variants
        elif schema == '4':
            assert len(result['tables_created']) == 3  # variants, samples, variant_samples


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
