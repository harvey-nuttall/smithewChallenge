from data import steam_names

def is_match_fully_parsed(match_data, expected_friend_id=None):
    """
    Validate match data for Unofficial BOT challenges only.
    Returns (bool, reason)
    """

    # Must be replay parsed
    if match_data.get("version") is None:
        return False, "Waiting for OpenDota replay parse"

    # Core match fields
    for field in ("match_id", "start_time", "duration"):
        if match_data.get(field) is None:
            return False, f"Missing {field}"

    players = match_data.get("players", [])
    if len(players) != 10:
        return False, f"Only {len(players)}/10 players"

    friends = [p for p in players if p.get("account_id") in steam_names]

    if expected_friend_id and expected_friend_id not in [f.get("account_id") for f in friends]:
        friend_name = steam_names.get(expected_friend_id, expected_friend_id)
        return False, f"{friend_name} has privacy enabled"

    if not friends:
        return True, None  # No tracked players, safe to skip

    required_fields = [
        "account_id",
        "hero_id",
        "kills",
        "deaths",
        "assists",
        "win",
        "player_slot",
        "tower_damage",
        "multi_kills",
        "party_size",
    ]

    for f in friends:
        for field in required_fields:
            if field not in f or f[field] is None:
                name = steam_names.get(f.get("account_id"), "Unknown")
                return False, f"{name} missing {field}"

    # Barracks status (for megas loss penalty)
    if match_data.get("barracks_status_radiant") is None:
        return False, "Missing radiant barracks status"
    if match_data.get("barracks_status_dire") is None:
        return False, "Missing dire barracks status"

    return True, None
