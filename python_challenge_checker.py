from datetime import datetime, timezone
from typing import List, Dict, Set
import requests
import json
import time
import os
import sys

# Add session for connection pooling
session = requests.Session()
session.headers.update({'User-Agent': 'ChallengeChecker/1.0'})

# ---------------- CONFIG ---------------- #
END_DATE = datetime(2026, 3, 1, tzinfo=timezone.utc)
if datetime.now(timezone.utc) >= END_DATE:
    print("End date reached, skipping run.")
    exit(0)

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
CHECK_FROM_DATE = datetime(2025, 12, 1, tzinfo=timezone.utc)
STORE_FILE = "store.json"
HEROES_FILE = "heroes.json"
BATCH_SIZE = 20
API_DELAY = 0.5  # Reduced from 1.0, OpenDota recommends < 1 req/sec
MAX_RETRIES = 3  # Reduced from 5 to fail faster on persistent issues
REQUEST_TIMEOUT = 20  # Increased from 15 for slower connections
CONNECT_TIMEOUT = 10  # Add separate connection timeout
DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() == "true"

steam_names = {
    78252078: "Was", 105122368: "Nobrain", 367108642: "Dreamer",
    119201202: "Corne", 1247397877: "Irishman", 254540347: "Big D Digby",
    330017819: "Sheep", 46243750: "Pet poo bum bum boy", 191496009: "Smithy",
    29468198: "Rowave", 121637548: "Thom", 8590617: "I.C.B.M",
    189958818: "Kingy", 246425616: "Bonzaro", 391287552: "Matt",
    131154163: "Heth", 211160675: "Sssmookin"
}

# ---------------- STORE MANAGEMENT ---------------- #
def load_store():
    try:
        with open(STORE_FILE, "r") as f:
            store = json.load(f)
            if "unparsed_matches" not in store:
                store["unparsed_matches"] = {}
            if "leaderboard" not in store:
                store["leaderboard"] = {}
            if "checked_matches" not in store:
                store["checked_matches"] = {}
            if "daily" not in store:
                store["daily"] = {}
            return store
    except:
        return {"checked_matches": {}, "unparsed_matches": {}, "leaderboard": {}, "daily": {}}

def save_store(store):
    with open(STORE_FILE, "w") as f:
        json.dump(store, f, indent=2)

# ---------------- HERO LOOKUP ---------------- #
def get_hero_name(hero_id):
    if not hasattr(get_hero_name, 'hero_map'):
        try:
            with open(HEROES_FILE, "r") as f:
                heroes = json.load(f)
                get_hero_name.hero_map = {str(h['id']): h['localized_name'] for h in heroes}
        except:
            get_hero_name.hero_map = {}
    return get_hero_name.hero_map.get(str(hero_id), f"Hero {hero_id}")

# ---------------- API CALLS WITH EXPONENTIAL BACKOFF ---------------- #
def fetch_recent_match_ids(account_id, limit=BATCH_SIZE, offset=0):
    """Fetch recent matches with optimized error handling and backoff."""
    url = f"https://api.opendota.com/api/players/{account_id}/matches?limit={limit}&offset={offset}"
    
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, timeout=(CONNECT_TIMEOUT, REQUEST_TIMEOUT))
            r.raise_for_status()
            matches = r.json()

            filtered = []
            for m in matches:
                start_time = datetime.fromtimestamp(m.get("start_time", 0), tz=timezone.utc)
                if start_time >= CHECK_FROM_DATE:
                    filtered.append(m.get("match_id"))
            
            time.sleep(API_DELAY)
            return filtered
            
        except requests.exceptions.Timeout:
            wait = min(10, 2 ** attempt)  # 1s, 2s, 4s max
            print(f"[WARN] Timeout for {account_id} (attempt {attempt+1}/{MAX_RETRIES}), waiting {wait}s...")
            time.sleep(wait)
            
        except requests.exceptions.ConnectionError as e:
            wait = min(10, 2 ** attempt)
            print(f"[WARN] Connection error for {account_id}, waiting {wait}s...")
            time.sleep(wait)
            
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                print(f"[ERROR] Fetch matches for {account_id}: {e}")
            time.sleep(min(5, 2 ** attempt))
    
    return []

def fetch_full_match(match_id):
    """Fetch full match data with exponential backoff."""
    url = f"https://api.opendota.com/api/matches/{match_id}"
    
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, timeout=(CONNECT_TIMEOUT, REQUEST_TIMEOUT))
            
            if r.status_code == 429:
                wait = min(30, 5 * (attempt + 1))  # 5s, 10s, 15s... up to 30s
                print(f"[WARN] Rate limited on match {match_id}, waiting {wait}s...")
                time.sleep(wait)
                continue
            
            if r.status_code == 404:
                print(f"[WARN] Match {match_id} not found (deleted/private)")
                return None
            
            r.raise_for_status()
            time.sleep(API_DELAY)
            return r.json()
            
        except requests.exceptions.Timeout:
            wait = min(10, 2 ** attempt)
            print(f"[WARN] Timeout fetching match {match_id} (attempt {attempt+1}/{MAX_RETRIES}), waiting {wait}s...")
            time.sleep(wait)
            
        except requests.exceptions.ConnectionError:
            wait = min(10, 2 ** attempt)
            print(f"[WARN] Connection error on match {match_id}, retrying in {wait}s...")
            time.sleep(wait)
            
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                print(f"[ERROR] Fetch match {match_id}: {e}")
            time.sleep(min(5, 2 ** attempt))
    
    return None

# ---------------- MATCH VALIDATION ---------------- #
def is_match_fully_parsed(match_data, expected_friend_id=None):
    """
    Check if match has all required data for challenge checking.
    Returns (bool, reason)
    """
    # Must have players data
    if 'players' not in match_data:
        return False, "No players data"

    players = match_data.get('players', [])
    if len(players) != 10:
        return False, f"Only {len(players)}/10 players"

    # Check if any of our tracked friends are in the match
    friends_in_match = [p for p in players if p.get('account_id') in steam_names.keys()]

    # If we expected a specific friend (because we got this match from their history)
    # but they're not visible, they have privacy enabled - retry later
    if expected_friend_id and expected_friend_id not in [f.get('account_id') for f in friends_in_match]:
        friend_name = steam_names.get(expected_friend_id, str(expected_friend_id))
        return False, f"{friend_name} has privacy enabled (not visible in match data)"

    if not friends_in_match:
        # No tracked friends visible - this shouldn't happen if expected_friend_id was set
        # But could happen for old processed matches
        return True, None

    # For each friend, verify they have all the stats we need
    required_friend_fields = ['account_id', 'hero_id', 'kills', 'deaths',
                              'assists', 'hero_damage', 'tower_damage', 'win', 'player_slot']

    for friend in friends_in_match:
        for field in required_friend_fields:
            if field not in friend or friend[field] is None:
                friend_name = steam_names.get(friend.get('account_id'), 'Unknown')
                return False, f"{friend_name}'s data incomplete (missing {field})"

    # Must have barracks status for mega creeps check
    if 'barracks_status_radiant' not in match_data or 'barracks_status_dire' not in match_data:
        return False, "Missing barracks data"

    # All good
    return True, None

# ---------------- CHALLENGE LOGIC ---------------- #
def check_challenges(match_data):
    """
    Check all challenges for a match. Returns list of triggers and match time.
    Only checks tracked friends - ignores anonymous/private players.
    """
    match_id = match_data.get("match_id")
    match_time = datetime.fromtimestamp(match_data.get("start_time", 0), tz=timezone.utc)
    players = match_data.get("players", [])

    # Get friends in match (skip players with no account_id - private profiles)
    friends = [p for p in players if p.get("account_id") in steam_names.keys()]
    if not friends:
        return [], match_time

    triggers = []

    # Individual challenges for each friend
    for p in friends:
        sid = p.get("account_id")
        hero_id = p.get("hero_id")
        hero = get_hero_name(hero_id)
        kills = int(p.get("kills", 0) or 0)
        deaths = int(p.get("deaths", 0) or 0)
        assists = int(p.get("assists", 0) or 0)
        dmg = int(p.get("hero_damage", 0) or 0)
        tower_dmg = int(p.get("tower_damage", 0) or 0)
        win = bool(p.get("win", 0))
        kda = f"{kills}/{deaths}/{assists}"

        # Base structure is used to capture player-specific stats once per match (even if no trigger)
        # Note: We keep hero/kda/damage in the trigger dict for the purpose of
        # temporarily carrying the stats to the store update/discord message
        base = {"steam_id": sid, "match_id": match_id, "hero": hero, "kda": kda, "damage": dmg}

        # WIN CHALLENGES
        if win and deaths == 0:
            triggers.append({**base, "name": "Immortal Reverse", "points": -10})

        # LOSS CHALLENGES
        if not win:
            if kills == 0:
                triggers.append({**base, "name": "Pacifist", "points": 10})
            if assists == 0:
                triggers.append({**base, "name": "Silent Supporter", "points": 15})
            if tower_dmg == 0:
                triggers.append({**base, "name": "Siege Breaker", "points": 5})
            if deaths >= 20:
                triggers.append({**base, "name": "Twenty Bomb", "points": 5})
            if kills == 0 and deaths >= 20:
                triggers.append({**base, "name": "Tragic 20", "points": 50})

            # Check megas
            is_radiant = p.get("player_slot") < 128
            enemy_rax = match_data.get("barracks_status_dire" if is_radiant else "barracks_status_radiant", 0)
            if enemy_rax == 0:
                triggers.append({**base, "name": "Throwback Throw", "points": 8})

    # TEAM CHALLENGES (only check once per match, ignores anonymous players)
    # For Wet Noodle: need to compare against ALL losing players (including anonymous)
    # For Double Disaster: only count tracked friends
    losing_all = [p for p in players if not bool(p.get("win", 0)) and p.get("hero_damage") is not None]
    losing_friends = [p for p in friends if not bool(p.get("win", 0))]

    if losing_all:
        # Wet Noodle - lowest damage on losing team
        lowest_dmg = min(int(p.get("hero_damage", 0) or 0) for p in losing_all)
        for p in losing_friends:
            dmg = int(p.get("hero_damage", 0) or 0)
            if dmg == lowest_dmg:
                # Same base logic as individual, but adding the specific challenge name/points
                base = {
                    "steam_id": p.get("account_id"), "match_id": match_id,
                    "hero": get_hero_name(p.get("hero_id")),
                    "kda": f"{p.get('kills',0)}/{p.get('deaths',0)}/{p.get('assists',0)}",
                    "damage": dmg
                }
                triggers.append({**base, "name": "Wet Noodle", "points": 3})

        # Double Disaster Duo - 2+ friends with 0 kills
        zero_kill_friends = [p for p in losing_friends if int(p.get("kills", 0) or 0) == 0]
        if len(zero_kill_friends) >= 2:
            for p in zero_kill_friends:
                base = {
                    "steam_id": p.get("account_id"), "match_id": match_id,
                    "hero": get_hero_name(p.get("hero_id")),
                    "kda": f"0/{p.get('deaths',0)}/{p.get('assists',0)}",
                    "damage": int(p.get("hero_damage", 0) or 0)
                }
                triggers.append({**base, "name": "Double Disaster Duo", "points": 30})

    return triggers, match_time

# ---------------- DISCORD ---------------- #
def send_discord(message):
    """Send to Discord. Always prints locally for testing."""
    print("\n" + "="*80)
    print("DISCORD MESSAGE:")
    print("="*80)
    print(message)
    print("="*80 + "\n")

    if not WEBHOOK_URL or DEBUG_MODE:
        print("[INFO] Skipping actual Discord send (no webhook or debug mode)")
        return

    for attempt in range(3):
        try:
            r = session.post(WEBHOOK_URL, json={"content": message}, timeout=10)
            r.raise_for_status()
            return
        except Exception as e:
            if attempt == 2:
                print(f"[ERROR] Discord send failed: {e}")
            time.sleep(2)

# ---------------- MAIN PROCESSING ---------------- #
def process_match(match_id, store, processed_this_run, expected_friend_id=None):
    """
    Process a single match and ALL friends in it.
    Only marks as checked after processing ALL friends' challenges.

    Args:
        match_id: The match ID to process
        store: The data store
        processed_this_run: Set of match IDs already processed this run
        expected_friend_id: If provided, the friend whose history led us to this match

    Returns True if successfully processed.
    """
    match_id_str = str(match_id)

    # Skip if already checked OR already processed this run
    if match_id_str in store.get("checked_matches", {}):
        return True
    if match_id in processed_this_run:
        return True

    # Fetch match data
    match_data = fetch_full_match(match_id)
    if not match_data:
        return False

    # Check if fully parsed - pass expected_friend_id to verify they're visible
    is_parsed, reason = is_match_fully_parsed(match_data, expected_friend_id)
    if not is_parsed:
        print(f"[WARN] Match {match_id} not parsed: {reason}")

        # Store with info about who we expected to see
        unparsed_data = {
            "added": datetime.now(timezone.utc).isoformat(),
            "reason": reason
        }
        if expected_friend_id:
            unparsed_data["expected_friend"] = expected_friend_id
            unparsed_data["expected_friend_name"] = steam_names.get(expected_friend_id, str(expected_friend_id))

        store["unparsed_matches"][match_id_str] = unparsed_data
        return False

    # Get challenges for ALL friends in this match
    triggers, match_time = check_challenges(match_data)

    # Even if no triggers, mark as checked (no friends or no challenges)
    store.setdefault("checked_matches", {})[match_id_str] = match_time.isoformat()
    if match_id_str in store.get("unparsed_matches", {}):
        del store["unparsed_matches"][match_id_str]

    # Build a map of all tracked friends in this match -> name (string keys)
    friends_in_match_names = {
        str(p.get("account_id")): steam_names.get(p.get("account_id"), str(p.get("account_id")))
        for p in match_data.get("players", [])
        if p.get("account_id") in steam_names
    }

    # If no triggers, we're done
    if not triggers:
        print(f"[INFO] Match {match_id}: No challenges triggered")
        return True

    # Process all triggers and update store
    messages_by_player = {}

    for t in triggers:
        sid = str(t["steam_id"])

        # --- MODIFIED STORE STRUCTURE START ---

        # Create leaderboard entry if missing
        if sid not in store.setdefault("leaderboard", {}):
            store["leaderboard"][sid] = {
                "name": steam_names.get(int(sid), sid),
                "total_points": 0,
                "matches": {}
            }

        # Add total points
        store["leaderboard"][sid]["total_points"] += t["points"]

        # Per-match structure - Store general match stats *outside* the challenges list
        match_entry = store["leaderboard"][sid]["matches"].setdefault(str(match_id), {
            "date": match_time.strftime("%Y-%m-%d %H:%M UTC"),
            "total_points_in_match": 0,
            "hero": t.get("hero"), # Store hero once at the match level
            "kda": t.get("kda"),   # Store KDA once at the match level
            "damage": t.get("damage"), # Store Damage once at the match level
            # Include ALL tracked friends in the match (including the player)
            "friends_in_match": [
                name for fid, name in friends_in_match_names.items()
            ],
            "challenges": [] # Challenges will only store name and points
        })

        match_entry["total_points_in_match"] += t["points"]

        # Append simplified challenge entry
        match_entry["challenges"].append({
            "name": t["name"],
            "points": t["points"]
        })

        # --- MODIFIED STORE STRUCTURE END ---

        # Update daily - Using player name as key
        date_str = match_time.strftime("%Y-%m-%d")
        player_name = steam_names.get(t["steam_id"], sid) # Get the name
        
        store.setdefault("daily", {})
        if date_str not in store["daily"]:
            store["daily"][date_str] = {}
            
        # Use player_name as the key
        if player_name not in store["daily"][date_str]:
            store["daily"][date_str][player_name] = 0
            
        store["daily"][date_str][player_name] += t["points"]

        # Group for Discord
        if sid not in messages_by_player:
            messages_by_player[sid] = []
        messages_by_player[sid].append(t)

    # Send Discord message per player
    friend_ids = set(t["steam_id"] for t in triggers)

    print(f"[INFO] Match {match_id}: {len(triggers)} challenge(s) for {len(friend_ids)} friend(s)")

    for sid, player_triggers in messages_by_player.items():
        # sid is string; convert to int for steam_names lookup safely
        try:
            sid_int = int(sid)
        except:
            sid_int = None

        name = steam_names.get(sid_int, sid)

        # Pull player-specific match stats from the saved store structure (which was just updated)
        current_match_data = store["leaderboard"][sid]["matches"][match_id_str]

        hero = current_match_data["hero"]
        kda = current_match_data["kda"]
        dmg = current_match_data["damage"]
        friends_in_match = current_match_data["friends_in_match"]


        # --- MODIFIED DISCORD OUTPUT START ---

        msg = [
            f"🎮 **{name}** earned {len(player_triggers)} challenge(s)!",
            ""
        ]

        # Show friends in match (this now includes the player themself)
        if friends_in_match:
            msg.append(f"👥 Playing with: {', '.join(friends_in_match)}")

        msg.extend([
            f"📊 https://www.opendota.com/matches/{match_id}",
            f"🕐 {current_match_data['date']}",
            f"🧙 Hero: {hero}",
            f"🔪 KDA: {kda}",
            f"🔥 Damage: {dmg:,}", # Use formatting for thousands
            ""
        ])

        total = 0
        for t in player_triggers:
            symbol = "⬇️" if t["points"] < 0 else "⬆️"
            # Challenges are now listed without repeated stats
            msg.append(f"{symbol} **{t['name']}** ({t['points']:+} pts)")
            total += t["points"]

        current_total = store["leaderboard"][sid]["total_points"]
        msg.extend([
            "",
            f"**Match Total: {total:+} pts**",
            f"Spidey Bot caught you for **{current_total:+} pts total :)**"
        ])

        send_discord("\n".join(msg))

        # --- MODIFIED DISCORD OUTPUT END ---

    return True

def run_check():
    """Main check routine."""
    print(f"\n{'='*80}")
    print(f"Starting check at {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*80}\n")

    store = load_store()
    processed_this_run = set()  # Tracks match IDs processed this run to avoid duplicates

    # Retry unparsed matches first
    unparsed = list(store.get("unparsed_matches", {}).keys())
    print(f"[INFO] Retrying {len(unparsed)} unparsed matches...")

    for match_id_str in unparsed:
        match_id = int(match_id_str)
        unparsed_data = store["unparsed_matches"][match_id_str]
        expected_friend = unparsed_data.get("expected_friend")

        if process_match(match_id, store, processed_this_run, expected_friend):
            print(f"[SUCCESS] Match {match_id} now parsed!")
            processed_this_run.add(match_id)

    # Check each friend for new matches
    print(f"\n[INFO] Checking for new matches...")

    for friend_id, friend_name in steam_names.items():
        print(f"\n[INFO] Checking {friend_name}...")
        offset = 0

        while True:
            match_ids = fetch_recent_match_ids(friend_id, limit=BATCH_SIZE, offset=offset)
            if not match_ids:
                break

            for match_id in match_ids:
                # Skip if already processed this run
                if match_id in processed_this_run:
                    continue

                # Pass friend_id so we can verify they're visible in the match
                if process_match(match_id, store, processed_this_run, friend_id):
                    processed_this_run.add(match_id)

            offset += BATCH_SIZE

    # Save and print summary
    save_store(store)

    print(f"\n{'='*80}")
    print(f"Check complete!")
    print(f"{'='*80}")
    print(f"  Matches processed this run: {len(processed_this_run)}")
    print(f"  Total checked all-time: {len(store.get('checked_matches', {}))}")
    print(f"  Waiting for parse: {len(store.get('unparsed_matches', {}))}")

    # Top 3
    if store.get("leaderboard"):
        sorted_players = sorted(
            store["leaderboard"].items(),
            key=lambda x: x[1].get("total_points", 0),
            reverse=True
        )[:3]
        print("\n  Top 3:")
        for i, (sid, data) in enumerate(sorted_players, 1):
            # attempt to use steam_names if possible
            try:
                sid_int = int(sid)
            except:
                sid_int = None
            name = steam_names.get(sid_int, data.get("name", sid))
            print(f"    {i}. {name}: {data.get('total_points', 0):+} pts")

    print(f"{'='*80}\n")

# ---------------- SINGLE MATCH TEST FUNCTION ---------------- #

def test_single_match(match_id):
    """Processes a single, specified match ID for testing purposes."""
    print(f"\n{'='*80}")
    print(f"Running single match test for ID: {match_id}")
    print(f"{'='*80}\n")

    try:
        match_id_int = int(match_id)
    except ValueError:
        print(f"[ERROR] Invalid match ID provided: '{match_id}'. Must be a number.")
        return

    store = load_store()
    processed_this_run = set()

    # The single test run does not need an expected_friend_id since we trust the user input
    # However, if the match wasn't fully parsed, it would still be added to unparsed_matches.
    process_match(match_id_int, store, processed_this_run)

    save_store(store)
    
    if match_id_int in processed_this_run:
        print(f"\n[SUCCESS] Test match {match_id} successfully processed and challenges checked.")
    else:
        print(f"\n[INFO] Test match {match_id} completed. Check logs for results/warnings.")

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            # If an argument is provided, treat it as the match ID for testing
            test_single_match(sys.argv[1])
        else:
            # Otherwise, run the normal check routine
            run_check()
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Critical error: {e}")
        import traceback
        traceback.print_exc()