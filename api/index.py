"""Vercel serverless entrypoint — mounts the FastAPI app.

Repo layout expected by Vercel (this file's parent dir = repo root):
  api/index.py      <- this file
  app/…             <- the FastAPI package
  requirements.txt
  vercel.json
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402,F401  (ASGI app picked up by @vercel/python)
