"""
Web Application & Mock CMS Server Launcher.
Runs the FastAPI web dashboard on http://127.0.0.1:8000.
"""

import sys
import uvicorn
from rich.console import Console

console = Console()

if __name__ == "__main__":
    port = 8000
    host = "127.0.0.1"

    print("\n" + "=" * 70)
    print("   AI AGENT INTAKE & DOWNSTREAM CMS WEB DASHBOARD")
    print("=" * 70)
    print(f" -> Web Dashboard URL:     http://{host}:{port}")
    print(f" -> Interactive API Docs:  http://{host}:{port}/docs")
    print(f" -> Alternative ReDoc:     http://{host}:{port}/redoc")
    print("=" * 70 + "\n")

    uvicorn.run("src.mock_cms:app", host=host, port=port, reload=False, log_level="info")
