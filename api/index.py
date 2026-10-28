"""
Vercel Serverless Entrypoint for FastAPI Application.
Imports the configured FastAPI app from src.mock_cms and applies
an ASGI Path Normalizer to handle Vercel serverless routing quirks.
"""

import sys
from pathlib import Path

# Add project root to sys.path so modules in src can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.mock_cms import app as fastapi_app


class VercelPathNormalizerMiddleware:
    """
    Normalizes ASGI request paths on Vercel.
    Vercel rewrites / to /api/index.py or /api/index, which causes FastAPI
    to return 404 {"detail": "Not Found"}.
    This middleware restores the intended path before FastAPI's router executes.
    """
    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            headers = dict(scope.get("headers", []))
            
            # Check for Vercel matched path in headers
            matched_path = None
            for h in (b"x-matched-path", b"x-forwarded-uri", b"x-vercel-matched-path", b"x-real-path"):
                if h in headers:
                    try:
                        val = headers[h].decode("utf-8")
                        if val and val not in ("/api/index.py", "/api/index"):
                            matched_path = val
                            break
                    except Exception:
                        pass

            if matched_path:
                scope["path"] = matched_path
            elif path in ("/api/index.py", "/api/index", "/api/index/", "/api", "/api/"):
                scope["path"] = "/"
            elif path.startswith("/api/index.py/"):
                scope["path"] = path[len("/api/index.py"):]
            elif path.startswith("/api/index/"):
                scope["path"] = path[len("/api/index"):]

        await self.asgi_app(scope, receive, send)


# Wrap FastAPI app with path normalizer for Vercel
app = VercelPathNormalizerMiddleware(fastapi_app)
