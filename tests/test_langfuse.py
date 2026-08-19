import json
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from app.adapters.langfuse.prompts import LangfusePromptProvider, LocalPromptProvider
from app.adapters.langfuse.prompts import build_prompt_provider


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


class LangfusePromptTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "prompt.md"
        self.path.write_text("local prompt", encoding="utf-8")
        self.local = LocalPromptProvider(self.path)

    def tearDown(self):
        self.directory.cleanup()

    @patch("app.adapters.langfuse.prompts.urllib.request.urlopen")
    def test_fetches_remote_prompt_and_version(self, urlopen):
        urlopen.return_value = FakeResponse({"prompt": [
            {"role": "system", "content": "remote rules"},
            {"role": "user", "content": "analyze {{content_json}}"},
        ], "version": 7})
        provider = LangfusePromptProvider(self.local, "https://langfuse.test", "pk", "sk", "filter", cache_seconds=60)
        messages, version = provider.get_prompt()
        self.assertEqual(version, "langfuse:7")
        self.assertEqual(messages[0], {"role": "system", "content": "remote rules"})
        self.assertEqual(messages[1], {"role": "user", "content": "analyze {{content_json}}"})
        request = urlopen.call_args.args[0]
        self.assertIn("/api/public/v2/prompts/filter?label=production", request.full_url)

    @patch("app.adapters.langfuse.prompts.urllib.request.urlopen", side_effect=OSError("offline"))
    def test_falls_back_to_local_prompt_when_remote_unavailable(self, urlopen):
        provider = LangfusePromptProvider(self.local, "https://langfuse.test", "pk", "sk", "filter")
        messages, version = provider.get_prompt()
        self.assertEqual(version, "local-v2")
        self.assertEqual(messages[0], {"role": "system", "content": "local prompt"})
        self.assertIn("{{content_json}}", messages[1]["content"])

    @patch.dict(os.environ, {
        "LANGFUSE_ENABLED": "true",
        "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
        "LANGFUSE_SECRET_KEY": "sk-lf-test",
        "LANGFUSE_BASE_URL": "https://self-hosted.example",
        "LANGFUSE_HOST": "https://cloud.langfuse.com",
    }, clear=False)
    def test_self_hosted_base_url_takes_precedence(self):
        provider = build_prompt_provider()
        self.assertEqual(provider.host, "https://self-hosted.example")


if __name__ == "__main__":
    unittest.main()
