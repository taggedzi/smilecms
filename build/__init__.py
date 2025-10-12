"""SmileCMS build package exposing CLI and pipeline interfaces."""
from .ingest import load_documents

__all__ = ["__version__", "load_documents"]
__version__ = "0.1.0"
