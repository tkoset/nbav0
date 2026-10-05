"""
make_sticker.py  (v2 -- kullanicinin gercek InDesign tasarimina gore)
----------------------------------
Kullanicinin InDesign'dan export ettigi gercek tasarimdan (publication.html +
idGeneratedStyles.css) cikarilan KESIN piksel koordinatlarina gore kurulmus
Panini tarzi NBA sticker ureteci.

Kart: 600x700px. Elemanlar (tum koordinatlar InDesign exportundan):
  - Arka plan gradyani: (0,0) 600x600, takim rengi -> beyaz
  - Capraz cizgi deseni (rrreflection.svg): tum kart uzerinde, fotografin
    arkasinda hafif gorunur
  - Oyuncu fotografi: (0,114) 600x436 kutusu (foto kutunun ustune tasabilir,
    NBA logosu/bayrak rozetleri onun USTUNE cizildigi icin sorun olmaz)
  - Ince ayirici cizgi: (0,547) 600x3, koyu kirmizi
  - Isim bandi: (0,545) 600x56, PRIMARY renk, siyah yazi
  - Takim logosu paneli: (0,599) 200x102, PRIMARY renk, -20 derece skew
  - Pozisyon+forma paneli: (163.6,599) 236x102, DARK renk, skew
  - Yas+boy paneli: (363.6,599) 236x102, ACCENT renk, skew
  - NBA logosu: (30,30) 77x180, beyaz yuvarlatilmis rozet icinde
  - Ulke bayragi: (457.8,30) 112x80, beyaz yuvarlatilmis rozet icinde

Kullanim:
    python make_sticker.py <foto.png> <player_id> [team_logo.svg]

player_id, players.json'daki ESPN ID'sine karsilik gelmeli.
"""

import json
import math
import os
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    import cairosvg
    HAS_CAIROSVG = True
except ImportError:
    HAS_CAIROSVG = False

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_COND = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
NBA_LOGO_SVG = os.path.join(ASSETS_DIR, "nba_logo.svg")
PATTERN_SVG = os.path.join(ASSETS_DIR, "crosshatch_pattern.svg")

CARD_W, CARD_H = 600, 700

# InDesign exportundan cikan kesin kutular (x, y, w, h)
PHOTO_BOX = (0, 114, 600, 436)
NAME_BAND = (0, 545, 600, 56)
DIVIDER = (0, 547, 600, 3)
TEAMLOGO_PANEL = (0, 599, 200, 102)
POSITION_PANEL = (163.6, 599, 236.4, 102)
AGEHEIGHT_PANEL = (363.6, 599, 236.4, 102)
NBA_LOGO_BOX = (30, 30, 77, 180)
FLAG_BOX = (457.8, 30, 112, 80)
SKEW_DEG = 20  # ucunun da panelin ortak capraz egimi

OUTLINE_PX = 8
SHADOW_OFFSET_X = 40
SHADOW_OFFSET_Y = 30
SHADOW_ALPHA = 180


def load_team_colors():
    path = os.path.join(ASSETS_DIR, "..", "team_colors.json")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    colors = {}
    for abbr, v in raw.items():
        if abbr.startswith("_"):
            continue
        colors[abbr] = (v["primary"], v["dark"], v["accent"])
    colors["DEFAULT"] = ("#4B2E83", "#080808", "#D9D9D9")
    return colors


TEAM_COLORS = load_team_colors()


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def load_font(path, size):
    return ImageFont.truetype(path, size)


def render_svg(path, width, height):
    """SVG'yi istenen piksel boyutunda PNG'ye cevirir (cairosvg ile)."""
    if not HAS_CAIROSVG or not os.path.exists(path):
        return None
    try:
        from io import BytesIO
        png_bytes = cairosvg.svg2png(url=path, output_width=int(width), output_height=int(height))
        return Image.open(BytesIO(png_bytes)).convert("RGBA")
    except Exception as exc:
        print(f"UYARI: {path} render edilemedi -> {exc}")
        return None


# ---------------- OYUNCU FOTOGRAFI: outline + golge ----------------
def has_real_transparency(img: Image.Image) -> bool:
    alpha = img.getchannel("A")
    return alpha.getextrema()[0] < 250


def prepare_cutout(photo_path: str) -> Image.Image:
    img = Image.open(photo_path).convert("RGBA")
    if has_real_transparency(img):
        return img
    print("UYARI: Fotografta seffaflik yok, rembg deneniyor...")
    try:
        from rembg import remove
        from io import BytesIO
        with open(photo_path, "rb") as f:
            result_bytes = remove(f.read())
        return Image.open(BytesIO(result_bytes)).convert("RGBA")
    except ImportError:
        print("UYARI: rembg kurulu degil, fotograf oldugu gibi kullanilacak.")
        return img


def add_outline_and_shadow(img: Image.Image) -> Image.Image:
    alpha = img.getchannel("A")
    dilate_size = OUTLINE_PX * 2 + 1
    dilated = alpha.filter(ImageFilter.MaxFilter(dilate_size))
    outline = Image.new("RGBA", img.size, (255, 255, 255, 255))
    outline.putalpha(dilated)

    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, SHADOW_ALPHA))
    shadow_layer.putalpha(alpha)
    shadow_positioned = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow_positioned.paste(shadow_layer, (SHADOW_OFFSET_X, SHADOW_OFFSET_Y))

    base = Image.new("RGBA", img.size, (0, 0, 0, 0))
    base = Image.alpha_composite(base, shadow_positioned)
    base = Image.alpha_composite(base, outline)
    base = Image.alpha_composite(base, img)
    return base


# ---------------- CAPRAZ PANEL CIZIMI ----------------
def draw_skewed_panel(card: Image.Image, box, color_hex, skew_deg=SKEW_DEG):
    """box=(x,y,w,h). Ust kenari asagidakine gore skew_deg kadar saga kaydirarak
    paralelkenar ciziyor -- InDesign exportundaki panellerle ayni gorunum."""
    x, y, w, h = box
    shift = h * math.tan(math.radians(skew_deg))
    poly = [(x + shift, y), (x + w + shift, y), (x + w, y + h), (x, y + h)]
    draw = ImageDraw.Draw(card)
    draw.polygon(poly, fill=hex_to_rgb(color_hex))


# ---------------- ROZET (NBA logosu / bayrak) ----------------
def draw_badge(card: Image.Image, box, content_img, corner_radius=16):
    """box icine beyaz yuvarlatilmis rozet ciz, icine content_img'i ortala."""
    x, y, w, h = box
    badge = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    ImageDraw.Draw(badge).rounded_rectangle([0, 0, w, h], radius=corner_radius, fill="white")

    if content_img is not None:
        pad = 8
        max_w, max_h = w - 2 * pad, h - 2 * pad
        scale = min(max_w / content_img.width, max_h / content_img.height)
        new_size = (int(content_img.width * scale), int(content_img.height * scale))
        resized = content_img.resize(new_size, Image.LANCZOS)
        px = (w - new_size[0]) / 2
        py = (h - new_size[1]) / 2
        badge.alpha_composite(resized, (int(px), int(py)))

    card.alpha_composite(badge, (int(x), int(y)))


# Basitlesmis bayrak ciziciler (yatay rozet icin, flag-icons benzeri kaynak
# gelene kadar gecici cozum)
def draw_flag_image(w, h, country):
    country = (country or "").strip().lower()
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if country in ("turkey", "türkiye", "tur"):
        d.rectangle([0, 0, w, h], fill="#E30A17")
        cx, cy, r = w * 0.38, h * 0.5, h * 0.28
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="white")
        d.ellipse([cx - r * 0.6, cy - r, cx + r * 1.4, cy + r], fill="#E30A17")
    elif country in ("usa", "united states"):
        d.rectangle([0, 0, w, h], fill="#B22234")
        for i in range(0, 7, 2):
            d.rectangle([0, i * h / 7, w, (i + 1) * h / 7], fill="white")
        d.rectangle([0, 0, w * 0.4, h * 0.55], fill="#3C3B6E")
    elif country == "australia":
        d.rectangle([0, 0, w, h], fill="#00247D")
        d.rectangle([0, 0, w * 0.5, h * 0.5], fill="#00247D")
        d.line([0, 0, w * 0.5, h * 0.5], fill="white", width=3)
    elif country == "canada":
        d.rectangle([0, 0, w, h], fill="white")
        d.rectangle([0, 0, w * 0.28, h], fill="#D80621")
        d.rectangle([w * 0.72, 0, w, h], fill="#D80621")
    elif country == "serbia":
        d.rectangle([0, 0, w, h / 3], fill="#C6363C")
        d.rectangle([0, h / 3, w, 2 * h / 3], fill="#0C4076")
        d.rectangle([0, 2 * h / 3, w, h], fill="white")
    elif country == "slovenia":
        d.rectangle([0, 0, w, h / 3], fill="white")
        d.rectangle([0, h / 3, w, 2 * h / 3], fill="#005CE7")
        d.rectangle([0, 2 * h / 3, w, h], fill="#ED1C24")
    elif country == "greece":
        d.rectangle([0, 0, w, h], fill="#0D5EAF")
        for i in range(0, 9, 2):
            d.rectangle([0, i * h / 9, w, (i + 1) * h / 9], fill="white")
    else:
        d.rectangle([0, 0, w, h], fill="#8A8D93")

    return img


# ---------------- ANA FONKSIYON ----------------
def make_sticker(photo_path, player, out_path, team_logo_path=None):
    primary, dark, accent = TEAM_COLORS.get(player["team_abbr"], TEAM_COLORS["DEFAULT"])

    card = Image.new("RGBA", (CARD_W, CARD_H), (255, 255, 255, 255))

    # --- 1) Arka plan gradyani (primary -> beyaz), ust 600px ---
    grad_h = 600
    for yy in range(grad_h):
        t = yy / grad_h
        r, g, b = hex_to_rgb(primary)
        rr = int(r + (255 - r) * t)
        gg = int(g + (255 - g) * t)
        bb = int(b + (255 - b) * t)
        ImageDraw.Draw(card).line([(0, yy), (CARD_W, yy)], fill=(rr, gg, bb, 255))

    # --- 2) Capraz cizgi deseni (foto arkasinda hafif) ---
    pattern = render_svg(PATTERN_SVG, 800 * 2.66, 800 * 2.66)
    if pattern is not None:
        crop = pattern.crop((789, 740, 789 + CARD_W, 740 + CARD_H))
        # hafif saydam uygula ki arka planla uyumlu olsun
        alpha = crop.getchannel("A").point(lambda p: int(p * 0.35))
        crop.putalpha(alpha)
        card.alpha_composite(crop, (0, 0))

    # --- 3) Oyuncu fotografi ---
    photo = prepare_cutout(photo_path)
    photo = add_outline_and_shadow(photo)
    bbox = photo.getbbox()
    if bbox:
        photo = photo.crop(bbox)

    px, py, pw, ph = PHOTO_BOX
    scale = pw / photo.width
    new_size = (int(photo.width * scale), int(photo.height * scale))
    photo_resized = photo.resize(new_size, Image.LANCZOS)
    photo_x = px
    photo_y = py + ph - new_size[1]  # alta (footer'a) yasla, yukari tasmasina izin ver
    card.alpha_composite(photo_resized, (int(photo_x), int(photo_y)))

    # --- 4) Ince ayirici cizgi ---
    dx, dy, dw, dh = DIVIDER
    ImageDraw.Draw(card).rectangle([dx, dy, dx + dw, dy + dh], fill=(*hex_to_rgb(dark), 200))

    # --- 5) Isim bandi ---
    nx, ny, nw, nh = NAME_BAND
    ImageDraw.Draw(card).rectangle([nx, ny, nx + nw, ny + nh], fill=hex_to_rgb(primary))
    name = player["full_name"].upper()
    f_name = load_font(FONT_COND, 34)
    draw = ImageDraw.Draw(card)
    bbox = draw.textbbox((0, 0), name, font=f_name)
    name_w = bbox[2] - bbox[0]
    while name_w > nw - 30 and f_name.size > 14:
        f_name = load_font(FONT_COND, f_name.size - 2)
        bbox = draw.textbbox((0, 0), name, font=f_name)
        name_w = bbox[2] - bbox[0]
    draw.text(((nw - name_w) / 2, ny + (nh - (bbox[3] - bbox[1])) / 2 - bbox[1]),
              name, font=f_name, fill="black")

    # --- 6) Alt 3 panel ---
    draw_skewed_panel(card, TEAMLOGO_PANEL, primary)
    draw_skewed_panel(card, POSITION_PANEL, dark)
    draw_skewed_panel(card, AGEHEIGHT_PANEL, accent)

    # 6a) Takim logosu
    logo_img = None
    if team_logo_path and os.path.exists(team_logo_path):
        logo_img = render_svg(team_logo_path, 300, 300)
    if logo_img is not None:
        lx, ly, lw, lh = TEAMLOGO_PANEL
        logo_size = 70
        scale = min(logo_size / logo_img.width, logo_size / logo_img.height)
        new_size = (int(logo_img.width * scale), int(logo_img.height * scale))
        logo_resized = logo_img.resize(new_size, Image.LANCZOS)
        lgx = lx + (lw / 2) - (new_size[0] / 2)
        lgy = ly + (lh / 2) - (new_size[1] / 2)
        card.alpha_composite(logo_resized, (int(lgx), int(lgy)))

    # 6b) Pozisyon + forma no (iki satir, beyaz)
    f_pos = load_font(FONT_BOLD, 24)
    px0, py0, pw0, ph0 = POSITION_PANEL
    pos_txt = player.get("position", "")
    jersey_txt = f"#{player.get('jersey_number', '')}"
    bbox1 = draw.textbbox((0, 0), pos_txt, font=f_pos)
    bbox2 = draw.textbbox((0, 0), jersey_txt, font=f_pos)
    draw.text((px0 + (pw0 - (bbox1[2] - bbox1[0])) / 2, py0 + 18), pos_txt, font=f_pos, fill="white")
    draw.text((px0 + (pw0 - (bbox2[2] - bbox2[0])) / 2, py0 + 54), jersey_txt, font=f_pos, fill="white")

    # 6c) Yas + boy (iki satir, siyah)
    f_age = load_font(FONT_BOLD, 22)
    ax0, ay0, aw0, ah0 = AGEHEIGHT_PANEL
    age_txt = f"{player.get('age', '')} y/o" if player.get("age") else ""
    height_txt = f"{player.get('height_cm', '')} cm" if player.get("height_cm") else ""
    bbox1 = draw.textbbox((0, 0), age_txt, font=f_age)
    bbox2 = draw.textbbox((0, 0), height_txt, font=f_age)
    draw.text((ax0 + (aw0 - (bbox1[2] - bbox1[0])) / 2, ay0 + 18), age_txt, font=f_age, fill="black")
    draw.text((ax0 + (aw0 - (bbox2[2] - bbox2[0])) / 2, ay0 + 54), height_txt, font=f_age, fill="black")

    # --- 7) NBA logosu (sol ust, beyaz rozet) ---
    nba_logo = render_svg(NBA_LOGO_SVG, 200, 480)
    draw_badge(card, NBA_LOGO_BOX, nba_logo, corner_radius=14)

    # --- 8) Ulke bayragi (sag ust, beyaz rozet) ---
    flag_w, flag_h = int(FLAG_BOX[2] - 16), int(FLAG_BOX[3] - 16)
    flag_img = draw_flag_image(flag_w, flag_h, player.get("nationality", ""))
    draw_badge(card, FLAG_BOX, flag_img, corner_radius=14)

    card.convert("RGB").save(out_path, quality=95)
    print(f"Kaydedildi: {out_path}")


if __name__ == "__main__":
    photo_path = sys.argv[1] if len(sys.argv) > 1 else "1630578_sticker_shadow.png"
    player_id = sys.argv[2] if len(sys.argv) > 2 else "1630578"
    team_logo_path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(ASSETS_DIR, "team_logo_ATL.svg")

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

    make_sticker(photo_path, player, f"{player_id}_panini_sticker.png", team_logo_path)
