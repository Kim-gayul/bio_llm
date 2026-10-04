import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import Client, TestCase, SimpleTestCase
from biolab.papers import load_papers, normalize_pmcid
from .models import Message
from .views import generation_lock

SOURCE = {"pmcid": "PMC123", "title": "Example methods", "text": "Evidence text", "chunk_id": "PMC123_ch000", "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/", "distance": 0.1}


class APITests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").json()["csrfToken"]
        response = self.post("/api/conversations/", {})
        self.assertEqual(response.status_code, 201)
        self.id = response.json()["id"]
        self.url = f"/api/conversations/{self.id}/messages/"

    def post(self, url, data):
        return self.client.post(url, json.dumps(data), content_type="application/json", HTTP_X_CSRFTOKEN=self.token)

    def packets(self, response):
        return [json.loads(line) for line in b"".join(response.streaming_content).decode().splitlines()]

    def test_csrf_and_session_isolation(self):
        self.assertEqual(self.client.post(self.url, "{}", content_type="application/json").status_code, 403)
        other = Client()
        other.get("/api/session/")
        self.assertEqual(other.get(f"/api/conversations/{self.id}/").status_code, 404)

    def test_invalid_inputs(self):
        for data in [{"question": " "}, {"question": []}, {"question": "a" * 4001}, {"question": "q", "top_k": True}, {"question": "q", "top_k": 7}, {"question": "q", "pmcid": "../secret"}]:
            self.assertEqual(self.post(self.url, data).status_code, 400)
        self.assertEqual(Message.objects.count(), 0)

    @patch("research.views.rag.answer", return_value=iter(["조건 설명 ", "[PMC123]"]))
    @patch("research.views.rag.retrieve", return_value=[SOURCE])
    def test_stream_persists_sources_and_supplies_history(self, retrieve, answer):
        response = self.post(self.url, {"question": "실험 조건?", "top_k": 3})
        packets = self.packets(response)
        self.assertEqual([p["type"] for p in packets], ["status", "sources", "token", "token", "done"])
        saved = Message.objects.get(role="assistant")
        self.assertEqual(saved.status, "complete")
        self.assertEqual(saved.content, "조건 설명 [PMC123]")
        self.assertEqual(saved.sources, [SOURCE])
        answer.return_value = iter(["후속 답변 [PMC123]"])
        self.packets(self.post(self.url, {"question": "그 이유는?"}))
        history = retrieve.call_args.args[1]
        self.assertEqual([m["role"] for m in history], ["user", "assistant"])

    @patch("research.views.rag.retrieve", side_effect=RuntimeError("private internal path"))
    def test_failure_is_saved_and_lock_released(self, retrieve):
        packets = self.packets(self.post(self.url, {"question": "question"}))
        self.assertEqual(packets[-1]["type"], "error")
        self.assertNotIn("private internal path", packets[-1]["message"])
        self.assertEqual(Message.objects.get(role="assistant").status, "failed")
        self.assertFalse(generation_lock.locked())

    @patch("research.views.rag.answer", return_value=iter(["Invented citation [PMC999]"]))
    @patch("research.views.rag.retrieve", return_value=[SOURCE])
    def test_unknown_citation_is_flagged(self, retrieve, answer):
        packets = self.packets(self.post(self.url, {"question": "question"}))
        self.assertTrue(packets[-1]["warnings"])
        saved = self.client.get(f"/api/conversations/{self.id}/").json()["messages"][-1]
        self.assertEqual(saved["warnings"], packets[-1]["warnings"])

    @patch("research.views.rag.answer", return_value=iter(["partial", " continuation"]))
    @patch("research.views.rag.retrieve", return_value=[SOURCE])
    def test_disconnected_stream_records_failure_and_releases_lock(self, retrieve, answer):
        response = self.post(self.url, {"question": "question"})
        iterator = iter(response.streaming_content)
        next(iterator)  # Status has been sent; generation has started.
        next(iterator)  # Sources
        next(iterator)  # First token
        response.close()
        self.assertFalse(generation_lock.locked())
        message = Message.objects.get(role="assistant")
        self.assertEqual(message.status, "failed")
        self.assertEqual(message.content, "partial")

    @patch("research.views.rag.retrieve", return_value=[])
    def test_empty_context_does_not_call_model(self, retrieve):
        with patch("biolab.rag.generate") as llm:
            packets = self.packets(self.post(self.url, {"question": "question"}))
        llm.assert_not_called()
        self.assertIn("찾을 수 없습니다", packets[2]["text"])

    def test_concurrent_request_is_rejected(self):
        generation_lock.acquire()
        try:
            self.assertEqual(self.post(self.url, {"question": "q"}).status_code, 409)
        finally:
            generation_lock.release()
        self.assertEqual(Message.objects.count(), 0)

    def test_delete_is_scoped(self):
        url = f"/api/conversations/{self.id}/"
        self.assertEqual(self.client.delete(url, HTTP_X_CSRFTOKEN=self.token).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 404)


class PipelineTests(SimpleTestCase):
    def test_collector_only_accepts_explicit_cc_by_full_text(self):
        from biolab.collect import reusable_article

        def record(url):
            return ("<OAI-PMH><GetRecord><record><metadata><article><front><article-meta>"
                    f"<permissions><license><ext-link href='{url}'/></license></permissions>"
                    "</article-meta></front><body><sec><p>Methods</p></sec></body>"
                    "</article></metadata></record></GetRecord></OAI-PMH>").encode()

        self.assertIn(b"<article>", reusable_article(record("https://creativecommons.org/licenses/by/4.0/")))
        self.assertIsNone(reusable_article(record("https://creativecommons.org/licenses/by-nc-nd/4.0/")))
        self.assertIsNone(reusable_article(record("https://example.org/unknown")))

    def test_legacy_pmcids_are_normalized(self):
        self.assertEqual(normalize_pmcid("123"), "PMC123")
        self.assertEqual(normalize_pmcid("PMC123"), "PMC123")
        with self.assertRaises(ValueError):
            normalize_pmcid("../../etc")
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "old.json").write_text(json.dumps({"pmcid": "123", "title": "old", "methods_chunks": []}))
            self.assertEqual(load_papers(Path(directory))[0]["pmcid"], "PMC123")

    def test_preprocessing_filters_and_deduplicates(self):
        from biolab.preprocess import parse_and_chunk_pmc_xml
        paragraph = "A measured experimental condition with cell culture observations. " * 20
        xml = f'<article article-type="research-article"><front><article-id pub-id-type="pmc">123</article-id><article-title>Title</article-title></front><body><sec><title>Materials and Methods</title><sec><title>Methods detail</title><p>{paragraph}</p></sec></sec></body></article>'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "123.xml")
            path.write_text(xml)
            paper = parse_and_chunk_pmc_xml(path)
            self.assertEqual(paper["pmcid"], "PMC123")
            self.assertEqual(paper["raw_methods_full"], paragraph.strip())
            self.assertTrue(all(c["char_length"] <= 1000 for c in paper["methods_chunks"]))
            self.assertTrue(paper["methods_chunks"][0]["chunk_id"].startswith("PMC123_ch"))
            path.write_text(xml.replace('article-type="research-article"', 'article-type="review-article"'))
            self.assertIsNone(parse_and_chunk_pmc_xml(path))
            path.write_text(xml.replace(paragraph, "short"))
            self.assertIsNone(parse_and_chunk_pmc_xml(path))
