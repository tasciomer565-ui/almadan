# Fırsat Asistanı MVP

## Hesaplar

Supabase Auth etkinleştirildiğinde kullanıcılar e-posta ve şifre ile hesap
oluşturabilir. Giriş sırasında aynı cihazdaki mevcut takipler hesaba taşınır ve
başka cihazlarda aynı hesapla görüntülenir. Giriş yapmayan kullanıcılar cihaz
kimliğiyle uygulamayı kullanmaya devam eder.

Bu ilk MVP, mobil uygulamanın bağlanacağı backend çekirdeğidir.

## Ne Yapar?

- Ürün ekler.
- Fiyat geçmişi tutar.
- Fırsat skoru hesaplar.
- `al`, `düşünülebilir`, `takip et`, `bekle` kararı verir.
- Günlük en iyi fırsatları listeler.
- Takip edilen ürünleri 6 saatte bir yeniden kontrol eder.
- `%5` ve üzeri fiyat düşüşlerinde uygulama içi bildirim oluşturur.
- Otomatik fiyat bulunamazsa eski fiyatı ve geçmişi korur.

## Çalıştırma

```powershell
cd "C:\Users\Ömer Taşcı\Documents\Codex\2026-06-10\files-mentioned-by-the-user-bot\work\firsat-asistani"
python -m uvicorn app.main:app --reload --port 8000
```

Sonra tarayıcıdan aç:

```text
http://127.0.0.1:8000/
```

API test ekranı:

```text
http://127.0.0.1:8000/docs
```

## Önemli Uçlar

- `GET /health`
- `GET /products`
- `POST /products`
- `POST /parse-url`
- `POST /products/from-url`
- `POST /products/{product_id}/prices`
- `POST /products/{product_id}/refresh`
- `POST /refresh-all`
- `GET /notifications`
- `GET /daily-deals`

## Otomatik Takip

Uygulama çalıştığı sürece otomatik kontrol motoru 6 saatte bir devreye girer.
Ana ekrandaki `Fiyatları kontrol et` düğmesiyle tüm ürünler hemen kontrol edilebilir.
Ürün detayındaki `Şimdi otomatik kontrol et` düğmesi yalnızca seçilen ürünü kontrol eder.

## Buluta Yayınlama

Ücretsiz Supabase, Render ve cron-job.org kurulum adımları için `DEPLOY.md`
dosyasını takip et.

## Linkten Ürün Okuma

`POST /parse-url` isteği:

```json
{
  "url": "https://magaza.example.com/urun"
}
```

Sistem mümkünse şu bilgileri çıkarır:

- Ürün başlığı
- Güncel fiyat
- Ürün görseli
- Kaynak site
- Güven skoru
- Eksik bilgi uyarıları

`POST /products/from-url` aynı işlemi yapar ve ürünü doğrudan takip listesine ekler.
Otomatik fiyat bulunamazsa `fallback_title` ve `fallback_price` gönderilebilir.

## Ürün Vizyonu

Bu uygulama sadece indirim göstermez. Kullanıcıya alışveriş kararında yardımcı olur:

- Bu fiyat gerçekten iyi mi?
- Şimdi alınır mı?
- Beklemek mantıklı mı?
- Son fiyat geçmişine göre fırsat skoru kaç?
