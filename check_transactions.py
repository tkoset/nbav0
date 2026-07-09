"""
check_transactions.py  (v3 -- ESPN public site API tabanli)
----------------------------------
GUNLUK calisir (GitHub Actions cron ile tetiklenir).

NEDEN DEGISTI (2 kez):
  v1 -> v2: stats.nba.com (nba_api), bulut/datacenter IP'lerini (GitHub
    Actions dahil) Akamai bot korumasiyla KALICI olarak engelliyor. Iyi
    belgelenmis, cozumsuz bir sorun (bkz. github.com/swar/nba_api/issues/155,
    176, 320, 498). GitHub Actions loglarinda TUM 30 takim "Read timed out"
    hatasi vermisti -- retry/header degisikligi ise yaramiyor.
  v2 -> v3: BALLDONTLIE planlanmisti (ucretsiz ama API key + 5 istek/dk
    limiti gerektiriyordu). Onun yerine ESPN'in kendi genel (resmi olmayan
    ama herkese acik, key gerektirmeyen) site API'si kullaniliyor --
    site.api.espn.com, GitHub Actions dahil her ortamdan calisiyor ve NBA'in
    stats.nba.com'undaki gibi bir bulut-IP engeli yok.

ONEMLI MIMARI NOKTASI: players.json'daki oyuncu ID'leri hala NBA'in kendi
"person_id"si (fetch_all_players.py ile SENIN bilgisayarindan bir kere
cekiliyor). Fotograflar bu ID'ye bagli oldugu icin korunuyor. ESPN'in kendi
oyuncu ID'si farkli oldugundan, gunluk is oyunculari ISIM ile eslestirip
mevcut NBA person_id kaydini gunceller. Isimle eslesmeyen (gercekten yeni)
oyuncular icin gecici bir anahtar ve placeholder (siluet) foto kullanilir --
bir sonraki fetch_all_players.py calistirmanda gercek foto/ID ile duzelir.

NOT: Bu ESPN endpoint'i resmi/dokumante degil (bkz. yorumlar), yapisi
onceden haber vermeden degisebilir. Bu yuzden defensive parsing (birden
fazla olasi JSON sekli deneniyor) ve genel saglik kontrolu (supheli dusuk
oyuncu sayisinda dosyalari GUNCELLEMEME) korunuyor.
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

# ESPN takim ID'si -> bizim standart NBA kisaltmamiz (players.json'da kullanilan).
# ESPN bazi takimlarda farkli kisaltma kullaniyor (GS/GSW, NY/NYK, SA/SAS, NO/NOP)
# bu yuzden isim/ID uzerinden elle eslestirip KENDI kisaltmamizi kullaniyoruz.
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

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_name(name: str) -> str:
    name = strip_accents(name).lower()
    name = re.sub(r"[.\-']", "", name)
    tokens = [t for t in name.split() if t not in SUFFIXES]
    return " ".join(tokens)


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


def load_json(path: str, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def silhouette_photo_url():
    return ""


def parse_height(h):
    """ESPN bazen '6' 9\"' bazen '81' (inc) formatinda dondurebiliyor.
    Mumkunse '6-9' (NBA formati) formatina cevirir, olmazsa oldugu gibi birakir."""
    if not h:
        return ""
    h = str(h)
    m = re.match(r"(\d+)'\s*(\d+)", h)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return h


def build_new_players(old_players: dict):
    name_to_pid = {normalize_name(p["full_name"]): pid for pid, p in old_players.items()}

    new_players = {}
    unverified_new = []
    failed_teams = []

    for espn_id, team_abbr, team_name in ESPN_TEAMS:
        athletes = fetch_team_roster(espn_id)
        time.sleep(REQUEST_DELAY_SECONDS)

        if not athletes or len(athletes) < 8:
            print(f"UYARI: {team_name} icin veri yok/supheli (len={len(athletes)}). "
                  f"Eski veri korunuyor, bugun diff yapilmayacak.")
            failed_teams.append(team_abbr)
            for pid, old_p in old_players.items():
                if old_p.get("team_abbr") == team_abbr:
                    new_players[pid] = old_p
            continue

        for a in athletes:
            full_name = a.get("fullName") or a.get("displayName") or ""
            if not full_name:
                continue
            norm = normalize_name(full_name)
            pid = name_to_pid.get(norm)

            position = (a.get("position") or {}).get("abbreviation", "")
            jersey = str(a.get("jersey") or "")
            height = parse_height(a.get("height") or a.get("displayHeight"))
            weight = str(a.get("weight") or "")
            birthplace = a.get("birthPlace") or {}
            country = birthplace.get("country", "")

            if pid:
                old_p = old_players[pid]
                new_players[pid] = {
                    **old_p,
                    "full_name": old_p["full_name"],
                    "position": position or old_p.get("position", ""),
                    "jersey_number": jersey or old_p.get("jersey_number", ""),
                    "height": height or old_p.get("height", ""),
                    "weight": weight or old_p.get("weight", ""),
                    "nationality": country or old_p.get("nationality", ""),
                    "team_id": str(espn_id),
                    "team_abbr": team_abbr,
                    "team_name": team_name,
                }
            else:
                synthetic_id = f"espn:{a.get('id', full_name)}"
                new_players[synthetic_id] = {
                    "player_id": synthetic_id,
                    "full_name": full_name,
                    "position": position,
                    "jersey_number": jersey,
                    "height": height,
                    "weight": weight,
                    "age": "",
                    "birth_date": "",
                    "nationality": country,
                    "team_id": str(espn_id),
                    "team_abbr": team_abbr,
                    "team_name": team_name,
                    "photo_url": silhouette_photo_url(),
                    "_unverified": True,
                }
                unverified_new.append(full_name)

    return new_players, failed_teams, unverified_new


def diff_rosters(old_players: dict, new_players: dict) -> list:
    events = []

    for pid, new_p in new_players.items():
        old_p = old_players.get(pid)

        if old_p is None:
            note = " (ISIM ESLESMESIYLE TESPIT EDILDI, DOGRULA)" if new_p.get("_unverified") else ""
            events.append({
                "type": "new_player",
                "player_id": pid,
                "full_name": new_p["full_name"],
                "team_abbr": new_p["team_abbr"],
                "message": f"{new_p['full_name']} NBA rosterlarina yeni katildi ({new_p['team_abbr']}){note}",
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

    print("Guncel kadrolar cekiliyor (ESPN site API, key gerekmiyor)...")
    new_players, failed_teams, unverified_new = build_new_players(old_players)

    if old_players and len(new_players) < 0.7 * len(old_players):
        print(f"\nDURDURULDU: Cekilen oyuncu sayisi supheli derecede dusuk "
              f"({len(new_players)} / eski {len(old_players)}). "
              f"players.json ve transactions.json GUNCELLENMEDI.")
        return

    if failed_teams:
        print(f"\nNot: bugun su takimlar cekilemedi (eski veri korundu): {', '.join(failed_teams)}")
    if unverified_new:
        print(f"\nNot: {len(unverified_new)} oyuncu isim eslesmesiyle 'yeni' sayildi, "
              f"bir sonraki fetch_all_players.py calistirmanda dogrulanacak: "
              f"{', '.join(unverified_new)}")

    events = diff_rosters(old_players, new_players)

    today = datetime.now(timezone.utc).date().isoformat()

    transactions_data = load_json(TRANSACTIONS_FILE, {"days": {}})
    transactions_data["days"][today] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "events": events,
    }

    with open(TRANSACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(transactions_data, f, ensure_ascii=False, indent=2)

    with open(PLAYERS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "player_count": len(new_players),
            "players": new_players,
        }, f, ensure_ascii=False, indent=2)

    if events:
        print(f"\n{len(events)} degisiklik bulundu ({today}):")
        for e in events:
            print(f"  - {e['message']}")
    else:
        print(f"\nBugun ({today}) herhangi bir roster degisikligi bulunamadi.")


if __name__ == "__main__":
    main()
