#!/usr/bin/env python3
"""
Property-based tests for VCF header sample extraction.

**Validates: Requirements 3.1**

Property 4: VCF Header Sample Extraction
For any valid VCF file, parsing the header should extract all sample names
from the #CHROM header line (columns 10+).
"""

import pytest
import os
import sys
import tempfile
from hypothesis import given, strategies as st
from io import StringIO

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from load_vcf_schema1 import parse_vcf_header


# Strategy for generating valid sample names
# Sample names can contain alphanumeric characters, underscores, hyphens, and dots
sample_names = st.text(
    alphabet=st.characters(categories=('Lu', 'Ll', 'Nd'), include_characters='_-.'),
    min_size=1,
    max_size=50
).filter(lambda x: x and x[0].isalnum())


# Strategy for generating lists of sample names
sample_lists = st.lists(sample_names, min_size=0, max_size=20, unique=True)


def create_vcf_header(samples):
    """
    Create a minimal VCF header with the given sample names.
    
    Args:
        samples: List of sample names
        
    Returns:
        String containing VCF header
    """
    header_lines = [
        "##fileformat=VCFv4.2",
        "##INFO=<ID=DP,Number=1,Type=Integer,Description=\"Total Depth\">",
        "##FORMAT=<ID=GT,Number=1,Type=String,Description=\"Genotype\">",
    ]
    
    # Build the #CHROM header line
    chrom_line = "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT"
    if samples:
        chrom_line += "\t" + "\t".join(samples)
    
    header_lines.append(chrom_line)
    
    return "\n".join(header_lines) + "\n"


class TestVCFHeaderSampleExtractionProperty:
    """Property-based tests for VCF header sample extraction."""
    
    @given(sample_lists)
    def test_all_samples_extracted(self, samples):
        """
        Property: For any list of sample names in the VCF header,
        parse_vcf_header should extract all sample names in order.
        
        **Validates: Requirements 3.1**
        """
        # Create VCF header with the given samples
        vcf_header = create_vcf_header(samples)
        
        # Parse the header
        vcf_file = StringIO(vcf_header)
        extracted_samples, info_fields, format_fields = parse_vcf_header(vcf_file)
        
        # Property: All samples should be extracted
        assert extracted_samples == samples, \
            f"Expected samples {samples}, got {extracted_samples}"
    
    @given(sample_lists)
    def test_sample_count_matches(self, samples):
        """
        Property: The number of extracted samples should match the number
        of samples in the header.
        
        **Validates: Requirements 3.1**
        """
        # Create VCF header with the given samples
        vcf_header = create_vcf_header(samples)
        
        # Parse the header
        vcf_file = StringIO(vcf_header)
        extracted_samples, _, _ = parse_vcf_header(vcf_file)
        
        # Property: Sample count should match
        assert len(extracted_samples) == len(samples), \
            f"Expected {len(samples)} samples, got {len(extracted_samples)}"
    
    @given(sample_lists)
    def test_sample_order_preserved(self, samples):
        """
        Property: The order of samples should be preserved during extraction.
        
        **Validates: Requirements 3.1**
        """
        # Create VCF header with the given samples
        vcf_header = create_vcf_header(samples)
        
        # Parse the header
        vcf_file = StringIO(vcf_header)
        extracted_samples, _, _ = parse_vcf_header(vcf_file)
        
        # Property: Order should be preserved
        for i, (expected, actual) in enumerate(zip(samples, extracted_samples)):
            assert expected == actual, \
                f"Sample order mismatch at position {i}: expected {expected}, got {actual}"
    
    @given(st.lists(sample_names, min_size=1, max_size=10, unique=True))
    def test_no_duplicate_samples(self, samples):
        """
        Property: When unique sample names are provided, no duplicates
        should appear in the extracted list.
        
        **Validates: Requirements 3.1**
        """
        # Create VCF header with unique samples
        vcf_header = create_vcf_header(samples)
        
        # Parse the header
        vcf_file = StringIO(vcf_header)
        extracted_samples, _, _ = parse_vcf_header(vcf_file)
        
        # Property: No duplicates in extracted samples
        assert len(extracted_samples) == len(set(extracted_samples)), \
            f"Duplicate samples found in {extracted_samples}"
    
    @given(sample_lists)
    def test_empty_samples_handled(self, samples):
        """
        Property: VCF headers with any number of samples (including zero)
        should be parsed without errors.
        
        **Validates: Requirements 3.1**
        """
        # Create VCF header with the given samples (may be empty)
        vcf_header = create_vcf_header(samples)
        
        # Parse the header
        vcf_file = StringIO(vcf_header)
        extracted_samples, _, _ = parse_vcf_header(vcf_file)
        
        # Property: Should handle empty sample lists
        if not samples:
            assert extracted_samples == [], \
                f"Expected empty list for no samples, got {extracted_samples}"
        else:
            assert len(extracted_samples) > 0, \
                "Expected non-empty sample list"
    
    @given(
        samples=sample_lists,
        extra_info_lines=st.integers(min_value=0, max_value=10)
    )
    def test_samples_extracted_regardless_of_header_size(self, samples, extra_info_lines):
        """
        Property: Sample extraction should work regardless of the number
        of INFO/FORMAT lines in the header.
        
        **Validates: Requirements 3.1**
        """
        # Create header with extra INFO lines
        header_lines = ["##fileformat=VCFv4.2"]
        
        # Add extra INFO lines
        for i in range(extra_info_lines):
            header_lines.append(
                f"##INFO=<ID=INFO{i},Number=1,Type=String,Description=\"Info field {i}\">"
            )
        
        # Add #CHROM line
        chrom_line = "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT"
        if samples:
            chrom_line += "\t" + "\t".join(samples)
        header_lines.append(chrom_line)
        
        vcf_header = "\n".join(header_lines) + "\n"
        
        # Parse the header
        vcf_file = StringIO(vcf_header)
        extracted_samples, _, _ = parse_vcf_header(vcf_file)
        
        # Property: Samples should be extracted correctly
        assert extracted_samples == samples, \
            f"Expected {samples}, got {extracted_samples} with {extra_info_lines} extra INFO lines"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
