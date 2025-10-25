#!/usr/bin/env python3
"""
GeoLint Web Application Launcher

This script launches the GeoLint Streamlit web application.
"""

import sys
import subprocess
from pathlib import Path


def main():
    """Launch the GeoLint web application."""
    # Get the path to the Streamlit app
    app_path = Path(__file__).parent / "geolint" / "web" / "app.py"
    
    if not app_path.exists():
        print(f"Error: Streamlit app not found at {app_path}")
        print("Please ensure you're running this from the GeoLint project root directory.")
        sys.exit(1)
    
    # Launch Streamlit
    try:
        print("Starting GeoLint Web Application...")
        print("Open your browser to http://localhost:8501")
        print("Press Ctrl+C to stop the application")
        print("-" * 50)
        
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", str(app_path),
            "--server.port", "8501",
            "--server.address", "localhost",
            "--browser.gatherUsageStats", "false"
        ])
        
    except KeyboardInterrupt:
        print("\nGeoLint application stopped.")
    except Exception as e:
        print(f"Error starting GeoLint: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
