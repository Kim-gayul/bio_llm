"""Extract Methods with ``python -m biolab.preprocess`` (1000/150 chunking)."""
import json
from pathlib import Path
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from biolab.config import ROOT, PROCESSED_PATH
from biolab.papers import normalize_pmcid


def parse_and_chunk_pmc_xml(file_path):
    path = Path(file_path)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml-xml")
    article = soup.find("article")
    if article is None:
        return None
    kind = article.get("article-type", "").lower()
    if any(value in kind for value in ("review", "letter", "editorial", "commentary")):
        return None
    paragraphs = []
    body = article.find("body")
    if body is None:
        return None
    for sec in body.find_all("sec"):
        title = sec.find("title", recursive=False)
        label = (sec.get("sec-type", "") + " " + (title.get_text(" ", strip=True) if title else "")).lower()
        if "method" in label or "material" in label:
            paragraphs.extend(p.get_text(" ", strip=True) for p in sec.find_all("p"))
    methods = "\n\n".join(dict.fromkeys(paragraphs))
    if len(methods) < 500:
        return None
    pmc_tag = article.find("article-id", attrs={"pub-id-type": "pmc"})
    if pmc_tag is None:
        pmc_tag = article.find("article-id", attrs={"pub-id-type": "pmcid"})
    pmcid = normalize_pmcid(pmc_tag.get_text(strip=True) if pmc_tag else path.stem)
    title_tag, abstract_tag = article.find("article-title"), article.find("abstract")
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150, separators=["\n\n", "\n", ". ", " ", ""])
    return {"pmcid": pmcid,
        "title": title_tag.get_text(" ", strip=True) if title_tag else pmcid,
        "abstract": abstract_tag.get_text(" ", strip=True) if abstract_tag else "",
        "raw_methods_full": methods,
        "methods_chunks": [{"chunk_id": f"{pmcid}_ch{i:03d}", "text": text, "char_length": len(text)}
            for i, text in enumerate(splitter.split_text(methods))]}


def main():
    PROCESSED_PATH.mkdir(exist_ok=True)
    count = 0
    for path in sorted((ROOT / "pmc_xml_data").glob("*.xml")):
        paper = parse_and_chunk_pmc_xml(path)
        if paper:
            target = PROCESSED_PATH / f"{paper['pmcid'].removeprefix('PMC')}_processed.json"
            target.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")
            count += 1
    print(f"Processed {count} papers into {PROCESSED_PATH}")


if __name__ == "__main__":
    main()
