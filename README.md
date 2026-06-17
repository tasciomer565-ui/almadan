# Almadan — Akıllı Fiyat Karşılaştırma Asistanı

Türkiye'deki online mağazaları gerçek zamanlı tarayarak en uygun fiyatı bulan PWA (Progressive Web App).

---

## Nasıl Çalışır?

Kullanıcı bir ürün adı yazar (örn: "süt", "Samsung S24", "Adidas spor ayakkabı"). Sistem:

1. **Kategori tespiti** — arama metnini analiz ederek doğru mağaza grubuna yönlendirir (market, elektronik, moda, kozmetik, ev)
2. **Paralel arama** — seçilen grubun mağazalarını eş zamanlı tarar
3. **Sonuç karşılaştırma** — fiyat, kargo, stok durumu ve 7 günlük fiyat trendi ile sıralar
4. **Cache** — sonuçlar 6 saat Supabase'de tutulur; aynı sorgu saniyeler içinde yanıtlanır

---

## Cache Mantığı

```
Kullanıcı arar
    │
    ├─ 1. Taze cache var mı?  ──→ EVET → Anında döner (< 100ms)
    │
    ├─ 2. HAYIR → Canlı kaynakları paralel çek (max 8 sn)
    │   ├─ CarrefourSA  (ScrapingBee proxy)
    │   ├─ Migros       (ScrapingBee proxy)
    │   └─ N11          (direkt scraping)
    │
    ├─ 3. Hepsi başarısız → Marketplace fallback (Trendyol / Amazon)
    │
    └─ 4. O da başarısız → Süresi dolmuş cache (stale)
             └─ ⚠️  "X saat önceki fiyatlar" uyarısı + "Tazele" butonu
```

Cache süresi: **6 saat** (`.env` ile `CACHE_TTL_HOURS` değiştirilebilir)
Manuel tazeleme: Arama sonucundaki **"Fiyatı Güncelle"** butonu cache'i siler ve taze veri çeker.

---

## AI Modülleri

### Barkod Okuma
- Kamera ile EAN-8, EAN-13, UPC-A, UPC-E formatlarını okur
- Önce özel veritabanını sorgular; bulunamazsa [Open Food Facts](https://world.openfoodfacts.org/) API'sini kullanır
- Bulunan ürün alışveriş listesine otomatik eklenir

### VTON (Sanal Kıyafet Deneme)
- Kullanıcı portre fotoğrafı + kıyafet görseli yükler
- İş `vton_jobs` tablosuna kuyruğa alınır
- [Replicate IDM-VTON](https://replicate.com/yisol/idm-vton) modeli kıyafeti portre üzerine giydirerek sonuç görseli üretir
- `REPLICATE_API_TOKEN` yoksa mock mod çalışır (test için kıyafet görselini döndürür)
- Durum: `GET /api/vton/{job_id}` ile sorgulanır

### Fiyat Geçmişi
- Her başarılı arama sonucu `price_history` tablosuna kaydedilir
- 7 günlük veri birikince ürün kartında **"%5 düştü"** / **"%3 arttı"** göstergesi çıkar

---

## Teknik Yığın

| Katman | Teknoloji |
|--------|-----------|
| Backend | Python 3.11, FastAPI, Vercel Serverless |
| Veritabanı | Supabase (PostgreSQL) |
| Scraping | BeautifulSoup, ScrapingBee (proxy) |
| Arama | AOL Search, N11 direkt |
| Auth | Supabase Auth (e-posta OTP + SMS OTP) |
| Frontend | Vanilla JS PWA, html5-qrcode, Lucide Icons |
| AI/ML | Replicate IDM-VTON, Open Food Facts |

---

## Kurulum

### Gereksinimler
- Python 3.11+
- Supabase hesabı
- Vercel hesabı

### Environment Variables

```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_PUBLISHABLE_KEY=eyJ...
SCRAPINGBEE_API_KEY=xxx          # CarrefourSA/Migros için (opsiyonel)
REPLICATE_API_TOKEN=r8_xxx       # VTON için (opsiyonel)
CACHE_TTL_HOURS=6                # Cache süresi (varsayılan: 6)
```

### Supabase Tablolarını Oluştur

SQL Editor'dan sırasıyla çalıştırın:
- `migrations/001_product_cache.sql`
- `migrations/002_price_history_and_admin.sql`

### Yerel Çalıştırma

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

---

## Admin Paneli

`https://almadan.vercel.app?admin=1` adresini açıp **F2** tuşuna basın.

Gösterir: Cache hit oranı, günlük arama sayısı, proxy kullanımı, stale fallback sayısı.

---

## Desteklenen Mağazalar

| Kategori | Mağazalar |
|----------|-----------|
| Market (GIDA) | Migros, CarrefourSA, Şok, Metro |
| Elektronik | Teknosa, MediaMarkt, Vatan, İtopya |
| Kozmetik | Gratis, Rossmann, Watsons, Sephora |
| Moda | LCW, DeFacto, Koton, Mavi, Boyner, Zara |
| Ev | Karaca, English Home, Madame Coco, IKEA, Koçtaş |
| Pazaryeri | Trendyol, Hepsiburada, Amazon TR, N11 |

> BİM, A101, File Market online sipariş almadığı için sistemde yer almaz.

---

## Debug & Loglama

Backend logları Vercel Dashboard → Functions → Logs'tan izlenir.

Yerel debug için:

```bash
LOG_LEVEL=DEBUG uvicorn app.main:app --reload
```

Kritik log satırları:

| Log | Anlamı |
|-----|--------|
| `Cache HIT: {key}` | Cache'den döndü |
| `Cache SET: {key}` | Yeni sonuç kaydedildi |
| `Stale cache fallback` | Eski veri kullanıldı |
| `ScrapingBee OK: {url}` | Proxy başarılı |
| `ScrapingBee 403: {url}` | Proxy de engellenmiş |

### Modül Bazlı Debug

**Barkod:** Tarayıcı konsolunda `html5QrCode` loglarını izleyin. Kamera açılıyor ama okumuyorsa ışığı artırın veya barkodu çerçeveye daha yakın tutun.

**SMS Giriş:** `/api/auth/otp/send` isteğini Network sekmesinden kontrol edin. `phone` alanı `+90XXX...` formatında olmalıdır.

**VTON:** `GET /api/vton/{job_id}` ile status `processing` → `done` geçişini izleyin. `failed` dönüyorsa Vercel loglarında Replicate hata mesajını görürsünüz.
