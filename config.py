from datetime import datetime, timezone
import os

# ---------------- CONFIG ---------------- #
END_DATE = datetime(2026, 3, 1, tzinfo=timezone.utc)
if datetime.now(timezone.utc) >= END_DATE:
    print("End date reached, skipping run.")
    exit(0)

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
CHECK_FROM_DATE = datetime(2026, 1, 16, tzinfo=timezone.utc)
STORE_FILE = "store.json"
HEROES_FILE = "heroes.json"
BATCH_SIZE = 20
API_DELAY = 0.5  # Reduced from 1.0, OpenDota recommends < 1 req/sec
MAX_RETRIES = 3  # Reduced from 5 to fail faster on persistent issues
REQUEST_TIMEOUT = 20  # Increased from 15 for slower connections
CONNECT_TIMEOUT = 10  # Add separate connection timeout
DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() == "true"
STEAM_NAMES_FILE = "steam_names.json"
