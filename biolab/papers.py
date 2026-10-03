import json
import re

from .config import PROCESSED_PATH


def normalize_pmcid(value):
    value = str(value).upper().removeprefix("PMC")
    if not re.fullmatch(r"\d+", value):
        raise ValueError("Invalid PMCID")
    return "PMC" + value


def load_papers(directory=PROCESSED_PATH):
    papers = {}
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["pmcid"] = normalize_pmcid(data["pmcid"])
        data["url"] = f"https://pmc.ncbi.nlm.nih.gov/articles/{data['pmcid']}/"
        papers[data["pmcid"]] = data
    return list(papers.values())


def paper_summary(paper):
    return {key: paper.get(key, "") for key in ("pmcid", "title", "abstract", "url")} | {
        "chunk_count": len(paper.get("methods_chunks", []))
    }
