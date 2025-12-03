import csv
import json
import os
from urllib.parse import urlparse
import requests

from config import YOUTUBE_API_KEY  # your existing config.py


CHANNELS_CSV_PATH = "channels.csv"
KEYWORDS_CSV_PATH = "keywords.csv"
CHANNELS_JSON_PATH = "channels.json"
KEYWORDS_JSON_PATH = "keywords.json"


def resolve_channel_id_from_url(api_key: str, url: str) -> str | None:
    """
    Try to extract or resolve a YouTube channel ID from a channel URL.

    Supports:
      - https://www.youtube.com/channel/UCxxxx
      - https://www.youtube.com/@handle
      - Falls back to search if needed.
    """
    if not url:
        return None

    parsed = urlparse(url)
    path = parsed.path or ""

    # Case 1: direct /channel/UCxxxxxx style
    if "/channel/" in path:
        parts = path.split("/channel/")
        if len(parts) > 1:
            candidate = parts[1].strip("/")
            if candidate.startswith("UC"):
                return candidate

    # Case 2: handle style /@handle
    # e.g. https://www.youtube.com/@hasanabi
    handle = None
    if "/@" in path:
        # path looks like /@hasanabi or /@hasanabi/videos
        after = path.split("/@")[-1]
        handle = "@" + after.split("/")[0]

    if handle:
        # Use channels.list with forHandle
        url = "https://www.googleapis.com/youtube/v3/channels"
        params = {
            "part": "id",
            "forHandle": handle,
            "key": api_key,
        }
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        if items:
            return items[0]["id"]

    # Fallback: treat the URL as a search query to find the channel
    # This is less precise, but better than nothing for odd URLs.
    search_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": url,
        "type": "channel",
        "maxResults": 1,
        "key": api_key,
    }
    r = requests.get(search_url, params=params)
    r.raise_for_status()
    data = r.json()
    items = data.get("items", [])
    if items:
        return items[0]["id"]["channelId"]

    return None


def build_channels_json_from_csv():
    if not YOUTUBE_API_KEY:
        raise RuntimeError("No YOUTUBE_API_KEY found in config.py")

    if not os.path.exists(CHANNELS_CSV_PATH):
        print(f"No {CHANNELS_CSV_PATH} file found. Skipping channels.")
        return

    channels = []
    with open(CHANNELS_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row.get("key") or "").strip()
            url = (row.get("url") or "").strip()
            label = (row.get("label") or "").strip() or key
            group = (row.get("group") or "").strip()

            if not key or not url:
                print(f"Skipping row with missing key/url: {row}")
                continue

            try:
                channel_id = resolve_channel_id_from_url(YOUTUBE_API_KEY, url)
            except Exception as e:
                print(f"Error resolving channel for {key} ({url}): {e}")
                channel_id = None

            if not channel_id:
                print(f"Could not resolve channel ID for {key} ({url})")
                continue

            channels.append({
                "key": key,
                "channel_id": channel_id,
                "label": label,
                "group": group,
            })

    with open(CHANNELS_JSON_PATH, "w", encoding="utf-8") as out:
        json.dump(channels, out, indent=2, ensure_ascii=False)

    print(f"Wrote {len(channels)} channels to {CHANNELS_JSON_PATH}")


def build_keywords_json_from_csv():
    if not os.path.exists(KEYWORDS_CSV_PATH):
        print(f"No {KEYWORDS_CSV_PATH} file found. Skipping keywords.")
        return

    keyword_entries = []
    with open(KEYWORDS_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row.get("key") or "").strip()
            label = (row.get("label") or "").strip() or key
            group = (row.get("group") or "").strip()
            queries_raw = (row.get("queries") or "").strip()

            if not key or not queries_raw:
                print(f"Skipping row with missing key/queries: {row}")
                continue

            # Split queries on ';'
            queries = [q.strip() for q in queries_raw.split(";") if q.strip()]

            keyword_entries.append({
                "key": key,
                "label": label,
                "group": group,
                "queries": queries,
            })

    with open(KEYWORDS_JSON_PATH, "w", encoding="utf-8") as out:
        json.dump(keyword_entries, out, indent=2, ensure_ascii=False)

    print(f"Wrote {len(keyword_entries)} keyword groups to {KEYWORDS_JSON_PATH}")


if __name__ == "__main__":
    build_channels_json_from_csv()
    build_keywords_json_from_csv()
