END_DATE = datetime(2026, 3, 1, tzinfo=timezone.utc)  # stop after Mar 1, 2026
if datetime.now(timezone.utc) >= END_DATE:
    print("End date reached, skipping run.")
    exit(0)

import requests
import json
import time
import os


# ---------------- CONFIG ---------------- #
FRIEND_IDS = [
    78252078, 105122368, 367108642, 119201202, 1247397877,
    254540347, 330017819, 46243750, 191496009, 29468198,
    121637548, 8590617, 189958818
]  # Your friends' Steam32 IDs

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")  # set as GitHub secret
CHECK_FROM_DATE = datetime(2025, 12, 1, tzinfo=timezone.utc)
STORE_FILE = "store.json"
BATCH_SIZE = 20  # matches per batch
API_DELAY = 1.0   # seconds between full match fetches
MAX_RETRIES = 5   # retries on 429 errors

# Optional manual caching of friend names
steam_names = {
    78252078: "Was",
    105122368: "Nobrain",
    367108642: "Dreamer",
    119201202: "Corne",
    1247397877: "Irishman",
    254540347: "Charlie",
    330017819: "Sheep",
    46243750: "Dranzer",
    191496009: "Smithy",
    29468198: "Rowave",
    121637548: "Thom",
    8590617: "I.C.B.M",
    189958818: "Kingy",
}

# ---------------- UTILITIES ---------------- #
def load_store():
    try:
        with open(STORE_FILE, "r") as f:
            return json.load(f)
    except:
        return {"checked_matches": {}, "leaderboard": {}, "daily": {}, "last_checked": None}

def save_store(store):
    with open(STORE_FILE, "w") as f:
        json.dump(store, f, indent=2)

def send_discord(message):
    if WEBHOOK_URL:
        try:
            requests.post(WEBHOOK_URL, json={"content": message})
        except Exception as e:
            print(f"[Discord] send error: {e}")

# ---------------- FETCH MATCHES ---------------- #
def fetch_recent_match_ids(account_id, limit=BATCH_SIZE, offset=0):
    url = f"https://api.opendota.com/api/players/{account_id}/matches?limit={limit}&offset={offset}"
    try:
        r = requests.get(url)
        r.raise_for_status()
        matches = r.json()
    except Exception as e:
        print(f"[ERROR] Could not fetch matches for {account_id}: {e}")
        return []

    filtered_ids = []
    for m in matches:
        start_time = datetime.fromtimestamp(m.get("start_time", 0), tz=timezone.utc)
        if start_time >= CHECK_FROM_DATE:
            filtered_ids.append(m.get("match_id"))
    return filtered_ids

def fetch_full_match(match_id):
    url = f"https://api.opendota.com/api/matches/{match_id}"
    retries = 0
    while retries < MAX_RETRIES:
        try:
            r = requests.get(url)
            if r.status_code == 429:
                wait = 5 + retries * 2
                print(f"[WARN] Rate limited. Waiting {wait}s before retrying match {match_id}...")
                time.sleep(wait)
                retries += 1
                continue
            r.raise_for_status()
            time.sleep(API_DELAY)
            return r.json()
        except Exception as e:
            print(f"[ERROR] Could not fetch match {match_id}: {e}")
            return None
    print(f"[WARN] Skipping match {match_id} after {MAX_RETRIES} retries")
    return None

# ---------------- CHALLENGE CHECK ---------------- #
def check_challenges(match):
    triggers = []
    match_id = match.get("match_id")
    match_start_time = datetime.fromtimestamp(match.get("start_time", 0), tz=timezone.utc)
    players = match.get("players", [])

    # Only keep friends
    friends_in_match = [p for p in players if p.get("account_id") in FRIEND_IDS]
    if not friends_in_match:
        return []

    for p in friends_in_match:
        steam_id = p.get("account_id")
        hero_name = p.get("hero_id")
        kills = int(p.get("kills", 0) or 0)
        deaths = int(p.get("deaths", 0) or 0)
        assists = int(p.get("assists", 0) or 0)
        hero_dmg = int(p.get("hero_damage", 0) or 0)
        tower_dmg = int(p.get("tower_damage", 0) or 0)
        win = bool(p.get("win", 0))
        player_slot = p.get("player_slot")

        # ---------------- LOSS-BASED CHALLENGES ---------------- #
        if not win:
            if kills == 0:
                triggers.append({"name": "Pacifist", "points": 10, "steam_id": steam_id,
                                 "match_id": match_id, "hero": hero_name,
                                 "kda": f"{kills}/{deaths}/{assists}", "damage": hero_dmg})
            if assists == 0:
                triggers.append({"name": "Silent Supporter", "points": 15, "steam_id": steam_id,
                                 "match_id": match_id, "hero": hero_name,
                                 "kda": f"{kills}/{deaths}/{assists}", "damage": hero_dmg})
            if tower_dmg == 0:
                triggers.append({"name": "Siege Breaker", "points": 5, "steam_id": steam_id,
                                 "match_id": match_id, "hero": hero_name,
                                 "kda": f"{kills}/{deaths}/{assists}", "damage": hero_dmg})
            if kills == 0 and deaths >= 20:
                triggers.append({"name": "Tragic 20", "points": 50, "steam_id": steam_id,
                                 "match_id": match_id, "hero": hero_name,
                                 "kda": f"{kills}/{deaths}/{assists}", "damage": hero_dmg})
            if deaths >= 20:
                triggers.append({"name": "Twenty Bomb", "points": 5, "steam_id": steam_id,
                                 "match_id": match_id, "hero": hero_name,
                                 "kda": f"{kills}/{deaths}/{assists}", "damage": hero_dmg})

    # ---------------- WIN-BASED CHALLENGE: Immortal Reverse ---------------- #
    if win and deaths == 0:
        triggers.append({"steam_id": steam_id, "match_id": match_id, "name": "Immortal Reverse",
                         "points": -10, "hero": hero_name,
                         "kda": f"{kills}/{deaths}/{assists}", "damage": hero_dmg})

    # ---------------- Wet Noodle (loss) ---------------- #
    losing_team_players = [p for p in players if not bool(p.get("win", 0))]
    if losing_team_players:
        lowest_dmg = min([int(p.get("hero_damage", 0) or 0) for p in losing_team_players])
        for p in losing_team_players:
            if p.get("account_id") in FRIEND_IDS and int(p.get("hero_damage", 0) or 0) == lowest_dmg:
                triggers.append({"steam_id": p.get("account_id"), "match_id": match_id,
                                 "name": "Wet Noodle", "points": 3, "hero": p.get("hero_id"),
                                 "kda": f"{p.get('kills',0)}/{p.get('deaths',0)}/{p.get('assists',0)}",
                                 "damage": int(p.get("hero_damage", 0) or 0)})

    # ---------------- Throwback Throw (loss, enemy megas) ---------------- #
    dire_megas = match.get("barracks_status_dire", 0)
    radiant_megas = match.get("barracks_status_radiant", 0)
    for p in friends_in_match:
        is_radiant = p.get("player_slot") < 128
        losing_team = not bool(p.get("win", 0))
        enemy_megas = dire_megas if is_radiant else radiant_megas
        if losing_team and enemy_megas == 0:
            triggers.append({"steam_id": p.get("account_id"), "match_id": match_id,
                             "name": "Throwback Throw", "points": 8,
                             "hero": p.get("hero_id"),
                             "kda": f"{p.get('kills',0)}/{p.get('deaths',0)}/{p.get('assists',0)}",
                             "damage": int(p.get("hero_damage",0) or 0)})

    # ---------------- Double Disaster Duo (loss) ---------------- #
    zero_killers = [p.get("account_id") for p in losing_team_players if int(p.get("kills",0) or 0)==0]
    for friend_id in zero_killers:
        for other_id in zero_killers:
            if other_id != friend_id:
                triggers.append({"steam_id": friend_id, "match_id": match_id,
                                 "name": "Double Disaster Duo", "points": 30,
                                 "hero": None, "kda": None, "damage": None})

    return triggers, match_start_time

# ---------------- RUN CHECK ---------------- #
def run_check():
    store = load_store()
    total_triggers = 0

    for friend_id in FRIEND_IDS:
        offset = 0
        while True:
            match_ids = fetch_recent_match_ids(friend_id, limit=BATCH_SIZE, offset=offset)
            if not match_ids:
                break
            for match_id in match_ids:
                if str(match_id) in store["checked_matches"]:
                    continue
                full_match = fetch_full_match(match_id)
                if not full_match:
                    continue
                triggers, match_time = check_challenges(full_match)
                total_triggers += len(triggers)

                messages_by_player = {}
                for t in triggers:
                    sid = str(t["steam_id"])
                    if sid not in store["leaderboard"]:
                        store["leaderboard"][sid] = {"points": 0, "history": []}
                    store["leaderboard"][sid]["points"] += t["points"]
                    store["leaderboard"][sid]["history"].append({
                        "date": match_time.strftime("%Y-%m-%d %H:%M UTC"),
                        "match_id": match_id,
                        "points": t["points"],
                        "challenge": t["name"]
                    })

                    date_str = match_time.strftime("%Y-%m-%d")
                    if date_str not in store["daily"]:
                        store["daily"][date_str] = {}
                    if sid not in store["daily"][date_str]:
                        store["daily"][date_str][sid] = 0
                    store["daily"][date_str][sid] += t["points"]

                    if sid not in messages_by_player:
                        messages_by_player[sid] = []
                    messages_by_player[sid].append(t)

                # Send one Discord message per player per match
                for sid, challenges in messages_by_player.items():
                    name = steam_names.get(int(sid), sid)
                    msg_lines = [f"Player **{name}** earned {len(challenges)} challenge(s) in match {match_id} (Start: {match_time.strftime('%Y-%m-%d %H:%M UTC')}):"]
                    total_points = 0
                    for c in challenges:
                        line = f"• {c['name']} ({'+' if c['points']>=0 else ''}{c['points']} pts)"
                        if c.get("damage") is not None:
                            line += f" | Damage: {c['damage']}"
                        if c.get("kda") is not None:
                            line += f" | KDA: {c['kda']}"
                        if c.get("hero") is not None:
                            line += f" | Hero: {c['hero']}"
                        msg_lines.append(line)
                        total_points += c['points']
                    msg_lines.append(f"Total points: {total_points:+}")
                    send_discord("\n".join(msg_lines))

                store["checked_matches"][str(match_id)] = match_time.isoformat()
            offset += BATCH_SIZE

    store["last_checked"] = datetime.now(timezone.utc).isoformat()
    save_store(store)
    print(f"[{datetime.now(timezone.utc).isoformat()}] Check complete. Found {total_triggers} triggers.")

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    run_check()
