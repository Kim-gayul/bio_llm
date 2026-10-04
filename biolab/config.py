import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-astra").strip() or "gpt-6-astra"
OPENAI_QUERY_MODEL = os.getenv("OPENAI_QUERY_MODEL", "gpt-6-luna").strip() or "gpt-6-luna"
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "low").strip()
OPENAI_QUERY_REASONING_EFFORT = os.getenv("OPENAI_QUERY_REASONING_EFFORT", "none").strip()
OPENAI_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "4096"))
OPENAI_QUERY_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_QUERY_MAX_OUTPUT_TOKENS", "512"))
if min(OPENAI_MAX_OUTPUT_TOKENS, OPENAI_QUERY_MAX_OUTPUT_TOKENS) < 1:
    raise ValueError("OpenAI output token limits must be positive.")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
CHROMA_PATH = ROOT / os.getenv("CHROMA_PATH", "chroma_db_v4")
COLLECTION = os.getenv("CHROMA_COLLECTION", "biolab_methods_v4")
PROCESSED_PATH = ROOT / "pmc_processed_data"
