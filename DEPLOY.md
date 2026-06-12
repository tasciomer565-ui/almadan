# Ücretsiz Yayınlama: Supabase + Render + cron-job.org

## Supabase Auth

Hesap girişini etkinleştirmek için Supabase `Project Settings > API Keys`
bölümündeki publishable anahtarı Vercel ortam değişkenlerine ekle:

```text
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
```

`SUPABASE_SERVICE_KEY` yalnızca backend veri erişimi içindir. Publishable ve
secret anahtarları birbirinin yerine kullanılmamalıdır.

Supabase `Authentication > URL Configuration` bölümünde:

```text
Site URL=https://almadan.vercel.app
```

değerini kullan. E-posta onayı açıksa kullanıcı bu adrese geri yönlendirilir.

## 1. Supabase Veritabanı

1. `https://supabase.com/dashboard` adresinde ücretsiz hesap aç.
2. `New project` ile bir proje oluştur.
3. Proje açılınca `SQL Editor` bölümüne gir.
4. Projedeki `supabase.sql` dosyasının tamamını çalıştır.
5. `Project Settings > API Keys` bölümünden şunları al:
   - Project URL
   - `service_role` secret key

`service_role` anahtarını kimseyle paylaşma ve frontend koduna koyma.

## 2. GitHub Deposu

1. `https://github.com/new` adresinde yeni bir depo oluştur.
2. Depo adı olarak `almadan` kullanabilirsin.
3. Depoyu `Private` yapabilirsin.
4. Proje dosyalarını depoya yükle.

Yüklenmesi gereken ana dosyalar:

- `app/`
- `requirements.txt`
- `render.yaml`
- `supabase.sql`
- `README.md`
- `.gitignore`

`.env`, `data/db.json`, `__pycache__` ve test ekran görüntülerini yükleme.

## 3. Render Web Servisi

1. `https://dashboard.render.com` adresinde GitHub ile giriş yap.
2. `New > Blueprint` seç.
3. GitHub'daki `almadan` deposunu bağla.
4. Render, `render.yaml` dosyasını otomatik okuyacak.
5. İstenen ortam değişkenlerini gir:

```text
SUPABASE_URL=https://PROJE_KODUN.supabase.co
SUPABASE_SERVICE_KEY=SUPABASE_SERVICE_ROLE_ANAHTARI
```

`CRON_SECRET` Render tarafından otomatik üretilecek.

Deploy tamamlanınca şöyle bir adres oluşur:

```text
https://almadan.onrender.com
```

## 4. Zamanlanmış Fiyat Kontrolü

1. Render servisinde `Environment` bölümünden `CRON_SECRET` değerini görüntüle.
2. `https://console.cron-job.org/signup` adresinde ücretsiz hesap aç.
3. Yeni cron işi oluştur.
4. URL:

```text
https://RENDER-ADRESIN.onrender.com/cron/refresh-all
```

5. İstek yöntemi: `POST`
6. Her 6 saatte bir çalışacak şekilde ayarla.
7. İstek başlığı ekle:

```text
X-Cron-Secret: RENDERDAKI_CRON_SECRET
```

## 5. Kontrol

Şu adresler çalışmalı:

```text
https://RENDER-ADRESIN.onrender.com/
https://RENDER-ADRESIN.onrender.com/health
```

`/health` cevabı:

```json
{
  "status": "ok"
}
```

Render ücretsiz servisleri trafiksizlikte uyuyabilir. İlk açılış bu nedenle yaklaşık
bir dakika sürebilir.
