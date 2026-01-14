from datetime import datetime, timezone
import requests
import time
from config import BATCH_SIZE, API_DELAY, MAX_RETRIES, REQUEST_TIMEOUT, CONNECT_TIMEOUT, CHECK_FROM_DATE

# Add session for connection pooling
session = requests.Session()
session.headers.update({'User-Agent': 'ChallengeChecker/1.0'})

# ---------------- API CALLS WITH EXPONENTIAL BACKOFF ---------------- #
def fetch_recent_match_ids(account_id, limit=BATCH_SIZE, offset=0):
    """Fetch recent matches with optimized error handling and backoff."""
    url = f"https://api.opendota.com/api/players/{account_id}/matches?limit={limit}&offset={offset}"
    
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, timeout=(CONNECT_TIMEOUT, REQUEST_TIMEOUT))
            r.raise_for_status()
            matches = r.json()
            if not isinstance(matches, list):
                raise ValueError(f"Unexpected response format: {type(matches)}")

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
