from datetime import datetime, timezone
from api import fetch_full_match
from validation import is_match_fully_parsed
from challenges import check_challenges
from data import steam_names, get_hero_name
from discord import send_discord

# ---------------- MAIN PROCESSING ---------------- #
def process_match(match_id, store, processed_this_run, expected_friend_id=None):
    """
    Handles fetching, validating, and saving match data.
    All logic/point/streak calculations happen inside check_challenges.
    """
    match_id_str = str(match_id)

    # 1. Skip already handled matches
    if match_id_str in store.get("checked_matches", {}):
        return True
    if match_id in processed_this_run:
        return True

    # 2. Fetch data from OpenDota
    match_data = fetch_full_match(match_id)
    if not match_data:
        return False

    # 3. Gatekeeper: Ensure match is fully parsed for advanced stats
    is_parsed, reason = is_match_fully_parsed(match_data, expected_friend_id)
    if not is_parsed:
        print(f"[WARN] Match {match_id} deferred: {reason}")
        store.setdefault("unparsed_matches", {})[str(match_id)] = {
    "first_seen": datetime.now(timezone.utc).isoformat(),
    "expected_friend": expected_friend_id,
       "retries": store["unparsed_matches"].get(str(match_id), {}).get("retries", 0) + 1
    }

        return False

    # 4. The Brain: Run all logic (including streak updates)
    # This is where streaks are compared against store["leaderboard"]
    triggers, match_time = check_challenges(match_data, store)
    match_log = store.setdefault("challenge_log", {}).setdefault(match_id_str, [])

    for t in triggers:
        match_log.append({
            **t,
            "timestamp": match_time.isoformat()
    })
    # 5. Clean up tracking lists
    store.setdefault("checked_matches", {})[match_id_str] = True

    if match_id_str in store.get("unparsed_matches", {}):
        del store["unparsed_matches"][match_id_str]

    # 6. Save Match History to Leaderboard
    # Even if there were no triggers, we record the match so streaks stay accurate
    players = match_data.get("players", [])
    friends_in_match = [p for p in players if p.get("account_id") in steam_names.keys()]
    
    # Pre-build a list of all tracked friends in this specific match
    all_friend_names = [steam_names[p['account_id']] for p in friends_in_match]

    for p in friends_in_match:
        sid_str = str(p.get("account_id"))
        
        # Ensure player has a folder in our leaderboard
        player_entry = store.setdefault("leaderboard", {}).setdefault(sid_str, {
            "name": steam_names.get(p["account_id"]),
            "total_points": 0,
            "matches": {}
        })

        # Map triggers to the correct player
        player_triggers = [t for t in triggers if str(t["steam_id"]) == sid_str]

        # Skip storing match entirely if nothing happened
        if not player_triggers:
            continue

        # Now create the match record (only when needed)
        match_record = player_entry["matches"].setdefault(match_id_str, {
            "date": match_time.strftime("%Y-%m-%d %H:%M UTC"),
            "hero": get_hero_name(p.get("hero_id")),
            "kda": f"{p.get('kills', 0)}/{p.get('deaths', 0)}/{p.get('assists', 0)}",
            "win": bool(p.get("win")),
            "points": 0,
            "friends_in_match": all_friend_names,
            "damage": int(p.get("hero_damage", 0) or 0),
            "challenges": []
        })

        # Apply triggers
        for t in player_triggers:
            match_record["challenges"].append({
                "name": t["name"],
                "points": t["points"]
            })
            match_record["points"] += t["points"]
            player_entry["total_points"] += t["points"]


    # 7. Final Notification (ONE MESSAGE PER MATCH)
    if triggers:
        print(f"[SUCCESS] Processed Match {match_id}: {len(triggers)} triggers found.")

        # Group triggers by player
        triggers_by_player = {}
        for t in triggers:
            triggers_by_player.setdefault(str(t["steam_id"]), []).append(t)

        # Match header
        msg = [
            "🎮 **Match Challenges Summary**",
            f"📊 https://www.opendota.com/matches/{match_id}",
            f"🕐 {match_time.strftime('%Y-%m-%d %H:%M UTC')}",
            ""
        ]

        # Build per-player sections
        for sid_str, player_triggers in triggers_by_player.items():
            player = store["leaderboard"][sid_str]
            match_data = player["matches"][match_id_str]

            name = player["name"]
            hero = match_data["hero"]
            kda = match_data["kda"]
            dmg = match_data["damage"]
            friends = match_data["friends_in_match"]

            msg.append(f"🧑 **{name}**")
            msg.append(f"🧙 {hero} | 🔪 {kda} | 🔥 {dmg:,} dmg")

            other_friends = [f for f in friends if f != name]

            if other_friends:
                msg.append(f"👥 With: {', '.join(other_friends)}")

            match_points = 0
            for t in player_triggers:
                symbol = "⬆️" if t["points"] > 0 else "⬇️"
                msg.append(f"{symbol} {t['name']} ({t['points']:+} pts)")
                match_points += t["points"]

            total_points = player["total_points"]
            msg.append(f"**Match: {match_points:+} pts | Total: {total_points:+} pts**")
            msg.append("")

        send_discord("\n".join(msg))
    else:
        print(f"[INFO] Processed Match {match_id}: No points awarded.")
