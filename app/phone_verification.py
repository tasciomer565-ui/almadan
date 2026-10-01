"""Giriş yapmış kullanıcının telefon numarasını doğrulama (Netgsm SMS ile).

Neden Supabase OTP değil: Supabase'in /otp ucu "telefonla giriş"tir --
numara kullanıcının auth.users.phone alanında kayıtlı değilse (profil
güncellemesi telefonu sadece user_metadata'ya yazıyor) o numarayla YENİ bir
hesap açar ve doğrulama o hesabın oturumunu döndürür; kullanıcı fark
etmeden boş bir hesaba geçerdi. Ayrıca Supabase'te SMS sağlayıcısı
(Twilio/MessageBird/Vonage) tanımlı değildi; projede Netgsm hesabı var.

Kodlar süreç belleğinde tutulur (Render tek örnek; 10 dk ömür). Sadece kodun
SHA-256 özeti saklanır.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

CODE_TTL_SECONDS = 600
MAX_ATTEMPTS = 5

_lock = threading.Lock()
# phone -> (code_hash, expires_at, attempts, user_id)
_pending: dict[str, tuple[str, float, int, str]] = {}


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def sms_available() -> bool:
    from app.netgsm import netgsm_enabled
    return netgsm_enabled()


def send_code(user_id: str, phone: str) -> bool:
    """6 haneli kod üretip Netgsm ile gönderir. Gönderilemezse False."""
    from app.netgsm import send_netgsm_sms
    code = f"{secrets.randbelow(1_000_000):06d}"
    message = f"Almadan dogrulama kodun: {code}. Kod 10 dakika gecerlidir, kimseyle paylasma."
    if not send_netgsm_sms(phone, message):
        return False
    with _lock:
        _pending[phone] = (_hash(code), time.time() + CODE_TTL_SECONDS, 0, user_id)
    return True


def has_pending(user_id: str, phone: str) -> bool:
    with _lock:
        entry = _pending.get(phone)
        return bool(entry and entry[3] == user_id and entry[1] > time.time())


def verify_code(user_id: str, phone: str, code: str) -> bool:
    """Doğruysa kodu tüketir ve True döner. Süresi dolan / 5 yanlış
    denemeden sonra kod geçersizleşir (yeni kod istenmeli)."""
    with _lock:
        entry = _pending.get(phone)
        if not entry:
            return False
        code_hash, expires_at, attempts, owner = entry
        if owner != user_id or expires_at < time.time() or attempts >= MAX_ATTEMPTS:
            _pending.pop(phone, None)
            return False
        if hmac.compare_digest(code_hash, _hash(code.strip())):
            _pending.pop(phone, None)
            return True
        _pending[phone] = (code_hash, expires_at, attempts + 1, owner)
        return False
