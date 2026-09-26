"""
Shared ATC backend. Run this ONCE, somewhere all your controllers can
reach (your own PC on a LAN, a small VPS, etc.) - every client points at
its address in client/config.py.

Handles:
  - user accounts (register/login)
  - a shared flight plan board (create/edit/delete, arrivals/departures,
    runway/gate/heading assignment, remarks, status)

Run with: python app.py
Listens on 0.0.0.0:5050 by default - change PORT below if needed.
"""

import hashlib
import os
import re
import sqlite3
import threading
import time

from flask import Flask, request, jsonify
import requests as http_requests

import discord_config as dcfg

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atc.db")
PORT = 5050

app = Flask(__name__)

_active_controllers = {}
_active_controllers_lock = threading.Lock()
CONTROLLER_STALE_SECONDS = 30


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flightplans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            callsign TEXT NOT NULL,
            aircraft_type TEXT,
            departure TEXT,
            arrival TEXT,
            route TEXT,
            altitude TEXT,
            squawk TEXT,
            runway TEXT,
            gate TEXT,
            heading TEXT,
            status TEXT NOT NULL DEFAULT 'Filed',
            remarks TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            callsign TEXT PRIMARY KEY,
            aircraft_type TEXT,
            x REAL,
            y REAL,
            confidence REAL,
            updated_at REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# ---------- Auth: Discord OAuth + role check ----------
#
# Flow: client opens a Discord OAuth login page in the browser, catches the
# redirect locally, and sends us the resulting "code". We exchange that code
# for the user's Discord identity, then use our BOT token to check whether
# they hold the required role in your Discord server. Only then do we let
# them in - no separate password system needed.

@app.route("/discord/callback", methods=["POST"])
def discord_callback():
    data = request.get_json(force=True)
    code = data.get("code")
    if not code:
        return jsonify({"error": "missing code"}), 400

    token_resp = http_requests.post(
        "https://discord.com/api/oauth2/token",
        data={
            "client_id": dcfg.DISCORD_CLIENT_ID,
            "client_secret": dcfg.DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": dcfg.DISCORD_REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    if token_resp.status_code != 200:
        return jsonify({"error": f"Discord token exchange failed: {token_resp.text}"}), 401
    access_token = token_resp.json().get("access_token")

    user_resp = http_requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if user_resp.status_code != 200:
        return jsonify({"error": "Could not fetch your Discord identity"}), 401
    user = user_resp.json()
    discord_user_id = user["id"]
    username = user.get("username", "unknown")

    member_resp = http_requests.get(
        f"https://discord.com/api/guilds/{dcfg.DISCORD_GUILD_ID}/members/{discord_user_id}",
        headers={"Authorization": f"Bot {dcfg.DISCORD_BOT_TOKEN}"},
        timeout=10,
    )
    if member_resp.status_code != 200:
        return jsonify({"error": "You are not a member of the required Discord server"}), 403

    roles = member_resp.json().get("roles", [])
    if dcfg.DISCORD_REQUIRED_ROLE_ID not in roles:
        return jsonify({"error": "You don't have the ATC role in the Discord server"}), 403

    return jsonify({"ok": True, "username": username})


# ---------- Flight plans ----------

def row_to_dict(row):
    return dict(row)


@app.route("/flightplans", methods=["GET"])
def list_flightplans():
    conn = get_db()
    rows = conn.execute("SELECT * FROM flightplans ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/flightplans", methods=["POST"])
def create_flightplan():
    data = request.get_json(force=True)
    now = time.time()
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO flightplans
           (callsign, aircraft_type, departure, arrival, route, altitude,
            squawk, runway, gate, heading, status, remarks, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("callsign", ""), data.get("aircraft_type", ""),
            data.get("departure", ""), data.get("arrival", ""),
            data.get("route", ""), data.get("altitude", ""),
            data.get("squawk", ""), data.get("runway", ""),
            data.get("gate", ""), data.get("heading", ""),
            data.get("status", "Filed"), data.get("remarks", ""),
            now, now,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"ok": True, "id": new_id})


@app.route("/flightplans/<int:plan_id>", methods=["PUT"])
def update_flightplan(plan_id):
    data = request.get_json(force=True)
    fields = ["callsign", "aircraft_type", "departure", "arrival", "route",
              "altitude", "squawk", "runway", "gate", "heading", "status", "remarks"]
    updates = {k: data[k] for k in fields if k in data}
    if not updates:
        return jsonify({"error": "no fields to update"}), 400

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [time.time(), plan_id]

    conn = get_db()
    conn.execute(
        f"UPDATE flightplans SET {set_clause}, updated_at = ? WHERE id = ?",
        values,
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/flightplans/<int:plan_id>", methods=["DELETE"])
def delete_flightplan(plan_id):
    conn = get_db()
    conn.execute("DELETE FROM flightplans WHERE id = ?", (plan_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------- Live positions (fed by the position tracker app) ----------

POSITION_STALE_SECONDS = 30  # positions older than this are hidden from GET


@app.route("/positions", methods=["POST"])
def post_position():
    data = request.get_json(force=True)
    callsign = (data.get("callsign") or "").strip().upper()
    if not callsign:
        return jsonify({"error": "callsign required"}), 400

    conn = get_db()
    conn.execute(
        """INSERT INTO positions (callsign, aircraft_type, x, y, confidence, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(callsign) DO UPDATE SET
               aircraft_type = excluded.aircraft_type,
               x = excluded.x,
               y = excluded.y,
               confidence = excluded.confidence,
               updated_at = excluded.updated_at""",
        (
            callsign, data.get("aircraft_type", ""),
            data.get("x", 0), data.get("y", 0),
            data.get("confidence", 0), time.time(),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/positions", methods=["GET"])
def list_positions():
    cutoff = time.time() - POSITION_STALE_SECONDS
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM positions WHERE updated_at >= ? ORDER BY callsign", (cutoff,)
    ).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])


# ---------- ATC station directory ----------

@app.route("/controllers", methods=["GET"])
def list_controllers():
    cutoff = time.time() - CONTROLLER_STALE_SECONDS
    with _active_controllers_lock:
        stale = [name for name, station in _active_controllers.items()
                 if station["updated_at"] < cutoff]
        for name in stale:
            del _active_controllers[name]
        stations = [dict(station) for station in _active_controllers.values()]
    stations.sort(key=lambda station: (station["island"], station["position"]))
    return jsonify(stations)


@app.route("/controllers", methods=["POST"])
def publish_controller():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    island = (data.get("island") or "").strip()
    position = (data.get("position") or "").strip()
    frequency = (data.get("frequency") or "").strip()
    if not username or not island or not position:
        return jsonify({"error": "username, island, and position are required"}), 400
    if not re.fullmatch(r"\d{3}\.\d{3}", frequency):
        return jsonify({"error": "frequency must use the format 123.450"}), 400

    station = {
        "username": username,
        "island": island,
        "position": position,
        "frequency": frequency,
        "updated_at": time.time(),
    }
    with _active_controllers_lock:
        _active_controllers[username] = station
    return jsonify({"ok": True})


@app.route("/controllers/<path:username>", methods=["DELETE"])
def release_controller(username):
    with _active_controllers_lock:
        _active_controllers.pop(username, None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    from radio_relay import start_radio_server

    init_db()
    start_radio_server(host="0.0.0.0", port=5051)
    print(f"ATC server running on http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT)
