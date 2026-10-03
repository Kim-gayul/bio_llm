"""Search PMC and download CC BY 4.0 full text through the official OAI-PMH API."""
import argparse
import os
import time
from xml.etree import ElementTree as ET

import requests
from Bio import Entrez

from .config import ROOT
from .papers import normalize_pmcid

OAI_ENDPOINT = "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
CC_BY_4 = "creativecommons.org/licenses/by/4.0/"


def configure_entrez():
    email = os.getenv("NCBI_EMAIL", "")
    if not email or "@" not in email:
        raise ValueError("Set your NCBI_EMAIL in .env before collecting papers.")
    Entrez.email = email
    Entrez.tool = "BioLabResearchAssistant"
    Entrez.api_key = os.getenv("NCBI_API_KEY") or None
    Entrez.max_tries = 3
    Entrez.sleep_between_tries = 5
    return email


def search_pmc_papers(query, max_results=15):
    configure_entrez()
    with Entrez.esearch(db="pmc", term=f"({query}) AND open access[filter]", retmax=max_results) as handle:
        return Entrez.read(handle)["IdList"]


def reusable_article(xml):
    root = ET.fromstring(xml)
    if any(node.tag.rsplit("}", 1)[-1] == "error" for node in root.iter()):
        return None
    article = next((node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "article"), None)
    if article is None:
        return None
    permissions = next((node for node in article.iter() if node.tag.rsplit("}", 1)[-1] == "permissions"), None)
    if permissions is None:
        return None
    license_urls = [
        value for node in permissions.iter()
        for key, value in node.attrib.items()
        if key.rsplit("}", 1)[-1] in {"href", "license_ref"}
    ]
    license_urls += [
        (node.text or "").strip() for node in permissions.iter()
        if node.tag.rsplit("}", 1)[-1] == "license_ref"
    ]
    if not any(CC_BY_4 in value.lower() and "/by-nc/" not in value.lower() and "/by-nc-nd/" not in value.lower() for value in license_urls):
        return None
    return ET.tostring(article, encoding="utf-8")


def fetch_pmc_xml(pmcid, email=None):
    email = email or configure_entrez()
    numeric_id = normalize_pmcid(pmcid).removeprefix("PMC")
    with requests.Session() as client:
        response = client.get(
            OAI_ENDPOINT,
            params={"verb": "GetRecord", "identifier": f"oai:pubmedcentral.nih.gov:{numeric_id}", "metadataPrefix": "pmc"},
            headers={"Accept-Encoding": "gzip, deflate", "User-Agent": f"BioLabResearchAssistant/1.0 ({email})"},
            timeout=45,
        )
        response.raise_for_status()
        return reusable_article(response.content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="molecular biology transfection")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")
    email = configure_entrez()
    output = ROOT / "pmc_xml_data"
    output.mkdir(exist_ok=True)
    saved = 0
    for pmcid in search_pmc_papers(args.query, args.limit):
        path = output / f"{normalize_pmcid(pmcid).removeprefix('PMC')}.xml"
        if path.exists():
            continue
        try:
            content = fetch_pmc_xml(pmcid, email)
        except requests.RequestException as exc:
            print(f"Skipped {pmcid}: PMC OAI-PMH unavailable ({exc.__class__.__name__})")
            continue
        if content:
            path.write_bytes(content)
            saved += 1
            print(f"Saved {path.name} (CC BY 4.0)")
        else:
            print(f"Skipped {pmcid}: full text unavailable or not CC BY 4.0")
        time.sleep(0.35)  # PMC OAI-PMH limit: at most three requests per second.
    print(f"Saved {saved} articles to {output}")


if __name__ == "__main__":
    main()
