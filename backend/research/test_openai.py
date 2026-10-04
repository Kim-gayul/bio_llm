from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import os
from pathlib import Path
import runpy
import tempfile

from django.test import SimpleTestCase
from biolab import rag


class OpenAIGenerationTests(SimpleTestCase):
    def test_project_env_loads_key_and_model_independent_of_cwd(self):
        from biolab import config
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            module = root / "biolab" / "config.py"
            module.parent.mkdir()
            module.write_text(Path(config.__file__).read_text(encoding="utf-8"), encoding="utf-8")
            (root / ".env").write_text("OPENAI_API_KEY=test-key\nOPENAI_MODEL=gpt-6-astra\n", encoding="utf-8")
            values = runpy.run_path(str(module))
            self.assertEqual(values["OPENAI_API_KEY"], "test-key")
            self.assertEqual(values["OPENAI_MODEL"], "gpt-6-astra")
            os.environ["OPENAI_MODEL"] = "environment-override"
            self.assertEqual(runpy.run_path(str(module))["OPENAI_MODEL"], "environment-override")

    def test_missing_key_fails_before_network(self):
        with patch.object(rag, "OPENAI_API_KEY", ""), patch.object(rag, "OpenAI") as sdk:
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                list(rag.generate([{"role": "user", "content": "question"}]))
            sdk.assert_not_called()

    def test_nonstream_passes_model_and_messages(self):
        messages = [{"role": "system", "content": "instruction"}, {"role": "user", "content": "question"}]
        with patch.object(rag, "OPENAI_API_KEY", "test-key"), patch.object(rag, "OPENAI_MODEL", "gpt-6-astra"), patch.object(rag, "OpenAI") as sdk:
            client = sdk.return_value.__enter__.return_value
            client.responses.create.return_value = SimpleNamespace(status="completed", output_text="English query")
            self.assertEqual(list(rag.generate(messages)), ["English query"])
            kwargs = client.responses.create.call_args.kwargs
            self.assertEqual(kwargs["model"], "gpt-6-astra")
            self.assertEqual(kwargs["input"], messages)
            self.assertFalse(kwargs["store"])
            self.assertEqual(kwargs["reasoning"], {"effort": rag.OPENAI_REASONING_EFFORT})
            self.assertEqual(kwargs["max_output_tokens"], rag.OPENAI_MAX_OUTPUT_TOKENS)
            self.assertNotIn("temperature", kwargs)
            sdk.return_value.__exit__.assert_called_once()

    def stream_result(self, events):
        stream = MagicMock()
        stream.__iter__.return_value = iter(events)
        return stream

    def test_stream_yields_only_text_and_closes_resources(self):
        packets = [SimpleNamespace(type="response.created"),
                   SimpleNamespace(type="response.output_text.delta", delta="Hello"),
                   SimpleNamespace(type="response.output_text.delta", delta=" world"),
                   SimpleNamespace(type="response.completed")]
        with patch.object(rag, "OPENAI_API_KEY", "test-key"), patch.object(rag, "OpenAI") as sdk:
            stream = self.stream_result(packets)
            sdk.return_value.__enter__.return_value.responses.create.return_value = stream
            self.assertEqual(list(rag.generate([], stream=True)), ["Hello", " world"])
            stream.__exit__.assert_called_once()
            sdk.return_value.__exit__.assert_called_once()

    def test_incomplete_failed_empty_and_interrupted_streams_raise(self):
        for ending in [None, "response.failed", "response.incomplete", "error", "response.completed"]:
            with self.subTest(ending=ending), patch.object(rag, "OPENAI_API_KEY", "test-key"), patch.object(rag, "OpenAI") as sdk:
                events = [] if ending is None else [SimpleNamespace(type=ending)]
                stream = self.stream_result(events)
                sdk.return_value.__enter__.return_value.responses.create.return_value = stream
                with self.assertRaises(RuntimeError):
                    list(rag.generate([], stream=True))
                stream.__exit__.assert_called_once()

    def test_nonstream_incomplete_output_is_not_accepted(self):
        with patch.object(rag, "OPENAI_API_KEY", "test-key"), patch.object(rag, "OpenAI") as sdk:
            sdk.return_value.__enter__.return_value.responses.create.return_value = SimpleNamespace(status="incomplete", output_text="partial")
            with self.assertRaises(RuntimeError):
                list(rag.generate([]))

    def test_cancelled_generator_closes_client_and_stream(self):
        with patch.object(rag, "OPENAI_API_KEY", "test-key"), patch.object(rag, "OpenAI") as sdk:
            stream = self.stream_result([SimpleNamespace(type="response.output_text.delta", delta="part")])
            sdk.return_value.__enter__.return_value.responses.create.return_value = stream
            generator = rag.generate([], stream=True)
            self.assertEqual(next(generator), "part")
            generator.close()
            stream.__exit__.assert_called_once()
            sdk.return_value.__exit__.assert_called_once()

    def test_health_exposes_configuration_not_credentials(self):
        with patch("research.views.OPENAI_API_KEY", "private-test-key"), patch("research.views.rag.collection") as collection, patch.object(rag, "OpenAI") as sdk:
            collection.return_value.count.return_value = 3
            response = self.client.get("/api/health/")
            self.assertTrue(response.json()["openai_configured"])
            self.assertTrue(response.json()["index"])
            self.assertNotIn("private-test-key", response.content.decode())
            sdk.assert_not_called()


class LatencyTests(SimpleTestCase):
    def setUp(self):
        rag.rewrite_query.cache_clear()
        rag.query_vector.cache_clear()

    def tearDown(self):
        rag.rewrite_query.cache_clear()
        rag.query_vector.cache_clear()

    def test_query_uses_separate_model_and_token_budget(self):
        with patch.object(rag, "OPENAI_API_KEY", "test-key"), patch.object(rag, "OpenAI") as sdk:
            client = sdk.return_value.__enter__.return_value
            client.responses.create.return_value = SimpleNamespace(status="completed", output_text="query")
            self.assertEqual(list(rag.generate([], purpose="query")), ["query"])
            params = client.responses.create.call_args.kwargs
            self.assertEqual(params["model"], rag.OPENAI_QUERY_MODEL)
            self.assertEqual(params["reasoning"], {"effort": rag.OPENAI_QUERY_REASONING_EFFORT})
            self.assertEqual(params["max_output_tokens"], rag.OPENAI_QUERY_MAX_OUTPUT_TOKENS)

    def test_standalone_english_skips_model_but_followup_does_not(self):
        with patch.object(rag, "generate", side_effect=lambda *a, **k: (v for v in ["rewritten query"])) as generate:
            self.assertEqual(rag.rewrite_query("Explain this study", ()), "Explain this study")
            generate.assert_not_called()
            rag.rewrite_query("Why?", (("user", "Previous question"),))
            generate.assert_called_once()

    def test_query_cache_includes_history(self):
        with patch.object(rag, "generate", side_effect=lambda *a, **k: (v for v in ["study question"])) as generate:
            first_history = (("user", "paper one"),)
            second_history = (("user", "paper two"),)
            rag.rewrite_query("그 이유는?", first_history)
            rag.rewrite_query("그 이유는?", first_history)
            self.assertEqual(generate.call_count, 1)
            rag.rewrite_query("그 이유는?", second_history)
            self.assertEqual(generate.call_count, 2)

    def test_failed_rewrite_is_not_cached(self):
        with patch.object(rag, "generate", side_effect=RuntimeError("failed")) as generate:
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    rag.rewrite_query("검색 질문", ())
            self.assertEqual(generate.call_count, 2)

    def test_repeat_search_reuses_embedding_but_reads_current_index(self):
        with patch.object(rag, "encoder") as encoder, patch.object(rag, "collection") as collection:
            encoder.return_value.encode.return_value.tolist.return_value = [[0.1, 0.2]]
            target = collection.return_value
            target.count.return_value = 2
            target.query.return_value = {"ids": [[]], "metadatas": [[]], "documents": [[]], "distances": [[]]}
            timings = {}
            rag.retrieve("English query", [], pmcid="PMC123", timings=timings)
            rag.retrieve("English query", [], pmcid="PMC456")
            self.assertEqual(encoder.return_value.encode.call_count, 1)
            self.assertEqual(target.query.call_count, 2)
            self.assertEqual(target.query.call_args.kwargs["where"], {"pmcid": "PMC456"})
            self.assertTrue({"query_rewrite_ms", "embedding_wait_ms", "vector_search_ms"} <= timings.keys())

    def test_warmup_overlaps_rewrite(self):
        from threading import Event
        warmed = Event()
        fake_encoder = MagicMock()
        fake_encoder.encode.return_value.tolist.return_value = [[0.1, 0.2]]

        def warm():
            warmed.set()
            return fake_encoder

        def rewrite(*args):
            self.assertTrue(warmed.wait(timeout=2), "Encoder was not started before query rewrite")
            return "query"

        with patch.object(rag, "encoder", side_effect=warm), patch.object(rag, "rewrite_query", side_effect=rewrite), patch.object(rag, "collection") as collection:
            collection.return_value.count.return_value = 1
            collection.return_value.query.return_value = {"ids": [[]], "metadatas": [[]], "documents": [[]], "distances": [[]]}
            rag.retrieve("한국어 질문", [])
