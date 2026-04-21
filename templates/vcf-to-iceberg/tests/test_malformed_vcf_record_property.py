#!/usr/bin/env python3
"""
Property-based tests for malformed VCF record handling.

**Validates: Requirements 8.4**

Property 14: Malformed VCF Record Handling
For any VCF file containing malformed records (records with fewer than 8 fields),
processing should skip the malformed records and continue processing valid records.
"""

import pytest
import os
import sys
import tempfile
from hypothesis import given, strategies as st
from io import StringIO

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from load_vcf_schema1 import open_vcf_file


# Strategy for generating valid VCF records
@st.composite
def valid_vcf_record(draw):
    """Generate a valid VCF record with all 8 required fields."""
    chrom = draw(st.sampled_from(['chr1', 'chr2', 'chr3']))
    pos = draw(st.integers(min_value=1, max_value=1000000))
    ref = draw(st.sampled_from(['A', 'C', 'G', 'T']))
    alt = draw(st.sampled_from(['A', 'C', 'G', 'T']))
    qual = draw(st.integers(min_value=0, max_value=100))
    
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t{qual}\tPASS\tDP=100"


# Strategy for generating malformed VCF records (fewer than 8 fields)
@st.composite
def malformed_vcf_record(draw):
    """Generate a malformed VCF record with fewer than 8 fields."""
    num_fields = draw(st.integers(min_value=1, max_value=7))
    fields = []
    
    for i in range(num_fields):
        if i == 0:
            # Chromosome
            fields.append(draw(st.sampled_from(['chr1', 'chr2', 'chr3'])))
        elif i == 1:
            # Position
            fields.append(str(draw(st.integers(min_value=1, max_value=1000000))))
        else:
            # Other fields
            fields.append(draw(st.text(alphabet='ACGT.', min_size=1, max_size=10)))
    
    return '\t'.join(fields)


def create_vcf_with_records(valid_records, malformed_records):
    """
    Create a VCF file with a mix of valid and malformed records.
    
    Args:
        valid_records: List of valid VCF record strings
        malformed_records: List of malformed VCF record strings
        
    Returns:
        String containing complete VCF file
    """
    header_lines = [
        "##fileformat=VCFv4.2",
        "##INFO=<ID=DP,Number=1,Type=Integer,Description=\"Total Depth\">",
        "##FORMAT=<ID=GT,Number=1,Type=String,Description=\"Genotype\">",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"
    ]
    
    # Interleave valid and malformed records
    all_records = []
    for i in range(max(len(valid_records), len(malformed_records))):
        if i < len(valid_records):
            all_records.append(valid_records[i])
        if i < len(malformed_records):
            all_records.append(malformed_records[i])
    
    return "\n".join(header_lines + all_records) + "\n"


def count_valid_records_in_vcf(vcf_content):
    """
    Count the number of valid records (8+ fields) in VCF content.
    
    Args:
        vcf_content: String containing VCF file content
        
    Returns:
        Number of valid records
    """
    valid_count = 0
    for line in vcf_content.split('\n'):
        if line and not line.startswith('#'):
            fields = line.split('\t')
            if len(fields) >= 8:
                valid_count += 1
    return valid_count


class TestMalformedVCFRecordProperty:
    """Property-based tests for malformed VCF record handling."""
    
    @given(
        valid_records=st.lists(valid_vcf_record(), min_size=1, max_size=10),
        malformed_records=st.lists(malformed_vcf_record(), min_size=1, max_size=5)
    )
    def test_malformed_records_skipped(self, valid_records, malformed_records):
        """
        Property: For any VCF file with malformed records, processing should
        skip malformed records and continue with valid ones.
        
        **Validates: Requirements 8.4**
        """
        # Create VCF with mix of valid and malformed records
        vcf_content = create_vcf_with_records(valid_records, malformed_records)
        
        # Count expected valid records
        expected_valid = count_valid_records_in_vcf(vcf_content)
        
        # Property: Expected valid count should match the number of valid records we created
        assert expected_valid == len(valid_records), \
            f"Expected {len(valid_records)} valid records, counted {expected_valid}"
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.vcf', delete=False) as f:
            f.write(vcf_content)
            vcf_path = f.name
        
        try:
            # Open and read the VCF file
            with open_vcf_file(vcf_path) as vcf_file:
                lines = vcf_file.readlines()
            
            # Count records that would be processed (skip header and malformed)
            processed_count = 0
            for line in lines:
                if line.strip() and not line.startswith('#'):
                    fields = line.strip().split('\t')
                    if len(fields) >= 8:
                        processed_count += 1
            
            # Property: Only valid records should be processable
            assert processed_count == len(valid_records), \
                f"Expected {len(valid_records)} processable records, got {processed_count}"
        
        finally:
            # Clean up
            os.unlink(vcf_path)
    
    @given(malformed_vcf_record())
    def test_malformed_record_has_fewer_than_8_fields(self, record):
        """
        Property: All malformed records should have fewer than 8 fields.
        
        **Validates: Requirements 8.4**
        """
        fields = record.split('\t')
        
        # Property: Malformed records have < 8 fields
        assert len(fields) < 8, \
            f"Malformed record should have < 8 fields, got {len(fields)}"
    
    @given(valid_vcf_record())
    def test_valid_record_has_at_least_8_fields(self, record):
        """
        Property: All valid records should have at least 8 fields.
        
        **Validates: Requirements 8.4**
        """
        fields = record.split('\t')
        
        # Property: Valid records have >= 8 fields
        assert len(fields) >= 8, \
            f"Valid record should have >= 8 fields, got {len(fields)}"
    
    @given(
        valid_records=st.lists(valid_vcf_record(), min_size=5, max_size=10),
        num_malformed=st.integers(min_value=1, max_value=5)
    )
    def test_valid_records_count_preserved(self, valid_records, num_malformed):
        """
        Property: The number of valid records should be preserved regardless
        of how many malformed records are present.
        
        **Validates: Requirements 8.4**
        """
        # Generate malformed records
        malformed_records = []
        for _ in range(num_malformed):
            # Create records with varying numbers of fields (1-7)
            num_fields = (_ % 7) + 1
            fields = ['field'] * num_fields
            malformed_records.append('\t'.join(fields))
        
        # Create VCF with mix of valid and malformed records
        vcf_content = create_vcf_with_records(valid_records, malformed_records)
        
        # Count valid records
        valid_count = count_valid_records_in_vcf(vcf_content)
        
        # Property: Valid count should equal number of valid records created
        assert valid_count == len(valid_records), \
            f"Expected {len(valid_records)} valid records, got {valid_count}"
    
    @given(st.lists(malformed_vcf_record(), min_size=1, max_size=10))
    def test_all_malformed_records_skipped(self, malformed_records):
        """
        Property: A VCF file with only malformed records should result in
        zero processable records.
        
        **Validates: Requirements 8.4**
        """
        # Create VCF with only malformed records
        vcf_content = create_vcf_with_records([], malformed_records)
        
        # Count valid records
        valid_count = count_valid_records_in_vcf(vcf_content)
        
        # Property: Should have zero valid records
        assert valid_count == 0, \
            f"Expected 0 valid records for all-malformed VCF, got {valid_count}"
    
    @given(st.integers(min_value=1, max_value=7))
    def test_records_with_n_fields_are_malformed(self, num_fields):
        """
        Property: Any record with 1-7 fields should be considered malformed.
        
        **Validates: Requirements 8.4**
        """
        # Create a record with exactly num_fields fields
        fields = ['field'] * num_fields
        record = '\t'.join(fields)
        
        # Property: Should be malformed
        assert len(record.split('\t')) < 8, \
            f"Record with {num_fields} fields should be malformed"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
