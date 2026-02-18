import os
import unittest
from unittest.mock import patch

from app.services.avatar_provider import AvatarProviderService


class AvatarProviderServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AvatarProviderService()

    @patch.dict(os.environ, {}, clear=True)
    def test_default_config_uses_browser_tts(self) -> None:
        config = self.service.get_config()
        self.assertFalse(config.enabled)
        self.assertEqual(config.provider, "browser")
        self.assertEqual(config.mode, "browser_tts")

    @patch.dict(
        os.environ,
        {
            "IIA_AVATAR_MODE": "provider",
            "IIA_AVATAR_PROVIDER": "did",
        },
        clear=True,
    )
    def test_provider_mode_without_key_falls_back(self) -> None:
        config = self.service.get_config()
        self.assertFalse(config.enabled)
        self.assertIn("IIA_AVATAR_API_KEY", config.message)

    @patch.dict(os.environ, {}, clear=True)
    def test_synthesize_falls_back_to_browser(self) -> None:
        result = self.service.synthesize_avatar_prompt(text="Hello candidate.")
        self.assertEqual(result["mode"], "browser_tts")
        self.assertEqual(result["provider"], "browser")
        self.assertEqual(result["text"], "Hello candidate.")

    @patch.dict(
        os.environ,
        {
            "IIA_AVATAR_MODE": "virtual3d",
        },
        clear=True,
    )
    def test_virtual3d_without_openai_key_falls_back(self) -> None:
        config = self.service.get_config()
        self.assertFalse(config.enabled)
        self.assertEqual(config.provider, "browser")
        self.assertIn("OPENAI_API_KEY", config.message)

    @patch.dict(
        os.environ,
        {
            "IIA_AVATAR_MODE": "virtual3d",
            "OPENAI_API_KEY": "test-key",
        },
        clear=True,
    )
    def test_virtual3d_with_openai_key_is_enabled(self) -> None:
        config = self.service.get_config()
        self.assertTrue(config.enabled)
        self.assertEqual(config.provider, "virtual3d")
        self.assertEqual(config.mode, "virtual_human_3d")

    @patch.dict(os.environ, {}, clear=True)
    def test_status_fallback_when_provider_disabled(self) -> None:
        result = self.service.get_render_status(request_id="req-1", provider="did")
        self.assertEqual(result["status"], "fallback")
        self.assertFalse(result["isReady"])

if __name__ == "__main__":
    unittest.main()
