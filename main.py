from datetime import datetime, timezone
import sys
from config import BATCH_SIZE
from data import steam_names, load_store, save_store
from api import fetch_recent_match_ids
from processor import process_match

def run_check():
    """Main check routine."""
    print(f"\n{'='*80}")
    print(f"Starting check at {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*80}\n")

    store = load_store()
    processed_this_run = set()  # Tracks match IDs processed this run to avoid duplicates

    # Retry unparsed matches first
    unparsed = list(store.get("unparsed_matches", {}).keys())
    print(f"[INFO] Retrying {len(unparsed)} unparsed matches...")

    for match_id_str in unparsed:
        match_id = int(match_id_str)
        unparsed_data = store["unparsed_matches"][match_id_str]
        expected_friend = unparsed_data.get("expected_friend")

        if process_match(match_id, store, processed_this_run, expected_friend):
            print(f"[SUCCESS] Match {match_id} now parsed!")
            processed_this_run.add(match_id)

    # Check each friend for new matches
    print(f"\n[INFO] Checking for new matches...")

    for friend_id, friend_name in steam_names.items():
        print(f"\n[INFO] Checking {friend_name}...")
        offset = 0

        while True:
            match_ids = fetch_recent_match_ids(friend_id, limit=BATCH_SIZE, offset=offset)
            if not match_ids:
                break

            for match_id in match_ids:
                # Skip if already processed this run
                if match_id in processed_this_run:
                    continue

                # Pass friend_id so we can verify they're visible in the match
                if process_match(match_id, store, processed_this_run, friend_id):
                    processed_this_run.add(match_id)

            offset += BATCH_SIZE

    # Save and print summary
    save_store(store)

    print(f"\n{'='*80}")
    print(f"Check complete!")
    print(f"{'='*80}")
    print(f"  Matches processed this run: {len(processed_this_run)}")
    print(f"  Total checked all-time: {len(store.get('checked_matches', {}))}")
    print(f"  Waiting for parse: {len(store.get('unparsed_matches', {}))}")

    # Top 3
    if store.get("leaderboard"):
        sorted_players = sorted(
            store["leaderboard"].items(),
            key=lambda x: x[1].get("total_points", 0),
            reverse=True
        )[:3]
        print("\n  Top 3:")
        for i, (sid, data) in enumerate(sorted_players, 1):
            # attempt to use steam_names if possible
            try:
                sid_int = int(sid)
            except:
                sid_int = None
            name = steam_names.get(sid_int, data.get("name", sid))
            print(f"    {i}. {name}: {data.get('total_points', 0):+} pts")

    print(f"{'='*80}\n")

# ---------------- SINGLE MATCH TEST FUNCTION ---------------- #

def test_single_match(match_id):
    """Processes a single, specified match ID for testing purposes."""
    print(f"\n{'='*80}")
    print(f"Running single match test for ID: {match_id}")
    print(f"{'='*80}\n")

    try:
        match_id_int = int(match_id)
    except ValueError:
        print(f"[ERROR] Invalid match ID provided: '{match_id}'. Must be a number.")
        return

    store = load_store()
    processed_this_run = set()

    # The single test run does not need an expected_friend_id since we trust the user input
    # However, if the match wasn't fully parsed, it would still be added to unparsed_matches.
    process_match(match_id_int, store, processed_this_run)

    save_store(store)
    
    if match_id_int in processed_this_run:
        print(f"\n[SUCCESS] Test match {match_id} successfully processed and challenges checked.")
    else:
        print(f"\n[INFO] Test match {match_id} completed. Check logs for results/warnings.")

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            # If an argument is provided, treat it as the match ID for testing
            test_single_match(sys.argv[1])
        else:
            # Otherwise, run the normal check routine
            run_check()
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Critical error: {e}")
        import traceback
        traceback.print_exc()
