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
from nba_api.stats.endpoints import commonteamroster, commonplayerinfo

PLAYERS_FILE = "players.json"
TRANSACTIONS_FILE = "transactions.json"
ROSTER_DELAY_SECONDS = 1.0
PLAYER_INFO_DELAY_SECONDS = 0.6


def photo_url(person_id: int) -> str:
    return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{person_id}.png"


def fetch_nationality(person_id: str) -> str:
    """Sadece daha önce hiç görülmemiş (yeni) oyuncular için çağrılır --
    böylece günlük iş, uyruk bilgisini bilinen oyuncular için tekrar tekrar
    çekip vakit kaybetmez."""
    try:
        info = commonplayerinfo.CommonPlayerInfo(player_id=person_id)
        row = info.get_normalized_dict()["CommonPlayerInfo"][0]
        return row.get("COUNTRY", "") or ""
    except Exception as exc:
        print(f"UYARI: {person_id} için uyruk bilgisi alınamadı -> {exc}")
        return ""


def fetch_current_rosters(old_players: dict) -> tuple[dict, list]:
    """old_players: players.json'daki mevcut kayıt (player_id -> data).

    KRİTİK: Bir takımın roster çekimi başarısız olursa (örn. GitHub Actions
    runner IP'si NBA tarafından geçici bloklanmışsa -- bu stats.nba.com'da
    bilinen bir durum), o takımın oyuncularını ATLAMIYORUZ. Bunun yerine
    o takım için ESKİ veriyi olduğu gibi koruyoruz, böylece diff bu oyuncuları
    yanlışlıkla "rosterdan düştü" sanıp, ertesi gün de "yeni katıldı" diye
    uydurma bir olay üretmiyor. Başarısız takımlar `failed_teams` listesinde
    döndürülür.
    """
    all_teams = static_teams.get_teams()
    players: dict[str, dict] = {}
    known_player_ids = set(old_players.keys())
    failed_teams = []

    for team in all_teams:
        team_id = team["id"]
        roster_data = None
        for attempt in range(3):
            try:
                roster = commonteamroster.CommonTeamRoster(team_id=team_id)
                roster_data = roster.get_normalized_dict()["CommonTeamRoster"]
                break
            except Exception as exc:
                print(f"HATA (deneme {attempt+1}/3): {team['full_name']} çekilemedi -> {exc}")
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))  # 3sn, 6sn bekleyip tekrar dene

        # Sağlık kontrolü: gerçek bir NBA kadrosu her zaman en az ~8-10
        # oyuncu içerir. Boş/çok kısa dönerse de "başarısız" say (garbage veri).
        if not roster_data or len(roster_data) < 8:
            print(f"UYARI: {team['full_name']} için veri yok/şüpheli (len={len(roster_data) if roster_data else 0}). "
                  f"Bu takım için ESKİ veri korunuyor, bugün diff yapılmayacak.")
            failed_teams.append(team["abbreviation"])
            # Eski veriyi bu takım için aynen taşı
            for pid, old_p in old_players.items():
                if old_p.get("team_abbr") == team["abbreviation"]:
                    players[pid] = old_p
            time.sleep(ROSTER_DELAY_SECONDS)
            continue

        for p in roster_data:
            person_id = str(p["PLAYER_ID"])
            is_new_player = person_id not in known_player_ids

            players[person_id] = {
                "player_id": person_id,
                "full_name": p["PLAYER"],
                "position": p.get("POSITION", ""),
                "jersey_number": p.get("NUM", ""),
                "height": p.get("HEIGHT", ""),
                "weight": p.get("WEIGHT", ""),
                "age": p.get("AGE", ""),
                "birth_date": p.get("BIRTH_DATE", ""),
                "nationality": "",  # birazdan doldurulacak (yeni ise) ya da main()'de eskiden kopyalanacak
                "team_id": str(team_id),
                "team_abbr": team["abbreviation"],
                "team_name": team["full_name"],
                "photo_url": photo_url(person_id),
            }

            if is_new_player:
                players[person_id]["nationality"] = fetch_nationality(person_id)
                time.sleep(PLAYER_INFO_DELAY_SECONDS)

        time.sleep(ROSTER_DELAY_SECONDS)

    return players, failed_teams


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
    stored = load_json(PLAYERS_FILE, {"players": {}})
    old_players = stored.get("players", {})

    print("Güncel kadrolar çekiliyor...")
    new_players, failed_teams = fetch_current_rosters(old_players)

    # GENEL SAĞLIK KONTROLÜ: çekilen toplam oyuncu sayısı eskiye göre
    # ciddi şekilde düşükse (örn. NBA tarafında IP toplu bloklandıysa),
    # hiçbir dosyayı güncelleme -- yanlış veriyle players.json/transactions.json'ı
    # bozmaktansa bu günü tamamen atlamak daha güvenli.
    if old_players and len(new_players) < 0.7 * len(old_players):
        print(f"\nDURDURULDU: Çekilen oyuncu sayısı şüpheli derecede düşük "
              f"({len(new_players)} / eski {len(old_players)}). "
              f"Muhtemelen NBA tarafı bu IP'yi geçici bloklamış. "
              f"players.json ve transactions.json GÜNCELLENMEDİ, "
              f"bir sonraki çalıştırmada tekrar denenecek.")
        return

    if failed_teams:
        print(f"\nNot: bugün şu takımlar çekilemedi (eski veri korundu): {', '.join(failed_teams)}")

    # Bilinen oyuncular için uyruk/doğum tarihi gibi nadiren değişen alanları
    # eski kayıttan koru (gereksiz yere tekrar API çağrısı yapmamak için).
    for pid, new_p in new_players.items():
        old_p = old_players.get(pid)
        if old_p and not new_p.get("nationality"):
            new_p["nationality"] = old_p.get("nationality", "")

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
