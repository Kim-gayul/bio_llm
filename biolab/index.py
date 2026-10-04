"""Build the configured index with ``python -m biolab.index``; preserve the original DB."""
import argparse
from biolab.config import EMBEDDING_MODEL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-model", action="store_true", help="Allow the initial Hugging Face model download")
    args = parser.parse_args()
    if args.download_model:
        from sentence_transformers import SentenceTransformer
        SentenceTransformer(EMBEDDING_MODEL)
    from biolab.rag import index_papers
    print(f"Indexed {index_papers()} chunks")


if __name__ == "__main__":
    main()
