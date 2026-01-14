import time
import requests
from config import WEBHOOK_URL, DEBUG_MODE
from api import session

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
