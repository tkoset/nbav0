# NBA Sticker Album — Veri Hattı

## Veri kaynakları (önemli, güncel durum)

- **`fetch_all_players.py`** (bir kere, senin bilgisayarından): stats.nba.com
  kullanıyor. Bu, senin kendi (residential) IP'nden çalıştığı için sorunsuz.
- **`check_transactions.py`** (günlük, GitHub Actions üzerinde): **ESPN'in
  genel site API'sini** kullanıyor (`site.api.espn.com`), stats.nba.com değil.
  Neden: NBA, `stats.nba.com`'u bulut/datacenter IP'lerine (GitHub Actions
  dahil) Akamai bot korumasıyla kalıcı olarak kapatmış durumda — bu iyi
  belgelenmiş, çözümü olmayan bir kısıt. ESPN'in API'si bu kısıtlamaya tabi
  değil ve **key/signup gerektirmiyor**.

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
5. Bundan sonra `.github/workflows/daily.yml` her gün otomatik olarak (artık ESPN üzerinden, key gerekmeden):
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
artifact ortamına özel `window.storage` değil). Varsayılan olarak:

- Sticker koleksiyonun, o an oyunu oynadığın **tarayıcı + cihaza bağlı**
  olarak saklanır.
- Telefonda ile bilgisayarda ayrı koleksiyonlar oluşur (otomatik senkron
  yok).
- Tarayıcı verilerini temizlersen koleksiyon da silinir.

### Cihazlar arası save senkronu (GitHub üzerinden)

Oyuna 3 buton eklendi:

- **Save'i indir** / **Dosyadan yükle**: koleksiyonunu bir `.json` dosyası
  olarak indirip başka bir cihazda geri yükleyebilirsin. Token gerektirmez,
  en güvenli yöntem.
- **GitHub'a yükle** / **GitHub'dan çek**: koleksiyonunu doğrudan reponda
  `save.json` olarak saklar, böylece hangi cihazdan girersen gir aynı
  koleksiyonu görebilirsin.

GitHub senkronu için bir **fine-grained personal access token** gerekiyor
(oyunun "Token ayarla" butonuyla gireceksin):

1. https://github.com/settings/tokens → **Fine-grained tokens** → **Generate new token**
2. **Repository access** → sadece bu repoyu seç (tüm hesaba erişim verme)
3. **Permissions → Contents → Read and write** seç, diğer izinleri kapalı bırak
4. Token'ı oluştur, oyunda "Token ayarla" butonuna yapıştır

**Önemli güvenlik notu:** Bu token yalnızca kendi tarayıcının
`localStorage`'ında saklanır, koda/repoya asla yazılmaz. Yine de:
- Sadece bu repoya ve sadece "içerik yazma" iznine sahip olacak şekilde
  oluştur (yukarıdaki adımlar bunu sağlıyor).
- Token'ı **paylaşılan/ortak bir bilgisayara** girme.
- `CONFIG.GITHUB_OWNER` / `GITHUB_REPO` alanlarını kendi kullanıcı adın ve
  repo adınla güncellemeyi unutma.

## Konuşulan / karar verilen tasarım noktaları

- **Veri kaynağı geçmişi**: v1 stats.nba.com (GitHub Actions'ta kalıcı
  bloklandı) → v2 planı BALLDONTLIE idi (key + rate limit gerektiriyordu) →
  **v3 (güncel): ESPN'in genel site API'si, key gerekmiyor.**
- **Yeni oyuncu doğrulama**: Günlük iş, ESPN'den gelen isimleri players.json'daki
  NBA person_id kayıtlarıyla İSİM üzerinden eşleştirir. Eşleşmeyen (gerçekten
  yeni) oyuncular `_unverified: true` ve geçici bir `espn:...` ID'siyle
  eklenir, fotoğrafları silüet kalır. Bu oyuncular bir sonraki
  `fetch_all_players.py` çalıştırmanda gerçek NBA person_id + fotoğrafla
  düzelir. Terminal çıktısında "isim eşleşmesiyle 'yeni' sayıldı" notunu
  görürsen, ara sıra `fetch_all_players.py`'ı tazelemek iyi olur.

- **Takım logoları**: standart, ücretsiz bir kaynaktan indirilecek (henüz
  yapılmadı). Adaylar: NBA'in kendi CDN'i (`cdn.nba.com/logos/nba/{team_id}/...`
  benzeri bir örüntü, henüz doğrulanmadı) ya da açık kaynak
  `sportslogos.net` / GitHub üzerindeki ücretsiz SVG logo setleri. Bir
  dahakine bunu netleştirip `players.json`'a `team_logo_url` gibi bir alan
  eklenecek.
- **Sticker kartı**: doğum tarihi yerine **yaş**, boy **cm** olarak, ülke
  bayrağı yerine **3 harfli ülke kodu (örn. TUR)**, arkada takım logosu +
  NBA logosu **filigran** olarak. Kullanıcı kendi örnek tasarımını
  paylaşınca buna göre yeniden yapılacak.
- **Günlük sticker üretimi**: her gün sadece **3-5 oyuncu** için (wordle
  cevabı + ödül sayısı kadar bonus) kart üretilecek, tüm oyuncular için
  toplu/batch işlem yapılmayacak.
- **Wordle kuralları (UYGULANDI)**:
  - 5 tahmin hakkı. Fotoğraf blur'u her yanlışta 3px azalır: 18→15→12→9→6px
    (son hak dahil hiçbir zaman tam netleşmez, cevap açıklanana kadar).
  - İpucu sırası (kullanıcının kendi bilgi seviyesine göre kişiselleştirildi):
    **Pozisyon → Yaş → Boy → Uyruk → Takım + Forma No (birlikte, son hakta)**.
    Forma No TEK BAŞINA hiç kullanılmıyor (kullanıcı sadece 1-2 takımın
    numaralarını biliyor, tek başına anlamsız); ama son hakta Takım ile
    birlikte verilince "en azından sticker'ı kurtar" mantığıyla güçlü bir
    kombinasyon oluyor. Boy, pozisyonla ilişkili olduğu için bilerek ortalara
    alındı (hemen ardına konmadı). Uyruk, ödülün 2 stickere düştüğü ana denk
    getirildi (getiri-götürü dengesi için).
  - Ödül: 1. tahminde doğru bilirsen **5 sticker** (kendisi + 4 bonus),
    2.'de **4**, 3.'te **3**, 4.'te **2**, son (5.) hakta sadece **1**
    (yalnızca sorulan oyuncu, bonus yok).
  - Wordle seçim havuzu = owned (sahip olunan) oyuncular **hariç** tüm
    oyuncular. Bilemediğin oyuncu tekrar çıkabilir, bildiğin (owned)
    oyuncu bir daha çıkmaz. Bonus stickerlarda ise tekrar/duplicate normal
    (owned olsa da çıkabilir, "zaten vardı" rozetiyle gösterilir).
  - Günün hedef oyuncusu ilk hesaplandığında `daily:{tarih}` kaydına
    sabitleniyor (`targetPlayerId`) — böylece gün içinde owned listesi
    değişse bile aynı günün tekrar açılmasında hedef oyuncu kaymıyor.
  - TR saatiyle (Europe/Istanbul) günde bir kez oynanabilir; oynadıktan
    sonra günün kartı (`.daily-card`) griye dönüp "oynandı" görünümü alıyor.
- **Albüm sidebar (UYGULANDI)**: takım isimleri solda dikey bir sidebar'da,
  her biri eski adres defterlerindeki A-Z sekmeleri gibi kademeli
  (staggered) görünüyor; tıklanan takım aktif/seçili stile geçiyor.
- **Blogger'da barındırma**: gerekmiyor, GitHub Pages yeterli (yukarıda
  anlatıldı).
- **Android**: responsive + PWA (manifest.json) ile "ana ekrana ekle"
  üzerinden app gibi kullanılabilir.
- **Transaction senkronu**: oyuncu takas olduğunda `team_abbr` güncellenip
  albümde otomatik doğru takım sayfasında (owned olarak) görünür.
