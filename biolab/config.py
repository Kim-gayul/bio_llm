import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def local_ollama_url():
    url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("OLLAMA_BASE_URL must be a local HTTP address.")
    return url


OLLAMA_URL = local_ollama_url()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "lancard/korean-yanolja-eeve")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
CHROMA_PATH = ROOT / os.getenv("CHROMA_PATH", "chroma_db_v2")
COLLECTION = os.getenv("CHROMA_COLLECTION", "biolab_methods_v2")
PROCESSED_PATH = ROOT / "pmc_processed_data"
