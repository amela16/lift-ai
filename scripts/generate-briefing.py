#!/usr/bin/env python3
"""Run with PYTHONPATH=backend and DATABASE_URL / OLLAMA_URL configured.

Use a local Ollama instance and an SSH-forwarded PostgreSQL connection to generate
cached briefings without running model inference on the VPS.
"""
import asyncio
from app.insights import generate_briefing
asyncio.run(generate_briefing())
