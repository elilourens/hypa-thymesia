#!/usr/bin/env python3
"""
Convenience script to run the video query service.
Usage: python run.py
"""
import os
import sys

# Ensure the src directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv

    # Load environment variables
    load_dotenv()

    # Get configuration
    port = int(os.getenv("PORT", "8001"))
    host = os.getenv("HOST", "0.0.0.0")

    print(f"Starting Hypa Thymesia Video Query Service on {host}:{port}")
    print("Reload mode: enabled")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        reload_dirs=[os.path.dirname(os.path.abspath(__file__))],
    )
