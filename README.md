# Almadan — Akıllı Alışveriş Asistanı

> Türkiye'nin lider fiyat karşılaştırma platformu. Gerçek zamanlı fiyat takibi, AI destekli arama ve kişiselleştirilmiş tasarruf önerileri.

---

## Mimari Genel Bakış

```
┌─────────────────────────────────────────────────────────────────┐
│                        Kullanıcı Katmanı                        │
│   PWA (Vanilla JS)  ·  iOS Kısayolu  ·  Android TWA            │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTPS / REST
┌─────────────────────────▼───────────────────────────────────────┐
│               Vercel Edge Network (fra1 bölgesi)                │
│   CDN Cache  ·  Edge Middleware  ·  Serverless Functions        │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │          FastAPI Uygulaması  (app/main.py)              │   │
│   │                                                         │   │
│   │  Güvenlik    Auth     Scraper   AI Katmanı   Ekosistem  │   │
│   │  ---------   ----     -------   ----------   ---------  │   │
│   │  CSRF/CORS   JWT      Parser    Semantic      Partner   │   │
│   │  Rate Limit  OAuth    Tracker   Forecast       Coupon   │   │
│   │  Security    Supabase Catalog   Vision         GroupBuy │   │
│   │  Headers     Auth     Matching  Guardrails     EcoScore │   │
│   │                                                         │   │
│   │  Kirılmazlık: CircuitBreaker  Retry  LRU Cache          │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
        ┌─────────────────┼──────────────────┐
        │                 │                  │
┌───────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐
│   Supabase   │  │   OpenAI     │  │  Replicate   │
│  PostgreSQL  │  │  GPT-4o      │  │  LLaVA-13B   │
│  pgvector    │  │  Embeddings  │  │  (async wh)  │
│  Auth        │  │  text-3-sm   │  └──────────────┘
│  Storage     │  └──────────────┘
└──────────────┘
        │
┌───────▼──────┐  ┌──────────────┐  ┌──────────────┐
│ ScrapingBee  │  │  Web Push    │  │  SMTP email  │
│ (proxy)      │  │  (VAPID)     │  │  (digest)    │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## Sprint Haritası (200 Madde)

| Sprint | Madde   | Tema                                           | Durum |
|--------|---------|------------------------------------------------|-------|
| 1–2    | 1–40    | Temel Altyapı (Auth, Scraper, Watchlist, PWA)  | Tamam |
| 3–4    | 41–80   | Katalog Otomasyonu + Fuzzy Matching             | Tamam |
| 5      | 81–100  | Analitik & Tutundurma (Dashboard, A/B, Puan)   | Tamam |
| 6      | 101–120 | AI Zeka Katmanı (Semantic, Forecast, Vision)   | Tamam |
| 7      | 121–140 | Ekosistem (Partner API, Kupon, GroupBuy, Eko)  | Tamam |
| 8      | 141–160 | Kirılmazlık (Circuit Breaker, Chaos, Cache)    | Tamam |
| 9      | 161–200 | Final: Uyumluluk, Dokümantasyon, IaC           | Devam |

---

## Teknoloji Yığını

| Katman          | Teknoloji                             | Neden?                             |
|-----------------|---------------------------------------|------------------------------------|
| **Backend**     | FastAPI (Python 3.11)                 | Async, OpenAPI otomatik, tip güvenli |
| **Veritabanı**  | Supabase PostgreSQL                   | RLS, Auth, Storage tek pakette     |
| **Vektör Arama**| pgvector (HNSW cosine)                | Supabase içinde, ek servis yok     |
| **AI**          | OpenAI GPT-4o + text-embedding-3-small| Görsel analiz + semantik arama     |
| **AI yedek**    | Replicate LLaVA-13B                   | OpenAI kesintisinde devreye girer  |
| **Scraper Proxy**| ScrapingBee                          | JS render + anti-bot aşımı         |
| **Deploy**      | Vercel (serverless, fra1)             | Sıfır DevOps, CDN dahil            |
| **Push**        | Web Push API (VAPID)                  | Tarayıcı bildirimleri              |
| **Email**       | SMTP (digest)                         | Haftalık tasarruf özeti            |
| **Güvenlik**    | CSRF, HMAC-SHA256, RLS                | Tüm katmanlarda savunma            |

---

## Uygulama Katmanları

### `app/` — Modüller

```
app/
├── main.py               # FastAPI app, tüm endpoint'ler (~4100 satır)
├── auth.py               # Supabase Auth, OAuth, JWT
├── security.py           # CSRF, rate limit, sanitize, admin guard
├── parser.py             # URL parser (Migros, CarrefourSA, Trendyol, A101...)
├── tracker.py            # Fiyat takibi, refresh döngüsü
├── storage.py            # Supabase CRUD, watchlist, fiyat geçmişi
├── scoring.py            # Deal score algoritması
├── shopping.py           # Sepet optimizasyonu, birim fiyat
├── forecast.py           # İndirim tahmini (basit)
├── push.py               # Web Push / VAPID
│
├── catalog_parser.py     # Katalog PDF/HTML parser
├── matching_engine.py    # Fuzzy matching (Jaccard + difflib)
│
├── analytics_engine.py   # Kullanıcı analitikleri, tasarruf paneli
├── ab_testing.py         # A/B test motoru (deterministic hash)
├── retention_service.py  # Puan sistemi, haftalık digest
│
├── semantic_search.py    # pgvector semantic arama, fallback n-gram
├── price_forecaster.py   # WLS regresyon + Prophet, guardrail
├── guardrails.py         # AI çıktı doğrulama, blocklist
├── ai_monitor.py         # Token/maliyet takibi, latency percentile
├── vision_analyzer.py    # GPT-4o / LLaVA buzdolabı analizi
│
├── partner_gateway.py    # Partner API key, HMAC webhook, rate limit
├── coupon_engine.py      # Puan → kupon dönüşümü, validasyon
├── group_buy.py          # Grup alışveriş motoru
├── eco_score.py          # Sürdürülebilirlik puanı
│
├── resilience.py         # Circuit Breaker, retry, fallback
├── cache_strategy.py     # LRU cache, CDN header preset'leri
├── observability.py      # Structured log, Sentry, PerformanceMiddleware
├── chaos.py              # Chaos engineering (fault injection)
│
├── gdpr.py               # KVKK/GDPR: forget, export, consent
└── openapi_config.py     # Swagger/OpenAPI metadata
```

### `migrations/` — Veritabanı Şeması

```
migrations/
├── 001_initial.sql                  # Temel tablolar
├── 002_watchlist_prices.sql         # Watchlist + fiyat geçmişi
├── 003_push_subscriptions.sql       # Web Push
├── 004_activity_log.sql             # Güvenlik audit
├── 005_catalog_automation.sql       # Katalog tarama
├── 006_sprint5_analytics.sql        # Analitik + A/B + puan
├── 007_sprint6_ai_intelligence.sql  # pgvector + tahmin + AI log
├── 008_sprint7_ecosystem.sql        # Partner + kupon + group_buy + eco
├── 009_sprint8_resilience.sql       # Metrik + circuit_breaker + chaos
└── 010_sprint9_compliance.sql       # GDPR + onay yönetimi
```

---

## Vercel Cron Jobs

| Endpoint                  | Zamanlama     | Görev                         |
|---------------------------|---------------|-------------------------------|
| `/cron/refresh-all`       | Her gün 05:00 | Tüm watchlist fiyatlarını güncelle |
| `/api/ai/worker`          | Her 5 dakika  | AI iş kuyruğunu işle          |
| `/cron/catalog-scan`      | Pzt+Perş 06:00| Katalog PDF tara              |
| `/cron/weekly-digest`     | Pzt 07:00     | Haftalık email özeti          |
| `/cron/semantic-index`    | Her gün 04:00 | pgvector indeksini güncelle   |
| `/cron/group-buy-expire`  | Her saat      | Süresi dolan grupları kapat   |
| `/cron/cleanup-metrics`   | Her gün 03:00 | Eski log/metrik temizle       |

---

## Güvenlik Mimarisi

```
İstek Akışı:
  Browser --> Vercel Edge --> FastAPI
                 |
                 |-- CORS kontrol (allow_origins whitelist)
                 |-- CSRF token doğrulama (state-changing request'ler)
                 |-- Rate limiting (sliding window, Supabase tablo)
                 |-- Auth wall (JWT doğrulama, Supabase Auth)
                 |-- Admin guard (user metadata.role = admin)
                 `-- Input sanitize (XSS temizleme, max_length)

Veri Güvenliği:
  - API key'ler   : SHA-256 hash DB'de saklanır, ham key gösterilmez
  - Webhook imzası: HMAC-SHA256 (timestamp + payload)
  - Replay koruması: 5 dakika webhook penceresi
  - Konum gizliliği: ilçe adı --> SHA-256[:8] hex hash
  - RLS           : Tüm tablolarda Row Level Security aktif
  - CSRF          : Her oturum için token, SameSite=Strict cookie
```

---

## AI Maliyet Tahmini

| Model                    | Kullanım        | Birim Maliyet       | Aylık Tahmin (10K kullanıcı) |
|--------------------------|-----------------|---------------------|------------------------------|
| text-embedding-3-small   | Arama/indeks    | $0.00002 / 1K token | ~$2                          |
| GPT-4o (vision)          | Buzdolabı analiz| $0.005 / 1K token   | ~$15                         |
| GPT-4o-mini              | Guardrail       | $0.00015 / 1K token | ~$1                          |
| Replicate LLaVA          | Vision yedek    | $0.0013 / saniye    | ~$5                          |
| **Toplam**               |                 |                     | **~$23/ay**                  |

---

## Yerel Geliştirme

```bash
# 1. Bağımlılıkları kur
pip install -r requirements.txt

# 2. Ortam değişkenlerini ayarla
cp .env.example .env
# SUPABASE_URL, SUPABASE_SERVICE_KEY, CSRF_SECRET, vb.

# 3. Sunucuyu başlat
uvicorn app.main:app --reload --port 8000

# 4. Swagger UI
# http://localhost:8000/docs

# 5. Testleri çalıştır
pytest tests/ -v
```

---

## Deployment (Vercel)

```bash
# Vercel CLI ile deploy
vercel --prod

# Gerekli environment değişkenleri:
# SUPABASE_URL           --> Supabase proje URL'i
# SUPABASE_SERVICE_KEY   --> Service role key (GIZLI - sadece Vercel'de sakla)
# CSRF_SECRET            --> openssl rand -base64 48  (GIZLI)
# CRON_SECRET            --> openssl rand -hex 16
# OPENAI_API_KEY         --> sk-...  (opsiyonel, embedding + vision için)
# REPLICATE_API_TOKEN    --> r8_...  (opsiyonel, vision yedek için)
# AI_WEBHOOK_SECRET      --> openssl rand -hex 32
# SCRAPING_BEE_KEY       --> ScrapingBee API key
# VAPID_PRIVATE_KEY      --> Web Push özel anahtar
# VAPID_PUBLIC_KEY       --> Web Push genel anahtar
# SMTP_HOST / SMTP_USER / SMTP_PASS  --> Haftalık digest email
# SENTRY_DSN             --> (opsiyonel) Sentry hata izleme
# CHAOS_ENABLED          --> true sadece staging ortamında
```

---

## API Dokümantasyonu

- **Swagger UI:** `https://almadan.vercel.app/docs`
- **ReDoc:**       `https://almadan.vercel.app/redoc`
- **OpenAPI JSON:** `https://almadan.vercel.app/openapi.json`

### Endpoint Grupları

| Grup           | Prefix                              | Endpoint |
|----------------|-------------------------------------|----------|
| Auth           | `/api/auth/`                        | 10       |
| Ürün Takibi    | `/api/products/`, `/api/watchlist/` | 12       |
| Alışveriş      | `/api/shopping/`                    | 4        |
| Arama          | `/api/search/`                      | 2        |
| Analitik       | `/api/dashboard/`, `/api/analytics/`| 8        |
| A/B Test       | `/api/ab/`                          | 4        |
| Puan           | `/api/points/`                      | 2        |
| AI             | `/api/forecast/`, `/api/vision/`    | 4        |
| Ekosistem      | `/api/coupons/`, `/api/group-buys/` | 11       |
| Partner        | `/api/partner/`                     | 3        |
| KVKK/GDPR      | `/api/me/`                          | 4        |
| Bildirimler    | `/api/push/`                        | 3        |
| Admin          | `/api/admin/`                       | 25+      |
| Sağlık         | `/health`                           | 1        |
| Cron           | `/cron/`                            | 7        |
| **Toplam**     |                                     | **~100** |

---

## KVKK / GDPR Uyumluluğu

| Hak                        | Endpoint                        | Yasal Dayanak     |
|----------------------------|---------------------------------|-------------------|
| Unutulma Hakkı             | `DELETE /api/me/forget`         | KVKK M.7 / GDPR Art.17 |
| Veri Erişim (SAR)          | `GET /api/me/export`            | KVKK M.11 / GDPR Art.15 |
| Onay Geri Alma             | `PUT /api/me/consent/{type}`    | KVKK M.5 / GDPR Art.7 |
| Onay Görüntüleme           | `GET /api/me/consents`          | KVKK M.11 |

Tüm GDPR talepleri `gdpr_requests` tablosuna audit logu olarak yazılır.

---

## Lisans

Bu proje **tescilli** (proprietary) yazılımdır. Tüm hakları saklıdır.

&copy; 2024–2026 Almadan. Tüm hakları saklıdır.
