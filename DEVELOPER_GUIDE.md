# Almadan — Developer Guide

> **1 sayfalık teknik özet** — Yeni bir geliştirici için sistemi 5 dakikada anlatır.

---

## Nedir?

Almadan; Türkiye pazarı için barkod + URL bazlı fiyat takibi yapan bir PWA (Progressive Web App).  
Backend: FastAPI (Python) → Vercel serverless. Database: Supabase (PostgreSQL + pgvector).

---

## Dizin Yapısı

```
app/
  main.py            # Tüm FastAPI endpoint'leri (~4300 satır, 9 sprint)
  matching_engine.py # FuzzyMatcher — Jaccard + difflib + substring
  resilience.py      # CircuitBreaker + retry + LRU cache
  notifier.py        # Telegram + SMTP hata bildirimleri
  gdpr.py            # KVKK/GDPR: sil, dışa aktar, denetle
  openapi_config.py  # Swagger/ReDoc şema özelleştirmesi
  static/
    index.html       # Minimal UI (Search + Barcode + Results)
    app.js           # ~360 satır vanilla JS
    sw.js            # Service Worker (PWA offline)

tests/
  health_check_test.py  # 7 test → app_logs/last_test.json + failure.log
  test_notifier.py      # 16 test — Telegram/SMTP mock
  test_sprint9_compliance.py  # GDPR + OpenAPI testleri

migrations/           # 010 dosya, Supabase'e sırayla uygulanır
vercel.json           # Routing + cron tanımları
```

---

## Yerel Geliştirme

```bash
# 1. Bağımlılıklar
pip install -r requirements.txt

# 2. .env.local oluştur (Vercel env'ini kopyala)
cp .env.example .env.local

# 3. Sunucuyu başlat
uvicorn app.main:app --reload --port 8000

# 4. Testleri çalıştır
python -m pytest tests/ -v

# 5. Health check (app_logs/ klasörü gerekli)
python -m pytest tests/health_check_test.py -v
```

---

## Kritik Ortam Değişkenleri

| Değişken | Açıklama |
|---|---|
| `SUPABASE_URL` | Supabase proje URL'i |
| `SUPABASE_SERVICE_KEY` | service_role key (admin erişim) |
| `CSRF_SECRET` | ⚠️ Sadece Vercel'de saklansın, paylaşılmasın |
| `TELEGRAM_BOT_TOKEN` | Hata bildirimi için BotFather token |
| `TELEGRAM_CHAT_ID` | Telegram chat/grup ID |
| `NOTIFY_EMAIL` | Hata e-posta adresi |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASS` | SMTP ayarları |

---

## Temel Akışlar

### Barkod → Sonuç
```
Kamera (Html5Qrcode)
  → GET /api/barcode/{ean}
  → OpenFoodFacts API (fallback: UPCitemdb)
  → FuzzyMatcher.score() ≥ 0.60 filtresi   ← kritik kapı
  → Market araması → sıralı sonuçlar
```

### URL Takibi
```
POST /api/track { url }
  → meta-tag scraper (og:price, og:title)
  → Supabase kayıt + bildirim
```

### Health Check → Bildirim
```
POST /api/admin/run-health-check
  → pytest tests/health_check_test.py
  → app_logs/last_test.json güncelle
  → failure ise: Telegram + email bildir
  → success + önceki failure ise: recovery bildir
```

---

## Deployment (Vercel)

```bash
vercel --prod
```

`vercel.json` otomatik yönlendirir: `/api/*` → `app/main.py`.  
Sunucusuz fonksiyon zaman aşımı: **10 saniye** (fra1 region).

---

## Güvenlik Notları

- API anahtarları DB'de **SHA-256 hash** olarak saklanır, asla plain-text değil.
- Tüm tablolarda Supabase **RLS (Row Level Security)** aktif.
- CSRF token `CSRF_SECRET` ile imzalanır; rotasyon gerekirse Vercel'de değiştir.
- GDPR: `/api/me/forget` → 9 tablo + Supabase Auth kaydını siler, audit log tutar.

---

## Katkı

1. `main` branch'e direkt push yapma — PR aç.
2. Yeni endpoint eklerken `tests/` altına test yaz.
3. Migration dosyalarını `migrations/NNN_açıklama.sql` formatında ekle.
4. `app_logs/` klasörü `.gitignore`'da değil ama içeriği `.gitkeep` dışında commit'lenmiyor.
