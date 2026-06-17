"""
Sprint 3 — AiOrchestrator birim testleri

Çalıştırma:
    pytest tests/test_sprint3_ai_orchestrator.py -v
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch


# ── JobResult ────────────────────────────────────────────────

class TestJobResult:
    def test_dataclass_fields(self):
        from app.ai_orchestrator import JobResult
        r = JobResult(job_id="abc", status="done", output_data={"result_url": "https://x.com/img.jpg"})
        assert r.job_id == "abc"
        assert r.status == "done"
        assert r.output_data["result_url"] == "https://x.com/img.jpg"
        assert r.error_message is None


# ── _build_inputs ────────────────────────────────────────────

class TestBuildInputs:
    def test_vton_inputs(self):
        from app.ai_orchestrator import AiOrchestrator
        inputs = AiOrchestrator._build_inputs("vton", {
            "portrait_url": "https://x.com/portrait.jpg",
            "garment_url":  "https://x.com/shirt.jpg",
        })
        assert inputs["human_img"] == "https://x.com/portrait.jpg"
        assert inputs["garm_img"]  == "https://x.com/shirt.jpg"
        assert "denoise_steps" in inputs

    def test_ocr_inputs(self):
        from app.ai_orchestrator import AiOrchestrator
        inputs = AiOrchestrator._build_inputs("ocr", {"image_url": "https://x.com/receipt.jpg"})
        assert inputs["image"] == "https://x.com/receipt.jpg"
        assert inputs.get("language") == "tr"

    def test_skin_analysis_inputs(self):
        from app.ai_orchestrator import AiOrchestrator
        inputs = AiOrchestrator._build_inputs("skin_analysis", {"image_url": "https://x.com/skin.jpg"})
        assert "question" in inputs


# ── Webhook Handler ──────────────────────────────────────────

class TestWebhookHandler:
    def _orch(self):
        from app.ai_orchestrator import AiOrchestrator
        return AiOrchestrator()

    def test_succeeded_webhook_updates_status(self):
        orch = self._orch()
        with patch("app.ai_orchestrator._db_update", return_value=True) as mock_update:
            result = orch.handle_replicate_webhook(
                job_id="test-job-123",
                payload={
                    "status":  "succeeded",
                    "output":  ["https://cdn.replicate.com/result.jpg"],
                    "metrics": {"predict_time": 12.5},
                },
                signature=None,   # imza doğrulaması atla
            )
        assert result["accepted"] is True
        assert result["status"] == "done"
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[0]
        assert call_kwargs[2]["status"] == "done"
        assert "result_url" in call_kwargs[2]["output_data"]

    def test_failed_webhook(self):
        orch = self._orch()
        with patch("app.ai_orchestrator._db_update", return_value=True) as mock_update:
            result = orch.handle_replicate_webhook(
                "test-job-456",
                {"status": "failed", "error": "CUDA out of memory"},
            )
        assert result["status"] == "failed"
        call_data = mock_update.call_args[0][2]
        assert call_data["status"] == "failed"
        assert "CUDA" in call_data["error_message"]

    def test_processing_webhook_updates_status(self):
        orch = self._orch()
        with patch("app.ai_orchestrator._db_update", return_value=True) as mock_update:
            result = orch.handle_replicate_webhook("job", {"status": "processing"})
        assert result["accepted"] is True
        mock_update.assert_called_once()

    def test_invalid_signature_rejected(self):
        orch = self._orch()
        with patch.dict(os.environ, {"AI_WEBHOOK_SECRET": "super_secret_key"}):
            from app import ai_orchestrator
            ai_orchestrator.WEBHOOK_SECRET = "super_secret_key"
            result = orch.handle_replicate_webhook(
                "job",
                {"status": "succeeded", "output": []},
                signature="bad_signature",
            )
        assert result.get("accepted") is False


# ── Mock Modu ────────────────────────────────────────────────

class TestMockMode:
    def test_vton_mock_when_no_token(self):
        from app.ai_orchestrator import AiOrchestrator, REPLICATE_TOKEN
        orch = AiOrchestrator()
        with patch.dict(os.environ, {"REPLICATE_API_TOKEN": ""}):
            with patch("app.ai_orchestrator.REPLICATE_TOKEN", ""):
                with patch("app.ai_orchestrator._db_get", return_value={
                    "job_id": "mock-job",
                    "job_type": "vton",
                    "input_data": {
                        "portrait_url": "https://x.com/p.jpg",
                        "garment_url":  "https://x.com/g.jpg",
                    },
                }):
                    with patch("app.ai_orchestrator._db_update", return_value=True):
                        result = orch.process_sync("mock-job")
        assert result.status == "done"
        assert result.output_data.get("mock") is True

    def test_ocr_mock_returns_text(self):
        from app.ai_orchestrator import AiOrchestrator
        orch = AiOrchestrator()
        with patch("app.ai_orchestrator.REPLICATE_TOKEN", ""):
            with patch("app.ai_orchestrator._db_update", return_value=True):
                result = orch._mock_result("job", "ocr", {"image_url": "https://x.com/img.jpg"})
        assert result.status == "done"
        assert "text" in result.output_data


# ── DB Yardımcıları ──────────────────────────────────────────

class TestDbHelpers:
    def test_db_ok_false_when_no_env(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""}):
            from app import ai_orchestrator
            ai_orchestrator.SUPABASE_URL = ""
            ai_orchestrator.SUPABASE_KEY = ""
            assert ai_orchestrator._db_ok() is False

    def test_db_insert_skips_when_disabled(self):
        from app import ai_orchestrator
        with patch.object(ai_orchestrator, "_db_ok", return_value=False):
            result = ai_orchestrator._db_insert("ai_jobs", {"job_id": "x"})
        assert result is None

    def test_db_update_skips_when_disabled(self):
        from app import ai_orchestrator
        with patch.object(ai_orchestrator, "_db_ok", return_value=False):
            ok = ai_orchestrator._db_update("ai_jobs", "job-id", {"status": "done"})
        assert ok is False


# ── Cost Tracking ────────────────────────────────────────────

class TestCostTracking:
    def test_webhook_calculates_cost(self):
        from app.ai_orchestrator import AiOrchestrator
        orch = AiOrchestrator()
        with patch("app.ai_orchestrator._db_update") as mock_update:
            orch.handle_replicate_webhook(
                "job-cost-test",
                {
                    "status":  "succeeded",
                    "output":  ["https://x.com/result.jpg"],
                    "metrics": {"predict_time": 10.0},
                },
            )
        call_data = mock_update.call_args[0][2]
        # 10 sn * 0.0023 = 0.023 USD
        assert call_data.get("actual_cost_usd", 0) > 0

    def test_model_estimated_costs_defined(self):
        from app.ai_orchestrator import MODELS
        for name, cfg in MODELS.items():
            assert "cost_est" in cfg, f"{name} modelinde cost_est eksik"
            assert cfg["cost_est"] >= 0


# ── Submit API ───────────────────────────────────────────────

class TestSubmitApi:
    def test_submit_vton_returns_job_id(self):
        from app.ai_orchestrator import AiOrchestrator
        orch = AiOrchestrator()
        with patch.object(orch, "_create_job", return_value={
            "job_id": "test-uuid-123",
            "status": "pending",
        }):
            result = orch.submit_vton(
                portrait_url="https://x.com/p.jpg",
                garment_url="https://x.com/g.jpg",
            )
        assert "job_id" in result
        assert "poll_url" in result
        assert result["job_id"] == "test-uuid-123"

    def test_submit_ocr_returns_job_id(self):
        from app.ai_orchestrator import AiOrchestrator
        orch = AiOrchestrator()
        with patch.object(orch, "_create_job", return_value={
            "job_id": "ocr-uuid-456",
            "status": "pending",
        }):
            result = orch.submit_ocr(image_url="https://x.com/receipt.jpg")
        assert result["job_id"] == "ocr-uuid-456"
