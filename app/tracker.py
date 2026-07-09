from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from app.parser import parse_product_url
from app.push import send_push_to_owner
from app.storage import current_price, load_db, save_db, utc_now


DROP_THRESHOLD = 0.05


def find_product(db: dict[str, Any], product_id: str) -> dict[str, Any] | None:
    return next(
        (product for product in db["products"] if product["id"] == product_id),
        None,
    )


def notification_payload(product: dict, notification: dict) -> dict[str, str]:
    return {
        "title": notification["title"],
        "body": notification["message"],
        "url": f"/?product={product['id']}",
        "tag": notification["id"],
    }


import json

# Production provider templates:
#
# def send_netgsm_sms(phone: str, message: str) -> None:
#     requests.post(
#         "https://api.netgsm.com.tr/sms/send/get",
#         data={"usercode": "...", "password": "...", "gsmno": phone,
#               "message": message, "msgheader": "..."},
#         timeout=15,
#     ).raise_for_status()
#
# def send_twilio_sms(phone: str, message: str) -> None:
#     requests.post(
#         f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Messages.json",
#         auth=(ACCOUNT_SID, AUTH_TOKEN),
#         data={"From": TWILIO_PHONE, "To": phone, "Body": message},
#         timeout=15,
#     ).raise_for_status()
#
# def send_smtp_email(recipient: str, subject: str, message: str) -> None:
#     import smtplib
#     from email.message import EmailMessage
#     mail = EmailMessage()
#     mail["From"], mail["To"], mail["Subject"] = SMTP_FROM, recipient, subject
#     mail.set_content(message)
#     with smtplib.SMTP_SSL(SMTP_HOST, 465) as smtp:
#         smtp.login(SMTP_USER, SMTP_PASSWORD)
#         smtp.send_message(mail)

def _whatsapp_display_name(user_info: dict) -> str:
    full_name = (user_info.get("full_name") or "").strip()
    email = user_info.get("email") or ""
    return (
        full_name.split()[0].capitalize() if full_name
        else (email.split("@")[0].capitalize() if email else "")
    ) or "Değerli kullanıcımız"


def _product_url_suffix(product_url: str | None) -> str:
    return (product_url or "").replace("https://www.almadan.app/", "").lstrip("/") or "urun"


def whatsapp_args_for_notification(notification: dict, product: dict | None = None) -> dict:
    """
    Bildirim turune gore dogru WhatsApp sablonu + parametrelerini secer.
    Bos dict donerse cagiran taraf genel (general_notification) sablona
    duser -- ozel bir sablon icin yeterli/anlamli veri yoksa budur.
    """
    ntype = notification.get("type")

    if ntype == "target_price_alert" and product:
        history = product.get("price_history", [])
        new_price = current_price(product)
        old_price = float(history[-2]["price"]) if len(history) >= 2 else None
        if old_price and old_price > new_price:
            return {
                "wa_template": os.getenv("WHATSAPP_TEMPLATE_NAME", "price_alert").strip(),
                "wa_params": [product.get("title", ""), f"{new_price:.2f}", f"{old_price - new_price:.2f}"],
                "wa_button_param": _product_url_suffix(product.get("url")),
            }

    if ntype == "stock_back" and product:
        new_price = current_price(product)
        return {
            "wa_template": os.getenv("WHATSAPP_STOCK_TEMPLATE_NAME", "stock_alert").strip(),
            "wa_params": [product.get("title", ""), f"{new_price:.2f}"],
            "wa_button_param": _product_url_suffix(product.get("url")),
        }

    if ntype == "catalog_match" and product:
        return {
            "wa_template": os.getenv("WHATSAPP_CATALOG_TEMPLATE_NAME", "catalog_alert").strip(),
            "wa_params": [product.get("title", ""), notification.get("title", "")],
            "wa_button_param": _product_url_suffix(product.get("url")),
        }

    return {}


def log_sms_notification(
    owner_id: str | None,
    title: str,
    message: str,
    wa_template: str | None = None,
    wa_params: list[str] | None = None,
    wa_button_param: str | None = None,
) -> None:
    if not owner_id or not owner_id.startswith("user:"):
        return

    db = load_db()
    user_info = db.get("users", {}).get(owner_id, {})
    pref = user_info.get("notification_pref", "both")
    phone = user_info.get("phone")

    if pref not in ("sms", "both") or not phone:
        return

    # Gercek WhatsApp bildirimi -- notification turune ozel bir sablon
    # (wa_template/wa_params, bkz. whatsapp_args_for_notification) varsa o
    # kullanilir; yoksa TUM diger bildirim turleri icin general_notification
    # (isim + hazirlanmis title/message metni) devreye girer. Meta onayli
    # sablonlar onaylanana kadar gonderim sessizce basarisiz olur.
    try:
        from app.whatsapp import whatsapp_enabled, send_whatsapp_template
        if whatsapp_enabled():
            display_name = _whatsapp_display_name(user_info)
            if wa_template and wa_params is not None:
                send_whatsapp_template(
                    phone, wa_template,
                    params=[display_name] + wa_params,
                    button_param=wa_button_param,
                )
            else:
                general_template = os.getenv("WHATSAPP_GENERAL_TEMPLATE_NAME", "general_notification").strip()
                send_whatsapp_template(
                    phone,
                    general_template,
                    params=[display_name, f"{title}: {message}"],
                )
    except Exception:
        pass

    from app.storage import DATA_DIR, utc_now
    sms_file = DATA_DIR / "sms_logs.json"
    
    logs = []
    if sms_file.exists():
        try:
            with open(sms_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
                if not isinstance(logs, list):
                    logs = []
        except Exception:
            logs = []
            
    logs.append({
        "owner_id": owner_id,
        "phone": phone,
        "title": title,
        "message": message,
        "sent_at": utc_now()
    })
    
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(sms_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def log_email_notification(owner_id: str | None, title: str, message: str) -> None:
    if not owner_id or not owner_id.startswith("user:"):
        return
        
    db = load_db()
    user_info = db.get("users", {}).get(owner_id, {})
    pref = user_info.get("notification_pref", "both")
    email = user_info.get("email")
    
    if pref not in ("email", "both") or not email:
        return
        
    from app.storage import DATA_DIR, utc_now
    email_file = DATA_DIR / "email_logs.json"
    
    logs = []
    if email_file.exists():
        try:
            with open(email_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
                if not isinstance(logs, list):
                    logs = []
        except Exception:
            logs = []
            
    logs.append({
        "owner_id": owner_id,
        "email": email,
        "title": title,
        "message": message,
        "sent_at": utc_now()
    })
    
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(email_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def is_in_silence_hours(owner_id: str | None) -> bool:
    if not owner_id or not owner_id.startswith("user:"):
        return False
    
    db = load_db()
    user_info = db.get("users", {}).get(owner_id, {})
    silence_hours = user_info.get("silence_hours")
    if not silence_hours:
        return False
        
    try:
        start_h = int(silence_hours.get("start", 22))
        end_h = int(silence_hours.get("end", 8))
        
        from datetime import datetime, timezone, timedelta
        tz_tr = timezone(timedelta(hours=3))
        current_hour = datetime.now(tz_tr).hour
        
        if start_h > end_h:
            return current_hour >= start_h or current_hour < end_h
        else:
            return start_h <= current_hour < end_h
    except Exception:
        return False


def queue_or_dispatch_notification(db: dict, product: dict, notification: dict) -> None:
    owner_id = product.get("owner_id")
    if is_in_silence_hours(owner_id):
        db.setdefault("queued_notifications", []).append({
            "product_id": product.get("id"),
            "owner_id": owner_id,
            "notification": notification
        })
        save_db(db)
    else:
        try:
            send_push_to_owner(owner_id, notification_payload(product, notification))
        except Exception:
            pass

        log_sms_notification(
            owner_id, notification["title"], notification["message"],
            **whatsapp_args_for_notification(notification, product),
        )
        log_email_notification(owner_id, notification["title"], notification["message"])


def queue_or_dispatch_catalog_notification(
    db: dict,
    owner_id: str,
    notification: dict,
    wa_template: str | None = None,
    wa_params: list[str] | None = None,
    wa_button_param: str | None = None,
) -> None:
    if is_in_silence_hours(owner_id):
        db.setdefault("queued_notifications", []).append({
            "owner_id": owner_id,
            "notification": notification
        })
        save_db(db)
    else:
        log_sms_notification(
            owner_id, notification["title"], notification["message"],
            wa_template=wa_template, wa_params=wa_params, wa_button_param=wa_button_param,
        )
        log_email_notification(owner_id, notification["title"], notification["message"])
        try:
            payload = {
                "title": notification["title"],
                "body": notification["message"],
                "url": "/?tab=notifications",
                "tag": notification["id"],
            }
            send_push_to_owner(owner_id, payload)
        except Exception:
            pass


def flush_queued_notifications() -> None:
    db = load_db()
    queued = db.get("queued_notifications", [])
    if not queued:
        return
        
    remaining = []
    changed = False
    for item in queued:
        owner_id = item.get("owner_id")
        if is_in_silence_hours(owner_id):
            remaining.append(item)
        else:
            notification = item.get("notification")

            product_id = item.get("product_id")
            product = next((p for p in db["products"] if p["id"] == product_id), None) if product_id else None

            log_sms_notification(
                owner_id, notification["title"], notification["message"],
                **whatsapp_args_for_notification(notification, product),
            )
            log_email_notification(owner_id, notification["title"], notification["message"])

            try:
                payload = notification_payload(product, notification) if product else {
                    "title": notification["title"],
                    "body": notification["message"],
                    "url": "/?tab=notifications",
                    "tag": notification["id"],
                }
                send_push_to_owner(owner_id, payload)
            except Exception:
                pass
            changed = True
            
    if changed:
        db["queued_notifications"] = remaining
        save_db(db)


def check_restock_alerts() -> None:
    db = load_db()
    checked_at = utc_now()
    from datetime import datetime, timezone, timedelta
    
    def parse_iso(dt_str):
        try:
            if dt_str.endswith('Z'):
                dt_str = dt_str[:-1] + '+00:00'
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None
            
    now_dt = datetime.now(timezone.utc)
    notifications_added = False
    
    for p in db.get("products", []):
        extra = p.get("extra_info", {})
        period = extra.get("restock_period_days")
        last_purchased_str = extra.get("last_purchased_date")
        
        if period and last_purchased_str:
            last_purchased = parse_iso(last_purchased_str)
            if not last_purchased:
                continue
                
            try:
                period_days = int(period)
                last_alerted_str = extra.get("last_restock_alerted_date")
                if last_alerted_str:
                    last_alerted = parse_iso(last_alerted_str)
                    if last_alerted and last_alerted > last_purchased:
                        continue
                        
                due_date = last_purchased + timedelta(days=period_days)
                alert_date = due_date - timedelta(days=5)
                
                if now_dt >= alert_date:
                    cheapest_price_msg = ""
                    try:
                        from app.comparator import search_products_by_name
                        res = search_products_by_name(p["title"])
                        if res:
                            in_stock = [x for x in res if not x["extra_info"].get("out_of_stock")]
                            if in_stock:
                                cheapest = min(in_stock, key=lambda x: x["price"])
                                cheapest_price_msg = f" En ucuz fırsat şu an {cheapest['source'].upper()} mağazasında: {cheapest['price']:.2f} TL."
                    except Exception:
                        pass
                        
                    notification = {
                        "id": str(uuid4()),
                        "product_id": p["id"],
                        "owner_id": p.get("owner_id"),
                        "title": "Ev İhtiyacı Alarmı!",
                        "message": f"Evdeki '{p['title']}' bitmek üzere!{cheapest_price_msg} Stok tazelemek ister misin?",
                        "created_at": checked_at,
                        "read": False,
                        "type": "restock_alert"
                    }
                    db["notifications"].insert(0, notification)
                    notifications_added = True
                    p.setdefault("extra_info", {})["last_restock_alerted_date"] = checked_at
                    
                    queue_or_dispatch_notification(db, p, notification)
            except Exception:
                pass
                
    if notifications_added:
        save_db(db)


def _trigger_weekly_catalogs_legacy() -> None:
    db = load_db()
    checked_at = utc_now()
    
    unique_users = set()
    for product in db.get("products", []):
        owner = product.get("owner_id")
        if owner and owner.startswith("user:"):
            unique_users.add(owner)
    for sub in db.get("push_subscriptions", []):
        owner = sub.get("owner_id")
        if owner and owner.startswith("user:"):
            unique_users.add(owner)
    for notif in db.get("notifications", []):
        owner = notif.get("owner_id")
        if owner and owner.startswith("user:"):
            unique_users.add(owner)

    if not unique_users:
        return
        
    from datetime import datetime, timezone
    
    def parse_iso(dt_str):
        try:
            if dt_str.endswith('Z'):
                dt_str = dt_str[:-1] + '+00:00'
            return datetime.fromisoformat(dt_str)
        except Exception:
            return datetime.now(timezone.utc)

    now_dt = datetime.now(timezone.utc)
    
    catalogs = [
        {
            "type": "catalog_bim",
            "title": "BİM Cuma Fırsatları",
            "message": "BİM Cuma Aktüel ürünleri yayınlandı! Bu haftaki indirimli ürünleri kaçırmayın.",
            "keywords": ["yağ", "yag", "seker", "şeker", "un", "bakliyat", "makarna", "pirinc", "pirinç", "sut", "süt", "peynir"]
        },
        {
            "type": "catalog_a101",
            "title": "A101 Haftanın Yıldızları",
            "message": "A101 haftalık aktüel kataloğu yayınlandı! Yeni indirimler sizi bekliyor.",
            "keywords": ["deterjan", "sabun", "temizlik", "kagit", "kağıt", "su", "cay", "çay", "kahve"]
        },
        {
            "type": "catalog_sok",
            "title": "Şok Haftanın Fırsatları",
            "message": "Şok haftalık katalog fırsatları yayınlandı.",
            "keywords": ["yağ", "süt", "peynir", "yumurta", "deterjan", "makarna", "kahve"]
        },
        {
            "type": "catalog_file",
            "title": "File Market Kataloğu",
            "message": "File Market haftalık katalog ürünleri yayınlandı.",
            "keywords": ["et", "tavuk", "süt", "peynir", "zeytin", "kahvaltı", "temizlik"]
        },
        {
            "type": "catalog_metro",
            "title": "Metro Fırsat Kataloğu",
            "message": "Metro toplu alışveriş fırsatları güncellendi.",
            "keywords": ["kg", "litre", "paket", "koli", "deterjan", "kahve", "içecek"]
        },
        {
            "type": "catalog_carrefoursa",
            "title": "CarrefourSA İndirim Kataloğu",
            "message": "CarrefourSA haftalık indirim kataloğu yayınlandı.",
            "keywords": ["meyve", "sebze", "et", "süt", "peynir", "atıştırmalık", "temizlik"]
        },
        {
            "type": "catalog_migros",
            "title": "Migroskop Fırsatları",
            "message": "Migroskop haftalık fırsatları yayınlandı.",
            "keywords": ["money", "yağ", "şeker", "kahve", "çay", "deterjan", "kişisel bakım"]
        },
        {
            "type": "catalog_gratis",
            "title": "Gratis Haftalık Kampanya",
            "message": "Gratis haftalık indirim kataloğu ve 1 hafta sonra başlayacak özel indirimler yayınlandı!",
            "keywords": ["sampuan", "şampuan", "krem", "parfum", "parfüm", "makyaj", "ruj", "maskara", "sac", "saç", "bakim", "bakım"]
        },
        {
            "type": "catalog_mediamarkt",
            "title": "MediaMarkt Gece Uçuran Kampanyası",
            "message": "MediaMarkt gece fırsatları kataloğu yayınlandı! İndirimli elektronikler sizi bekliyor.",
            "keywords": ["ssd", "gb", "tb", "laptop", "bilgisayar", "kulaklık", "telefon", "tablet", "mouse", "klavye"]
        },
        {
            "type": "catalog_boyner",
            "title": "Boyner Büyük Kelebek İndirimi",
            "message": "Boyner sezon sonu giyim kataloğu yayınlandı! Yeni indirimli moda ürünlerini kaçırmayın.",
            "keywords": ["tişört", "corap", "çorap", "ceket", "pantolon", "hırka", "kazak", "gömlek", "kaban", "ayakkabı"]
        }
    ]
    
    notifications_added = False
    
    for owner_id in unique_users:
        owner_notifs = [n for n in db.get("notifications", []) if n.get("owner_id") == owner_id]
        owner_products = [p for p in db.get("products", []) if p.get("owner_id") == owner_id]
        
        for cat in catalogs:
            sent_recently = False
            for n in owner_notifs:
                if n.get("type") == cat["type"]:
                    created_at_str = n.get("created_at")
                    if created_at_str:
                        created_dt = parse_iso(created_at_str)
                        if (now_dt - created_dt).total_seconds() < 24 * 3600:
                            sent_recently = True
                            break
            
            if not sent_recently:
                notification = {
                    "id": str(uuid4()),
                    "owner_id": owner_id,
                    "title": cat["title"],
                    "message": cat["message"],
                    "created_at": checked_at,
                    "read": False,
                    "type": cat["type"],
                }
                db["notifications"].insert(0, notification)
                notifications_added = True
                
                queue_or_dispatch_catalog_notification(db, owner_id, notification)
                
                # Check for keyword matches with user's tracked products
                for p in owner_products:
                    p_title = p.get("title")
                    if not p_title:
                        continue
                    title_lower = p_title.lower()
                    if any(k in title_lower for k in cat["keywords"]):
                        match_notification = {
                            "id": str(uuid4()),
                            "product_id": p["id"],
                            "owner_id": owner_id,
                            "title": "Kataloğa Düştü!",
                            "message": f"Takip ettiğin '{p_title}' ürünü bu haftaki {cat['title']} kataloğunda indirimde!",
                            "created_at": checked_at,
                            "read": False,
                            "type": "catalog_match"
                        }
                        db["notifications"].insert(0, match_notification)
                        queue_or_dispatch_notification(db, p, match_notification)

    if notifications_added:
        save_db(db)


def _store_followers(store_slug: str) -> set[str]:
    import requests
    from app.storage import supabase_enabled, supabase_base_url, supabase_headers
    if not supabase_enabled():
        return set()
    try:
        resp = requests.get(
            f"{supabase_base_url()}/rest/v1/followed_stores",
            headers=supabase_headers(),
            params={"store_slug": f"eq.{store_slug}", "select": "user_id"},
            timeout=10,
        )
        rows = resp.json() if resp.ok else []
        return {f"user:{row['user_id']}" for row in rows if row.get("user_id")}
    except Exception:
        return set()


def trigger_weekly_catalogs() -> None:
    """
    Her market (BİM, A101, ŞOK vb.) icin o haftaki aktuel/katalog verisi
    degistiginde takipci kullanicilara TEK bir bildirim gonderir --
    kullanicinin takip ettigi urunlerle eslesme aranmaz (aktuel zaten
    degisken/cesitli urunler iceriyor, eslesme mantiksal olarak dar
    kapsamli kaliyordu). WhatsApp butonu /aktuel/{store} sayfasina
    yonlenir, orada o haftanin gercek katalog icerigi listelenir.
    """
    from app.catalogs import fetch_all_catalogs

    db = load_db()
    checked_at = utc_now()

    fetched = fetch_all_catalogs()
    stored_snapshots = db.setdefault("catalog_snapshots", {})
    changed_catalogs = []

    for snapshot in fetched:
        store = snapshot["store"]
        previous = stored_snapshots.get(store, {})
        if not snapshot.get("ok"):
            if previous:
                previous["last_error"] = snapshot.get("error")
                previous["last_checked_at"] = snapshot.get("checked_at")
            continue

        snapshot["last_checked_at"] = snapshot["checked_at"]
        snapshot["changed"] = snapshot.get("fingerprint") != previous.get("fingerprint")
        stored_snapshots[store] = snapshot
        if snapshot["changed"]:
            changed_catalogs.append(snapshot)

    if not changed_catalogs:
        save_db(db)
        return

    # Yalnizca o magazayi GERCEKTEN takip eden kullanicilara bildirim
    # gonderilir (followed_stores tablosu) -- daha once TUM kullanicilara
    # gonderiliyordu, bu yanlisti.
    notifications_added = False
    for catalog in changed_catalogs:
        followers = _store_followers(catalog["store"])
        if not followers:
            continue
        for owner_id in followers:
            item_count = len(catalog.get("items", []))
            notification = {
                "id": str(uuid4()),
                "owner_id": owner_id,
                "title": catalog["title"],
                "message": (
                    f"{catalog['title']} bu hafta güncellendi. "
                    f"{item_count} ürün taranıyor, hemen göz at."
                ),
                "url": f"/aktuel/{catalog['store']}",
                "created_at": checked_at,
                "read": False,
                "type": f"catalog_{catalog['store']}",
            }
            db["notifications"].insert(0, notification)
            notifications_added = True
            queue_or_dispatch_catalog_notification(
                db, owner_id, notification,
                wa_template=os.getenv("WHATSAPP_CATALOG_TEMPLATE_NAME", "catalog_alert").strip(),
                wa_params=[catalog["title"], f"{item_count} ürün taranıyor"],
                wa_button_param=f"aktuel/{catalog['store']}",
            )

    if notifications_added or fetched:
        save_db(db)


def refresh_product(product_id: str) -> dict[str, Any]:
    db = load_db()
    product = find_product(db, product_id)

    if not product:
        raise KeyError("Ürün bulunamadı")

    checked_at = utc_now()
    old_price = current_price(product)
    parsed = parse_product_url(product["url"])

    product["last_checked_at"] = checked_at
    was_out_of_stock = product.get("extra_info", {}).get("out_of_stock", False)

    if not parsed.price:
        product["last_check_status"] = "failed"
        product["last_check_message"] = (
            parsed.warnings[0] if parsed.warnings else "Güncel fiyat bulunamadı."
        )
        product["updated_at"] = checked_at
        save_db(db)
        return {
            "status": "failed",
            "price_changed": False,
            "old_price": old_price,
            "new_price": None,
            "message": product["last_check_message"],
            "product": product,
        }

    new_price = parsed.price
    product["last_check_status"] = "success"
    product["last_check_message"] = "Fiyat başarıyla kontrol edildi."
    product["updated_at"] = checked_at

    if parsed.title:
        product["title"] = parsed.title
    if parsed.image_url:
        product["image_url"] = parsed.image_url

    price_changed = abs(new_price - old_price) > 0.001
    drop_rate = (old_price - new_price) / old_price if old_price > 0 else 0
    push_notifications = []

    if was_out_of_stock and new_price > 0:
        product["extra_info"]["out_of_stock"] = False
        notification = {
            "id": str(uuid4()),
            "product_id": product["id"],
            "owner_id": product.get("owner_id"),
            "title": "Stok Geldi!",
            "message": f"{product['title']} tekrar stoklara girdi! Güncel Fiyat: {new_price:.2f} TL",
            "created_at": checked_at,
            "read": False,
            "type": "stock_back",
        }
        db["notifications"].insert(0, notification)
        push_notifications.append(notification)
        price_changed = True

    if price_changed:
        product["price_history"].append(
            {
                "price": new_price,
                "seen_at": checked_at,
                "source": "automatic",
            }
        )

    target_price = product.get("extra_info", {}).get("target_price")
    if target_price:
        try:
            target_price = float(target_price)
            crossed_target = (
                new_price <= target_price
                and (not old_price or old_price > target_price)
            )
            if crossed_target:
                notification = {
                    "id": str(uuid4()),
                    "product_id": product["id"],
                    "owner_id": product.get("owner_id"),
                    "title": "Hedef fiyata ulaşıldı",
                    "message": (
                        f"{product['title']} hedeflediğin fiyata "
                        f"({target_price:.2f} TL) ulaştı: "
                        f"Şu anki fiyat {new_price:.2f} TL!"
                    ),
                    "created_at": checked_at,
                    "read": False,
                    "type": "target_price_alert",
                }
                db["notifications"].insert(0, notification)
                push_notifications.append(notification)
                
                owner_id = product.get("owner_id")
                if owner_id and owner_id.startswith("user:"):
                    user_info = db.get("users", {}).get(owner_id, {})
                    email = user_info.get("email")
                    pref = user_info.get("notification_pref", "both")
                    if email and pref in ("email", "both"):
                        from app.notifier import send_user_email
                        html_body = f"""<div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:24px;">
  <h2 style="color:#287a50;margin:0 0 8px;">🎯 Hedef Fiyata Ulaşıldı!</h2>
  <p style="color:#444;margin:0 0 16px;">Takip ettiğin <strong>{product['title']}</strong> ürünü, hedeflediğin <strong>{target_price:.2f} TL</strong> fiyatına ulaştı!</p>
  <p style="color:#444;margin:0 0 16px;">Şu anki fiyatı: <strong style="color:#287a50;font-size:18px;">{new_price:.2f} TL</strong></p>
  <a href="{product.get('url', '#')}" style="display:inline-block;padding:10px 20px;background:#287a50;color:#fff;border-radius:8px;text-decoration:none;font-weight:700;">Hemen Satın Al →</a>
</div>"""
                        send_user_email(email, "🎯 Hedef Fiyata Ulaşıldı!", html_body)
        except (ValueError, TypeError):
            pass

    save_db(db)

    # Queue or dispatch each notification
    for notification in push_notifications:
        queue_or_dispatch_notification(db, product, notification)

    return {
        "status": "success",
        "price_changed": price_changed,
        "old_price": old_price,
        "new_price": new_price,
        "drop_rate": drop_rate,
        "message": product["last_check_message"],
        "product": product,
    }


def refresh_all_products() -> dict[str, Any]:
    db = load_db()
    product_ids = [product["id"] for product in db["products"]]
    results = []

    for product_id in product_ids:
        try:
            results.append(refresh_product(product_id))
        except Exception as exc:
            results.append(
                {
                    "status": "failed",
                    "product_id": product_id,
                    "message": str(exc),
                }
            )

    try:
        trigger_weekly_catalogs()
    except Exception:
        pass

    try:
        check_restock_alerts()
    except Exception:
        pass

    try:
        check_cosmetics_expiration()
    except Exception:
        pass

    try:
        flush_queued_notifications()
    except Exception:
        pass

    return {
        "checked": len(results),
        "successful": sum(result["status"] == "success" for result in results),
        "failed": sum(result["status"] == "failed" for result in results),
        "results": results,
    }


def refresh_owner_products(owner_id: str) -> dict[str, Any]:
    db = load_db()
    product_ids = [
        product["id"]
        for product in db["products"]
        if product.get("owner_id") == owner_id
    ]
    results = []

    for product_id in product_ids:
        try:
            results.append(refresh_product(product_id))
        except Exception as exc:
            results.append(
                {
                    "status": "failed",
                    "product_id": product_id,
                    "message": str(exc),
                }
            )

    return {
        "checked": len(results),
        "successful": sum(result["status"] == "success" for result in results),
        "failed": sum(result["status"] == "failed" for result in results),
        "results": results,
    }


def check_cosmetics_expiration() -> None:
    db = load_db()
    checked_at = utc_now()
    from datetime import datetime, timezone, timedelta
    
    def parse_iso(dt_str):
        try:
            if dt_str.endswith('Z'):
                dt_str = dt_str[:-1] + '+00:00'
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None
            
    now_dt = datetime.now(timezone.utc)
    notifications_added = False
    
    for p in db.get("products", []):
        extra = p.get("extra_info", {})
        opening_date_str = extra.get("opening_date")
        shelf_life = extra.get("shelf_life_months")
        
        if opening_date_str and shelf_life:
            opening_date = parse_iso(opening_date_str)
            if not opening_date:
                continue
                
            try:
                shelf_months = int(shelf_life)
                last_alerted_str = extra.get("last_expiration_alerted_date")
                if last_alerted_str:
                    last_alerted = parse_iso(last_alerted_str)
                    if last_alerted and last_alerted > opening_date:
                        continue
                        
                exp_date = opening_date + timedelta(days=shelf_months * 30)
                alert_date = exp_date - timedelta(days=15)
                
                if now_dt >= alert_date:
                    notification = {
                        "id": str(uuid4()),
                        "product_id": p["id"],
                        "owner_id": p.get("owner_id"),
                        "title": "Kozmetik Son Kullanma Uyarısı!",
                        "message": f"Açtığın '{p['title']}' kozmetik ürününün kullanım ömrü dolmak üzere! Güvenli kullanım için yenisiyle değiştirebilirsin.",
                        "created_at": checked_at,
                        "read": False,
                        "type": "cosmetic_expiration_alert"
                    }
                    db["notifications"].insert(0, notification)
                    notifications_added = True
                    p.setdefault("extra_info", {})["last_expiration_alerted_date"] = checked_at
                    
                    queue_or_dispatch_notification(db, p, notification)
            except Exception:
                pass
                
    if notifications_added:
        save_db(db)
