# Render'a Geçiş Rehberi

Vercel hesabı ücretsiz plan CPU limitini aştığı için "Paused" duruma düştü.
Bu rehber, aynı kodu Render.com'da (ücretsiz veya $7/ay Starter plan) canlıya
almak için gereken adımları anlatır.

## 1. Render Hesabı ve Servis

1. `https://dashboard.render.com` adresinde GitHub ile giriş yap.
2. `New > Blueprint` seç, GitHub'daki `almadan` deposunu bağla.
3. Render, repodaki `render.yaml` dosyasını otomatik okuyacak ve servisi
   oluşturacak.
4. Blueprint kurulumu sırasında Render, `render.yaml`'da `sync: false`
   olarak işaretlenmiş her ortam değişkeni için sana bir giriş alanı
   gösterecek. Bu değerleri **Vercel'deki mevcut proje ayarlarından**
   (`Vercel Dashboard > almadan > Settings > Environment Variables`)
   birebir kopyala -- yeni değer üretme, aynısını kullan.

   En kritik olanlar:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_PUBLISHABLE_KEY`
   - `CRON_SECRET` -- **GitHub Actions'taki `secrets.CRON_SECRET` ile aynı
     değer olmalı**, aksi halde `.github/workflows/*.yml` içindeki cron
     tetikleyicileri 401 hatası alır.
   - `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`
   - `NETGSM_USERCODE`, `NETGSM_PASSWORD`, `NETGSM_MSGHEADER`

   Kalanlar (WhatsApp, SMTP, Replicate, Google Sheets vb.) hangi
   özellikleri kullanıyorsan onları doldur; boş bırakılırsa ilgili özellik
   sessizce devre dışı kalır (uygulama çökmez).

5. Deploy tamamlanınca geçici bir adres oluşur:
   ```
   https://almadan.onrender.com
   ```
   Bu adreste sitenin sorunsuz açıldığını doğrula (`/health` endpoint'i
   `{"status": "ok"}` dönmeli).

## 2. Domain'i Render'a Taşı

1. Render'da `almadan` servisinin `Settings > Custom Domains` bölümüne git,
   `almadan.app` ve `www.almadan.app` ekle.
2. Render'ın verdiği DNS kayıtlarını (genelde bir `CNAME` veya `A` kaydı)
   domain sağlayıcındaki (Vercel'de mi yoksa ayrı bir domain kayıt firmasında
   mı olduğuna bağlı) DNS ayarlarına ekle.
3. DNS yayılması birkaç dakika ile birkaç saat sürebilir.
4. Yayıldıktan sonra `https://www.almadan.app` Render'daki uygulamayı
   göstermeye başlar -- `.github/workflows/*.yml` içindeki cron URL'leri
   zaten `https://www.almadan.app/...` kullandığı için **hiçbir değişiklik
   gerekmez**, otomatik olarak Render'ı tetiklemeye devam ederler.

## 3. Vercel'i Kapat (isteğe bağlı)

Domain tamamen Render'a taşındıktan ve birkaç gün sorunsuz çalıştığını
doğruladıktan sonra Vercel projesini silebilir ya da sadece devre dışı
bırakabilirsin -- artık trafik almayacağı için CPU limiti sorunu da ortadan
kalkar.

## 4. Kontrol

Şu adresler çalışmalı:
```
https://www.almadan.app/
https://www.almadan.app/health
```

`/health` cevabı:
```json
{"status": "ok"}
```

Render ücretsiz planı 15 dakika trafiksizlikte uyur; ilk istek bu yüzden
~30-60 saniye sürebilir. `.github/workflows/warm-price-cache.yml` ve
`catalog-crawl.yml` zaten 30 dakikada/saatte bir siteye istek attığı için
pratikte site çoğu zaman uyanık kalır. Sorun yaşarsan Starter plana
($7/ay) geçmek uyku sorununu tamamen ortadan kaldırır.
