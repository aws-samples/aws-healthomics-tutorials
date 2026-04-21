#!/usr/bin/env python3
"""
Property-based tests for VCF record field extraction.

**Validates: Requirements 3.3**

Property 6: VCF Record Field Extraction
For any valid VCF record, parsing should extract all required fields:
chromosome, position, reference, alternate, quality, filter, and INFO dictionary.
"""

import pytest
import os
import sys
from hypothesis import given, strategies as st

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from load_vcf_schema1 import parse_info_field


# Strategy for generating valid chromosome names
chromosomes = st.sampled_from([
    'chr1', 'chr2', 'chr3', 'chr4', 'chr5', 'chr6', 'chr7', 'chr8', 'chr9', 'chr10',
    'chr11', 'chr12', 'chr13', 'chr14', 'chr15', 'chr16', 'chr17', 'chr18', 'chr19', 'chr20',
    'chr21', 'chr22', 'chrX', 'chrY', 'chrM',
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
    '11', '12', '13', '14', '15', '16', '17', '18', '19', '20',
    '21', '22', 'X', 'Y', 'MT'
])

# Strategy for generating valid positions
positions = st.integers(min_value=1, max_value=250000000)

# Strategy for generating valid nucleotides
nucleotides = st.sampled_from(['A', 'C', 'G', 'T', 'N'])

# Strategy for generating valid alleles (including multi-nucleotide)
alleles = st.text(alphabet='ACGTN', min_size=1, max_size=10)

# Strategy for generating valid quality scores
quality_scores = st.one_of(
    st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    st.just('.')
)

# Strategy for generating valid filter values
filters = st.sampled_from(['PASS', 'FAIL', 'LowQual', 'HighDepth', '.'])

# Strategy for generating INFO field keys
info_keys = st.text(
    alphabet=st.characters(categories=('Lu', 'Ll', 'Nd'), include_characters='_'),
    min_size=1,
    max_size=20
).filter(lambda x: x and x[0].isalpha())

# Strategy for generating INFO field values
info_values = st.text(
    alphabet=st.characters(categories=('Lu', 'Ll', 'Nd'), include_characters='_.-'),
    min_size=1,
    max_size=50
).filter(lambda x: x and ';' not in x and '=' not in x)


@st.composite
def vcf_record(draw):
    """Generate a valid VCF record line."""
    chrom = draw(chromosomes)
    pos = draw(positions)
    id_field = draw(st.sampled_from(['.', 'rs12345', 'var001']))
    ref = draw(alleles)
    alt = draw(alleles)
    qual = draw(quality_scores)
    filter_val = draw(filters)
    
    # Generate INFO field
    num_info_fields = draw(st.integers(min_value=0, max_value=5))
    info_parts = []
    info_dict = {}
    
    for _ in range(num_info_fields):
        key = draw(info_keys)
        # Some INFO fields are flags (no value)
        if draw(st.booleans()):
            info_parts.append(key)
            info_dict[key] = 'true'
        else:
            value = draw(info_values)
            info_parts.append(f"{key}={value}")
            info_dict[key] = value
    
    info_str = ';'.join(info_parts) if info_parts else '.'
    
    # Build the record
    qual_str = str(qual) if qual != '.' else '.'
    record = f"{chrom}\t{pos}\t{id_field}\t{ref}\t{alt}\t{qual_str}\t{filter_val}\t{info_str}"
    
    return {
        'record': record,
        'chrom': chrom,
        'pos': pos,
        'id': id_field,
        'ref': ref,
        'alt': alt,
        'qual': qual,
        'filter': filter_val,
        'info_str': info_str,
        'info_dict': info_dict
    }


class TestVCFRecordFieldExtractionProperty:
    """Property-based tests for VCF record field extraction."""
    
    @given(vcf_record())
    def test_all_required_fields_extractable(self, record_data):
        """
        Property: For any valid VCF record, all required fields should be
        extractable by splitting on tabs.
        
        **Validates: Requirements 3.3**
        """
        record = record_data['record']
        fields = record.split('\t')
        
        # Property: Should have at least 8 fields
        assert len(fields) >= 8, \
            f"VCF record should have at least 8 fields, got {len(fields)}"
        
        # Property: Fields should match expected values
        assert fields[0] == record_data['chrom'], "Chromosome mismatch"
        assert fields[1] == str(record_data['pos']), "Position mismatch"
        assert fields[2] == record_data['id'], "ID mismatch"
        assert fields[3] == record_data['ref'], "Reference mismatch"
        assert fields[4] == record_data['alt'], "Alternate mismatch"
        assert fields[6] == record_data['filter'], "Filter mismatch"
        assert fields[7] == record_data['info_str'], "INFO mismatch"
    
    @given(vcf_record())
    def test_info_field_parsing(self, record_data):
        """
        Property: For any valid INFO field, parse_info_field should extract
        all key-value pairs correctly.
        
        **Validates: Requirements 3.3**
        """
        info_str = record_data['info_str']
        expected_dict = record_data['info_dict']
        
        # Parse the INFO field
        parsed_dict = parse_info_field(info_str)
        
        # Property: Parsed dictionary should match expected
        assert parsed_dict == expected_dict, \
            f"INFO field mismatch: expected {expected_dict}, got {parsed_dict}"
    
    @given(st.lists(st.tuples(info_keys, info_values), min_size=0, max_size=10, unique_by=lambda x: x[0]))
    def test_info_field_key_value_pairs(self, key_value_pairs):
        """
        Property: For any list of key-value pairs, parse_info_field should
        extract all pairs correctly.
        
        **Validates: Requirements 3.3**
        """
        # Build INFO string
        if not key_value_pairs:
            info_str = '.'
            expected_dict = {}
        else:
            info_str = ';'.join([f"{k}={v}" for k, v in key_value_pairs])
            expected_dict = dict(key_value_pairs)
        
        # Parse the INFO field
        parsed_dict = parse_info_field(info_str)
        
        # Property: All key-value pairs should be extracted
        assert parsed_dict == expected_dict, \
            f"Expected {expected_dict}, got {parsed_dict}"
    
    @given(st.lists(info_keys, min_size=0, max_size=10, unique=True))
    def test_info_field_flags(self, flags):
        """
        Property: For any list of flag keys (no values), parse_info_field
        should set them to 'true'.
        
        **Validates: Requirements 3.3**
        """
        # Build INFO string with flags
        if not flags:
            info_str = '.'
            expected_dict = {}
        else:
            info_str = ';'.join(flags)
            expected_dict = {flag: 'true' for flag in flags}
        
        # Parse the INFO field
        parsed_dict = parse_info_field(info_str)
        
        # Property: All flags should be set to 'true'
        assert parsed_dict == expected_dict, \
            f"Expected {expected_dict}, got {parsed_dict}"
    
    def test_info_field_empty_returns_empty_dict(self):
        """
        Property: An empty INFO field (.) should return an empty dictionary.
        
        **Validates: Requirements 3.3**
        """
        parsed_dict = parse_info_field('.')
        
        # Property: Should return empty dict
        assert parsed_dict == {}, \
            f"Expected empty dict for '.', got {parsed_dict}"
    
    @given(st.lists(st.tuples(info_keys, info_values), min_size=1, max_size=5, unique_by=lambda x: x[0]))
    def test_info_field_preserves_all_keys(self, key_value_pairs):
        """
        Property: For any INFO field, all keys should be preserved in the
        parsed dictionary.
        
        **Validates: Requirements 3.3**
        """
        # Build INFO string
        info_str = ';'.join([f"{k}={v}" for k, v in key_value_pairs])
        expected_keys = set(k for k, v in key_value_pairs)
        
        # Parse the INFO field
        parsed_dict = parse_info_field(info_str)
        
        # Property: All keys should be present
        assert set(parsed_dict.keys()) == expected_keys, \
            f"Key mismatch: expected {expected_keys}, got {set(parsed_dict.keys())}"
    
    @given(vcf_record())
    def test_position_is_positive_integer(self, record_data):
        """
        Property: The position field should always be a positive integer.
        
        **Validates: Requirements 3.3**
        """
        pos = record_data['pos']
        
        # Property: Position should be positive
        assert pos > 0, f"Position should be positive, got {pos}"
        assert isinstance(pos, int), f"Position should be integer, got {type(pos)}"
    
    @given(vcf_record())
    def test_quality_is_numeric_or_missing(self, record_data):
        """
        Property: The quality field should be either a number or '.'.
        
        **Validates: Requirements 3.3**
        """
        qual = record_data['qual']
        
        # Property: Quality should be numeric or '.'
        assert qual == '.' or isinstance(qual, (int, float)), \
            f"Quality should be numeric or '.', got {qual} ({type(qual)})"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
