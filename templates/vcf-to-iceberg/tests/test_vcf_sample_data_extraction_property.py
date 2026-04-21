#!/usr/bin/env python3
"""
Property-based tests for VCF sample data extraction.

**Validates: Requirements 3.4**

Property 7: VCF Sample Data Extraction
For any VCF record with sample columns, parsing should extract genotype
and all FORMAT field attributes for each sample.
"""

import pytest
import os
import sys
from hypothesis import given, strategies as st

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from load_vcf_schema1 import parse_format_field


# Strategy for generating valid genotypes
genotypes = st.sampled_from(['0/0', '0/1', '1/1', '0|0', '0|1', '1|1', './.', '.|.', '0', '1', '.'])

# Strategy for generating valid FORMAT field keys
format_keys = st.text(
    alphabet=st.characters(categories=('Lu',), include_characters='_'),
    min_size=2,
    max_size=10
).filter(lambda x: x and x[0].isupper())

# Strategy for generating valid FORMAT field values
format_values = st.text(
    alphabet=st.characters(categories=('Nd',), include_characters='.,'),
    min_size=1,
    max_size=20
).filter(lambda x: x and x != '')


@st.composite
def format_sample_pair(draw):
    """Generate a valid FORMAT and sample data pair."""
    # Generate FORMAT keys
    num_fields = draw(st.integers(min_value=1, max_value=5))
    keys = []
    values = []
    
    for i in range(num_fields):
        if i == 0:
            # First field is always GT (genotype)
            keys.append('GT')
            # Avoid generating '.' as the entire sample string
            values.append(draw(genotypes.filter(lambda x: x != '.')))
        else:
            # Other fields
            key = draw(format_keys)
            # Ensure unique keys
            while key in keys:
                key = draw(format_keys)
            keys.append(key)
            values.append(draw(format_values))
    
    format_str = ':'.join(keys)
    sample_str = ':'.join(values)
    expected_dict = dict(zip(keys, values))
    
    return {
        'format_str': format_str,
        'sample_str': sample_str,
        'expected_dict': expected_dict
    }


class TestVCFSampleDataExtractionProperty:
    """Property-based tests for VCF sample data extraction."""
    
    @given(format_sample_pair())
    def test_all_format_fields_extracted(self, data):
        """
        Property: For any FORMAT and sample data pair, parse_format_field
        should extract all key-value pairs correctly.
        
        **Validates: Requirements 3.4**
        """
        format_str = data['format_str']
        sample_str = data['sample_str']
        expected_dict = data['expected_dict']
        
        # Parse the FORMAT and sample fields
        parsed_dict = parse_format_field(format_str, sample_str)
        
        # Property: All fields should be extracted
        assert parsed_dict == expected_dict, \
            f"Expected {expected_dict}, got {parsed_dict}"
    
    @given(format_sample_pair())
    def test_genotype_always_extractable(self, data):
        """
        Property: For any FORMAT/sample pair with GT field, the genotype
        should be extractable (unless sample is missing).
        
        **Validates: Requirements 3.4**
        """
        format_str = data['format_str']
        sample_str = data['sample_str']
        
        # Parse the FORMAT and sample fields
        parsed_dict = parse_format_field(format_str, sample_str)
        
        # Property: If GT is in format and sample is not '.', it should be in parsed dict
        if 'GT' in format_str and sample_str != '.':
            assert 'GT' in parsed_dict, \
                "GT field should be present in parsed dictionary"
    
    @given(st.lists(format_keys, min_size=1, max_size=10, unique=True))
    def test_format_field_count_matches(self, keys):
        """
        Property: The number of parsed fields should match the number
        of FORMAT keys.
        
        **Validates: Requirements 3.4**
        """
        # Build FORMAT and sample strings
        format_str = ':'.join(keys)
        sample_str = ':'.join(['value' for _ in keys])
        
        # Parse the FORMAT and sample fields
        parsed_dict = parse_format_field(format_str, sample_str)
        
        # Property: Number of fields should match
        assert len(parsed_dict) == len(keys), \
            f"Expected {len(keys)} fields, got {len(parsed_dict)}"
    
    def test_missing_format_returns_empty_dict(self):
        """
        Property: Missing FORMAT field (.) should return an empty dictionary.
        
        **Validates: Requirements 3.4**
        """
        parsed_dict = parse_format_field('.', '.')
        
        # Property: Should return empty dict
        assert parsed_dict == {}, \
            f"Expected empty dict for missing FORMAT, got {parsed_dict}"
    
    @given(st.lists(format_keys, min_size=1, max_size=5, unique=True))
    def test_missing_sample_values_handled(self, keys):
        """
        Property: When sample values are fewer than FORMAT keys,
        missing values should be filled with '.'.
        
        **Validates: Requirements 3.4**
        """
        # Build FORMAT string with more keys than sample values
        format_str = ':'.join(keys)
        # Only provide half the values
        num_values = max(1, len(keys) // 2)
        sample_str = ':'.join(['value' for _ in range(num_values)])
        
        # Parse the FORMAT and sample fields
        parsed_dict = parse_format_field(format_str, sample_str)
        
        # Property: Should have all keys
        assert len(parsed_dict) == len(keys), \
            f"Expected {len(keys)} fields, got {len(parsed_dict)}"
        
        # Property: Missing values should be '.'
        for i, key in enumerate(keys):
            if i >= num_values:
                assert parsed_dict[key] == '.', \
                    f"Expected '.' for missing value at key {key}, got {parsed_dict[key]}"
    
    @given(format_sample_pair())
    def test_format_keys_preserved(self, data):
        """
        Property: All FORMAT keys should be preserved in the parsed dictionary
        (unless sample is missing).
        
        **Validates: Requirements 3.4**
        """
        format_str = data['format_str']
        sample_str = data['sample_str']
        
        # Parse the FORMAT and sample fields
        parsed_dict = parse_format_field(format_str, sample_str)
        
        # Property: All keys should be present (unless sample is '.')
        if sample_str != '.':
            expected_keys = set(format_str.split(':'))
            assert set(parsed_dict.keys()) == expected_keys, \
                f"Key mismatch: expected {expected_keys}, got {set(parsed_dict.keys())}"
    
    @given(genotypes)
    def test_genotype_formats_handled(self, gt):
        """
        Property: All valid genotype formats should be parseable
        (except missing genotype '.').
        
        **Validates: Requirements 3.4**
        """
        format_str = 'GT'
        sample_str = gt
        
        # Parse the FORMAT and sample fields
        parsed_dict = parse_format_field(format_str, sample_str)
        
        # Property: Genotype should be extracted (unless it's '.')
        if gt != '.':
            assert 'GT' in parsed_dict, "GT should be in parsed dictionary"
            assert parsed_dict['GT'] == gt, \
                f"Expected GT={gt}, got {parsed_dict['GT']}"
        else:
            # When sample is '.', function returns empty dict
            assert parsed_dict == {}, \
                f"Expected empty dict for missing sample, got {parsed_dict}"
    
    @given(
        keys=st.lists(format_keys, min_size=2, max_size=5, unique=True),
        values=st.lists(format_values, min_size=2, max_size=5)
    )
    def test_key_value_pairing_correct(self, keys, values):
        """
        Property: Keys and values should be correctly paired in order.
        
        **Validates: Requirements 3.4**
        """
        # Ensure we have matching lengths
        min_len = min(len(keys), len(values))
        keys = keys[:min_len]
        values = values[:min_len]
        
        format_str = ':'.join(keys)
        sample_str = ':'.join(values)
        
        # Parse the FORMAT and sample fields
        parsed_dict = parse_format_field(format_str, sample_str)
        
        # Property: Each key should map to its corresponding value
        for key, value in zip(keys, values):
            assert parsed_dict[key] == value, \
                f"Expected {key}={value}, got {key}={parsed_dict[key]}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
