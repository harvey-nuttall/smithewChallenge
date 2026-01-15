from datetime import datetime, timezone
from data import steam_names, get_hero_name

def check_challenges(match_data, store):
    """
    Unofficial BOT-only challenges.
    Assumes match is fully parsed. Each match is evaluated independently.
    """
    match_id = match_data.get("match_id")
    match_time = datetime.fromtimestamp(match_data.get("start_time", 0), tz=timezone.utc)
    players = match_data.get("players", [])
    duration = int(match_data.get("duration", 0))

    friends = [p for p in players if p.get("account_id") in steam_names]
    if not friends:
        return [], match_time

    triggers = []

    for p in friends:
        sid = p.get("account_id")

        hero = get_hero_name(p.get("hero_id"))
        kills = int(p.get("kills", 0) or 0)
        deaths = int(p.get("deaths", 0) or 0)
        assists = int(p.get("assists", 0) or 0)
        win = bool(p.get("win", 0))
        tower_dmg = int(p.get("tower_damage", 0) or 0)

        is_radiant = p.get("player_slot", 0) < 128
        enemy_rax = match_data.get(
            "barracks_status_dire" if is_radiant else "barracks_status_radiant", 0
        )

        base = {
            "steam_id": sid,
            "match_id": match_id,
            "hero": hero,
            "kda": f"{kills}/{deaths}/{assists}",
        }

        # ============================================================
        # 🎁 UNOFFICIAL REWARDS
        # ============================================================

        # 5 Stack Doom (Win)
        if p.get("party_size") == 5 and win:
            triggers.append({**base, "name": "5-Stack Doom Win", "points": 5})

        # Rampages
        multi = p.get("multi_kills", {})
        if isinstance(multi, dict):
            rampages = int(multi.get("5", 0))
            if rampages > 0:
                points = 15 + (rampages - 1) * 3
                triggers.append({
                    **base,
                    "name": f"Rampage x{rampages}",
                    "points": points
                })

        # Win < 25 mins
        if win and duration < 1500:
            triggers.append({**base, "name": "Win <25m", "points": 3})

        # 15+ Kills Performance
        if kills >= 15:
            points = 5
            if deaths == 0:
                points *= 2
            if assists == 0:
                points *= 3
            triggers.append({
                **base,
                "name": "15+ Kill Game",
                "points": points
            })
        
        # Winning a game without taking all barracks
        if win:
            if enemy_rax == 63:  # Opponent took all your barracks
                points = 10
                triggers.append({**base, "name": "Win vs Full Enemy Megas, without MEGAS!", "points": points})
            else:
                points = 1
                triggers.append({**base, "name": "Win without Taking All Barracks", "points": points})

        # ============================================================
        # ⚠️ UNOFFICIAL PENALTIES
        # ============================================================

        # 5 Stack Doom (Loss)
        if p.get("party_size") == 5 and not win:
            triggers.append({**base, "name": "5-Stack Doom Loss", "points": -5})

        # Tower Damage
        if tower_dmg < 100:
            triggers.append({
                **base,
                "name": "Low Tower Damage",
                "points": -3 if tower_dmg == 0 else -1
            })

        # 0 Kills
        if kills == 0:
            points = -40 if assists == 0 else -20
            triggers.append({
                **base,
                "name": "0 Kill Game",
                "points": points
            })

        # Lost with Enemy Megas
        if not win and enemy_rax == 0:
            triggers.append({
                **base,
                "name": "Lost vs Megas",
                "points": -5
            })

        # 20+ Deaths
        if deaths >= 20:
            points = -20 if kills == 0 else -10
            triggers.append({
                **base,
                "name": "20+ Deaths",
                "points": points
            })

        # Loss < 25 mins
        if not win and duration < 1500:
            triggers.append({**base, "name": "Loss <25m", "points": -5})

    return triggers, match_time