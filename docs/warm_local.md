# Önbellek ısıtmayı yerel bilgisayardan çalıştırma

## Neden

Canlı arama, çok mağazalı sonucu `product_cache` tablosundan okur. Bu tabloyu
GitHub Actions'taki ısıtma workflow'u dolduruyor, ama GitHub'ın runner'ı yurt
dışı veri merkezi IP'si kullanıyor ve Türk mağazalarının çoğu buradan yanıt
vermiyor: 2026-11-08'de 120 terimin 114'ünde yalnızca tek mağaza döndü, 5'inde
hiç sonuç gelmedi. Aynı betik Türk Telekom IP'sinden N11, Amazon, MediaMarkt,
Vatan ve Karaca'yı birlikte döndürüyor.

Çözüm: betiği, Türkiye'deki bilgisayardan zamanlanmış görev olarak çalıştırmak.

## Kurulum (bir kez)

1. Proje kökünde `.env.warm` dosyası oluştur (`.gitignore`'da, repoya girmez):

   ```
   SUPABASE_URL=https://xxxx.supabase.co
   SUPABASE_SERVICE_KEY=...
   ```

   Değerler Render'daki ortam değişkenleriyle aynıdır. **service_role** anahtarı
   tam yetkilidir: dosyayı kimseyle paylaşma, sohbete yapıştırma.

2. Önce denemeyi çalıştır (veritabanına yazmaz):

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\warm_local.ps1 -Limit 20 -DryRun
   ```

   İlk çalışmada `.venv-warm` kurulur (birkaç dakika). Çıktıda `yazilacakti`
   satırlarının yanında birden fazla mağaza adı görmelisin.

3. Gerçek çalıştırma:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\warm_local.ps1 -Limit 400
   ```

4. Zamanlanmış görev (2 saatte bir, bilgisayar açıkken):

   ```powershell
   schtasks /create /tn "AlmadanWarm" /sc HOURLY /mo 2 /tr "powershell -NoProfile -ExecutionPolicy Bypass -File E:\Almadan\proje\scripts\warm_local.ps1"
   ```

   Kaldırmak için: `schtasks /delete /tn "AlmadanWarm" /f`

Günlük: `app_logs/warm_local.log`.

## Sınırlar

- Bilgisayar kapalıyken ısıtma çalışmaz; kayıtların ömrü 48 saattir, bu süre
  içinde bir kez çalışması yeterlidir.
- GitHub workflow'u kalabilir: yerel çalışma çok mağazalı kaydı yazar, workflow
  tek mağazalı yeni veriyle çok mağazalı eski kaydı ezmez (`atlandi:az-magaza`).
- Kalıcı çözüm Türkiye çıkışlı ücretli bir proxy servisidir (ScrapingBee/
  Scrapingdog, `country=tr`); o zaman bilgisayarın açık olması gerekmez.
