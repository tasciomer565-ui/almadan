"""app/whatsapp.py ve app/netgsm.py'deki _normalize_phone fonksiyonlarini
cesitli girdi formatlariyla test eder (+90..., 0..., 90..., bosluklu/tireli)."""
import pytest

from app.whatsapp import _normalize_phone as wa_normalize
from app.netgsm import _normalize_phone as netgsm_normalize


# ── WhatsApp: sadece '+' / bosluk / tire temizler, ulke kodu donusumu yapmaz ──

@pytest.mark.parametrize("raw,expected", [
    ("+905551234567", "905551234567"),
    ("905551234567", "905551234567"),
    ("+90 555 123 45 67", "905551234567"),
    ("+90-555-123-45-67", "905551234567"),
    ("90 555 123 45 67", "905551234567"),
])
def test_whatsapp_normalize_phone(raw, expected):
    assert wa_normalize(raw) == expected


# ── Netgsm: 0-> 90 donusumu de yapar, hep 90 ile baslayan 12 haneli sonuc ──

@pytest.mark.parametrize("raw,expected", [
    ("+905551234567", "905551234567"),
    ("905551234567", "905551234567"),
    ("05551234567", "905551234567"),
    ("5551234567", "905551234567"),
    ("+90 555 123 45 67", "905551234567"),
    ("0555 123 45 67", "905551234567"),
    ("0-555-123-45-67", "905551234567"),
    ("90-555-123-45-67", "905551234567"),
])
def test_netgsm_normalize_phone(raw, expected):
    assert netgsm_normalize(raw) == expected
