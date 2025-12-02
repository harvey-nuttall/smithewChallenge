from datetime import datetime, timezone
END_DATE = datetime(2026, 3, 1, tzinfo=timezone.utc) # stop after Mar 1, 2026
if datetime.now(timezone.utc) >= END_DATE:
    print("End date reached, skipping run.")
    exit(0)

import requests
import json
import time
import os

# ---------------- CONFIG ---------------- #
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK") # set as GitHub secret
CHECK_FROM_DATE = datetime(2025, 12, 1, tzinfo=timezone.utc)
STORE_FILE = "store.json"
HEROES_FILE = "heroes.json" # <--- New constant for the hero data file
BATCH_SIZE = 20  # matches per batch
API_DELAY = 1.0   # seconds between full match fetches
MAX_RETRIES = 5   # retries on 429 errors

# The single source of truth for tracked Steam IDs and their display names
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
    246425616: "Bonzaro",
    391287552: "Matt",
    131154163: "Heth"
}

# Derive FRIEND_IDS from steam_names for easy membership checking
FRIEND_IDS = list(steam_names.keys())

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

# ---------------- HERO DATA FUNCTION ---------------- #
def get_hero_name(hero_id):
    """
    Looks up the hero name from the ID using the heroes.json file.
    This function uses a cached map (hero_map) for efficiency.
    """
    if not hasattr(get_hero_name, 'hero_map'):
        try:
            with open(HEROES_FILE, "r") as f:
                hero_data = json.load(f)
                # Create the ID-to-name map: {"1": "Anti-Mage", ...}
                get_hero_name.hero_map = {str(h['id']): h['localized_name'] for h in hero_data}
        except FileNotFoundError:
            print(f"[ERROR] Hero map file '{HEROES_FILE}' not found. Please ensure it exists.")
            get_hero_name.hero_map = {}
        except Exception as e:
            print(f"[ERROR] Failed to load hero map: {e}")
            get_hero_name.hero_map = {}

    # Convert the integer ID to a string for dictionary lookup
    return get_hero_name.hero_map.get(str(hero_id), f"Unknown Hero ({hero_id})")
    
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
    
    # Use the keys from steam_names as the set of tracked friends
    tracked_friend_ids = steam_names.keys()

    # Filter for friends only
    friends_in_match = [p for p in players if p.get("account_id") in tracked_friend_ids]
    if not friends_in_match:
        return [], match_start_time

    # ---------------- PART 1: INDIVIDUAL CHECKS ---------------- #
    # We iterate through every friend to check their specific stats
    for p in friends_in_match:
        steam_id = p.get("account_id")
        hero_id = p.get("hero_id")
        hero_name = get_hero_name(hero_id)
        
        # Stats
        kills = int(p.get("kills", 0) or 0)
        deaths = int(p.get("deaths", 0) or 0)
        assists = int(p.get("assists", 0) or 0)
        hero_dmg = int(p.get("hero_damage", 0) or 0)
        tower_dmg = int(p.get("tower_damage", 0) or 0)
        win = bool(p.get("win", 0))
        
        # Common data for the trigger
        base_info = {
            "steam_id": steam_id,
            "match_id": match_id,
            "hero": hero_name,
            "kda": f"{kills}/{deaths}/{assists}",
            "damage": hero_dmg
        }

        # --- WIN CHALLENGES ---
        if win:
            # Immortal Reverse: Win with 0 deaths (-10 pts)
            if deaths == 0:
                triggers.append({**base_info, "name": "Immortal Reverse", "points": -10})

        # --- LOSS CHALLENGES ---
        else:
            # Pacifist: 0 kills (+10)
            if kills == 0:
                triggers.append({**base_info, "name": "Pacifist", "points": 10})

            # Silent Supporter: 0 assists (+15)
            if assists == 0:
                triggers.append({**base_info, "name": "Silent Supporter", "points": 15})

            # Siege Breaker: 0 tower damage (+5)
            if tower_dmg == 0:
                triggers.append({**base_info, "name": "Siege Breaker", "points": 5})

            # Twenty Bomb: 20+ deaths (+5)
            # Note: This will stack with Tragic 20 if both happen. 
            if deaths >= 20:
                triggers.append({**base_info, "name": "Twenty Bomb", "points": 5})

            # Tragic 20: 0 kills AND 20+ deaths (+50)
            if kills == 0 and deaths >= 20:
                triggers.append({**base_info, "name": "Tragic 20", "points": 50})

            # Throwback Throw: Lose against Megas (+8)
            # Check enemy barracks status. 
            # If player is Radiant (slot < 128), check Dire barracks (bitmask). 0 means all destroyed.
            is_radiant = p.get("player_slot") < 128
            dire_rax = match.get("barracks_status_dire", 0)
            radiant_rax = match.get("barracks_status_radiant", 0)
            enemy_rax = dire_rax if is_radiant else radiant_rax

            if enemy_rax == 0:
                triggers.append({**base_info, "name": "Throwback Throw", "points": 8})

    # ---------------- PART 2: GROUP COMPARISONS ---------------- #
    # We do this OUTSIDE the loop so we don't count things twice.
    
    losing_team_players = [p for p in players if not bool(p.get("win", 0))]

    if losing_team_players:
        # --- Wet Noodle: Lowest damage on losing team (+3) ---
        # 1. Find the lowest damage amount among ALL losers (friends or randoms)
        lowest_dmg_amount = min([int(p.get("hero_damage", 0) or 0) for p in losing_team_players])
        
        # 2. Check if any FRIENDS matched that amount
        for p in losing_team_players:
            if p.get("account_id") in tracked_friend_ids:
                dmg = int(p.get("hero_damage", 0) or 0)
                if dmg == lowest_dmg_amount:
                    triggers.append({
                        "steam_id": p.get("account_id"),
                        "match_id": match_id,
                        "name": "Wet Noodle",
                        "points": 3,
                        "hero": get_hero_name(p.get("hero_id")),
                        "kda": f"{p.get('kills',0)}/{p.get('deaths',0)}/{p.get('assists',0)}",
                        "damage": dmg
                    })

        # --- Double Disaster Duo: Two friends with 0 kills (+30 each) ---
        # 1. Find all friends on losing team with 0 kills
        zero_kill_friends = []
        for p in losing_team_players:
            if p.get("account_id") in tracked_friend_ids and int(p.get("kills", 0) or 0) == 0:
                zero_kill_friends.append(p)

        # 2. If there are 2 or more such friends, award points to ALL of them
        if len(zero_kill_friends) >= 2:
            for p in zero_kill_friends:
                triggers.append({
                    "steam_id": p.get("account_id"),
                    "match_id": match_id,
                    "name": "Double Disaster Duo",
                    "points": 30,
                    "hero": get_hero_name(p.get("hero_id")),
                    "kda": f"0/{p.get('deaths',0)}/{p.get('assists',0)}",
                    "damage": int(p.get("hero_damage", 0) or 0)
                })

    return triggers, match_start_time

# ---------------- RUN CHECK ---------------- #
def run_check():
    store = load_store()
    total_triggers = 0
    
    # Iterate over the keys (the account IDs) in steam_names
    for friend_id in steam_names.keys():
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
                            line += f" | Hero: **{c['hero']}**"
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