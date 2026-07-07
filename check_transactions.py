"""
check_transactions.py
----------------------------------
GÜNLÜK çalışır (GitHub Actions cron ile tetiklenir). Güncel kadroları tekrar
çeker, elimizdeki players.json ile karşılaştırır (diff), farkları
transactions.json'a yeni bir "gün" kaydı olarak ekler ve players.json'ı
günceller.

Tespit ettiği olaylar:
  - "team_change": Oyuncu farklı bir takıma geçmiş (trade / signing)
  - "new_player": players.json'da hiç olmayan yeni bir oyuncu_id (rookie,
    yeni imza, vs.)
  - "jersey_change": Aynı takımda forma numarası değişmiş

Not: Bu, NBA'in "transactions" HTML sayfasını scrape etmek yerine roster
snapshot'larını KIYASLAYARAK (diffing) çalışır. Bu yöntem, sayfa yapısı
değişse bile kırılmaz ve stats.nba.com'un resmi JSON endpoint'lerine dayanır.
"""

import json
import os
import time
from datetime import datetime, timezone

from nba_api.stats.static import teams as static_teams
from nba_api.stats.endpoints import commonteamroster

PLAYERS_FILE = "players.json"
TRANSACTIONS_FILE = "transactions.json"
REQUEST_DELAY_SECONDS = 1.0


def photo_url(person_id: int) -> str:
    return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{person_id}.png"


def fetch_current_rosters() -> dict:
    all_teams = static_teams.get_teams()
    players: dict[str, dict] = {}

    for team in all_teams:
        team_id = team["id"]
        try:
            roster = commonteamroster.CommonTeamRoster(team_id=team_id)
            data = roster.get_normalized_dict()["CommonTeamRoster"]
        except Exception as exc:
            print(f"HATA: {team['full_name']} çekilemedi -> {exc}")
            continue

        for p in data:
            person_id = str(p["PLAYER_ID"])
            players[person_id] = {
                "player_id": person_id,
                "full_name": p["PLAYER"],
                "position": p.get("POSITION", ""),
                "jersey_number": p.get("NUM", ""),
                "team_id": str(team_id),
                "team_abbr": team["abbreviation"],
                "team_name": team["full_name"],
                "photo_url": photo_url(person_id),
            }

        time.sleep(REQUEST_DELAY_SECONDS)

    return players


def load_json(path: str, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def diff_rosters(old_players: dict, new_players: dict) -> list:
    """old_players / new_players: {player_id: {...}} şeklinde."""
    events = []

    for pid, new_p in new_players.items():
        old_p = old_players.get(pid)

        if old_p is None:
            events.append({
                "type": "new_player",
                "player_id": pid,
                "full_name": new_p["full_name"],
                "team_abbr": new_p["team_abbr"],
                "message": f"{new_p['full_name']} NBA rosterlarına yeni katıldı ({new_p['team_abbr']})",
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
        elif old_p.get("jersey_number") != new_p.get("jersey_number"):
            events.append({
                "type": "jersey_change",
                "player_id": pid,
                "full_name": new_p["full_name"],
                "team_abbr": new_p["team_abbr"],
                "old_number": old_p.get("jersey_number"),
                "new_number": new_p.get("jersey_number"),
                "message": f"{new_p['full_name']} forma numarasını değiştirdi: #{old_p.get('jersey_number')} -> #{new_p.get('jersey_number')}",
            })

    # Rosterdan tamamen düşenler (waived / released / retired)
    for pid, old_p in old_players.items():
        if pid not in new_players:
            events.append({
                "type": "left_league",
                "player_id": pid,
                "full_name": old_p["full_name"],
                "team_abbr": old_p["team_abbr"],
                "message": f"{old_p['full_name']} aktif roster'lardan düştü (waived/retired/G-League)",
            })

    return events


def main():
    print("Güncel kadrolar çekiliyor...")
    new_players = fetch_current_rosters()

    stored = load_json(PLAYERS_FILE, {"players": {}})
    old_players = stored.get("players", {})

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
        print(f"{len(events)} değişiklik bulundu ({today}):")
        for e in events:
            print(f"  - {e['message']}")
    else:
        print(f"Bugün ({today}) herhangi bir roster değişikliği bulunamadı.")


if __name__ == "__main__":
    main()
