import json
import sqlite3
from pathlib import Path

import flask
import numpy as np
from flask import Flask

app = Flask(__name__)


# DB functions:


def get_picks(event_id):
    with sqlite3.connect("picks.db") as cur:
        res = cur.execute(
            "SELECT channel_id, pick_sample, MAX(created_time) FROM picks WHERE event_id = ? GROUP BY channel_id;",
            (event_id,),
        )
        return {row[0]: row[1] for row in res}


def do_save_picks(event_id, trace_start_time, picks, user_id):
    current_picks = get_picks(event_id)
    new_picks = {
        channel_id: pick_sample
        for channel_id, pick_sample in picks.items()
        if current_picks.get(channel_id) != pick_sample
    }
    rows = [
        (event_id, channel_id, trace_start_time, pick_sample, user_id)
        for channel_id, pick_sample in new_picks.items()
    ]
    with sqlite3.connect("picks.db") as cur:
        cur.executemany(
            "INSERT INTO picks (event_id, channel_id, trace_start_time, pick_sample, user_id) VALUES (?, ?, ?, ?, ?);",
            rows,
        )
        # Update # of user picks. Doesn't really work with deleted picks (they
        # still are stored as NULL picks).
        n_user_picks = len(picks)
        cur.execute(
            "UPDATE events SET n_user_picks = ? WHERE event_id = ?",
            (n_user_picks, event_id),
        )


def get_all_event_info():
    with sqlite3.connect("picks.db") as cur:
        res = cur.execute(
            "SELECT event_id, reference_pick_channel_id, trace_start_time, n_reference_picks, n_user_picks FROM events;"
        )
        return [
            dict(
                event_id=row[0],
                reference_pick_channel_id=row[1],
                trace_start_time=row[2],
                n_reference_picks=row[3],
                n_user_picks=row[4],
            )
            for row in res.fetchall()
        ]


def get_random_unpicked_event():
    with sqlite3.connect("picks.db") as cur:
        res = cur.execute(
            "SELECT event_id FROM events WHERE n_user_picks = 0 ORDER BY RANDOM() LIMIT 1;"
        )
        return res.fetchone()[0]


def get_random_picked_event():
    with sqlite3.connect("picks.db") as cur:
        res = cur.execute(
            "SELECT event_id FROM events WHERE n_user_picks <> 0 ORDER BY RANDOM() LIMIT 1;"
        )
        return res.fetchone()[0]


# Routes:


@app.route("/event/<event_id>")
def event(event_id):
    event_dir = Path("events") / event_id
    with open(event_dir / "metadata.json", "r") as f:
        metadata = json.load(f)
    metadata["picks"] = get_picks(event_id)
    return flask.render_template("index.html", client_config=metadata)


@app.route("/xy/<event_id>/<channel>")
def xy(event_id, channel):
    event_dir = Path("events") / event_id
    # Assume file has correct dtype!
    try:
        Y = np.load(event_dir / f"{channel}.npy")
    except Exception:
        Y = np.zeros(2, dtype="<f")
    X = np.linspace(0, len(Y) / 100, len(Y), dtype=Y.dtype)
    XY = np.concatenate((X, Y), axis=None)
    response = flask.make_response(XY.tobytes())
    response.headers.set("Content-Type", "application/octet-stream")
    return response


@app.route("/random_unpicked")
def random_unpicked_event():
    event_id = get_random_unpicked_event()
    return flask.redirect(f"/event/{event_id}")


@app.route("/random_picked")
def random_picked_event():
    event_id = get_random_picked_event()
    return flask.redirect(f"/event/{event_id}")


@app.route("/")
def index():
    event_info = get_all_event_info()
    sum_user_picks = sum(i["n_user_picks"] for i in event_info)
    sum_reference_picks = sum(i["n_reference_picks"] for i in event_info)
    n_events_total = len(event_info)
    n_events_picked = sum(i["n_user_picks"] > 0 for i in event_info)
    return flask.render_template(
        "home.html",
        event_info=event_info,
        sum_user_picks=sum_user_picks,
        sum_reference_picks=sum_reference_picks,
        n_events_total=n_events_total,
        n_events_picked=n_events_picked,
    )


@app.route("/save_picks/<event_id>", methods=["POST"])
def save_picks(event_id):
    event_dir = Path("events") / event_id
    with open(event_dir / "metadata.json", "r") as f:
        metadata = json.load(f)
    trace_start_time = metadata["trace_start_time"]
    req_dict = flask.request.json
    picks = req_dict["picks"]
    user_id = req_dict["user_id"]
    do_save_picks(event_id, trace_start_time, picks, user_id)
    return {}  # Need to return a non-None response.
