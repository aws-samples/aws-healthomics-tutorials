#!/usr/bin/env python3
"""
Property-based tests for gzipped VCF decompression.

**Validates: Requirements 3.2**

Property 5: Gzipped VCF Decompression
For any VCF content, processing a gzipped version should produce the same
parsed results as processing the uncompressed version.
"""

import pytest
import os
import sys
import tempfile
import gzip
from hypothesis import given, strategies as st

# Import the module to test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from load_vcf_schema1 import open_vcf_file, parse_vcf_header


# Strategy for generating valid sample names
sample_names = st.text(
    alphabet=st.characters(categories=('Lu', 'Ll', 'Nd'), include_characters='_-.'),
    min_size=1,
    max_size=30
).filter(lambda x: x and x[0].isalnum())


# Strategy for generating VCF content
@st.composite
def vcf_content(draw):
    """Generate valid VCF file content."""
    # Generate samples
    num_samples = draw(st.integers(min_value=0, max_value=5))
    samples = [draw(sample_names) for _ in range(num_samples)]
    
    # Make samples unique
    samples = list(dict.fromkeys(samples))
    
    # Build header
    header_lines = [
        "##fileformat=VCFv4.2",
        "##INFO=<ID=DP,Number=1,Type=Integer,Description=\"Total Depth\">",
        "##INFO=<ID=AF,Number=A,Type=Float,Description=\"Allele Frequency\">",
        "##FORMAT=<ID=GT,Number=1,Type=String,Description=\"Genotype\">",
        "##FORMAT=<ID=DP,Number=1,Type=Integer,Description=\"Read Depth\">",
    ]
    
    # Add #CHROM line
    chrom_line = "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT"
    if samples:
        chrom_line += "\t" + "\t".join(samples)
    header_lines.append(chrom_line)
    
    # Generate a few variant records
    num_records = draw(st.integers(min_value=0, max_value=5))
    for i in range(num_records):
        chrom = draw(st.sampled_from(['chr1', 'chr2', 'chr3', 'chrX']))
        pos = draw(st.integers(min_value=1, max_value=1000000))
        ref = draw(st.sampled_from(['A', 'C', 'G', 'T']))
        alt = draw(st.sampled_from(['A', 'C', 'G', 'T']))
        qual = draw(st.integers(min_value=0, max_value=100))
        
        record = f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t{qual}\tPASS\tDP=100\tGT:DP"
        
        # Add sample data
        for _ in samples:
            gt = draw(st.sampled_from(['0/0', '0/1', '1/1', './.']))
            dp = draw(st.integers(min_value=0, max_value=50))
            record += f"\t{gt}:{dp}"
        
        header_lines.append(record)
    
    return "\n".join(header_lines) + "\n"


class TestGzippedVCFDecompressionProperty:
    """Property-based tests for gzipped VCF decompression."""
    
    @given(vcf_content())
    def test_gzipped_and_uncompressed_produce_same_header(self, content):
        """
        Property: Parsing the header from a gzipped VCF should produce
        the same results as parsing from an uncompressed VCF.
        
        **Validates: Requirements 3.2**
        """
        # Create temporary files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.vcf', delete=False) as f_plain:
            f_plain.write(content)
            plain_path = f_plain.name
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.vcf.gz', delete=False) as f_gz:
            f_gz.write(gzip.compress(content.encode('utf-8')))
            gz_path = f_gz.name
        
        try:
            # Parse plain VCF
            with open_vcf_file(plain_path) as vcf_plain:
                samples_plain, info_plain, format_plain = parse_vcf_header(vcf_plain)
            
            # Parse gzipped VCF
            with open_vcf_file(gz_path) as vcf_gz:
                samples_gz, info_gz, format_gz = parse_vcf_header(vcf_gz)
            
            # Property: Results should be identical
            assert samples_plain == samples_gz, \
                f"Sample mismatch: plain={samples_plain}, gzipped={samples_gz}"
            
            assert info_plain == info_gz, \
                f"INFO fields mismatch: plain={info_plain}, gzipped={info_gz}"
            
            assert format_plain == format_gz, \
                f"FORMAT fields mismatch: plain={format_plain}, gzipped={format_gz}"
        
        finally:
            # Clean up
            os.unlink(plain_path)
            os.unlink(gz_path)
    
    @given(vcf_content())
    def test_gzipped_and_uncompressed_produce_same_content(self, content):
        """
        Property: Reading all lines from a gzipped VCF should produce
        the same content as reading from an uncompressed VCF.
        
        **Validates: Requirements 3.2**
        """
        # Create temporary files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.vcf', delete=False) as f_plain:
            f_plain.write(content)
            plain_path = f_plain.name
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.vcf.gz', delete=False) as f_gz:
            f_gz.write(gzip.compress(content.encode('utf-8')))
            gz_path = f_gz.name
        
        try:
            # Read plain VCF
            with open_vcf_file(plain_path) as vcf_plain:
                lines_plain = vcf_plain.readlines()
            
            # Read gzipped VCF
            with open_vcf_file(gz_path) as vcf_gz:
                lines_gz = vcf_gz.readlines()
            
            # Property: Content should be identical
            assert lines_plain == lines_gz, \
                f"Content mismatch between plain and gzipped VCF"
        
        finally:
            # Clean up
            os.unlink(plain_path)
            os.unlink(gz_path)
    
    @given(vcf_content())
    def test_gzipped_file_opens_successfully(self, content):
        """
        Property: Any valid VCF content should be successfully opened
        when gzipped.
        
        **Validates: Requirements 3.2**
        """
        # Create temporary gzipped file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.vcf.gz', delete=False) as f_gz:
            f_gz.write(gzip.compress(content.encode('utf-8')))
            gz_path = f_gz.name
        
        try:
            # Property: Should open without errors
            with open_vcf_file(gz_path) as vcf_gz:
                # Read at least one line to ensure it's working
                first_line = vcf_gz.readline()
                assert first_line is not None
        
        finally:
            # Clean up
            os.unlink(gz_path)
    
    @given(vcf_content())
    def test_uncompressed_file_opens_successfully(self, content):
        """
        Property: Any valid VCF content should be successfully opened
        when uncompressed.
        
        **Validates: Requirements 3.2**
        """
        # Create temporary plain file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.vcf', delete=False) as f_plain:
            f_plain.write(content)
            plain_path = f_plain.name
        
        try:
            # Property: Should open without errors
            with open_vcf_file(plain_path) as vcf_plain:
                # Read at least one line to ensure it's working
                first_line = vcf_plain.readline()
                assert first_line is not None
        
        finally:
            # Clean up
            os.unlink(plain_path)
    
    @given(vcf_content())
    def test_file_extension_determines_decompression(self, content):
        """
        Property: Files with .gz extension should be decompressed,
        files without should be read as plain text.
        
        **Validates: Requirements 3.2**
        """
        # Create both file types
        with tempfile.NamedTemporaryFile(mode='w', suffix='.vcf', delete=False) as f_plain:
            f_plain.write(content)
            plain_path = f_plain.name
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.vcf.gz', delete=False) as f_gz:
            f_gz.write(gzip.compress(content.encode('utf-8')))
            gz_path = f_gz.name
        
        try:
            # Both should produce the same first line
            with open_vcf_file(plain_path) as vcf_plain:
                first_line_plain = vcf_plain.readline()
            
            with open_vcf_file(gz_path) as vcf_gz:
                first_line_gz = vcf_gz.readline()
            
            # Property: First lines should match
            assert first_line_plain == first_line_gz, \
                "First line mismatch between plain and gzipped files"
        
        finally:
            # Clean up
            os.unlink(plain_path)
            os.unlink(gz_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
