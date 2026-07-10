"""
make_sticker.py
----------------------------------
ESPN'den gelen oyuncu fotoğrafını (a.espncdn.com/i/headshots/nba/players/full/...)
alıp Panini tarzı bir NBA çıkartması üretir: takım renginde çerçeve, sol üstte
ülke bayrağı rozeti, sağ üstte forma numarası rozeti, altta isim bandı ve
doğum tarihi bandı.

ÖNEMLİ DEĞİŞİKLİK: ESPN'in oyuncu fotoğrafları zaten arka planı temizlenmiş
(şeffaf/kesilmiş) geliyor gibi görünüyor -- bu yüzden artık rembg ile ayrıca
arka plan silme adımına GEREK YOK. Sadece beyaz outline + gölge ekliyoruz.
Yine de foto şeffaf gelmezse (tam opak/arka planlı çıkarsa) diye bir güvenlik
kontrolü var: eğer rembg kuruluysa otomatik devreye girer, kurulu değilse
uyarı basıp foto olduğu gibi kullanılır (outline/gölge o durumda anlamsız
görünebilir, ama script çökmez).

Kullanım:
    python make_sticker.py <espn_foto.png> <player_id>

player_id, players.json içindeki oyuncuya karşılık gelmeli (isim, forma no,
takım, yaş, uyruk gibi bilgiler oradan okunur; players.json artık ESPN ID'si
ve `height_cm` alanı kullanıyor).

TODO (kullanıcının kendi örneği gelince uygulanacak -- henüz YAPILMADI):
- Doğum tarihi yerine YAŞ gösterilecek (age alanı zaten players.json'da var)
- Ülke bayrağı KALDIRILACAK, yerine "TUR" gibi 3 harfli ülke kodu yazılacak
- Takım logosu + NBA logosu arka planda filigran (watermark) olarak eklenecek
- Kullanıcı kendi örnek tasarımını yollayacak, o örnek baz alınarak yeniden düzenlenecek
"""

import json
import math
import sys
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_COND = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"

CARD_W, CARD_H = 600, 800
BORDER = 16
INNER_BORDER = 5

OUTLINE_PX = 16       # beyaz çerçevenin kalınlığı
SHADOW_OFFSET_X = 40
SHADOW_OFFSET_Y = 30
SHADOW_ALPHA = 180


def has_real_transparency(img: Image.Image) -> bool:
    """Alfa kanalında gerçek şeffaflık var mı kontrol eder (min < 250 gibi bir
    eşik) -- ESPN fotoğrafı beklenildiği gibi zaten kesilmiş mi diye bakmak için."""
    alpha = img.getchannel("A")
    return alpha.getextrema()[0] < 250


def prepare_cutout(photo_path: str) -> Image.Image:
    """ESPN fotoğrafını açar. Zaten şeffafsa olduğu gibi döner. Değilse
    (beklenmedik şekilde opak/arka planlı gelirse) rembg kuruluysa onunla
    arka planı siler, kurulu değilse uyarı basıp fotoğrafı olduğu gibi kullanır."""
    img = Image.open(photo_path).convert("RGBA")

    if has_real_transparency(img):
        return img

    print("UYARI: Bu fotoğrafta beklenen şeffaflık yok (ESPN'den opak geldi). "
          "Arka plan silme deneniyor...")
    try:
        from rembg import remove
        from io import BytesIO
        with open(photo_path, "rb") as f:
            result_bytes = remove(f.read())
        return Image.open(BytesIO(result_bytes)).convert("RGBA")
    except ImportError:
        print("UYARI: rembg kurulu değil (pip install rembg), fotoğraf "
              "arka planlı haliyle kullanılacak. Outline/gölge efekti bu "
              "durumda beklendiği gibi görünmeyebilir.")
        return img


def add_outline_and_shadow(img: Image.Image) -> Image.Image:
    """Şeffaf bir oyuncu kesitine (img) beyaz outline + ofsetli gölge ekler.
    cv2 gerektirmez -- dilation için PIL'in kendi MaxFilter'ı kullanılıyor."""
    alpha = img.getchannel("A")

    # Beyaz outline: alfa maskesini genişlet (dilate)
    dilate_size = OUTLINE_PX * 2 + 1  # MaxFilter tek sayı boyut ister
    dilated = alpha.filter(ImageFilter.MaxFilter(dilate_size))
    outline = Image.new("RGBA", img.size, (255, 255, 255, 255))
    outline.putalpha(dilated)

    # Solid gölge: opak alanların siyah silüeti
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, SHADOW_ALPHA))
    shadow_layer.putalpha(alpha)
    shadow_positioned = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow_positioned.paste(shadow_layer, (SHADOW_OFFSET_X, SHADOW_OFFSET_Y))

    base = Image.new("RGBA", img.size, (0, 0, 0, 0))
    base = Image.alpha_composite(base, shadow_positioned)
    base = Image.alpha_composite(base, outline)
    base = Image.alpha_composite(base, img)
    return base


# Takım renkleri: (ana renk, ikincil/koyu renk, aksan rengi)
TEAM_COLORS = {
    "HOU": ("#CE1141", "#080808", "#C4CED4"),
    "LAL": ("#552583", "#080808", "#FDB927"),
    "BOS": ("#007A33", "#080808", "#BA9653"),
    "GSW": ("#1D428A", "#080808", "#FFC72C"),
    "DEN": ("#0E2240", "#080808", "#FEC524"),
    "MIL": ("#00471B", "#080808", "#EEE1C6"),
    "OKC": ("#007AC1", "#080808", "#EF3B24"),
    "DEFAULT": ("#4B2E83", "#080808", "#D9D9D9"),
}

# Basitleştirilmiş bayrak çizimleri (tam vektörel değil, kart üstünde
# küçük bir rozet olarak yeterince tanınabilir olacak şekilde)
def draw_flag(size, country):
    country = (country or "").strip().lower()
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size, size], fill="#E5E5E5")

    if country == "turkey":
        d.ellipse([0, 0, size, size], fill="#E30A17")
        cx, cy, r = size * 0.42, size * 0.5, size * 0.22
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="white")
        d.ellipse([cx - r * 0.65, cy - r, cx + r * 1.35, cy + r], fill="#E30A17")
        star = star_polygon(size * 0.62, size * 0.5, size * 0.09)
        d.polygon(star, fill="white")
    elif country == "usa":
        d.rectangle([0, 0, size, size], fill="#B22234")
        stripe_h = size / 7
        for i in range(0, 7, 2):
            d.rectangle([0, i * stripe_h, size, (i + 1) * stripe_h], fill="white")
        d.rectangle([0, 0, size * 0.5, size * 0.55], fill="#3C3B6E")
    elif country == "serbia":
        d.rectangle([0, 0, size, size / 3], fill="#C6363C")
        d.rectangle([0, size / 3, size, 2 * size / 3], fill="#0C4076")
        d.rectangle([0, 2 * size / 3, size, size], fill="white")
    elif country == "slovenia":
        d.rectangle([0, 0, size, size / 3], fill="white")
        d.rectangle([0, size / 3, size, 2 * size / 3], fill="#005CE7")
        d.rectangle([0, 2 * size / 3, size, size], fill="#ED1C24")
    elif country == "greece":
        d.rectangle([0, 0, size, size], fill="#0D5EAF")
        for i in range(0, 9, 2):
            d.rectangle([0, i * size / 9, size, (i + 1) * size / 9], fill="white")
        d.rectangle([0, 0, size * 0.45, size * 0.55], fill="#0D5EAF")
        d.rectangle([size * 0.16, 0, size * 0.26, size * 0.55], fill="white")
        d.rectangle([0, size * 0.22, size * 0.45, size * 0.32], fill="white")
    elif country == "canada":
        d.rectangle([0, 0, size, size], fill="white")
        d.rectangle([0, 0, size * 0.28, size], fill="#D80621")
        d.rectangle([size * 0.72, 0, size, size], fill="#D80621")
    else:
        d.ellipse([0, 0, size, size], fill="#8A8D93")

    # yuvarlak maske uygula (rozet gibi görünsün)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    img.putalpha(mask)
    return img


def star_polygon(cx, cy, r):
    pts = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.42
        pts.append((cx + radius * math.cos(angle), cy - radius * math.sin(angle)))
    return pts


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def load_font(path, size):
    return ImageFont.truetype(path, size)


def make_sticker(photo_path, player, out_path):
    primary, dark, accent = TEAM_COLORS.get(player["team_abbr"], TEAM_COLORS["DEFAULT"])

    card = Image.new("RGBA", (CARD_W, CARD_H), hex_to_rgb(primary) + (255,))
    draw = ImageDraw.Draw(card)

    # İç panel (fotoğrafın oturacağı hafif degrade zemin)
    inner = [BORDER, BORDER, CARD_W - BORDER, CARD_H - BORDER]
    draw.rectangle(inner, fill=hex_to_rgb(primary))
    draw.rectangle(
        [BORDER + INNER_BORDER, BORDER + INNER_BORDER,
         CARD_W - BORDER - INNER_BORDER, CARD_H - BORDER - INNER_BORDER],
        outline="white", width=3
    )

    # Hafif alt-degrade (fotoğrafın arkasında derinlik hissi)
    for y in range(CARD_H):
        t = y / CARD_H
        shade = tuple(int(c * (1 - 0.15 * t)) for c in hex_to_rgb(primary))
        draw.line([(BORDER + INNER_BORDER + 3, y), (CARD_W - BORDER - INNER_BORDER - 3, y)], fill=shade)

    # --- Oyuncu fotoğrafı (ESPN'den, zaten şeffaf gelmesi bekleniyor) ---
    photo = prepare_cutout(photo_path)
    photo = add_outline_and_shadow(photo)
    bbox = photo.getbbox()  # şeffaf kenar boşluklarını at
    if bbox:
        photo = photo.crop(bbox)

    photo_area_w = CARD_W - 2 * (BORDER + INNER_BORDER) - 20
    photo_area_h = CARD_H - 2 * (BORDER + INNER_BORDER) - 210  # alt bantlar + üst rozetler için pay

    scale = min(photo_area_w / photo.width, photo_area_h / photo.height)
    new_w, new_h = int(photo.width * scale), int(photo.height * scale)
    photo = photo.resize((new_w, new_h), Image.LANCZOS)

    px = (CARD_W - new_w) // 2
    py = BORDER + INNER_BORDER + 130 + (photo_area_h - new_h)  # alt bantlara yasla (waist-up görünüm)
    card.alpha_composite(photo, (px, py))

    # --- Üst sol: bayrak rozeti ---
    flag_size = 84
    flag = draw_flag(flag_size, player.get("nationality", ""))
    ring = Image.new("RGBA", (flag_size + 10, flag_size + 10), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([0, 0, flag_size + 10, flag_size + 10], fill="white")
    card.alpha_composite(ring, (24, 24))
    card.alpha_composite(flag, (29, 29))

    # --- Üst sağ: forma numarası rozeti ---
    num_size = 90
    num_badge = Image.new("RGBA", (num_size, num_size), (0, 0, 0, 0))
    nd = ImageDraw.Draw(num_badge)
    nd.ellipse([0, 0, num_size, num_size], fill="white")
    nd.ellipse([5, 5, num_size - 5, num_size - 5], fill=hex_to_rgb(dark))
    f_num = load_font(FONT_BOLD, 40)
    txt = f"#{player['jersey_number']}"
    bbox = nd.textbbox((0, 0), txt, font=f_num)
    nd.text(((num_size - (bbox[2]-bbox[0])) / 2, (num_size - (bbox[3]-bbox[1])) / 2 - bbox[1]),
            txt, font=f_num, fill="white")
    card.alpha_composite(num_badge, (CARD_W - num_size - 24, 24))

    # --- Pozisyon etiketi (bayrağın altında) ---
    f_small = load_font(FONT_COND, 26)
    pos_badge_w = flag_size + 10
    draw.rounded_rectangle([24, 24 + flag_size + 16, 24 + pos_badge_w, 24 + flag_size + 16 + 34],
                            radius=8, fill=hex_to_rgb(dark))
    pos_txt = player.get("position", "")
    bbox = draw.textbbox((0, 0), pos_txt, font=f_small)
    draw.text((24 + (pos_badge_w - (bbox[2]-bbox[0])) / 2, 24 + flag_size + 16 + 3), pos_txt, font=f_small, fill="white")

    # --- Alt isim bandı ---
    band_h = 90
    band_y = CARD_H - BORDER - INNER_BORDER - band_h - 46
    draw.rectangle([BORDER + INNER_BORDER, band_y, CARD_W - BORDER - INNER_BORDER, band_y + band_h],
                   fill=hex_to_rgb(dark))
    name = player["full_name"].upper()
    f_name = load_font(FONT_COND, 42 if len(name) < 16 else 32)
    bbox = draw.textbbox((0, 0), name, font=f_name)
    name_w = bbox[2] - bbox[0]
    if name_w > CARD_W - 2 * (BORDER + INNER_BORDER) - 30:
        f_name = load_font(FONT_COND, 26)
        bbox = draw.textbbox((0, 0), name, font=f_name)
        name_w = bbox[2] - bbox[0]
    draw.text(((CARD_W - name_w) / 2, band_y + (band_h - (bbox[3]-bbox[1])) / 2 - bbox[1]),
               name, font=f_name, fill="white")

    # --- En alt: yaş + boy (cm) + takım bandı ---
    info_h = 40
    info_y = band_y + band_h
    draw.rectangle([BORDER + INNER_BORDER, info_y, CARD_W - BORDER - INNER_BORDER, info_y + info_h],
                   fill=hex_to_rgb(accent))
    height_txt = f"{player.get('height_cm','')} cm" if player.get('height_cm') else ""
    age_txt = f"{player.get('age','')} yaş" if player.get('age') else ""
    info_txt = "   ·   ".join(filter(None, [age_txt, height_txt, player.get('team_abbr', '')]))
    f_info = load_font(FONT_BOLD, 20)
    bbox = draw.textbbox((0, 0), info_txt, font=f_info)
    draw.text(((CARD_W - (bbox[2]-bbox[0])) / 2, info_y + (info_h - (bbox[3]-bbox[1])) / 2 - bbox[1]),
               info_txt, font=f_info, fill=hex_to_rgb(dark))

    card.convert("RGB").save(out_path, quality=95)
    print(f"Kaydedildi: {out_path}")


if __name__ == "__main__":
    photo_path = sys.argv[1] if len(sys.argv) > 1 else "1630578_sticker_shadow.png"
    player_id = sys.argv[2] if len(sys.argv) > 2 else "1630578"

    # Örnek: gerçek akışta bunu players.json'dan okuyacaksın (ESPN ID + height_cm)
    player = {
        "player_id": player_id,
        "full_name": "Alperen Sengun",
        "position": "C",
        "jersey_number": "28",
        "height_cm": "211",
        "weight": "243",
        "age": 23,
        "nationality": "Turkey",
        "team_id": "10",
        "team_abbr": "HOU",
        "team_name": "Houston Rockets",
    }

    make_sticker(photo_path, player, f"{player_id}_panini_sticker.png")
