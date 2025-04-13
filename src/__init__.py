# src/__init__.py
from flask import Flask
from deepgram import DeepgramClient

# Initialize Flask app
app = Flask(__name__)

# Initialize Deepgram client
try:
    dg_client = DeepgramClient()  # Or your custom initialization
    print("✅ Deepgram client initialized")
except Exception as e:
    print(f"❌ Deepgram init failed: {str(e)}")
    raise

# Make core components importable from package root
from .app import *  # Imports your routes, etc.

# Optional: Add package metadata
__version__ = "0.1.0"
__all__ = ['app', 'dg_client']  # Controls 'from src import *'