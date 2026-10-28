"""
Vercel Serverless Entrypoint for FastAPI Application.
Imports the configured FastAPI app from src.mock_cms.
"""

import sys
from pathlib import Path

# Add project root to sys.path so modules in src can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mock_cms import app
