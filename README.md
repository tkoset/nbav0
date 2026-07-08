# NBA Sticker Album — Veri Hattı

## Kurulum (bir kere yapılır)

1. Bu klasördeki dosyaları kendi GitHub reponuza yükleyin (public repo — Actions ücretsiz kotası ve raw dosya erişimi için).
2. Lokalde (veya Colab'da) bir kere çalıştırın:
   ```bash
   pip install nba_api
   python fetch_all_players.py
   ```
   Bu, `players.json` dosyasını oluşturur (tüm 30 takım, ~450-500 oyuncu: isim, pozisyon, forma no, foto linki).
3. `players.json`'ı da repoya commit'leyip push edin.
4. GitHub reponuzda **Settings → Actions → General → Workflow permissions** kısmından
   "Read and write permissions" seçeneğini açın (yoksa Action commit atamaz).
5. Bundan sonra `.github/workflows/daily.yml` her gün otomatik olarak:
   - Güncel kadroları çeker
   - `players.json` ile karşılaştırır (trade, yeni oyuncu, forma değişikliği, ayrılma)
   - Farkları `transactions.json` içine o güne ait yeni bir kayıt olarak ekler
   - Her iki dosyayı da repoya commit'ler

## Oyun arayüzünün veriye erişimi

Oyun arayüzü (Claude artifact) şu adreslerden JSON'ları okuyacak:

```
https://raw.githubusercontent.com/KULLANICI_ADIN/REPO_ADIN/main/players.json
https://raw.githubusercontent.com/KULLANICI_ADIN/REPO_ADIN/main/transactions.json
```

Bu adresler GitHub tarafından CORS'a açık şekilde sunulduğu için tarayıcıdan
doğrudan `fetch()` ile okunabilir, ekstra bir proxy/backend gerekmez.

Repo adını bana verdiğinde, oyun arayüzündeki placeholder URL'leri
gerçek reponla değiştiririm.

## Oyunu GitHub Pages ile yayınlama (Blogger'a gerek yok)

Bu repo zaten oyunun kendisini de barındırabilir — ekstra bir siteye gerek yok:

1. GitHub reponda **Settings → Pages** kısmına git.
2. "Build and deployment" altında **Source: Deploy from a branch** seç.
3. Branch olarak `main`, klasör olarak **/ (root)** seç, kaydet.
4. Birkaç dakika içinde oyun şu adreste yayında olur:
   ```
   https://KULLANICI_ADIN.github.io/REPO_ADIN/
   ```
5. `index.html` içindeki `CONFIG.PLAYERS_URL` / `TRANSACTIONS_URL` değerlerini
   kendi repona göre güncelle ve `CONFIG.USE_LIVE_DATA = true` yap.

Bu adres Android'de tarayıcıdan açılıp "Ana ekrana ekle" dendiğinde gerçek
bir app gibi ikonla açılır (PWA — `manifest.json` ve `sw.js` bunun için var).

### Save'ler nerede duruyor?

Oyun artık gerçek tarayıcı `localStorage`'ını kullanıyor (Claude'un kendi
artifact ortamına özel `window.storage` değil). Bunun anlamı:

- Sticker koleksiyonun, o an oyunu oynadığın **tarayıcı + cihaza bağlı**
  olarak saklanır.
- Telefonda ile bilgisayarda ayrı koleksiyonlar oluşur (otomatik senkron
  yok).
- Tarayıcı verilerini temizlersen koleksiyon da silinir.

İleride cihazlar arası senkron istersen, ücretsiz bir bulut veritabanı
(örn. Firebase Firestore free tier) eklenebilir — şimdilik bu kapsam dışı.



- **Sticker kartı**: doğum tarihi yerine **yaş**, boy **cm** olarak, ülke
  bayrağı yerine **3 harfli ülke kodu (örn. TUR)**, arkada takım logosu +
  NBA logosu **filigran** olarak. Kullanıcı kendi örnek tasarımını
  paylaşınca buna göre yeniden yapılacak.
- **Günlük sticker üretimi**: her gün sadece **3 oyuncu** için (wordle
  cevabı + 2 bonus) kart üretilecek, tüm oyuncular için toplu/batch işlem
  yapılmayacak. Arka plan silme (rembg) muhtemelen bir kereye mahsus tüm
  oyuncular için ön hazırlık olarak yapılacak; kart tasarımı (çerçeve/
  isim/numara/filigran) ise günlük sadece o 3 oyuncu için oluşturulacak.
- **Wordle seçim mantığı**: aday havuzu = owned (sahip olunan) oyuncular
  HARİÇ tüm oyuncular. Bilinmeyen/bilemediğin oyuncu tekrar çıkabilir,
  bildiğin (owned) oyuncu bir daha çıkmaz.
- **Günlük limit**: TR saatiyle (Europe/Istanbul, UTC+3) günde bir kez
  oynanabilir; oynadıktan sonra o günkü oyun alanı gri/greyed-out görünür.
- **Blogger'da barındırma**: HTML/JS gadget ile embed edilebilir. Persistan
  veri için `window.storage` (Claude artifact'e özel) yerine gerçek
  tarayıcı `localStorage`'a geçilecek.
- **Android**: responsive + PWA (manifest.json) ile "ana ekrana ekle"
  üzerinden app gibi kullanılabilir; istenirse Trusted Web Activity /
  Bubblewrap ile Play Store'a da taşınabilir.
- **Transaction senkronu**: oyuncu takas olduğunda `team_abbr` güncellenip
  albümde otomatik doğru takım sayfasında (owned olarak) görünür, eski
  takım sayfasından kalkar. Haber panelinde owned oyuncular için zaten
  vurgulu "STICKER TAŞINDI" bildirimi var.
