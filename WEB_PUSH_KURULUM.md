# Web Push Kurulumu

## 1. Vercel ortam degiskenleri

`E:\Almadan\VAPID-ANAHTARLARI\vercel-env.txt` dosyasindaki uc degeri
Vercel `Settings > Environment Variables` bolumune ekle:

- `VAPID_PUBLIC_KEY`
- `VAPID_PRIVATE_KEY`
- `VAPID_SUBJECT`

Bu dosyayi GitHub'a yukleme. `VAPID_PRIVATE_KEY` yalnizca backend tarafinda
kalmalidir.

## 2. Deploy

Degiskenleri ekledikten sonra Production deploy'u yeniden calistir.

## 3. Kullanim

- Masaustu ve Android: Almadan'da zil simgesine bas, bildirimleri `Ac`.
- iPhone/iPad: Safari paylasim menusunden `Ana Ekrana Ekle`, uygulamayi ana
  ekrandan ac, sonra zil simgesinden bildirimleri etkinlestir.

Bildirimler hedef fiyat yakalandiginda veya fiyat en az yuzde 5 dustugunde
gonderilir.
