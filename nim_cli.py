# nim_cli.py
import json
import os
from datetime import datetime, timedelta

from nim_core import (
    load_previous_data,
    save_current_data,
    compute_deltas_all,
    apply_deltas_to_snapshot,
    get_top_videos_by_metric,
    fetch_current_snapshot_from_youtube,
    build_snapshot_from_channels_and_keywords,
)

# Original tracked videos list (for assignment / option 1 & 4)
TRACKED_VIDEOS = {
    "hasan_x8d6K399WW4": {
        "channel_name": "HasanAbi",
        "video_id": "x8d6K399WW4",
        "label": "HasanAbi – we are Charlie Kirk"
    },
    "boyboy_Sfrjpy5cJCs": {
        "channel_name": "Boy Boy",
        "video_id": "Sfrjpy5cJCs",
        "label": "BoyBoy – I snuck into a major arms dealer conference"
    },
    # ... (rest of your fixed list – same as before)
}

LAST_RUN_FILE = "last_option5_run.json"


def get_last_option5_run():
    if not os.path.exists(LAST_RUN_FILE):
        return None
    try:
        with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return datetime.fromisoformat(data.get("last_run"))
    except Exception:
        return None


def set_last_option5_run():
    now = datetime.now().isoformat(timespec="seconds")
    with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_run": now}, f, indent=2)


def fetch_current_data_for_all_videos_manual():
    """
    Manual entry mode (option 1).
    """
    snapshot = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "videos": {}
    }

    print("Enter current YouTube stats for tracked videos:")
    print("------------------------------------------------\n")

    for video_key, meta in TRACKED_VIDEOS.items():
        print(f"Channel: {meta['channel_name']}")
        print(f"Video ID: {meta['video_id']}")
        print(f"Label:    {meta.get('label', video_key)}")

        views = int(input("  Views: ").strip())
        likes = int(input("  Likes: ").strip())
        comments = int(input("  Comments: ").strip())
        subs = int(input("  Subscribers: ").strip())

        snapshot["videos"][video_key] = {
            "channel_name": meta["channel_name"],
            "video_id": meta["video_id"],
            "views": views,
            "likes": likes,
            "comments": comments,
            "subscribers": subs,
            "label": meta.get("label", video_key),
        }

        print("")

    return snapshot


def display_top_movers_grid(top_list, heading="TOP YOUTUBE MOVERS"):
    print("\n" * 3)
    print("===========================================")
    print(f"        {heading}      ")
    print("===========================================\n")

    if not top_list:
        print("No data to display.")
        input("\nPress ENTER to return to menu...")
        return

    row_size = 4
    for i in range(0, len(top_list), row_size):
        row = top_list[i:i + row_size]

        # First line: labels
        for item in row:
            label = item["label"][:20]
            print(f"{label:<22}", end=" | ")
        print("")

        # Second line: deltas
        for item in row:
            delta = item["delta"]
            print(f"Δ {delta:<18}", end=" | ")
        print("\n")

    input("\nPress ENTER to return to menu...")


def main_menu():
    running = True

    while running:
        print("\n===== YOUTUBE DASHBOARD (CLI) =====")
        print("1. Capture ALL tracked videos manually + show top movers")
        print("2. View last snapshot only")
        print("3. Exit")
        print("4. Fetch ALL tracked videos from YouTube API (fixed list) + show top movers")
        print("5. Build snapshot from channels + keywords config + show top movers")
        choice = input("Select an option: ").strip()

        if choice == "1":
            previous_snapshot = load_previous_data()
            current_snapshot = fetch_current_data_for_all_videos_manual()
            # embed deltas (raw + %)
            current_snapshot = apply_deltas_to_snapshot(previous_snapshot, current_snapshot)
            save_current_data(current_snapshot)

            top_list = get_top_videos_by_metric(
                current_snapshot, metric="views_delta_pct", top_n=16
            )
            display_top_movers_grid(top_list, heading="TOP MOVERS (Manual)")

        elif choice == "2":
            snapshot = load_previous_data()
            if snapshot is None:
                print("No saved data found.")
                input("Press ENTER to return to menu...")
            else:
                # If snapshot already has deltas, use them; otherwise fall back to views.
                metric = "views_delta_pct" if any(
                    "views_delta_pct" in v for v in snapshot.get("videos", {}).values()
                ) else "views"
                top_list = get_top_videos_by_metric(snapshot, metric=metric, top_n=16)
                display_top_movers_grid(top_list, heading="LAST SNAPSHOT")

        elif choice == "3":
            running = False

        elif choice == "4":
            print("Fetching stats from YouTube API for fixed TRACKED_VIDEOS...")
            previous_snapshot = load_previous_data()
            current_snapshot = fetch_current_snapshot_from_youtube(TRACKED_VIDEOS)
            current_snapshot = apply_deltas_to_snapshot(previous_snapshot, current_snapshot)
            save_current_data(current_snapshot)

            top_list = get_top_videos_by_metric(
                current_snapshot, metric="views_delta_pct", top_n=16
            )
            display_top_movers_grid(top_list, heading="TOP MOVERS (Fixed list)")

        elif choice == "5":
            last_run = get_last_option5_run()
            if last_run is not None:
                elapsed = datetime.now() - last_run
                if elapsed < timedelta(minutes=1):
                    print("\n[INFO] Option 5 was already run within the last 1 minute.")
                    print("      Skipping to avoid burning YouTube API quota.")
                    input("\nPress ENTER to return to menu...")
                    continue

            current_snapshot = build_snapshot_from_channels_and_keywords(
                max_per_channel=5,
                max_per_keyword=3,
            )

            if not current_snapshot.get("videos"):
                print("\n[INFO] No videos were fetched this run (likely quota or config issue).")
                print("       Keeping previous snapshot on disk, not overwriting.")
                input("\nPress ENTER to return to menu...")
                continue

            previous_snapshot = load_previous_data()
            current_snapshot = apply_deltas_to_snapshot(previous_snapshot, current_snapshot)
            save_current_data(current_snapshot)
            set_last_option5_run()

            top_list = get_top_videos_by_metric(
                current_snapshot, metric="views_delta_pct", top_n=16
            )
            display_top_movers_grid(top_list, heading="TOP MOVERS (Channels + Keywords)")

        else:
            print("Invalid option. Please try again.")


if __name__ == "__main__":
    main_menu()