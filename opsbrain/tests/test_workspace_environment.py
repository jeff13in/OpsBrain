"""Offline setup checks use synthetic values and require no application imports."""

import unittest

from scripts.check_workspace_environment import check_environment, origin_is_valid


class WorkspaceEnvironmentTests(unittest.TestCase):
    def settings(self, **overrides):
        values = {
            "APP_ENV": "staging",
            "APP_ORIGIN": "https://app.example.test",
            "SUPABASE_URL": "https://provider.example.test",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_synthetic",
        }
        values.update(overrides)
        return values

    def test_valid_environment_shape(self):
        self.assertEqual(check_environment(self.settings()), [])

    def test_missing_settings_fail(self):
        self.assertEqual(len(check_environment({})), 4)

    def test_loopback_http_requires_development(self):
        for stage in ("staging", "production"):
            self.assertTrue(check_environment(self.settings(APP_ENV=stage, APP_ORIGIN="http://localhost:8000")))
        self.assertEqual(check_environment(self.settings(APP_ENV="development", APP_ORIGIN="http://localhost:8000", SUPABASE_URL="http://127.0.0.1:54321")), [])
        self.assertFalse(origin_is_valid("http://example.test", local_allowed=True))

    def test_reject_credentials_paths_and_malformed_origins(self):
        for value in (
            "https://secret@example.test", "https://example.test/auth/callback",
            "https://example.test?token=secret", "https://example.test#fragment",
            "https://example.test:invalid", "https://example.test:0",
            "https://example.test:99999", "https://[invalid", "https://exam ple.test",
            "https://example.test\\path", "https://localhost",
        ):
            with self.subTest(value=value):
                self.assertFalse(origin_is_valid(value))

    def test_administrative_key_rejected_without_disclosure(self):
        secret = "sb_secret_do_not_print_this"
        errors = check_environment(self.settings(SUPABASE_PUBLISHABLE_KEY=secret))
        self.assertTrue(errors)
        self.assertNotIn(secret, " ".join(errors))

    def test_unknown_stage_cannot_enable_local_http(self):
        self.assertTrue(check_environment(self.settings(APP_ENV="test", APP_ORIGIN="http://localhost")))


if __name__ == "__main__":
    unittest.main()
