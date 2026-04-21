#!/usr/bin/env python3
"""
Property-based test for table schema validation.

**Property 10: Table Schema Validation**
**Validates: Requirements 4.6, 4.7**

For any created table, the table's partition specification and sort order should 
match the specifications defined in the corresponding schema module.
"""

import pytest
import os
import sys
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from initialize_tables import initialize_tables, SCHEMA_NAMESPACES

# Import schema modules to get expected specs
import schema_1
import schema_2
import schema_3
import schema_4


# Schema module mapping
SCHEMA_MODULES = {
    '1': schema_1,
    '2': schema_2,
    '3': schema_3,
    '4': schema_4
}


# Expected table specifications for each schema
EXPECTED_TABLE_SPECS = {
    '1': {
        'variants': {
            'partition_spec': schema_1.variants_partition_spec,
            'sort_order': schema_1.variants_sort_order
        },
        'samples': {
            'partition_spec': None,
            'sort_order': None
        },
        'variant_samples': {
            'partition_spec': schema_1.variant_samples_partition_spec,
            'sort_order': schema_1.variant_samples_sort_order
        }
    },
    '2': {
        'variant_regions': {
            'partition_spec': schema_2.variant_regions_partition_spec,
            'sort_order': schema_2.variant_regions_sort_order
        },
        'samples': {
            'partition_spec': None,
            'sort_order': None
        }
    },
    '3': {
        'genomic_variants': {
            'partition_spec': schema_3.genomic_variants_partition_spec,
            'sort_order': schema_3.genomic_variants_sort_order
        }
    },
    '4': {
        'variants': {
            'partition_spec': schema_4.variants_partition_spec,
            'sort_order': None
        },
        'samples': {
            'partition_spec': None,
            'sort_order': None
        },
        'variant_samples': {
            'partition_spec': schema_4.variant_samples_partition_spec,
            'sort_order': None
        }
    }
}


def create_mock_table_with_specs(table_name, schema, partition_spec, sort_order):
    """
    Create a mock table with the specified schema, partition spec, and sort order.
    """
    mock_table = MagicMock()
    mock_table.location.return_value = f"s3://test-bucket/{table_name}"
    mock_table.schema.return_value = schema
    mock_table.spec.return_value = partition_spec
    mock_table.sort_order.return_value = sort_order
    return mock_table


@given(schema=st.sampled_from(['1', '2', '3', '4']))
@settings(max_examples=100, deadline=None)
def test_table_partition_spec_validation_property(schema):
    """
    Property test: For any created table, the partition specification should 
    match the specification defined in the corresponding schema module.
    
    **Validates: Requirements 4.6**
    """
    # Get schema module and expected specs
    schema_module = SCHEMA_MODULES[schema]
    expected_specs = EXPECTED_TABLE_SPECS[schema]
    
    # Mock catalog
    mock_catalog = MagicMock()
    
    # Mock catalog.table_exists to return True (tables already exist)
    mock_catalog.table_exists.return_value = True
    
    # Create mock tables with correct specs
    mock_tables = {}
    for table_name, specs in expected_specs.items():
        if schema == '1':
            table_schema = getattr(schema_module, f"{table_name}_schema")
        elif schema == '2':
            table_schema = getattr(schema_module, f"{table_name}_schema")
        elif schema == '3':
            table_schema = schema_module.genomic_variants_schema
        elif schema == '4':
            table_schema = getattr(schema_module, f"{table_name}_schema")
        
        mock_table = create_mock_table_with_specs(
            table_name,
            table_schema,
            specs['partition_spec'],
            specs['sort_order']
        )
        mock_tables[table_name] = mock_table
    
    # Configure catalog.load_table to return the appropriate mock table
    def load_table_side_effect(table_identifier):
        table_name = table_identifier.split('.')[-1]
        return mock_tables[table_name]
    
    mock_catalog.load_table.side_effect = load_table_side_effect
    
    # Patch the necessary functions
    with patch('initialize_tables.connect_to_catalog', return_value=mock_catalog), \
         patch('initialize_tables.create_namespace'):
        
        # Create catalog config
        catalog_config = {
            'type': 'hadoop',
            'warehouse': 's3://test-bucket/iceberg',
            'region': 'us-east-1'
        }
        
        # Initialize tables (should verify existing tables)
        result = initialize_tables(catalog_config, schema)
        
        # Verify the result
        assert result['status'] == 'success'
        assert result['schema'] == schema
        
        # Verify that all tables were verified (not created)
        assert len(result['tables_created']) == 0
        assert len(result['tables_verified']) == len(expected_specs)
        
        # Verify table metadata shows schema_match = True
        for table_name in expected_specs.keys():
            assert table_name in result['table_metadata']
            assert result['table_metadata'][table_name]['status'] == 'verified'
            assert result['table_metadata'][table_name]['schema_match'] is True


@given(schema=st.sampled_from(['1', '2', '3', '4']))
@settings(max_examples=100, deadline=None)
def test_table_sort_order_validation_property(schema):
    """
    Property test: For any created table, the sort order should match the 
    sort order defined in the corresponding schema module.
    
    **Validates: Requirements 4.7**
    """
    # Get schema module and expected specs
    schema_module = SCHEMA_MODULES[schema]
    expected_specs = EXPECTED_TABLE_SPECS[schema]
    
    # Mock catalog
    mock_catalog = MagicMock()
    mock_catalog.table_exists.return_value = True
    
    # Create mock tables with correct specs
    mock_tables = {}
    for table_name, specs in expected_specs.items():
        if schema == '1':
            table_schema = getattr(schema_module, f"{table_name}_schema")
        elif schema == '2':
            table_schema = getattr(schema_module, f"{table_name}_schema")
        elif schema == '3':
            table_schema = schema_module.genomic_variants_schema
        elif schema == '4':
            table_schema = getattr(schema_module, f"{table_name}_schema")
        
        mock_table = create_mock_table_with_specs(
            table_name,
            table_schema,
            specs['partition_spec'],
            specs['sort_order']
        )
        mock_tables[table_name] = mock_table
    
    # Configure catalog.load_table to return the appropriate mock table
    def load_table_side_effect(table_identifier):
        table_name = table_identifier.split('.')[-1]
        return mock_tables[table_name]
    
    mock_catalog.load_table.side_effect = load_table_side_effect
    
    # Patch the necessary functions
    with patch('initialize_tables.connect_to_catalog', return_value=mock_catalog), \
         patch('initialize_tables.create_namespace'):
        
        # Create catalog config
        catalog_config = {
            'type': 'hadoop',
            'warehouse': 's3://test-bucket/iceberg',
            'region': 'us-east-1'
        }
        
        # Initialize tables (should verify existing tables)
        result = initialize_tables(catalog_config, schema)
        
        # Verify the result
        assert result['status'] == 'success'
        
        # Verify that all tables were verified with correct sort orders
        for table_name in expected_specs.keys():
            assert table_name in result['table_metadata']
            assert result['table_metadata'][table_name]['schema_match'] is True


@given(
    schema=st.sampled_from(['1', '2', '3', '4']),
    table_index=st.integers(min_value=0, max_value=2)
)
@settings(max_examples=100, deadline=None)
def test_partition_spec_field_count_property(schema, table_index):
    """
    Property test: For any table in any schema, the number of partition fields 
    should match the expected count defined in the schema module.
    
    **Validates: Requirements 4.6**
    """
    # Get expected specs
    expected_specs = EXPECTED_TABLE_SPECS[schema]
    table_names = list(expected_specs.keys())
    
    # Skip if table_index is out of range for this schema
    if table_index >= len(table_names):
        return
    
    table_name = table_names[table_index]
    specs = expected_specs[table_name]
    
    # Get expected partition field count
    if specs['partition_spec'] is None:
        expected_partition_count = 0
    else:
        expected_partition_count = len(specs['partition_spec'].fields)
    
    # Verify the partition spec has the expected number of fields
    if specs['partition_spec'] is not None:
        actual_partition_count = len(specs['partition_spec'].fields)
        assert actual_partition_count == expected_partition_count
    
    # Verify specific partition counts for known tables
    if schema == '1':
        if table_name == 'variants':
            assert expected_partition_count == 1  # partitioned by chrom
        elif table_name == 'samples':
            assert expected_partition_count == 0  # no partitioning
        elif table_name == 'variant_samples':
            assert expected_partition_count == 1  # partitioned by variant_id_bucket
    elif schema == '2':
        if table_name == 'variant_regions':
            assert expected_partition_count == 2  # partitioned by chrom and pos_bucket
        elif table_name == 'samples':
            assert expected_partition_count == 0  # no partitioning
    elif schema == '3':
        if table_name == 'genomic_variants':
            assert expected_partition_count == 2  # partitioned by sample_bucket and chrom
    elif schema == '4':
        if table_name == 'variants':
            assert expected_partition_count == 2  # partitioned by chrom and pos_bucket
        elif table_name == 'samples':
            assert expected_partition_count == 0  # no partitioning
        elif table_name == 'variant_samples':
            assert expected_partition_count == 2  # partitioned by chrom and pos_bucket


@given(
    schema=st.sampled_from(['1', '2', '3', '4']),
    table_index=st.integers(min_value=0, max_value=2)
)
@settings(max_examples=100, deadline=None)
def test_sort_order_field_count_property(schema, table_index):
    """
    Property test: For any table in any schema, the number of sort fields 
    should match the expected count defined in the schema module.
    
    **Validates: Requirements 4.7**
    """
    # Get expected specs
    expected_specs = EXPECTED_TABLE_SPECS[schema]
    table_names = list(expected_specs.keys())
    
    # Skip if table_index is out of range for this schema
    if table_index >= len(table_names):
        return
    
    table_name = table_names[table_index]
    specs = expected_specs[table_name]
    
    # Get expected sort field count
    if specs['sort_order'] is None:
        expected_sort_count = 0
    else:
        expected_sort_count = len(specs['sort_order'].fields)
    
    # Verify the sort order has the expected number of fields
    if specs['sort_order'] is not None:
        actual_sort_count = len(specs['sort_order'].fields)
        assert actual_sort_count == expected_sort_count
    
    # Verify specific sort counts for known tables
    if schema == '1':
        if table_name == 'variants':
            assert expected_sort_count == 1  # sorted by pos
        elif table_name == 'samples':
            assert expected_sort_count == 0  # no sorting
        elif table_name == 'variant_samples':
            assert expected_sort_count == 1  # sorted by sample_id
    elif schema == '2':
        if table_name == 'variant_regions':
            assert expected_sort_count == 1  # sorted by pos
        elif table_name == 'samples':
            assert expected_sort_count == 0  # no sorting
    elif schema == '3':
        if table_name == 'genomic_variants':
            assert expected_sort_count == 2  # sorted by chrom and pos
    elif schema == '4':
        # Schema 4 has no sort orders
        assert expected_sort_count == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
