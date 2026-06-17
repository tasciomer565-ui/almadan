"""
Sprint 9 — GDPR / KVKK & OpenAPI Konfigürasyonu

Test kapsamı:
  - GDPRService.forget() — tablo silme + anonimleştirme
  - GDPRService.export() — SAR veri paketi
  - audit log yazma (_log_request)
  - Supabase yokken sessiz geçme
  - openapi_config metadata doğrulama
"""
from __future__ import annotations

import unittest
import unittest.mock as mock

import app.gdpr as gdpr_mod
from app.gdpr import GDPRService, GDPRResult, SARResult, gdpr_service


class TestGDPRForget(unittest.TestCase):
    def setUp(self):
        self.svc = GDPRService()
        self.uid = "00000000-0000-0000-0000-000000000001"

    def _mock_delete_ok(self):
        resp = mock.MagicMock()
        resp.ok = True
        resp.status_code = 204
        return resp

    def _mock_delete_fail(self):
        resp = mock.MagicMock()
        resp.ok = False
        resp.status_code = 500
        return resp

    def test_forget_returns_gdpr_result(self):
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", ""):
            result = self.svc.forget(self.uid)
        self.assertIsInstance(result, GDPRResult)
        self.assertEqual(result.user_id, self.uid)

    def test_forget_no_supabase_fails_gracefully(self):
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", ""):
            result = self.svc.forget(self.uid)
        self.assertFalse(result.success)
        self.assertIn("Supabase bağlantısı yok", result.errors)

    def test_forget_all_tables_deleted_on_success(self):
        ok = self._mock_delete_ok()
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", "https://fake.supabase.co"):
            with mock.patch("requests.delete", return_value=ok) as del_mock:
                with mock.patch("requests.patch", return_value=ok):
                    with mock.patch.object(self.svc, "_log_request"):
                        result = self.svc.forget(self.uid)
        # delete tabloları çağrıldı
        self.assertGreater(del_mock.call_count, 0)
        self.assertTrue(result.success)
        self.assertGreater(len(result.deleted_tables), 0)

    def test_forget_partial_failure_recorded_in_errors(self):
        fail = self._mock_delete_fail()
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", "https://fake.supabase.co"):
            with mock.patch("requests.delete", return_value=fail):
                with mock.patch("requests.patch", return_value=fail):
                    with mock.patch.object(self.svc, "_log_request"):
                        result = self.svc.forget(self.uid)
        self.assertFalse(result.success)
        self.assertGreater(len(result.errors), 0)

    def test_forget_to_dict_has_required_keys(self):
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", ""):
            result = self.svc.forget(self.uid)
        d = result.to_dict()
        for key in ("user_id", "success", "anonymized_tables", "deleted_tables",
                    "auth_deleted", "errors", "requested_at"):
            self.assertIn(key, d)

    def test_forget_auth_deletion_attempted(self):
        ok = self._mock_delete_ok()
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", "https://fake.supabase.co"):
            with mock.patch("requests.delete", return_value=ok) as del_mock:
                with mock.patch("requests.patch", return_value=ok):
                    with mock.patch.object(self.svc, "_log_request"):
                        result = self.svc.forget(self.uid)
        # Auth silme çağrısı url'sinde /admin/users/ içermelidir
        calls_urls = [str(c[0][0]) for c in del_mock.call_args_list]
        auth_calls = [u for u in calls_urls if "admin/users" in u]
        self.assertEqual(len(auth_calls), 1)

    def test_anonymize_tables_patched(self):
        ok_resp = mock.MagicMock()
        ok_resp.ok = True
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", "https://fake.supabase.co"):
            with mock.patch("requests.delete", return_value=ok_resp):
                with mock.patch("requests.patch", return_value=ok_resp) as patch_mock:
                    with mock.patch.object(self.svc, "_log_request"):
                        result = self.svc.forget(self.uid)
        # ANONYMIZE_TABLES patch ile güncellendi
        self.assertGreater(patch_mock.call_count, 0)
        self.assertGreater(len(result.anonymized_tables), 0)


class TestGDPRExport(unittest.TestCase):
    def setUp(self):
        self.svc = GDPRService()
        self.uid = "00000000-0000-0000-0000-000000000002"

    def test_export_no_supabase(self):
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", ""):
            result = self.svc.export(self.uid)
        self.assertIsInstance(result, SARResult)
        self.assertIn("error", result.data)

    def test_export_returns_all_tables(self):
        ok = mock.MagicMock()
        ok.ok = True
        ok.json.return_value = []
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", "https://fake.supabase.co"):
            with mock.patch("requests.get", return_value=ok):
                with mock.patch.object(self.svc, "_log_request"):
                    result = self.svc.export(self.uid)
        expected_tables = [
            "user_analytics_events", "user_savings", "user_points",
            "digest_log", "coupon_redemptions", "group_buy_members",
            "vision_analyses", "ab_assignments",
        ]
        for t in expected_tables:
            self.assertIn(t, result.data)

    def test_export_sar_result_fields(self):
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", ""):
            result = self.svc.export(self.uid)
        self.assertEqual(result.user_id, self.uid)
        self.assertIsNotNone(result.generated_at)
        self.assertIsInstance(result.data, dict)

    def test_export_handles_request_error(self):
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", "https://fake.supabase.co"):
            with mock.patch("requests.get", side_effect=ConnectionError("timeout")):
                with mock.patch.object(self.svc, "_log_request"):
                    result = self.svc.export(self.uid)
        # Hata olduğunda boş liste döner, exception yutulur
        self.assertIsInstance(result.data, dict)


class TestGDPRAuditLog(unittest.TestCase):
    def test_log_request_skipped_without_supabase(self):
        svc = GDPRService()
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", ""):
            svc._log_request("uid", "forget", None)  # sessiz geçmeli

    def test_log_request_calls_supabase(self):
        svc = GDPRService()
        ok = mock.MagicMock()
        ok.ok = True
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", "https://fake.supabase.co"):
            with mock.patch("requests.post", return_value=ok) as post_mock:
                svc._log_request("uid", "export", None)
        post_mock.assert_called_once()
        call_json = post_mock.call_args[1]["json"]
        self.assertEqual(call_json["request_type"], "export")

    def test_log_request_with_result_includes_details(self):
        svc = GDPRService()
        ok = mock.MagicMock()
        ok.ok = True
        result = GDPRResult(user_id="uid", success=True,
                            deleted_tables=["user_savings"],
                            anonymized_tables=["request_metrics"])
        with mock.patch.object(gdpr_mod, "_SUPABASE_URL", "https://fake.supabase.co"):
            with mock.patch("requests.post", return_value=ok) as post_mock:
                svc._log_request("uid", "forget", result)
        call_json = post_mock.call_args[1]["json"]
        self.assertIn("details", call_json)
        self.assertIn("deleted_tables", call_json["details"])


class TestGDPRServiceSingleton(unittest.TestCase):
    def test_singleton_instance(self):
        from app.gdpr import gdpr_service as gs
        self.assertIsInstance(gs, GDPRService)


# ── openapi_config ──────────────────────────────────────────────

from app.openapi_config import (
    TAGS_METADATA,
    SECURITY_SCHEMES,
    build_openapi_overrides,
    custom_openapi,
    APP_TITLE,
    APP_VERSION,
    SERVERS,
)


class TestOpenAPIConfig(unittest.TestCase):
    def test_tags_metadata_not_empty(self):
        self.assertGreater(len(TAGS_METADATA), 0)

    def test_all_tags_have_name_and_description(self):
        for tag in TAGS_METADATA:
            self.assertIn("name", tag)
            self.assertIn("description", tag)

    def test_security_schemes_has_bearer(self):
        self.assertIn("BearerAuth", SECURITY_SCHEMES)
        self.assertEqual(SECURITY_SCHEMES["BearerAuth"]["scheme"], "bearer")

    def test_security_schemes_has_partner_api_key(self):
        self.assertIn("PartnerApiKey", SECURITY_SCHEMES)

    def test_build_openapi_overrides_has_tag_groups(self):
        overrides = build_openapi_overrides()
        self.assertIn("x-tagGroups", overrides)
        self.assertGreater(len(overrides["x-tagGroups"]), 0)

    def test_servers_list_has_production(self):
        prod = [s for s in SERVERS if "almadan.vercel.app" in s["url"]]
        self.assertEqual(len(prod), 1)

    def test_servers_list_has_local(self):
        local = [s for s in SERVERS if "localhost" in s["url"]]
        self.assertEqual(len(local), 1)

    def test_app_title_not_empty(self):
        self.assertTrue(len(APP_TITLE) > 0)

    def test_app_version_semver(self):
        parts = APP_VERSION.split(".")
        self.assertEqual(len(parts), 3)
        for p in parts:
            self.assertTrue(p.isdigit())

    def test_custom_openapi_caches_schema(self):
        fake_app = mock.MagicMock()
        fake_app.openapi_schema = None
        fake_app.routes = []

        with mock.patch("fastapi.openapi.utils.get_openapi") as mock_get:
            mock_get.return_value = {
                "info":       {},
                "components": {},
                "paths":      {},
            }
            schema1 = custom_openapi(fake_app)
            schema2 = custom_openapi(fake_app)

        # İkinci çağrıda cache'den dönmeli
        self.assertEqual(mock_get.call_count, 1)

    def test_custom_openapi_adds_security(self):
        fake_app = mock.MagicMock()
        fake_app.openapi_schema = None
        fake_app.routes = []

        with mock.patch("fastapi.openapi.utils.get_openapi") as mock_get:
            mock_get.return_value = {
                "info":       {},
                "components": {},
                "paths":      {},
            }
            schema = custom_openapi(fake_app)

        self.assertIn("security", schema)
        self.assertIn("BearerAuth", schema["security"][0])

    def test_custom_openapi_adds_tag_groups(self):
        fake_app = mock.MagicMock()
        fake_app.openapi_schema = None
        fake_app.routes = []

        with mock.patch("fastapi.openapi.utils.get_openapi") as mock_get:
            mock_get.return_value = {
                "info":       {},
                "components": {},
                "paths":      {},
            }
            schema = custom_openapi(fake_app)

        self.assertIn("x-tagGroups", schema)


if __name__ == "__main__":
    unittest.main()
