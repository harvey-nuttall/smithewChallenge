from data import steam_names

def is_match_fully_parsed(match_data, expected_friend_id=None):
    """
    Validate match data based on specific challenge requirements 
    rather than just the OpenDota 'version' flag.
    """
    # 1. Essential Match-Level Data
    # Required for: Speedrunner Vibes, Comeback/Throw (Barracks)
    essential_fields = [
        "match_id", 
        "duration", 
        "barracks_status_radiant", 
        "barracks_status_dire"
    ]
    for field in essential_fields:
        if match_data.get(field) is None:
            return False, f"Waiting for OpenDota to parse {field}"

    players = match_data.get("players", [])
    if not players or len(players) < 10:
        return False, "Player data incomplete"

    # 2. Identify tracked friends
    friends = [p for p in players if p.get("account_id") in steam_names]

    # Privacy Check
    if expected_friend_id and expected_friend_id not in [f.get("account_id") for f in friends]:
        friend_name = steam_names.get(expected_friend_id, expected_friend_id)
        return False, f"{friend_name} has privacy enabled (Data missing)"

    if not friends:
        return True, None # No friends to track, no need to wait for parse

    # 3. Deep Player-Level Validation
    # These fields are required for Pudge/God/Greedy/AFK/Rampage challenges
    required_player_fields = [
        "kills", "deaths", "assists", "win", 
        "tower_damage", "hero_id"
    ]

    for f in friends:
        name = steam_names.get(f.get("account_id"), "Unknown")
        
        # Check standard stats
        for field in required_player_fields:
            if f.get(field) is None:
                return False, f"Waiting for parse: {name} {field} is null"

    return True, None
