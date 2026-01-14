import json
from config import STORE_FILE, HEROES_FILE, STEAM_NAMES_FILE

# ---------------- STEAM NAMES LOADING ---------------- #
def load_steam_names():
    """Load steam names from JSON file, converting string keys to integers."""
    try:
        with open(STEAM_NAMES_FILE, "r") as f:
            names_dict = json.load(f)
            # Convert string keys to integers
            return {int(k): v for k, v in names_dict.items()}
    except FileNotFoundError:
        print(f"[WARN] {STEAM_NAMES_FILE} not found, using empty steam_names")
        return {}
    except Exception as e:
        print(f"[ERROR] Failed to load {STEAM_NAMES_FILE}: {e}")
        return {}

steam_names = load_steam_names()

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
