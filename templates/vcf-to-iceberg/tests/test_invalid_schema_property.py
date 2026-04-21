#!/usr/bin/env python3
"""
Property-based tests for invalid schema rejection.

**Validates: Requirements 8.1**

Property 13: Invalid Schema Rejection
For any schema value that is not in the set {1, 2, 3, 4}, the validation function
should raise an error.
"""

import pytest
import os
import sys
from hypothesis import given, strategies as st, assume

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from validate_inputs import validate_schema


class TestInvalidSchemaRejectionProperty:
    """Property-based tests for invalid schema rejection."""
    
    @given(st.integers())
    def test_invalid_integer_schemas_rejected(self, schema_int):
        """
        Property: Any integer schema value not in {1, 2, 3, 4} should raise ValueError.
        
        **Validates: Requirements 8.1**
        """
        # Assume the schema is not valid
        assume(schema_int not in [1, 2, 3, 4])
        
        # Property: should raise ValueError for invalid schema integers
        with pytest.raises(ValueError, match="Invalid schema selection"):
            validate_schema(str(schema_int))
    
    @given(st.text(min_size=1, max_size=50))
    def test_non_numeric_schemas_rejected(self, schema_str):
        """
        Property: Any non-numeric string schema value should raise ValueError.
        
        **Validates: Requirements 8.1**
        """
        # Assume the schema string is not a valid integer
        try:
            schema_int = int(schema_str)
            # If it converts to int, assume it's not in valid set
            assume(schema_int not in [1, 2, 3, 4])
        except (ValueError, OverflowError):
            # This is what we want - non-numeric strings
            pass
        
        # Property: should raise ValueError for non-numeric schemas
        with pytest.raises(ValueError, match="Invalid schema selection"):
            validate_schema(schema_str)
    
    @given(st.one_of(
        st.lists(st.integers()),
        st.dictionaries(st.text(), st.integers()),
        st.none()
    ))
    def test_invalid_type_schemas_rejected(self, schema_value):
        """
        Property: Any non-string/non-integer type should raise ValueError or TypeError.
        
        **Validates: Requirements 8.1**
        """
        # Property: should raise ValueError or TypeError for invalid types
        with pytest.raises((ValueError, TypeError, AttributeError)):
            validate_schema(schema_value)
    
    @given(st.integers(min_value=-1000, max_value=0))
    def test_negative_schemas_rejected(self, schema_int):
        """
        Property: Any negative integer schema value should raise ValueError.
        
        **Validates: Requirements 8.1**
        """
        # Property: should raise ValueError for negative schemas
        with pytest.raises(ValueError, match="Invalid schema selection"):
            validate_schema(str(schema_int))
    
    @given(st.integers(min_value=5, max_value=1000))
    def test_large_positive_schemas_rejected(self, schema_int):
        """
        Property: Any integer schema value greater than 4 should raise ValueError.
        
        **Validates: Requirements 8.1**
        """
        # Property: should raise ValueError for schemas > 4
        with pytest.raises(ValueError, match="Invalid schema selection"):
            validate_schema(str(schema_int))
    
    @given(st.sampled_from(['1', '2', '3', '4']))
    def test_valid_schemas_accepted(self, schema_str):
        """
        Property: Schema values in {1, 2, 3, 4} should be accepted and return the integer.
        
        **Validates: Requirements 8.1**
        """
        # Property: valid schemas should not raise an error
        result = validate_schema(schema_str)
        
        # Should return the integer value
        assert result in [1, 2, 3, 4]
        assert result == int(schema_str)
    
    @given(st.sampled_from([1, 2, 3, 4]))
    def test_valid_integer_schemas_accepted(self, schema_int):
        """
        Property: Integer schema values in {1, 2, 3, 4} should be accepted.
        
        **Validates: Requirements 8.1**
        """
        # Property: valid integer schemas should not raise an error
        result = validate_schema(str(schema_int))
        
        # Should return the integer value
        assert result == schema_int
        assert result in [1, 2, 3, 4]
    
    @given(st.text(alphabet='0123456789', min_size=2, max_size=10))
    def test_multi_digit_invalid_schemas_rejected(self, schema_str):
        """
        Property: Multi-digit numeric strings not in {1, 2, 3, 4} should raise ValueError.
        
        **Validates: Requirements 8.1**
        """
        # Assume it's not a valid schema (both as string and as converted int)
        assume(schema_str not in ['1', '2', '3', '4'])
        try:
            schema_int = int(schema_str)
            assume(schema_int not in [1, 2, 3, 4])
        except (ValueError, OverflowError):
            pass
        
        # Property: should raise ValueError for multi-digit invalid schemas
        with pytest.raises(ValueError, match="Invalid schema selection"):
            validate_schema(schema_str)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
