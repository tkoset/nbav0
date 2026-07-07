"""
fetch_all_players.py
----------------------------------
BİR KERE çalıştırılır (ilk kurulumda). Tüm NBA takımlarının güncel kadrolarını
NBA'in resmi stats.nba.com endpoint'lerinden çeker ve players.json dosyasına
kaydeder. Fotoğraf linki olarak NBA'in kendi CDN'ini kullanır — bu sayede
oyuncu ID'si (PERSON_ID) hem veri hem de foto için aynıdır, eşleştirme sorunu
yaşanmaz.

Kurulum:
    pip install nba_api

Kullanım:
    python fetch_all_players.py

Çıktı:
    players.json  -> { "player_id": {...}, ... } şeklinde tüm oyuncular
"""

import json
import time
from datetime import datetime, timezone

from nba_api.stats.static import teams as static_teams
from nba_api.stats.endpoints import commonteamroster

OUTPUT_FILE = "players.json"
REQUEST_DELAY_SECONDS = 1.0  # NBA stats endpoint'lerine nazik davranmak için


def photo_url(person_id: int) -> str:
    """NBA'in resmi headshot CDN linki. Tarayıcıda <img> ile CORS sorunu
    olmadan doğrudan gösterilebilir."""
    return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{person_id}.png"


def fetch_all_players() -> dict:
    all_teams = static_teams.get_teams()
    players: dict[str, dict] = {}

    print(f"{len(all_teams)} takım bulundu, kadrolar çekiliyor...")

    for team in all_teams:
        team_id = team["id"]
        team_abbr = team["abbreviation"]
        team_name = team["full_name"]

        print(f"  -> {team_name} ({team_abbr})")

        try:
            roster = commonteamroster.CommonTeamRoster(team_id=team_id)
            data = roster.get_normalized_dict()["CommonTeamRoster"]
        except Exception as exc:
            print(f"     HATA: {team_name} çekilemedi -> {exc}")
            continue

        for p in data:
            person_id = str(p["PLAYER_ID"])
            players[person_id] = {
                "player_id": person_id,
                "full_name": p["PLAYER"],
                "position": p.get("POSITION", ""),
                "jersey_number": p.get("NUM", ""),
                "team_id": str(team_id),
                "team_abbr": team_abbr,
                "team_name": team_name,
                "photo_url": photo_url(person_id),
            }

        time.sleep(REQUEST_DELAY_SECONDS)

    return players


def main():
    players = fetch_all_players()

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "player_count": len(players),
        "players": players,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nTamamlandı: {len(players)} oyuncu -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
