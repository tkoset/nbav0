"""
update_players.py  (v4 -- tamamen ESPN tabanli, tek script)
----------------------------------
Hem ILK KURULUM hem GUNLUK GUNCELLEME icin kullanilan TEK script.

- players.json yoksa (ilk calistirma): ESPN'den tum kadrolari ceker, baseline
  olusturur, transactions.json'a "ilk kurulum" notu duser (diff/olay uretmez).
- players.json varsa: guncel kadrolari ceker, eskiyle KARSILASTIRIR (diff),
  farklari transactions.json'a ekler.

NEDEN TAMAMEN ESPN: 
  - stats.nba.com (NBA'in kendisi), bulut/datacenter IP'lerini (GitHub
    Actions, Google Colab, AWS, GCP -- hepsi ayni kategori) Akamai bot
    korumasiyla KALICI olarak engelliyor. Sadece "residential" (ev/ofis)
    IP'lerden calisir.
  - ESPN'in genel site API'si (site.api.espn.com) bu engele tabi degil,
    key/signup gerektirmiyor, ve GitHub Actions'tan (herhangi bir bulut
    ortamindan) sorunsuz calisiyor.
  - Oyuncu ID'si olarak ESPN'in kendi ID'si kullaniliyor (NBA person_id
    DEGIL). Bu sayede ilk kurulum ve gunluk guncelleme AYNI kaynaktan AYNI
    ID sistemiyle geliyor -- isimle eslestirme gibi kirilgan bir adima hic
    gerek kalmiyor, ID'ler birebir eslesiyor.
  - Fotograflar da ESPN CDN'inden (a.espncdn.com) -- bu foto'lar zaten
    arka plani temizlenmis (kesilmis, seffaf) geliyor gibi gorunuyor, bu
    yuzden sticker uretiminde ayrica rembg/arka plan silme adimina gerek
    kalmiyor (bkz. make_sticker.py).

Kurulum: bu script'i GitHub Actions ile GUNLUK calistir (bkz. daily.yml).
Ilk calistirmada otomatik baseline olusturur, ekstra bir "ilk kurulum"
adimina/scriptine gerek yok -- fetch_all_players.py ARTIK KULLANILMIYOR,
repodan silebilirsin.
"""

import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone

import requests

PLAYERS_FILE = "players.json"
TRANSACTIONS_FILE = "transactions.json"
BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
REQUEST_DELAY_SECONDS = 1.5  # nazik davranmak icin, sert bir rate limit belgelenmedi

# ESPN takim ID'si -> bizim standart NBA kisaltmamiz.
# ESPN bazi takimlarda farkli kisaltma kullaniyor (GS/GSW, NY/NYK, SA/SAS,
# NO/NOP) bu yuzden kendi kisaltmamizi burada sabitliyoruz.
ESPN_TEAMS = [
    (1, "ATL", "Atlanta Hawks"), (2, "BOS", "Boston Celtics"),
    (17, "BKN", "Brooklyn Nets"), (30, "CHA", "Charlotte Hornets"),
    (4, "CHI", "Chicago Bulls"), (5, "CLE", "Cleveland Cavaliers"),
    (6, "DAL", "Dallas Mavericks"), (7, "DEN", "Denver Nuggets"),
    (8, "DET", "Detroit Pistons"), (9, "GSW", "Golden State Warriors"),
    (10, "HOU", "Houston Rockets"), (11, "IND", "Indiana Pacers"),
    (12, "LAC", "LA Clippers"), (13, "LAL", "Los Angeles Lakers"),
    (29, "MEM", "Memphis Grizzlies"), (14, "MIA", "Miami Heat"),
    (15, "MIL", "Milwaukee Bucks"), (16, "MIN", "Minnesota Timberwolves"),
    (3, "NOP", "New Orleans Pelicans"), (18, "NYK", "New York Knicks"),
    (25, "OKC", "Oklahoma City Thunder"), (19, "ORL", "Orlando Magic"),
    (20, "PHI", "Philadelphia 76ers"), (21, "PHX", "Phoenix Suns"),
    (22, "POR", "Portland Trail Blazers"), (23, "SAC", "Sacramento Kings"),
    (24, "SAS", "San Antonio Spurs"), (28, "TOR", "Toronto Raptors"),
    (26, "UTA", "Utah Jazz"), (27, "WAS", "Washington Wizards"),
]


def get_with_retry(url, attempts=3):
    for attempt in range(attempts):
        try:
            resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 429:
                print("UYARI: rate limit (429), 10sn bekleyip tekrar deneniyor...")
                time.sleep(10)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            print(f"HATA (deneme {attempt+1}/{attempts}): {url} -> {exc}")
            if attempt < attempts - 1:
                time.sleep(4 * (attempt + 1))
    return None


def extract_athletes(roster_json):
    """ESPN roster JSON iki farkli sekilde gelebiliyor: duz 'athletes' listesi
    ya da pozisyona gore gruplanmis [{'items':[...]}]. Ikisini de destekle."""
    athletes = roster_json.get("athletes", [])
    flat = []
    for entry in athletes:
        if isinstance(entry, dict) and "items" in entry:
            flat.extend(entry["items"])
        elif isinstance(entry, dict):
            flat.append(entry)
    return flat


def fetch_team_roster(espn_id):
    data = get_with_retry(f"{BASE_URL}/teams/{espn_id}/roster")
    if not data:
        return []
    return extract_athletes(data)


def height_to_cm(a):
    """ESPN athlete objesinden boy bilgisini santimetreye cevirir.
    Once numerik 'height' (inc cinsinden toplam) alanini dener, yoksa
    "6' 9\"" gibi displayHeight'i parse eder."""
    raw = a.get("height")
    if isinstance(raw, (int, float)) and raw > 0:
        return str(round(raw * 2.54))

    display = a.get("displayHeight") or ""
    m = re.match(r"(\d+)'\s*(\d+)", str(display))
    if m:
        feet, inches = int(m.group(1)), int(m.group(2))
        total_inches = feet * 12 + inches
        return str(round(total_inches * 2.54))

    return ""


def photo_url(espn_id):
    return f"https://a.espncdn.com/i/headshots/nba/players/full/{espn_id}.png"


def load_json(path: str, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def fetch_all_current_players():
    all_players = {}
    failed_teams = []

    for espn_id, team_abbr, team_name in ESPN_TEAMS:
        athletes = fetch_team_roster(espn_id)
        time.sleep(REQUEST_DELAY_SECONDS)

        if not athletes or len(athletes) < 8:
            print(f"UYARI: {team_name} icin veri yok/supheli (len={len(athletes) if athletes else 0}).")
            failed_teams.append(team_abbr)
            continue

        for a in athletes:
            pid = str(a.get("id", ""))
            full_name = a.get("fullName") or a.get("displayName") or ""
            if not pid or not full_name:
                continue

            position = (a.get("position") or {}).get("abbreviation", "")
            jersey = str(a.get("jersey") or "")
            weight = str(a.get("weight") or "")
            birthplace = a.get("birthPlace") or {}
            country = birthplace.get("country", "")
            age = a.get("age", "")

            all_players[pid] = {
                "player_id": pid,
                "full_name": full_name,
                "position": position,
                "jersey_number": jersey,
                "height_cm": height_to_cm(a),  # artik santimetre, orn. "195"
                "weight": weight,
                "age": age,
                "nationality": country,
                "team_id": str(espn_id),
                "team_abbr": team_abbr,
                "team_name": team_name,
                "photo_url": photo_url(pid),
            }

    return all_players, failed_teams


def diff_rosters(old_players: dict, new_players: dict) -> list:
    events = []

    for pid, new_p in new_players.items():
        old_p = old_players.get(pid)

        if old_p is None:
            events.append({
                "type": "new_player",
                "player_id": pid,
                "full_name": new_p["full_name"],
                "team_abbr": new_p["team_abbr"],
                "message": f"{new_p['full_name']} NBA rosterlarina yeni katildi ({new_p['team_abbr']})",
            })
            continue

        if old_p["team_id"] != new_p["team_id"]:
            events.append({
                "type": "team_change",
                "player_id": pid,
                "full_name": new_p["full_name"],
                "from_team": old_p["team_abbr"],
                "to_team": new_p["team_abbr"],
                "message": f"{new_p['full_name']}: {old_p['team_abbr']} -> {new_p['team_abbr']}",
            })
        elif str(old_p.get("jersey_number")) != str(new_p.get("jersey_number")) and new_p.get("jersey_number"):
            events.append({
                "type": "jersey_change",
                "player_id": pid,
                "full_name": new_p["full_name"],
                "team_abbr": new_p["team_abbr"],
                "old_number": old_p.get("jersey_number"),
                "new_number": new_p.get("jersey_number"),
                "message": f"{new_p['full_name']} forma numarasini degistirdi: #{old_p.get('jersey_number')} -> #{new_p.get('jersey_number')}",
            })

    for pid, old_p in old_players.items():
        if pid not in new_players:
            events.append({
                "type": "left_league",
                "player_id": pid,
                "full_name": old_p["full_name"],
                "team_abbr": old_p["team_abbr"],
                "message": f"{old_p['full_name']} aktif roster'lardan dustu (waived/retired/G-League)",
            })

    return events


def main():
    stored = load_json(PLAYERS_FILE, {"players": {}})
    old_players = stored.get("players", {})
    is_first_run = len(old_players) == 0

    print("ESPN'den guncel kadrolar cekiliyor (key gerekmiyor, ~1 dakika surer)...")
    new_players, failed_teams = fetch_all_current_players()

    if not is_first_run and len(new_players) < 0.7 * len(old_players):
        print(f"\nDURDURULDU: Cekilen oyuncu sayisi supheli derecede dusuk "
              f"({len(new_players)} / eski {len(old_players)}). Dosyalar GUNCELLENMEDI.")
        return

    if failed_teams:
        print(f"\nNot: bugun su takimlar cekilemedi: {', '.join(failed_teams)}")

    today = datetime.now(timezone.utc).date().isoformat()
    transactions_data = load_json(TRANSACTIONS_FILE, {"days": {}})

    if is_first_run:
        print(f"\nILK KURULUM: {len(new_players)} oyuncu ile baseline olusturuldu, "
              f"diff/transaction uretilmedi.")
        transactions_data["days"][today] = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "events": [],
            "note": f"Ilk kurulum: {len(new_players)} oyuncu ile baseline olusturuldu.",
        }
    else:
        events = diff_rosters(old_players, new_players)
        transactions_data["days"][today] = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "events": events,
        }
        if events:
            print(f"\n{len(events)} degisiklik bulundu ({today}):")
            for e in events:
                print(f"  - {e['message']}")
        else:
            print(f"\nBugun ({today}) herhangi bir roster degisikligi bulunamadi.")

    with open(TRANSACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(transactions_data, f, ensure_ascii=False, indent=2)

    with open(PLAYERS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "player_count": len(new_players),
            "players": new_players,
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
