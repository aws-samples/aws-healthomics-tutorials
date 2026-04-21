#!/usr/bin/env python3
"""
Property-based tests for GVCF reference block identification.

**Validates: Requirements 3.5**

Property 8: GVCF Reference Block Identification
For any VCF record, if the INFO field contains an "END" key, the record
should be flagged as a reference block (is_reference_block = true).
"""

import pytest
import os
import sys
from hypothesis import given, strategies as st

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from load_vcf_schema1 import parse_info_field


# Strategy for generating INFO field keys
info_keys = st.text(
    alphabet=st.characters(categories=('Lu', 'Ll', 'Nd'), include_characters='_'),
    min_size=1,
    max_size=20
).filter(lambda x: x and x[0].isalpha() and x != 'END')

# Strategy for generating INFO field values
info_values = st.text(
    alphabet=st.characters(categories=('Lu', 'Ll', 'Nd'), include_characters='_.-'),
    min_size=1,
    max_size=50
).filter(lambda x: x and ';' not in x and '=' not in x)

# Strategy for generating END positions
end_positions = st.integers(min_value=1, max_value=250000000)


@st.composite
def info_field_with_end(draw):
    """Generate an INFO field that contains an END key."""
    # Generate END value
    end_value = draw(end_positions)
    
    # Generate other INFO fields
    num_other_fields = draw(st.integers(min_value=0, max_value=5))
    info_parts = [f"END={end_value}"]
    
    for _ in range(num_other_fields):
        key = draw(info_keys)
        # Some INFO fields are flags (no value)
        if draw(st.booleans()):
            info_parts.append(key)
        else:
            value = draw(info_values)
            info_parts.append(f"{key}={value}")
    
    # Use hypothesis's permutations instead of random.shuffle
    info_parts = draw(st.permutations(info_parts))
    
    info_str = ';'.join(info_parts)
    
    return {
        'info_str': info_str,
        'end_value': str(end_value),
        'has_end': True
    }


@st.composite
def info_field_without_end(draw):
    """Generate an INFO field that does NOT contain an END key."""
    # Generate other INFO fields (no END)
    num_fields = draw(st.integers(min_value=0, max_value=5))
    
    if num_fields == 0:
        return {
            'info_str': '.',
            'has_end': False
        }
    
    info_parts = []
    for _ in range(num_fields):
        key = draw(info_keys)
        # Some INFO fields are flags (no value)
        if draw(st.booleans()):
            info_parts.append(key)
        else:
            value = draw(info_values)
            info_parts.append(f"{key}={value}")
    
    info_str = ';'.join(info_parts) if info_parts else '.'
    
    return {
        'info_str': info_str,
        'has_end': False
    }


class TestGVCFReferenceBlockProperty:
    """Property-based tests for GVCF reference block identification."""
    
    @given(info_field_with_end())
    def test_info_with_end_is_reference_block(self, data):
        """
        Property: For any INFO field containing an END key, the record
        should be identified as a reference block.
        
        **Validates: Requirements 3.5**
        """
        info_str = data['info_str']
        
        # Parse the INFO field
        parsed_info = parse_info_field(info_str)
        
        # Property: END key should be present
        assert 'END' in parsed_info, \
            f"END key should be present in parsed INFO: {parsed_info}"
        
        # Property: This indicates a reference block
        is_reference_block = 'END' in parsed_info
        assert is_reference_block is True, \
            "Record with END in INFO should be a reference block"
    
    @given(info_field_without_end())
    def test_info_without_end_is_not_reference_block(self, data):
        """
        Property: For any INFO field NOT containing an END key, the record
        should NOT be identified as a reference block.
        
        **Validates: Requirements 3.5**
        """
        info_str = data['info_str']
        
        # Parse the INFO field
        parsed_info = parse_info_field(info_str)
        
        # Property: END key should NOT be present
        assert 'END' not in parsed_info, \
            f"END key should not be present in parsed INFO: {parsed_info}"
        
        # Property: This is NOT a reference block
        is_reference_block = 'END' in parsed_info
        assert is_reference_block is False, \
            "Record without END in INFO should not be a reference block"
    
    @given(info_field_with_end())
    def test_end_value_extractable(self, data):
        """
        Property: For any INFO field with END key, the END value should
        be extractable.
        
        **Validates: Requirements 3.5**
        """
        info_str = data['info_str']
        expected_end = data['end_value']
        
        # Parse the INFO field
        parsed_info = parse_info_field(info_str)
        
        # Property: END value should match expected
        assert parsed_info['END'] == expected_end, \
            f"Expected END={expected_end}, got END={parsed_info.get('END')}"
    
    @given(end_positions)
    def test_end_position_always_identifies_reference_block(self, end_pos):
        """
        Property: Any INFO field with END=<position> should be identified
        as a reference block.
        
        **Validates: Requirements 3.5**
        """
        info_str = f"END={end_pos}"
        
        # Parse the INFO field
        parsed_info = parse_info_field(info_str)
        
        # Property: Should be identified as reference block
        is_reference_block = 'END' in parsed_info
        assert is_reference_block is True, \
            f"INFO with END={end_pos} should be a reference block"
    
    @given(info_field_with_end())
    def test_end_presence_independent_of_other_fields(self, data):
        """
        Property: The presence of END key should identify a reference block
        regardless of other INFO fields present.
        
        **Validates: Requirements 3.5**
        """
        info_str = data['info_str']
        
        # Parse the INFO field
        parsed_info = parse_info_field(info_str)
        
        # Property: END should be present regardless of other fields
        assert 'END' in parsed_info, \
            "END should be present regardless of other INFO fields"
        
        # Property: Should be identified as reference block
        is_reference_block = 'END' in parsed_info
        assert is_reference_block is True, \
            "Should be reference block when END is present"
    
    def test_empty_info_not_reference_block(self):
        """
        Property: An empty INFO field (.) should not be a reference block.
        
        **Validates: Requirements 3.5**
        """
        info_str = '.'
        
        # Parse the INFO field
        parsed_info = parse_info_field(info_str)
        
        # Property: Should not be a reference block
        is_reference_block = 'END' in parsed_info
        assert is_reference_block is False, \
            "Empty INFO should not be a reference block"
    
    @given(st.lists(info_keys, min_size=1, max_size=10, unique=True))
    def test_non_end_keys_not_reference_block(self, keys):
        """
        Property: INFO fields with any keys except END should not be
        identified as reference blocks.
        
        **Validates: Requirements 3.5**
        """
        # Build INFO string without END
        info_str = ';'.join(keys)
        
        # Parse the INFO field
        parsed_info = parse_info_field(info_str)
        
        # Property: Should not be a reference block
        is_reference_block = 'END' in parsed_info
        assert is_reference_block is False, \
            f"INFO without END should not be a reference block: {info_str}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
