from datetime import datetime, timezone
from api import fetch_recent_match_ids, fetch_full_match
from data import steam_names
from discord import send_discord

def check_friends_privacy(store):
    store.setdefault("privacy_issues", {})

    for friend_id, friend_name in steam_names.items():
        match_ids = fetch_recent_match_ids(friend_id, limit=1)
        if not match_ids:
            store["privacy_issues"][str(friend_id)] = {
                "name": friend_name,
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "reason": "No matches visible / private profile"
            }
            continue

        match_data = fetch_full_match(match_ids[0])
        if not match_data:
            store["privacy_issues"][str(friend_id)] = {
                "name": friend_name,
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "reason": "Match data private or inaccessible"
            }
            continue

        friend_in_match = any(p.get("account_id") == friend_id for p in match_data.get("players", []))
        if not friend_in_match:
            store["privacy_issues"][str(friend_id)] = {
                "name": friend_name,
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "reason": "Friend not visible in match (private profile)"
            }

    return store

def notify_privacy_issues(store):
    if "privacy_issues" not in store:
        return

    lines = ["🔒 **Steam Privacy Issues Detected**", ""]
    for pid, info in store["privacy_issues"].items():
        lines.append(f"• **{info['name']}** – {info['reason']}")

    send_discord("\n".join(lines))
