from __future__ import annotations

import json
import os
from typing import Any


VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@almadan.app").strip()


def push_enabled() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and VAPID_SUBJECT)


def send_push(subscription: dict[str, Any], payload: dict[str, Any]) -> None:
    if not push_enabled():
        return

    from pywebpush import webpush

    webpush(
        subscription_info={
            "endpoint": subscription["endpoint"],
            "keys": subscription["keys"],
        },
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=VAPID_PRIVATE_KEY,
        vapid_claims={"sub": VAPID_SUBJECT},
        ttl=60 * 60,
        timeout=15,
    )


def send_push_to_owner(owner_id: str | None, payload: dict[str, Any]) -> dict[str, int]:
    if not owner_id or not push_enabled():
        return {"sent": 0, "removed": 0}

    from pywebpush import WebPushException

    from app.storage import load_db, save_db

    db = load_db()
    subscriptions = db.get("push_subscriptions", [])
    owner_subscriptions = [
        item for item in subscriptions if item.get("owner_id") == owner_id
    ]
    expired_endpoints: set[str] = set()
    sent = 0

    for subscription in owner_subscriptions:
        try:
            send_push(subscription, payload)
            sent += 1
        except WebPushException as exc:
            status_code = (
                exc.response.status_code if exc.response is not None else None
            )
            if status_code in {404, 410}:
                expired_endpoints.add(subscription.get("endpoint", ""))
        except (KeyError, TypeError, ValueError):
            expired_endpoints.add(subscription.get("endpoint", ""))
        except Exception:
            continue

    if expired_endpoints:
        db["push_subscriptions"] = [
            item
            for item in subscriptions
            if item.get("endpoint") not in expired_endpoints
        ]
        save_db(db)

    return {"sent": sent, "removed": len(expired_endpoints)}
