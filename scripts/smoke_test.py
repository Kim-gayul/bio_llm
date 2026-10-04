"""Verify the running Next.js -> Django proxy; --live additionally calls the paid OpenAI API."""
import argparse
import json
import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    with requests.Session() as client:
        client.trust_env = False
        response = client.get(base, timeout=10)
        response.raise_for_status()
        assert "BioLab" in response.text
        response = client.get(base + "/api/session/", timeout=10)
        response.raise_for_status()
        client.headers["X-CSRFToken"] = response.json()["csrfToken"]
        client.headers["Origin"] = base
        response = client.get(base + "/api/papers/", timeout=10)
        response.raise_for_status()
        papers = response.json()["papers"]
        assert papers and all(p["pmcid"].startswith("PMC") for p in papers)
        health = client.get(base + "/api/health/", timeout=15).json()
        print(json.dumps({"papers": len(papers), "health": health}, ensure_ascii=False))
        response = client.post(base + "/api/conversations/", json={}, timeout=10)
        response.raise_for_status()
        url = base + "/api/conversations/" + response.json()["id"] + "/"
        try:
            assert client.get(url, timeout=10).json()["messages"] == []
            if args.live:
                assert health["openai_configured"] and health["index"], "Prepare model and index before --live"
                with client.post(url + "messages/", json={"question": "검색된 논문이 다루는 연구 목적과 Methods의 실험 종류만 간단히 설명해 주세요.", "top_k": 2}, stream=True, timeout=(10, 300)) as response:
                    response.raise_for_status()
                    events = [json.loads(line) for line in response.iter_lines() if line]
                assert events[-1]["type"] == "done", events[-1]
                messages = client.get(url, timeout=10).json()["messages"]
                assert len(messages) == 2 and messages[-1]["status"] == "complete"
                assert messages[-1]["content"] and messages[-1]["sources"]
                print(json.dumps({"live_stream": "passed", "tokens": sum(e["type"] == "token" for e in events),
                    "sources": [s["pmcid"] for s in messages[-1]["sources"]],
                    "answer_characters": len(messages[-1]["content"])}, ensure_ascii=False))
        finally:
            response = client.delete(url, timeout=10)
            response.raise_for_status()
        print("Proxy, CSRF, session cookies, library and conversation persistence: passed")


if __name__ == "__main__":
    main()
