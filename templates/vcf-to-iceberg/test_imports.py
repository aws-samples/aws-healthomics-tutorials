#!/usr/bin/env python3
"""
Test script to verify all Python modules can be imported correctly.
This simulates what will happen inside the Docker container.
"""

import sys

def test_imports():
    """Test importing all required modules."""
    errors = []
    
    # Test standard library imports
    try:
        import json
        import os
        import gzip
        print("✓ Standard library imports successful")
    except ImportError as e:
        errors.append(f"Standard library import error: {e}")
        print(f"✗ Standard library import error: {e}")
    
    # Test third-party dependencies
    try:
        import pyiceberg
        print("✓ PyIceberg imported successfully")
    except ImportError as e:
        errors.append(f"PyIceberg import error: {e}")
        print(f"✗ PyIceberg import error: {e}")
    
    try:
        import pyarrow
        print("✓ PyArrow imported successfully")
    except ImportError as e:
        errors.append(f"PyArrow import error: {e}")
        print(f"✗ PyArrow import error: {e}")
    
    try:
        import boto3
        print("✓ boto3 imported successfully")
    except ImportError as e:
        errors.append(f"boto3 import error: {e}")
        print(f"✗ boto3 import error: {e}")
    
    # Test project modules
    try:
        import utils
        print("✓ utils module imported successfully")
    except ImportError as e:
        errors.append(f"utils import error: {e}")
        print(f"✗ utils import error: {e}")
    
    try:
        import metadata_schema
        print("✓ metadata_schema module imported successfully")
    except ImportError as e:
        errors.append(f"metadata_schema import error: {e}")
        print(f"✗ metadata_schema import error: {e}")
    
    # Test schema modules
    for i in range(1, 5):
        try:
            module = __import__(f'schema_{i}')
            print(f"✓ schema_{i} module imported successfully")
        except ImportError as e:
            errors.append(f"schema_{i} import error: {e}")
            print(f"✗ schema_{i} import error: {e}")
    
    # Test loader modules
    for i in range(1, 5):
        try:
            module = __import__(f'load_vcf_schema{i}')
            print(f"✓ load_vcf_schema{i} module imported successfully")
        except ImportError as e:
            errors.append(f"load_vcf_schema{i} import error: {e}")
            print(f"✗ load_vcf_schema{i} import error: {e}")
    
    print()
    if errors:
        print(f"FAILED: {len(errors)} import error(s) found")
        for error in errors:
            print(f"  - {error}")
        return 1
    else:
        print("SUCCESS: All modules imported successfully!")
        return 0

if __name__ == '__main__':
    sys.exit(test_imports())
