from datetime import datetime, timezone
from data import steam_names, get_hero_name

def check_challenges(match_data, store):
    match_id = match_data.get("match_id")
    match_time = datetime.fromtimestamp(match_data.get("start_time", 0), tz=timezone.utc)
    players = match_data.get("players", [])
    duration = int(match_data.get("duration", 0))

    friends = [p for p in players if p.get("account_id") in steam_names]
    if not friends:
        return [], match_time
    is_group_game = len(friends) >= 4

    triggers = []

    for p in friends:
        sid = p.get("account_id")
        hero = get_hero_name(p.get("hero_id"))
        kills = int(p.get("kills", 0) or 0)
        deaths = int(p.get("deaths", 0) or 0)
        assists = int(p.get("assists", 0) or 0)
        win = bool(p.get("win", 0))
        tower_dmg = int(p.get("tower_damage", 0) or 0)
        
        # Barracks Math
        is_radiant = p.get("player_slot", 0) < 128
        your_rax = match_data.get("barracks_status_radiant" if is_radiant else "barracks_status_dire")
        enemy_rax = match_data.get("barracks_status_dire" if is_radiant else "barracks_status_radiant")

        base = {
            "steam_id": sid,
            "match_id": match_id,
            "hero": hero,
            "kda": f"{kills}/{deaths}/{assists}",
        }

        # --- 🎁 REWARDS ---
        
        # 5-Stack Win
        if is_group_game and win:
            triggers.append({**base, "name": "The Unstoppable Hivemind", "points": 5})

        # Performance: Pudge's Wet Dream / Literal God / Greedy Bastard
        if kills >= 15:
            p_val = 5
            bonus_desc = ""
            if deaths == 0:
                p_val *= 2  # Literal God
                bonus_desc += " (Literal God x2)"
            if assists == 0:
                p_val *= 3  # Greedy Bastard
                bonus_desc += " (Greedy Bastard x3)"
            
            triggers.append({**base, "name": f"Pudge's Wet Dream{bonus_desc}", "points": p_val})

        # Speedrunner Vibes
        if win and duration < 1500:
            triggers.append({**base, "name": "Speedrunner Vibes: <25m Win", "points": 3})

        # Win Logic: Anime Protagonist vs Work Smarter
        if win:
            if your_rax == 0:
                triggers.append({**base, "name": "The Anime Protagonist: Comeback", "points": 10})
            elif enemy_rax > 0:
                triggers.append({**base, "name": "Work Smarter, Not Harder: Efficiency", "points": 1})

        # --- ⚠️ PENALTIES ---

        # 5-Stack Loss
        if is_group_game and not win:
            triggers.append({**base, "name": "Collective Brain Lag: 5-Stack Loss", "points": -5})

        # AFK Jungler
        if tower_dmg < 100:
            p_val = -3 if tower_dmg == 0 else -1
            triggers.append({**base, "name": "AFK Jungler Syndrome", "points": p_val})

        # Kill-less Penalties
        if kills == 0:
            if assists == 0:
                triggers.append({**base, "name": "The Uninstalled Client (0K/0A)", "points": -40})
            else:
                triggers.append({**base, "name": "The Spectator (0 Kills)", "points": -20})

        # Tactical Throw / Stomped
        if not win:
            if enemy_rax == 0:
                triggers.append({**base, "name": "Tactical Throw: Lost with Megas", "points": -5})
            if duration < 1500:
                triggers.append({**base, "name": "Sub-20 Minute Trash: Stomped", "points": -5})

        # The Walking Ward / Double Taxed
        if deaths >= 20:
            p_val = -10
            p_name = "The Walking Ward: 20+ Deaths"
            if kills == 0:
                p_val *= 2  # Double Taxed
                p_name = "Double Taxed: 0 Kills Feeding"
            triggers.append({**base, "name": p_name, "points": p_val})

    return triggers, match_time
