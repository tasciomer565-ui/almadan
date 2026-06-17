"""
ABTestEngine — Sprint 5: A/B Test Altyapısı

Tasarım:
  - Deterministik varyant atama: hash(user_id + experiment_key) % 100
  - Supabase ab_experiments / ab_assignments / ab_events tablolarına yazar
  - Sonuçlar get_ab_results() SQL fonksiyonuyla çekilir
  - Aktif deneyi olmayan key için her zaman "control" döner (safe default)

Örnek kullanım:
    engine = ABTestEngine()
    variant = engine.get_variant(user_id, "price_display")
    # variant → "control" veya "variant_a"

    engine.track_conversion(user_id, "price_display", "click_buy")
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any

import requests as _req

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())


def _headers() -> dict[str, str]:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _sb(path: str) -> str:
    return f"{_SUPABASE_URL}/rest/v1/{path}"


# ── Veri Sınıfları ────────────────────────────────────────────

@dataclass
class Experiment:
    id: int
    key: str
    variants: list[str]
    traffic_pct: int
    is_active: bool

    @classmethod
    def from_row(cls, row: dict) -> "Experiment":
        return cls(
            id=row["id"],
            key=row["key"],
            variants=row.get("variants", ["control", "variant_a"]),
            traffic_pct=row.get("traffic_pct", 100),
            is_active=row.get("is_active", True),
        )


# ── ABTestEngine ──────────────────────────────────────────────

class ABTestEngine:
    """
    A/B deneyi yönetimi: varyant atama, dönüşüm takibi, sonuç raporlama.
    """

    _cache: dict[str, Experiment | None] = {}

    # ── Varyant Atama ─────────────────────────────────────────

    def get_variant(
        self,
        user_id: str | None,
        experiment_key: str,
        *,
        device_id: str | None = None,
    ) -> str:
        """
        Kullanıcı/cihaz için deterministik varyant döndürür.
        Deneyi bulamazsa veya aktif değilse "control" döner.
        """
        exp = self._get_experiment(experiment_key)
        if exp is None or not exp.is_active:
            return "control"

        # Önceden atanmış varyantı kontrol et
        existing = self._get_assignment(exp.id, user_id, device_id)
        if existing:
            return existing

        # Traffic limiti — kullanıcı deneye dahil değilse
        identity = user_id or device_id or ""
        bucket = self._hash_bucket(identity, experiment_key)
        if bucket >= exp.traffic_pct:
            return "control"

        # Yeni varyant ata
        variant_index = bucket % len(exp.variants)
        variant = exp.variants[variant_index]
        self._save_assignment(exp.id, user_id, device_id, variant)
        return variant

    def track_event(
        self,
        experiment_key: str,
        event_name: str,
        *,
        user_id: str | None = None,
        device_id: str | None = None,
        value: float | None = None,
    ) -> bool:
        """
        Deney için bir olay kaydeder (tıklama, dönüşüm, vb.).
        """
        exp = self._get_experiment(experiment_key)
        if exp is None:
            return False

        assignment_id = self._get_assignment_id(exp.id, user_id, device_id)
        if assignment_id is None:
            return False

        row: dict[str, Any] = {
            "experiment_id": exp.id,
            "assignment_id": assignment_id,
            "event_name": event_name,
        }
        if value is not None:
            row["value"] = value

        try:
            r = _req.post(_sb("ab_events"), headers=_headers(), json=row, timeout=4)
            return r.ok
        except Exception as exc:
            logger.debug("track_ab_event failed: %s", exc)
            return False

    def track_conversion(
        self,
        user_id: str | None,
        experiment_key: str,
        event_name: str = "conversion",
        *,
        device_id: str | None = None,
        value: float | None = None,
    ) -> bool:
        """track_event için kolaylık metodu."""
        return self.track_event(
            experiment_key,
            event_name,
            user_id=user_id,
            device_id=device_id,
            value=value,
        )

    # ── Sonuç Raporlama ───────────────────────────────────────

    def get_results(self, experiment_key: str) -> list[dict]:
        """
        Deney sonuçlarını katılımcı / dönüşüm / oran olarak döndürür.
        Supabase get_ab_results() RPC'sini çağırır.
        """
        try:
            r = _req.post(
                f"{_SUPABASE_URL}/rest/v1/rpc/get_ab_results",
                headers={**_headers(), "Prefer": ""},
                json={"p_experiment_key": experiment_key},
                timeout=6,
            )
            return r.json() if r.ok else []
        except Exception:
            return []

    def list_experiments(self) -> list[dict]:
        """Tüm deneyleri listeler (admin paneli için)."""
        try:
            r = _req.get(
                _sb("ab_experiments"),
                params={"select": "id,key,description,variants,traffic_pct,is_active,started_at,ended_at,winner_variant"},
                headers={**_headers(), "Prefer": ""},
                timeout=5,
            )
            return r.json() if r.ok else []
        except Exception:
            return []

    def create_experiment(
        self,
        key: str,
        description: str,
        variants: list[str] | None = None,
        traffic_pct: int = 100,
    ) -> dict | None:
        """Yeni bir deney oluşturur."""
        row = {
            "key": key,
            "description": description,
            "variants": variants or ["control", "variant_a"],
            "traffic_pct": traffic_pct,
            "is_active": True,
        }
        try:
            r = _req.post(
                _sb("ab_experiments"),
                headers={**_headers(), "Prefer": "return=representation"},
                json=row,
                timeout=5,
            )
            return r.json()[0] if r.ok else None
        except Exception:
            return None

    def stop_experiment(self, key: str, winner_variant: str | None = None) -> bool:
        """Deneyi durdurur ve kazanan varyantı kaydeder."""
        payload: dict[str, Any] = {"is_active": False}
        if winner_variant:
            payload["winner_variant"] = winner_variant
        try:
            r = _req.patch(
                _sb("ab_experiments"),
                params={"key": f"eq.{key}"},
                headers=_headers(),
                json=payload,
                timeout=4,
            )
            self._cache.pop(key, None)
            return r.ok
        except Exception:
            return False

    # ── Özel Yardımcılar ──────────────────────────────────────

    def _get_experiment(self, key: str) -> Experiment | None:
        if key in self._cache:
            return self._cache[key]
        try:
            r = _req.get(
                _sb("ab_experiments"),
                params={"key": f"eq.{key}", "is_active": "eq.true", "select": "*"},
                headers={**_headers(), "Prefer": ""},
                timeout=4,
            )
            if r.ok and r.json():
                exp = Experiment.from_row(r.json()[0])
                self._cache[key] = exp
                return exp
        except Exception:
            pass
        self._cache[key] = None
        return None

    def _get_assignment(
        self, exp_id: int, user_id: str | None, device_id: str | None
    ) -> str | None:
        """Mevcut atamayı sorgular, varsa varyant adını döndürür."""
        try:
            if user_id:
                r = _req.get(
                    _sb("ab_assignments"),
                    params={"experiment_id": f"eq.{exp_id}", "user_id": f"eq.{user_id}", "select": "variant"},
                    headers={**_headers(), "Prefer": ""},
                    timeout=4,
                )
                if r.ok and r.json():
                    return r.json()[0]["variant"]
            if device_id:
                r = _req.get(
                    _sb("ab_assignments"),
                    params={"experiment_id": f"eq.{exp_id}", "device_id": f"eq.{device_id}", "select": "variant"},
                    headers={**_headers(), "Prefer": ""},
                    timeout=4,
                )
                if r.ok and r.json():
                    return r.json()[0]["variant"]
        except Exception:
            pass
        return None

    def _get_assignment_id(
        self, exp_id: int, user_id: str | None, device_id: str | None
    ) -> int | None:
        try:
            params = {"experiment_id": f"eq.{exp_id}", "select": "id"}
            if user_id:
                params["user_id"] = f"eq.{user_id}"
            elif device_id:
                params["device_id"] = f"eq.{device_id}"
            else:
                return None
            r = _req.get(_sb("ab_assignments"), params=params, headers={**_headers(), "Prefer": ""}, timeout=4)
            if r.ok and r.json():
                return r.json()[0]["id"]
        except Exception:
            pass
        return None

    def _save_assignment(
        self, exp_id: int, user_id: str | None, device_id: str | None, variant: str
    ) -> None:
        row: dict[str, Any] = {
            "experiment_id": exp_id,
            "variant": variant,
        }
        if user_id:
            row["user_id"] = user_id
        if device_id:
            row["device_id"] = device_id
        try:
            _req.post(
                _sb("ab_assignments"),
                headers={**_headers(), "Prefer": "resolution=ignore-duplicates"},
                json=row,
                timeout=4,
            )
        except Exception:
            pass

    @staticmethod
    def _hash_bucket(identity: str, experiment_key: str) -> int:
        """0–99 arası deterministik bucket döndürür."""
        raw = f"{identity}:{experiment_key}".encode()
        digest = hashlib.md5(raw, usedforsecurity=False).hexdigest()
        return int(digest[:4], 16) % 100


# Singleton
ab_engine = ABTestEngine()
