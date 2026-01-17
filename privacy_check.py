from data import load_store, save_store
from discord import send_discord
from privacy_utils import check_friends_privacy, notify_privacy_issues  # we'll put the function there

# Load your current store
store = load_store()

# Run the privacy check
store = check_friends_privacy(store)

# Save updates
save_store(store)

# Send Discord notification if there are privacy issues
notify_privacy_issues(store)
