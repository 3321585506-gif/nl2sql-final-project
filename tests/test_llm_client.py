import unittest
from unittest.mock import patch

from src.llm_client import LLMClient


class LLMClientTest(unittest.TestCase):
    def test_deepseek_provider_uses_deepseek_key_and_default_base_url(self):
        with patch.dict(
            "os.environ",
            {"DEEPSEEK_API_KEY": "ds-test-key"},
            clear=True,
        ):
            client = LLMClient("deepseek", "deepseek-chat")
            self.assertEqual(client._resolve_openai_base_url(), "https://api.deepseek.com/v1")

        self.assertEqual(client.api_key, "ds-test-key")

    def test_openai_provider_keeps_openai_key_and_no_default_base_url(self):
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "sk-test-key"},
            clear=True,
        ):
            client = LLMClient("openai", "gpt-4o-mini")
            self.assertIsNone(client._resolve_openai_base_url())

        self.assertEqual(client.api_key, "sk-test-key")


if __name__ == "__main__":
    unittest.main()
