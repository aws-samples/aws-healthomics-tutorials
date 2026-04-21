#!/usr/bin/env python3
"""
Unit tests for initialize_tables module.

Tests cover:
- Loading schema modules
- Connecting to catalog
- Schema comparison
- Table initialization logic
- Error handling
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock, Mock

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from initialize_tables import (
    load_schema_module,
    connect_to_catalog,
    get_table_schema_info,
    compare_schemas,
    SCHEMA_NAMESPACES
)


class TestLoadSchemaModule:
    """Test loading schema modules."""
    
    def test_load_schema_1(self):
        """Test loading schema 1 module."""
        module = load_schema_module('1')
        assert hasattr(module, 'create_schema_tables')
        assert hasattr(module, 'variants_schema')
        assert hasattr(module, 'samples_schema')
        assert hasattr(module, 'variant_samples_schema')
    
    def test_load_schema_2(self):
        """Test loading schema 2 module."""
        module = load_schema_module('2')
        assert hasattr(module, 'create_schema_tables')
        assert hasattr(module, 'variant_regions_schema')
        assert hasattr(module, 'samples_schema')
    
    def test_load_schema_3(self):
        """Test loading schema 3 module."""
        module = load_schema_module('3')
        assert hasattr(module, 'create_schema_tables')
        assert hasattr(module, 'genomic_variants_schema')
    
    def test_load_schema_4(self):
        """Test loading schema 4 module."""
        module = load_schema_module('4')
        assert hasattr(module, 'create_schema_tables')
        assert hasattr(module, 'variants_schema')
        assert hasattr(module, 'samples_schema')
        assert hasattr(module, 'variant_samples_schema')
    
    def test_load_invalid_schema_0(self):
        """Test error when loading invalid schema 0."""
        with pytest.raises(ValueError, match="Invalid schema: 0"):
            load_schema_module('0')
    
    def test_load_invalid_schema_5(self):
        """Test error when loading invalid schema 5."""
        with pytest.raises(ValueError, match="Invalid schema: 5"):
            load_schema_module('5')
    
    def test_load_invalid_schema_string(self):
        """Test error when loading invalid schema string."""
        with pytest.raises(ValueError, match="Invalid schema: invalid"):
            load_schema_module('invalid')


class TestConnectToCatalog:
    """Test catalog connection."""
    
    @patch('initialize_tables.load_catalog')
    def test_connect_s3tables_catalog(self, mock_load_catalog):
        """Test connecting to S3 Tables catalog."""
        mock_catalog = MagicMock()
        mock_load_catalog.return_value = mock_catalog
        
        catalog_config = {
            'type': 'rest',
            'warehouse': 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-bucket',
            'uri': 'https://s3tables.us-east-1.amazonaws.com/iceberg',
            'rest.sigv4-enabled': 'true',
            'rest.signing-name': 's3tables',
            'rest.signing-region': 'us-east-1',
            'region': 'us-east-1'
        }
        
        catalog = connect_to_catalog(catalog_config)
        
        assert catalog == mock_catalog
        mock_load_catalog.assert_called_once()
        call_args = mock_load_catalog.call_args
        assert call_args[0][0] == 's3tables'
    
    @patch('initialize_tables.load_catalog')
    def test_connect_vanilla_catalog(self, mock_load_catalog):
        """Test connecting to vanilla Iceberg catalog."""
        mock_catalog = MagicMock()
        mock_load_catalog.return_value = mock_catalog
        
        catalog_config = {
            'type': 'glue',
            'warehouse': 's3://my-bucket/iceberg',
            'client.region': 'us-east-1'
        }
        
        catalog = connect_to_catalog(catalog_config)
        
        assert catalog == mock_catalog
        mock_load_catalog.assert_called_once()
        call_args = mock_load_catalog.call_args
        assert call_args[0][0] == 'glue'
    
    def test_connect_catalog_missing_type(self):
        """Test error when catalog config missing type."""
        catalog_config = {
            'warehouse': 's3://my-bucket/iceberg'
        }
        
        with pytest.raises(ValueError, match="Catalog configuration missing 'type' field"):
            connect_to_catalog(catalog_config)
    
    @patch('initialize_tables.load_catalog')
    def test_connect_catalog_connection_failure(self, mock_load_catalog):
        """Test error when catalog connection fails."""
        mock_load_catalog.side_effect = Exception("Connection failed")
        
        catalog_config = {
            'type': 'rest',
            'warehouse': 'arn:aws:s3tables:us-east-1:123456789012:bucket/my-bucket'
        }
        
        with pytest.raises(Exception, match="Failed to connect to catalog"):
            connect_to_catalog(catalog_config)


class TestGetTableSchemaInfo:
    """Test extracting schema information from tables."""
    
    def test_get_schema_info_with_partitions_and_sort(self):
        """Test extracting schema info with partitions and sort order."""
        # Create mock table
        mock_table = MagicMock()
        
        # Mock schema
        mock_field1 = MagicMock()
        mock_field1.field_id = 1
        mock_field1.name = 'chrom'
        mock_field1.field_type = 'string'
        
        mock_field2 = MagicMock()
        mock_field2.field_id = 2
        mock_field2.name = 'pos'
        mock_field2.field_type = 'long'
        
        mock_schema = MagicMock()
        mock_schema.fields = [mock_field1, mock_field2]
        mock_table.schema.return_value = mock_schema
        
        # Mock partition spec
        mock_partition_field = MagicMock()
        mock_partition_field.source_id = 1
        mock_partition_field.name = 'chrom'
        mock_partition_field.transform = 'identity'
        
        mock_partition_spec = MagicMock()
        mock_partition_spec.fields = [mock_partition_field]
        mock_table.spec.return_value = mock_partition_spec
        
        # Mock sort order
        mock_sort_field = MagicMock()
        mock_sort_field.source_id = 2
        mock_sort_field.direction = 'ASC'
        
        mock_sort_order = MagicMock()
        mock_sort_order.fields = [mock_sort_field]
        mock_table.sort_order.return_value = mock_sort_order
        
        # Get schema info
        schema_info = get_table_schema_info(mock_table)
        
        assert len(schema_info['fields']) == 2
        assert schema_info['fields'][0]['name'] == 'chrom'
        assert schema_info['fields'][1]['name'] == 'pos'
        assert len(schema_info['partition_fields']) == 1
        assert schema_info['partition_fields'][0]['name'] == 'chrom'
        assert len(schema_info['sort_fields']) == 1
        assert schema_info['sort_fields'][0]['source_id'] == 2
    
    def test_get_schema_info_no_partitions_or_sort(self):
        """Test extracting schema info without partitions or sort order."""
        # Create mock table
        mock_table = MagicMock()
        
        # Mock schema
        mock_field = MagicMock()
        mock_field.field_id = 1
        mock_field.name = 'sample_id'
        mock_field.field_type = 'string'
        
        mock_schema = MagicMock()
        mock_schema.fields = [mock_field]
        mock_table.schema.return_value = mock_schema
        
        # No partition spec
        mock_table.spec.return_value = None
        
        # No sort order
        mock_table.sort_order.return_value = None
        
        # Get schema info
        schema_info = get_table_schema_info(mock_table)
        
        assert len(schema_info['fields']) == 1
        assert schema_info['fields'][0]['name'] == 'sample_id'
        assert schema_info['partition_fields'] == []
        assert schema_info['sort_fields'] == []


class TestCompareSchemas:
    """Test schema comparison logic."""
    
    def test_compare_schemas_match(self):
        """Test comparing matching schemas."""
        from pyiceberg.schema import Schema
        from pyiceberg.types import NestedField, StringType, LongType
        
        # Existing schema info
        existing_schema_info = {
            'fields': [
                {'id': 1, 'name': 'chrom', 'type': 'string'},
                {'id': 2, 'name': 'pos', 'type': 'long'}
            ],
            'partition_fields': [],
            'sort_fields': []
        }
        
        # Expected schema
        expected_schema = Schema(
            NestedField(1, 'chrom', StringType()),
            NestedField(2, 'pos', LongType())
        )
        
        matches, differences = compare_schemas(existing_schema_info, expected_schema)
        
        assert matches is True
        assert len(differences) == 0
    
    def test_compare_schemas_missing_field(self):
        """Test comparing schemas with missing field."""
        from pyiceberg.schema import Schema
        from pyiceberg.types import NestedField, StringType, LongType
        
        # Existing schema info (missing 'pos' field)
        existing_schema_info = {
            'fields': [
                {'id': 1, 'name': 'chrom', 'type': 'string'}
            ],
            'partition_fields': [],
            'sort_fields': []
        }
        
        # Expected schema
        expected_schema = Schema(
            NestedField(1, 'chrom', StringType()),
            NestedField(2, 'pos', LongType())
        )
        
        matches, differences = compare_schemas(existing_schema_info, expected_schema)
        
        assert matches is False
        assert len(differences) > 0
        assert any('Missing fields' in diff for diff in differences)
    
    def test_compare_schemas_extra_field(self):
        """Test comparing schemas with extra field."""
        from pyiceberg.schema import Schema
        from pyiceberg.types import NestedField, StringType, LongType
        
        # Existing schema info (has extra 'ref' field)
        existing_schema_info = {
            'fields': [
                {'id': 1, 'name': 'chrom', 'type': 'string'},
                {'id': 2, 'name': 'pos', 'type': 'long'},
                {'id': 3, 'name': 'ref', 'type': 'string'}
            ],
            'partition_fields': [],
            'sort_fields': []
        }
        
        # Expected schema
        expected_schema = Schema(
            NestedField(1, 'chrom', StringType()),
            NestedField(2, 'pos', LongType())
        )
        
        matches, differences = compare_schemas(existing_schema_info, expected_schema)
        
        assert matches is False
        assert len(differences) > 0
        assert any('Extra fields' in diff for diff in differences)
    
    def test_compare_schemas_type_mismatch(self):
        """Test comparing schemas with type mismatch."""
        from pyiceberg.schema import Schema
        from pyiceberg.types import NestedField, StringType, LongType
        
        # Existing schema info (pos is string instead of long)
        existing_schema_info = {
            'fields': [
                {'id': 1, 'name': 'chrom', 'type': 'string'},
                {'id': 2, 'name': 'pos', 'type': 'string'}
            ],
            'partition_fields': [],
            'sort_fields': []
        }
        
        # Expected schema
        expected_schema = Schema(
            NestedField(1, 'chrom', StringType()),
            NestedField(2, 'pos', LongType())
        )
        
        matches, differences = compare_schemas(existing_schema_info, expected_schema)
        
        assert matches is False
        assert len(differences) > 0
        assert any('type mismatch' in diff for diff in differences)


class TestSchemaNamespaces:
    """Test schema namespace mappings."""
    
    def test_schema_1_namespace(self):
        """Test schema 1 has correct namespace."""
        assert SCHEMA_NAMESPACES['1'] == 'variant_db'
    
    def test_schema_2_namespace(self):
        """Test schema 2 has correct namespace."""
        assert SCHEMA_NAMESPACES['2'] == 'variant_db_2'
    
    def test_schema_3_namespace(self):
        """Test schema 3 has correct namespace."""
        assert SCHEMA_NAMESPACES['3'] == 'variant_db_3'
    
    def test_schema_4_namespace(self):
        """Test schema 4 has correct namespace."""
        assert SCHEMA_NAMESPACES['4'] == 'variant_db_4'


class TestInitializeTables:
    """Test table initialization for different schemas."""
    
    @patch('initialize_tables.create_namespace')
    @patch('initialize_tables.load_catalog')
    def test_create_schema_1_tables(self, mock_load_catalog, mock_create_namespace):
        """Test creating schema 1 tables (variants, samples, variant_samples)."""
        # Mock catalog
        mock_catalog = MagicMock()
        mock_load_catalog.return_value = mock_catalog
        
        # Mock table_exists to return False (tables don't exist)
        mock_catalog.table_exists.return_value = False
        
        # Mock created tables
        mock_variants_table = MagicMock()
        mock_variants_table.location.return_value = 's3://bucket/variant_db/variants'
        
        mock_samples_table = MagicMock()
        mock_samples_table.location.return_value = 's3://bucket/variant_db/samples'
        
        mock_variant_samples_table = MagicMock()
        mock_variant_samples_table.location.return_value = 's3://bucket/variant_db/variant_samples'
        
        # Mock schema module's create_schema_tables
        with patch('initialize_tables.importlib.import_module') as mock_import:
            mock_schema_module = MagicMock()
            mock_schema_module.create_schema_tables.return_value = {
                'variants': mock_variants_table,
                'samples': mock_samples_table,
                'variant_samples': mock_variant_samples_table
            }
            mock_import.return_value = mock_schema_module
            
            from initialize_tables import initialize_tables
            
            catalog_config = {
                'type': 'hadoop',
                'warehouse': 's3://bucket/iceberg'
            }
            
            result = initialize_tables(catalog_config, '1')
            
            # Verify results
            assert result['status'] == 'success'
            assert result['schema'] == '1'
            assert result['namespace'] == 'variant_db'
            assert set(result['tables_created']) == {'variants', 'samples', 'variant_samples'}
            assert len(result['table_metadata']) == 3
            assert 'variants' in result['table_metadata']
            assert 'samples' in result['table_metadata']
            assert 'variant_samples' in result['table_metadata']
    
    @patch('initialize_tables.create_namespace')
    @patch('initialize_tables.load_catalog')
    def test_create_schema_2_tables(self, mock_load_catalog, mock_create_namespace):
        """Test creating schema 2 tables (variant_regions, samples)."""
        # Mock catalog
        mock_catalog = MagicMock()
        mock_load_catalog.return_value = mock_catalog
        
        # Mock table_exists to return False
        mock_catalog.table_exists.return_value = False
        
        # Mock created tables
        mock_variant_regions_table = MagicMock()
        mock_variant_regions_table.location.return_value = 's3://bucket/variant_db_2/variant_regions'
        
        mock_samples_table = MagicMock()
        mock_samples_table.location.return_value = 's3://bucket/variant_db_2/samples'
        
        # Mock schema module's create_schema_tables
        with patch('initialize_tables.importlib.import_module') as mock_import:
            mock_schema_module = MagicMock()
            mock_schema_module.create_schema_tables.return_value = {
                'variant_regions': mock_variant_regions_table,
                'samples': mock_samples_table
            }
            mock_import.return_value = mock_schema_module
            
            from initialize_tables import initialize_tables
            
            catalog_config = {
                'type': 'hadoop',
                'warehouse': 's3://bucket/iceberg'
            }
            
            result = initialize_tables(catalog_config, '2')
            
            # Verify results
            assert result['status'] == 'success'
            assert result['schema'] == '2'
            assert result['namespace'] == 'variant_db_2'
            assert set(result['tables_created']) == {'variant_regions', 'samples'}
            assert len(result['table_metadata']) == 2
    
    @patch('initialize_tables.create_namespace')
    @patch('initialize_tables.load_catalog')
    def test_create_schema_3_tables(self, mock_load_catalog, mock_create_namespace):
        """Test creating schema 3 tables (genomic_variants)."""
        # Mock catalog
        mock_catalog = MagicMock()
        mock_load_catalog.return_value = mock_catalog
        
        # Mock table_exists to return False
        mock_catalog.table_exists.return_value = False
        
        # Mock created table
        mock_genomic_variants_table = MagicMock()
        mock_genomic_variants_table.location.return_value = 's3://bucket/variant_db_3/genomic_variants'
        
        # Mock schema module's create_schema_tables
        with patch('initialize_tables.importlib.import_module') as mock_import:
            mock_schema_module = MagicMock()
            mock_schema_module.create_schema_tables.return_value = {
                'genomic_variants': mock_genomic_variants_table
            }
            mock_import.return_value = mock_schema_module
            
            from initialize_tables import initialize_tables
            
            catalog_config = {
                'type': 'hadoop',
                'warehouse': 's3://bucket/iceberg'
            }
            
            result = initialize_tables(catalog_config, '3')
            
            # Verify results
            assert result['status'] == 'success'
            assert result['schema'] == '3'
            assert result['namespace'] == 'variant_db_3'
            assert result['tables_created'] == ['genomic_variants']
            assert len(result['table_metadata']) == 1
            assert 'genomic_variants' in result['table_metadata']
    
    @patch('initialize_tables.create_namespace')
    @patch('initialize_tables.load_catalog')
    def test_create_schema_4_tables(self, mock_load_catalog, mock_create_namespace):
        """Test creating schema 4 tables (variants, samples, variant_samples)."""
        # Mock catalog
        mock_catalog = MagicMock()
        mock_load_catalog.return_value = mock_catalog
        
        # Mock table_exists to return False
        mock_catalog.table_exists.return_value = False
        
        # Mock created tables
        mock_variants_table = MagicMock()
        mock_variants_table.location.return_value = 's3://bucket/variant_db_4/variants'
        
        mock_samples_table = MagicMock()
        mock_samples_table.location.return_value = 's3://bucket/variant_db_4/samples'
        
        mock_variant_samples_table = MagicMock()
        mock_variant_samples_table.location.return_value = 's3://bucket/variant_db_4/variant_samples'
        
        # Mock schema module's create_schema_tables
        with patch('initialize_tables.importlib.import_module') as mock_import:
            mock_schema_module = MagicMock()
            mock_schema_module.create_schema_tables.return_value = {
                'variants': mock_variants_table,
                'samples': mock_samples_table,
                'variant_samples': mock_variant_samples_table
            }
            mock_import.return_value = mock_schema_module
            
            from initialize_tables import initialize_tables
            
            catalog_config = {
                'type': 'hadoop',
                'warehouse': 's3://bucket/iceberg'
            }
            
            result = initialize_tables(catalog_config, '4')
            
            # Verify results
            assert result['status'] == 'success'
            assert result['schema'] == '4'
            assert result['namespace'] == 'variant_db_4'
            assert set(result['tables_created']) == {'variants', 'samples', 'variant_samples'}
            assert len(result['table_metadata']) == 3
    
    @patch('initialize_tables.create_namespace')
    @patch('initialize_tables.load_catalog')
    @patch('initialize_tables.get_table_schema_info')
    @patch('initialize_tables.compare_schemas')
    def test_skip_creation_when_tables_exist_with_correct_schema(
        self, mock_compare_schemas, mock_get_schema_info, 
        mock_load_catalog, mock_create_namespace
    ):
        """Test skipping table creation when tables already exist with correct schema."""
        # Mock catalog
        mock_catalog = MagicMock()
        mock_load_catalog.return_value = mock_catalog
        
        # Mock table_exists to return True (tables exist)
        mock_catalog.table_exists.return_value = True
        
        # Mock existing table
        mock_table = MagicMock()
        mock_table.location.return_value = 's3://bucket/variant_db/variants'
        mock_catalog.load_table.return_value = mock_table
        
        # Mock schema info
        mock_get_schema_info.return_value = {
            'fields': [],
            'partition_fields': [],
            'sort_fields': []
        }
        
        # Mock schema comparison - schemas match
        mock_compare_schemas.return_value = (True, [])
        
        # Mock schema module
        with patch('initialize_tables.importlib.import_module') as mock_import:
            mock_schema_module = MagicMock()
            # create_schema_tables should not be called
            mock_import.return_value = mock_schema_module
            
            from initialize_tables import initialize_tables
            
            catalog_config = {
                'type': 'hadoop',
                'warehouse': 's3://bucket/iceberg'
            }
            
            result = initialize_tables(catalog_config, '3')
            
            # Verify results
            assert result['status'] == 'success'
            assert result['tables_created'] == []  # No tables created
            assert result['tables_existing'] == ['genomic_variants']
            assert result['tables_verified'] == ['genomic_variants']
            assert result['table_metadata']['genomic_variants']['status'] == 'verified'
            assert result['table_metadata']['genomic_variants']['schema_match'] is True
            
            # Verify create_schema_tables was not called
            mock_schema_module.create_schema_tables.assert_not_called()
    
    @patch('initialize_tables.create_namespace')
    @patch('initialize_tables.load_catalog')
    @patch('initialize_tables.get_table_schema_info')
    @patch('initialize_tables.compare_schemas')
    def test_error_when_tables_exist_with_incorrect_schema(
        self, mock_compare_schemas, mock_get_schema_info,
        mock_load_catalog, mock_create_namespace
    ):
        """Test error when tables exist with incorrect schema."""
        # Mock catalog
        mock_catalog = MagicMock()
        mock_load_catalog.return_value = mock_catalog
        
        # Mock table_exists to return True (tables exist)
        mock_catalog.table_exists.return_value = True
        
        # Mock existing table
        mock_table = MagicMock()
        mock_table.location.return_value = 's3://bucket/variant_db/variants'
        mock_catalog.load_table.return_value = mock_table
        
        # Mock schema info
        mock_get_schema_info.return_value = {
            'fields': [],
            'partition_fields': [],
            'sort_fields': []
        }
        
        # Mock schema comparison - schemas don't match
        mock_compare_schemas.return_value = (False, ['Missing fields: {\'pos\', \'chrom\'}'])
        
        # Mock schema module
        with patch('initialize_tables.importlib.import_module') as mock_import:
            mock_schema_module = MagicMock()
            mock_import.return_value = mock_schema_module
            
            from initialize_tables import initialize_tables
            
            catalog_config = {
                'type': 'hadoop',
                'warehouse': 's3://bucket/iceberg'
            }
            
            # Should raise exception due to schema mismatch
            with pytest.raises(Exception, match="Schema mismatch detected"):
                initialize_tables(catalog_config, '3')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
