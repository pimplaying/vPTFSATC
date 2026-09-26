"""
Thin wrapper around the ATC server's REST API. Every method returns
(success: bool, data_or_error).
"""

import requests
from urllib.parse import quote

import config


def _url(path: str) -> str:
    return f"{config.SERVER_URL.rstrip('/')}{path}"


def register(username: str, password: str):
    try:
        resp = requests.post(_url("/register"), json={
            "username": username, "password": password,
        }, timeout=6)
    except requests.RequestException as e:
        return False, f"Could not reach server: {e}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, resp.json().get("error", f"HTTP {resp.status_code}")


def login(username: str, password: str):
    try:
        resp = requests.post(_url("/login"), json={
            "username": username, "password": password,
        }, timeout=6)
    except requests.RequestException as e:
        return False, f"Could not reach server: {e}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, resp.json().get("error", f"HTTP {resp.status_code}")


def discord_login(code: str):
    try:
        resp = requests.post(_url("/discord/callback"), json={"code": code}, timeout=15)
    except requests.RequestException as e:
        return False, f"Could not reach server: {e}"

    try:
        payload = resp.json()
    except ValueError:
        return False, f"HTTP {resp.status_code}"

    if resp.status_code == 200:
        return True, payload
    return False, payload.get("error", f"HTTP {resp.status_code}")


def list_flightplans():
    try:
        resp = requests.get(_url("/flightplans"), timeout=6)
    except requests.RequestException as e:
        return False, f"Could not reach server: {e}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, f"HTTP {resp.status_code}"


def list_positions():
    try:
        resp = requests.get(_url("/positions"), timeout=6)
    except requests.RequestException as e:
        return False, f"Could not reach server: {e}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, f"HTTP {resp.status_code}"


def list_controllers():
    try:
        resp = requests.get(_url("/controllers"), timeout=6)
    except requests.RequestException as e:
        return False, f"Could not reach server: {e}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, f"HTTP {resp.status_code}"


def publish_controller(station: dict):
    try:
        resp = requests.post(_url("/controllers"), json=station, timeout=6)
    except requests.RequestException as e:
        return False, f"Could not reach server: {e}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, resp.json().get("error", f"HTTP {resp.status_code}")


def release_controller(username: str):
    try:
        resp = requests.delete(
            _url(f"/controllers/{quote(username, safe='')}"), timeout=6
        )
    except requests.RequestException as e:
        return False, f"Could not reach server: {e}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, f"HTTP {resp.status_code}"


def create_flightplan(plan: dict):
    try:
        resp = requests.post(_url("/flightplans"), json=plan, timeout=6)
    except requests.RequestException as e:
        return False, f"Could not reach server: {e}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, f"HTTP {resp.status_code}"


def update_flightplan(plan_id: int, plan: dict):
    try:
        resp = requests.put(_url(f"/flightplans/{plan_id}"), json=plan, timeout=6)
    except requests.RequestException as e:
        return False, f"Could not reach server: {e}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, f"HTTP {resp.status_code}"


def delete_flightplan(plan_id: int):
    try:
        resp = requests.delete(_url(f"/flightplans/{plan_id}"), timeout=6)
    except requests.RequestException as e:
        return False, f"Could not reach server: {e}"

    if resp.status_code == 200:
        return True, resp.json()
    return False, f"HTTP {resp.status_code}"
