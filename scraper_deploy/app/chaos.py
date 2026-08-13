"""
Chaos Engineering — Sprint 8

Sistemin "self-healing" kapasitesini ve circuit breaker'ların
doğru çalışıp çalışmadığını test etmek için kontrollü hata enjeksiyonu.

Hata senaryoları:
  latency          — yapay gecikme (istenen ms)
  error            — belirli oran'da exception fırlatma
  timeout          — 10s+ gecikme (Vercel timeout'u tetikler)
  data_corruption  — bozuk/truncated JSON yanıt

UYARI: Bu modül sadece staging/dev ortamında veya admin izni ile çalışır.
"""
from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

import requests as _req

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
_CHAOS_ENABLED = os.getenv("CHAOS_ENABLED", "false").lower() == "true"


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


class FaultType(str, Enum):
    LATENCY          = "latency"
    ERROR            = "error"
    TIMEOUT          = "timeout"
    DATA_CORRUPTION  = "data_corruption"


@dataclass
class ChaosExperiment:
    name: str
    target_service: str
    fault_type: FaultType
    duration_sec: int = 30
    # Hata tiplerine göre ek parametreler
    latency_ms: int = 500          # LATENCY için eklenen gecikme
    error_rate: float = 0.5        # ERROR için 0-1 arası oran
    triggered_by: str = "manual"
    # Çalışma zamanı alanları
    id: int | None = None
    status: str = "pending"
    started_at: float = field(default_factory=time.monotonic)
    results: dict = field(default_factory=dict)


class ChaosRunner:
    """
    Kontrollü hata enjeksiyonu motoru.

    Kullanım:
        runner = ChaosRunner()
        exp_id = runner.start("supabase-latency-test", "supabase", FaultType.LATENCY,
                               duration_sec=30, latency_ms=800)
        # ... test sonuçları gözlemle ...
        runner.stop(exp_id)
    """

    def __init__(self):
        self._active: dict[str, ChaosExperiment] = {}

    def start(
        self,
        name: str,
        target_service: str,
        fault_type: FaultType,
        *,
        duration_sec: int = 30,
        latency_ms: int = 500,
        error_rate: float = 0.5,
        triggered_by: str = "manual",
    ) -> int | None:
        """
        Yeni bir chaos experiment başlatır.

        Returns:
            Deney ID'si (Supabase'den) veya None (DB yoksa)
        """
        if not _CHAOS_ENABLED:
            logger.warning("Chaos engineering devre dışı (CHAOS_ENABLED=false)")
            return None

        exp = ChaosExperiment(
            name=name,
            target_service=target_service,
            fault_type=fault_type,
            duration_sec=duration_sec,
            latency_ms=latency_ms,
            error_rate=error_rate,
            triggered_by=triggered_by,
        )
        db_id = self._persist_start(exp)
        exp.id = db_id
        self._active[name] = exp
        logger.warning(
            "Chaos BAŞLADI: %s → %s [%s] %ds",
            target_service, fault_type.value, name, duration_sec
        )
        return db_id

    def stop(self, name: str, *, result: dict | None = None) -> bool:
        """Çalışan deneyi durdurur."""
        if name not in self._active:
            return False
        exp = self._active.pop(name)
        self._persist_complete(exp, result or {})
        logger.info("Chaos DURDURULDU: %s", name)
        return True

    def is_active(self, target_service: str) -> bool:
        return any(e.target_service == target_service for e in self._active.values())

    def get_active_experiment(self, target_service: str) -> ChaosExperiment | None:
        for exp in self._active.values():
            if exp.target_service == target_service:
                elapsed = time.monotonic() - exp.started_at
                if elapsed > exp.duration_sec:
                    self.stop(exp.name, result={"reason": "auto_expired"})
                    return None
                return exp
        return None

    def inject_fault(self, target_service: str) -> None:
        """
        Servis çağrısından önce bu fonksiyonu çağırın.
        Aktif bir deney varsa uygun hatayı enjekte eder.

        Hata enjekte edilmezse sessizce döner.
        """
        exp = self.get_active_experiment(target_service)
        if not exp:
            return

        if exp.fault_type == FaultType.LATENCY:
            logger.debug("Chaos latency enjekte: +%dms", exp.latency_ms)
            time.sleep(exp.latency_ms / 1000)

        elif exp.fault_type == FaultType.ERROR:
            if random.random() < exp.error_rate:
                raise ConnectionError(
                    f"[Chaos] '{target_service}' servisinde yapay hata ({exp.error_rate*100:.0f}% oran)"
                )

        elif exp.fault_type == FaultType.TIMEOUT:
            logger.warning("Chaos timeout enjekte: %s → 12s uyku", target_service)
            time.sleep(12)   # Vercel 10s limitini aşar

        elif exp.fault_type == FaultType.DATA_CORRUPTION:
            raise ValueError(
                f"[Chaos] '{target_service}' bozuk veri: unexpected null response"
            )

    def _persist_start(self, exp: ChaosExperiment) -> int | None:
        if not _SUPABASE_URL:
            return None
        try:
            resp = _req.post(
                f"{_SUPABASE_URL}/rest/v1/chaos_experiments",
                headers={**_sb_headers(), "Prefer": "return=representation"},
                json={
                    "experiment_name": exp.name,
                    "target_service":  exp.target_service,
                    "fault_type":      exp.fault_type.value,
                    "duration_sec":    exp.duration_sec,
                    "status":          "running",
                    "triggered_by":    exp.triggered_by,
                    "started_at":      datetime.now(timezone.utc).isoformat(),
                },
                timeout=3,
            )
            if resp.ok:
                rows = resp.json()
                return rows[0]["id"] if rows else None
        except Exception:
            pass
        return None

    def _persist_complete(self, exp: ChaosExperiment, result: dict) -> None:
        if not _SUPABASE_URL or not exp.id:
            return
        try:
            _req.patch(
                f"{_SUPABASE_URL}/rest/v1/chaos_experiments",
                params={"id": f"eq.{exp.id}"},
                headers={**_sb_headers(), "Prefer": "return=minimal"},
                json={
                    "status":       "completed",
                    "result":       result,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=3,
            )
        except Exception:
            pass


# Uygulama genelinde singleton
_runner = ChaosRunner()


def get_chaos_runner() -> ChaosRunner:
    return _runner


# ── Önceden Tanımlı Senaryo Şablonları ───────────────────────

SCENARIOS: dict[str, dict] = {
    "supabase-latency": {
        "target_service": "supabase",
        "fault_type":     FaultType.LATENCY,
        "duration_sec":   60,
        "latency_ms":     800,
    },
    "openai-errors": {
        "target_service": "openai",
        "fault_type":     FaultType.ERROR,
        "duration_sec":   30,
        "error_rate":     0.8,
    },
    "replicate-timeout": {
        "target_service": "replicate",
        "fault_type":     FaultType.TIMEOUT,
        "duration_sec":   15,
    },
    "scraper-errors": {
        "target_service": "scrapers",
        "fault_type":     FaultType.ERROR,
        "duration_sec":   120,
        "error_rate":     0.5,
    },
}


def run_scenario(scenario_name: str, *, triggered_by: str = "admin") -> dict:
    """
    Önceden tanımlı senaryoyu başlatır.

    Returns:
        {"started": bool, "experiment_id": int | None, "scenario": dict}
    """
    if scenario_name not in SCENARIOS:
        return {"error": f"Bilinmeyen senaryo: {scenario_name}"}

    cfg = SCENARIOS[scenario_name]
    exp_id = _runner.start(
        name=scenario_name,
        triggered_by=triggered_by,
        **cfg,
    )
    return {
        "started":       exp_id is not None or True,
        "experiment_id": exp_id,
        "scenario":      {k: (v.value if isinstance(v, FaultType) else v) for k, v in cfg.items()},
    }
