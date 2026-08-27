import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coding_agent.config import DEFAULT_BASE_URL, DEFAULT_MODEL, Config, ConfigError


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cfg-test-"))

    def test_missing_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError):
                Config.from_env(self.tmp)

    def test_env_key_and_defaults(self):
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "sk-env-123"}):
            cfg = Config.from_env(self.tmp)
        self.assertEqual(cfg.api_key, "sk-env-123")
        self.assertEqual(cfg.base_url, DEFAULT_BASE_URL)
        self.assertEqual(cfg.model, DEFAULT_MODEL)

    def test_env_precedence_over_file(self):
        (self.tmp / "config.local.json").write_text(
            '{"api_key": "sk-file", "model": "glm-x"}', encoding="utf-8"
        )
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "sk-env", "ZHIPU_MODEL": "glm-env"}):
            cfg = Config.from_env(self.tmp)
        self.assertEqual(cfg.api_key, "sk-env")
        self.assertEqual(cfg.model, "glm-env")

    def test_file_fallback(self):
        (self.tmp / "config.local.json").write_text(
            '{"api_key": "sk-file", "model": "glm-x", "temperature": 0.5}', encoding="utf-8"
        )
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config.from_env(self.tmp)
        self.assertEqual(cfg.api_key, "sk-file")
        self.assertEqual(cfg.model, "glm-x")
        self.assertEqual(cfg.temperature, 0.5)

    def test_cli_override(self):
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "sk-env"}):
            cfg = Config.from_env(self.tmp, model="glm-cli", max_turns=7)
        self.assertEqual(cfg.model, "glm-cli")
        self.assertEqual(cfg.max_turns, 7)

    def test_repr_masks_key(self):
        cfg = Config(api_key="sk-abcdef123456", workspace=self.tmp)
        text = repr(cfg)
        self.assertNotIn("sk-abcdef123456", text)
        self.assertIn("***", text)

    def test_invalid_values(self):
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "sk-x"}):
            with self.assertRaises(ConfigError):
                Config.from_env(self.tmp, temperature=5)
            with self.assertRaises(ConfigError):
                Config.from_env(self.tmp, max_turns=0)

    def test_base_url_trailing_slash(self):
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "sk-x", "ZHIPU_BASE_URL": "http://x/api/"}):
            cfg = Config.from_env(self.tmp)
        self.assertEqual(cfg.base_url, "http://x/api")


if __name__ == "__main__":
    unittest.main()
