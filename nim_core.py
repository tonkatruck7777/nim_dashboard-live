# nim_core.py
import json
import os
from datetime import datetime

import requests
from requests.exceptions import HTTPError

from config import YOUTUBE_API_KEY

DATA_FILE_PATH = "youtube_metrics.json"
CHANNELS_CONFIG_PATH = "channels.json"
KEYWORDS_CONFIG_PATH = "keywords.json"
MIN_VIEWS_FOR_DISPLAY = 25000  # only show videos with at least this many views


# ---------- CONFIG LOADERS ----------

def load_channels_config():
    """
    Load list of channels from channels.json.
    Expected format: list of dicts, e.g.
    [
      {"key": "hasan", "channel_id": "...", "label": "HasanAbi"},
      ...
    ]
    """
    if not os.path.exists(CHANNELS_CONFIG_PATH):
        return []

    try:
        with open(CHANNELS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except json.JSONDecodeError:
        pass

    return []


def load_keywords_config():
    """
    Load list of keyword sources from keywords.json.
    Expected format: list of dicts, e.g.
    [
      {
        "key": "neuralink",
        "label": "Neuralink",
        "queries": ["neuralink", "musk neuralink"]
      },
      ...
    ]
    """
    if not os.path.exists(KEYWORDS_CONFIG_PATH):
        return []

    try:
        with open(KEYWORDS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except json.JSONDecodeError:
        pass

    return []


# ---------- FILE I/O ----------

def load_previous_data():
    """
    Load the last saved snapshot from youtube_metrics.json.
    Returns a dict or None.
    """
    if not os.path.exists(DATA_FILE_PATH):
        return None

    try:
        with open(DATA_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except json.JSONDecodeError:
        return None

    return None


def save_current_data(current_snapshot):
    """
    Save the current snapshot to youtube_metrics.json.
    """
    with open(DATA_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(current_snapshot, f, indent=2)


# ---------- DELTAS & RANKING ----------

def compute_deltas_all(previous_snapshot, current_snapshot):
    """
    Compute raw deltas between previous and current snapshot.
    Returns:
    {
      "videos": {
        video_key: {
          "views_delta": int | "N/A",
          "likes_delta": ...,
          "comments_delta": ...,
          "subscribers_delta": ...,
        }
      }
    }
    """
    deltas = {"videos": {}}

    if previous_snapshot is None or "videos" not in previous_snapshot:
        for video_key in current_snapshot.get("videos", {}):
            deltas["videos"][video_key] = {
                "views_delta": "N/A",
                "likes_delta": "N/A",
                "comments_delta": "N/A",
                "subscribers_delta": "N/A",
            }
        return deltas

    prev_videos = previous_snapshot.get("videos", {})

    for video_key, curr_metrics in current_snapshot.get("videos", {}).items():
        if video_key in prev_videos:
            prev_metrics = prev_videos[video_key]
            deltas["videos"][video_key] = {
                "views_delta": curr_metrics["views"] - prev_metrics["views"],
                "likes_delta": curr_metrics["likes"] - prev_metrics["likes"],
                "comments_delta": curr_metrics["comments"] - prev_metrics["comments"],
                "subscribers_delta": (
                    curr_metrics.get("subscribers", 0) -
                    prev_metrics.get("subscribers", 0)
                ),
            }
        else:
            deltas["videos"][video_key] = {
                "views_delta": "N/A",
                "likes_delta": "N/A",
                "comments_delta": "N/A",
                "subscribers_delta": "N/A",
            }

    return deltas


def apply_deltas_to_snapshot(previous_snapshot, current_snapshot):
    """
    Injects delta metrics into current_snapshot["videos"][...]:
      - views_delta, likes_delta, comments_delta, subscribers_delta
      - views_delta_pct (percentage change vs previous views)

    Returns the mutated current_snapshot.
    """
    if current_snapshot is None or "videos" not in current_snapshot:
        return current_snapshot

    deltas = compute_deltas_all(previous_snapshot, current_snapshot)

    for video_key, delta_vals in deltas["videos"].items():
        cur = current_snapshot["videos"].get(video_key)
        if cur is None:
            continue

        # Copy raw deltas into snapshot
        for k, v in delta_vals.items():
            cur[k] = v

        # Compute % delta for views, if possible
        views_delta = delta_vals.get("views_delta")
        if isinstance(views_delta, int):
            # Approx previous views
            prev_views = cur["views"] - views_delta
            if prev_views > 0:
                pct = round((views_delta / prev_views) * 100.0, 2)
            else:
                pct = "N/A"
        else:
            pct = "N/A"

        cur["views_delta_pct"] = pct

    return current_snapshot


def get_top_videos_by_metric(snapshot, metric="views_delta_pct", top_n=16):
    """
    Sort videos in a snapshot by the given metric and return top N.

    metric options:
      - "views_delta_pct" (default)
      - "views_delta"
      - "views"

    Applies a global minimum view threshold (MIN_VIEWS_FOR_DISPLAY), so
    only videos with at least that many total views are considered.
    """
    rows = []
    videos = snapshot.get("videos", {})

    for video_key, metrics in videos.items():
        views = metrics.get("views", 0)

        # Enforce minimum-views filter
        if not isinstance(views, int) or views < MIN_VIEWS_FOR_DISPLAY:
            continue

        label = metrics.get("label", video_key)
        channel_name = metrics.get("channel_name", "")
        video_id = metrics.get("video_id", "")

        # Decide what we use as sort value
        if metric == "views":
            sort_value = views
            delta_display = sort_value
        else:
            sort_value = metrics.get(metric, "N/A")
            if isinstance(sort_value, str):
                # skip items without a real numeric delta (e.g. first snapshot)
                continue
            delta_display = sort_value

        rows.append({
            "video_key": video_key,
            "channel_name": channel_name,
            "video_id": video_id,
            "label": label,
            "current_value": views,
            "delta": delta_display,
        })

    # Sort by chosen metric descending
    rows.sort(key=lambda r: r["delta"], reverse=True)

    # Take top N
    return rows[:top_n]



# ---------- YOUTUBE API HELPERS ----------

def fetch_youtube_stats_for_videos(api_key, video_ids):
    """
    Call the YouTube Data API to get stats for a list of video IDs.
    Returns:
    {
      "video_id": {
        "title": "...",
        "channel_title": "...",
        "views": int,
        "likes": int,
        "comments": int,
      },
      ...
    }
    """
    if not api_key:
        raise RuntimeError("No API key found in config.py")

    stats_by_id = {}
    base_url = "https://www.googleapis.com/youtube/v3/videos"

    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        params = {
            "part": "snippet,statistics",
            "id": ",".join(batch),
            "key": api_key,
        }

        try:
            resp = requests.get(base_url, params=params, timeout=10)
            resp.raise_for_status()
        except HTTPError as e:
            print("\n====================== API ERROR ======================")
            print(f"Error fetching stats batch: {e}")
            try:
                print("YouTube response snippet:")
                print(resp.text[:500])
            except Exception:
                pass
            print("Returning partial results so far...")
            print("=======================================================\n")
            return stats_by_id

        data = resp.json()
        for item in data.get("items", []):
            vid = item["id"]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})

            stats_by_id[vid] = {
                "title": snippet.get("title", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)) if "likeCount" in stats else 0,
                "comments": int(stats.get("commentCount", 0)) if "commentCount" in stats else 0,
            }

    return stats_by_id


def fetch_latest_video_ids_for_channel_via_playlist(api_key, channel_id, max_results=5):
    """
    Get latest uploads for a channel via its 'uploads' playlist.
    Much cheaper than search.list in quota terms.
    """
    if not api_key:
        raise RuntimeError("No API key found in config.py")

    # 1) Get uploads playlist
    channels_url = "https://www.googleapis.com/youtube/v3/channels"
    chan_params = {
        "part": "contentDetails",
        "id": channel_id,
        "key": api_key,
    }
    resp = requests.get(channels_url, params=chan_params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    items = data.get("items", [])
    if not items:
        print(f"[WARN] No channel found for id {channel_id}")
        return []

    uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # 2) Fetch recent items from uploads playlist
    playlist_items_url = "https://www.googleapis.com/youtube/v3/playlistItems"
    pl_params = {
        "part": "contentDetails",
        "playlistId": uploads_playlist_id,
        "maxResults": max_results,
        "key": api_key,
    }
    resp = requests.get(playlist_items_url, params=pl_params, timeout=10)
    resp.raise_for_status()
    pl_data = resp.json()

    video_ids = []
    for item in pl_data.get("items", []):
        vid = item["contentDetails"]["videoId"]
        video_ids.append(vid)

    return video_ids


def fetch_video_ids_for_keyword(api_key, query, max_results=5):
    """
    Use YouTube search.list to discover recent videos for a keyword.
    This is quota-heavier, so use sparingly.
    """
    if not api_key:
        raise RuntimeError("No API key found in config.py")

    base_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "order": "date",
        "type": "video",
        "maxResults": max_results,
        "key": api_key,
    }

    try:
        resp = requests.get(base_url, params=params, timeout=10)
        resp.raise_for_status()
    except HTTPError as e:
        print("\n====================== API ERROR ======================")
        print(f"Error fetching videos for keyword '{query}': {e}")
        try:
            print("YouTube response snippet:")
            print(resp.text[:500])
        except Exception:
            pass
        print("Returning empty list for this keyword...")
        print("=======================================================\n")
        return []

    data = resp.json()
    video_ids = []
    for item in data.get("items", []):
        vid = item["id"].get("videoId")
        if vid:
            video_ids.append(vid)

    return video_ids


# ---------- SNAPSHOT BUILDERS ----------

def fetch_current_snapshot_from_youtube(tracked_videos):
    """
    For the fixed TRACKED_VIDEOS dict in your assignment.
    Builds a snapshot dict with current stats from YouTube.
    """
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is not set")

    video_ids = [meta["video_id"] for meta in tracked_videos.values()]
    stats_by_id = fetch_youtube_stats_for_videos(YOUTUBE_API_KEY, video_ids)

    snapshot = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "videos": {}
    }

    for video_key, meta in tracked_videos.items():
        vid = meta["video_id"]
        s = stats_by_id.get(vid)
        if s is None:
            continue

        label = meta.get("label", f"{s['channel_title']} – {s['title'][:50]}")

        snapshot["videos"][video_key] = {
            "channel_name": s["channel_title"] or meta["channel_name"],
            "video_id": vid,
            "views": s["views"],
            "likes": s["likes"],
            "comments": s["comments"],
            "subscribers": 0,
            "label": label,
        }

    return snapshot


def build_snapshot_from_channels_and_keywords(
    max_per_channel=5,
    max_per_keyword=3,
):
    """
    Build a snapshot using:
      - recent uploads from channels in channels.json
      - recent videos matching keyword queries in keywords.json
    """
    if not YOUTUBE_API_KEY:
        raise RuntimeError("No API key found in config.py")

    channels_cfg = load_channels_config()
    keywords_cfg = load_keywords_config()

    all_video_ids = set()
    video_meta_list = []

    # ---- Channels via playlist ----
    for ch in channels_cfg:
        ch_key = ch.get("key", "channel")
        ch_id = ch.get("channel_id")
        ch_label = ch.get("label", ch_key)

        if not ch_id:
            continue

        try:
            ids = fetch_latest_video_ids_for_channel_via_playlist(
                YOUTUBE_API_KEY, ch_id, max_results=max_per_channel
            )
        except Exception as e:
            print(f"Error fetching channel {ch_key}: {e}")
            continue

        for vid in ids:
            if vid not in all_video_ids:
                all_video_ids.add(vid)
                video_meta_list.append({
                    "video_id": vid,
                    "source_type": "channel",
                    "source_key": ch_key,
                    "source_label": ch_label,
                })

    # ---- Keywords via search.list ----
    for kw in keywords_cfg:
        kw_key = kw.get("key", "keyword")
        queries = kw.get("queries", [])
        kw_label = kw.get("label", kw_key)

        for q in queries:
            try:
                ids = fetch_video_ids_for_keyword(
                    YOUTUBE_API_KEY, q, max_results=max_per_keyword
                )
            except Exception as e:
                print(f"Error fetching keyword '{q}': {e}")
                continue

            for vid in ids:
                if vid not in all_video_ids:
                    all_video_ids.add(vid)
                    video_meta_list.append({
                        "video_id": vid,
                        "source_type": "keyword",
                        "source_key": kw_key,
                        "source_label": kw_label,
                    })

    # No videos? Return empty snapshot
    snapshot = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "videos": {}
    }

    if not all_video_ids:
        return snapshot

    # Fetch stats for all unique videos
    all_video_ids_list = list(all_video_ids)
    stats_by_id = fetch_youtube_stats_for_videos(
        YOUTUBE_API_KEY,
        all_video_ids_list,
    )

    for meta in video_meta_list:
        vid = meta["video_id"]
        stats = stats_by_id.get(vid)
        if not stats:
            continue

        source_key = meta["source_key"]
        video_key = f"{meta['source_type']}_{source_key}_{vid}"
        label = f"{meta['source_label']} – {stats['title'][:50]}"

        snapshot["videos"][video_key] = {
            "channel_name": stats["channel_title"],
            "video_id": vid,
            "views": stats["views"],
            "likes": stats["likes"],
            "comments": stats["comments"],
            "subscribers": 0,
            "label": label,
        }

    return snapshot
