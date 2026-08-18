from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime

from flask import Flask, jsonify, render_template, request

from analysis_engine import TOOL_LABELS, build_report
from open_data import search_airports
from providers import ProviderRouter

app = Flask(__name__)
router = ProviderRouter()

_CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "1200"))
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_rate_log: dict[str, deque] = defaultdict(deque)


def _validate(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Invalid JSON body")
    origin = str(payload.get("origin", "")).strip().upper()
    destination = str(payload.get("destination", "")).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", origin) or not re.fullmatch(r"[A-Z]{3}", destination):
        raise ValueError("Origin and destination must be 3-letter IATA codes")
    if origin == destination:
        raise ValueError("Origin and destination must be different")
    try:
        departure = datetime.fromisoformat(str(payload.get("departureDate", ""))).date()
    except ValueError as exc:
        raise ValueError("Departure date must use YYYY-MM-DD") from exc
    return_raw = str(payload.get("returnDate") or "").strip()
    return_date = None
    if return_raw:
        try:
            return_date = datetime.fromisoformat(return_raw).date()
        except ValueError as exc:
            raise ValueError("Return date must use YYYY-MM-DD") from exc
        if return_date < departure:
            raise ValueError("Return date cannot be before departure date")
    if departure < date.today():
        raise ValueError("Departure date cannot be in the past")
    travelers = max(1, min(int(payload.get("travelers", 1)), 9))
    cabin = str(payload.get("cabin", "economy")).strip().lower()
    if cabin not in {"economy", "premium economy", "business", "first"}:
        cabin = "economy"
    currency = str(payload.get("currency", "INR")).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        currency = "INR"
    tools = payload.get("tools") or ["flights"]
    tools = [str(item) for item in tools if str(item) in TOOL_LABELS]
    if not tools:
        tools = ["flights"]
    max_stops_raw = payload.get("maxStops")
    max_stops = None if max_stops_raw in (None, "", "any") else max(0, min(int(max_stops_raw), 2))
    return {
        "origin": origin,
        "destination": destination,
        "departureDate": departure.isoformat(),
        "returnDate": return_date.isoformat() if return_date else "",
        "travelers": travelers,
        "cabin": cabin,
        "currency": currency,
        "country": str(payload.get("country", "IN")).strip().upper()[:2] or "IN",
        "maxStops": max_stops,
        "flexDays": max(1, min(int(payload.get("flexDays", 2)), 7)),
        "bag": str(payload.get("bag", "cabin")),
        "seat": str(payload.get("seat", "standard")),
        "tools": tools,
    }


def _cache_key(query: dict) -> str:
    encoded = json.dumps(query, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _check_rate_limit() -> None:
    identity = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    now = time.time()
    window = _rate_log[identity]
    while window and now - window[0] > 900:
        window.popleft()
    if len(window) >= int(os.getenv("SEARCHES_PER_15_MIN", "8")):
        raise RuntimeError("Free-source safety limit reached. Please try again after 15 minutes.")
    window.append(now)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "activeProvider": router.active.name, "sources": router.status(), "time": datetime.utcnow().isoformat(timespec="seconds") + "Z"})


@app.get("/api/sources")
def sources():
    return jsonify({"sources": router.status()})


@app.get("/api/airports")
def airports():
    return jsonify({"results": search_airports(request.args.get("q", ""))})


@app.post("/api/search")
def search():
    try:
        _check_rate_limit()
        query = _validate(request.get_json(silent=True) or {})
        key = _cache_key(query)
        with _cache_lock:
            cached = _cache.get(key)
            if cached and time.time() - cached[0] < _CACHE_TTL:
                result = dict(cached[1])
                result["cached"] = True
                return jsonify(result)
        report = build_report(query, router)
        report["cached"] = False
        with _cache_lock:
            _cache[key] = (time.time(), report)
            if len(_cache) > 128:
                oldest = min(_cache, key=lambda item: _cache[item][0])
                _cache.pop(oldest, None)
        status = 200 if report.get("ok") else 503
        return jsonify(report), status
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 429
    except Exception as exc:
        app.logger.exception("Search failed")
        return jsonify({"ok": False, "error": f"Search failed safely: {exc}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=os.getenv("FLASK_DEBUG") == "1")
