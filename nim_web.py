# nim_web.py
import os
import json
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify, abort

from nim_core import (
    load_previous_data,
    save_current_data,
    build_snapshot_from_channels_and_keywords,
    apply_deltas_to_snapshot,
    get_top_videos_by_metric,
)

app = Flask(__name__)

LAST_RUN_FILE = "last_option5_run.json"
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN", "")


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


@app.route("/")
def index():
    """
    Main dashboard view.
    Query param: mode = pct | delta | views
    """
    snapshot = load_previous_data()
    mode = request.args.get("mode", "pct")

    if snapshot is None or not snapshot.get("videos"):
        top_list = []
        last_updated = None
    else:
        if mode == "views":
            metric = "views"
        elif mode == "delta":
            metric = "views_delta"
        else:
            metric = "views_delta_pct"

        top_list = get_top_videos_by_metric(snapshot, metric=metric, top_n=16)
        last_updated = snapshot.get("timestamp")

    return render_template(
        "dashboard.html",
        top_list=top_list,
        mode=mode,
        last_updated=last_updated,
    )


@app.route("/refresh/<token>", methods=["POST", "GET"])
def refresh_snapshot(token):
    """
    Server-side snapshot builder, used by:
      - You (manual hit)
      - Render Cron Job (daily curl)
    """
    if not REFRESH_TOKEN:
        abort(500, description="REFRESH_TOKEN not configured on server.")

    if token != REFRESH_TOKEN:
        abort(403, description="Invalid refresh token.")

    # 24h guard
    last_run = get_last_option5_run()
    if last_run is not None:
        elapsed = datetime.now() - last_run
        if elapsed < timedelta(hours=24):
            return jsonify({
                "status": "skipped_recent",
                "message": "Already refreshed within last 24 hours.",
                "last_run": last_run.isoformat(timespec="seconds"),
            })

    # Build snapshot
    prev = load_previous_data()
    current = build_snapshot_from_channels_and_keywords(
        max_per_channel=5,
        max_per_keyword=3,
    )

    if not current.get("videos"):
        return jsonify({
            "status": "error_no_videos",
            "message": "No videos fetched (likely quota or config issue)."
        })

    current = apply_deltas_to_snapshot(prev, current)
    save_current_data(current)
    set_last_option5_run()

    return jsonify({
        "status": "ok",
        "timestamp": current.get("timestamp"),
        "video_count": len(current["videos"]),
    })


if __name__ == "__main__":
    app.run(debug=True)
