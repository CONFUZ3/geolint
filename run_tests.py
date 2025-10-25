#!/usr/bin/env python3
"""
GeoLint Test Runner

This script runs the complete test suite for GeoLint.
"""

import sys
import subprocess
from pathlib import Path


def main():
    """Run the GeoLint test suite."""
    print("Running GeoLint Test Suite...")
    print("=" * 50)
    
    # Check if pytest is available
    try:
        import pytest
    except ImportError:
        print("pytest not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pytest", "pytest-cov"])
    
    # Run tests
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest",
            "tests/",
            "-v",
            "--cov=geolint",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--tb=short"
        ])
        
        if result.returncode == 0:
            print("\nAll tests passed!")
            print("Coverage report generated in htmlcov/")
        else:
            print("\nSome tests failed.")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error running tests: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
