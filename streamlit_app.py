"""Entry point for Streamlit Cloud deployment.

Streamlit Cloud auto-detects streamlit_app.py at the repository root.
This file simply delegates to the main web UI module.
"""

import sys
from pathlib import Path

# Ensure the src directory is on the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from testcode.web_ui import main

if __name__ == "__main__":
    main()
