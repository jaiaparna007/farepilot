from __future__ import annotations

import csv
import io
import math
import threading
from datetime import date, datetime
from typing import Any

import requests

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"

_FALLBACK_AIRPORTS = [
    {"iata": "DEL", "name": "Indira Gandhi International Airport", "municipality": "Delhi", "country": "IN", "latitude": 28.5665, "longitude": 77.1031},
    {"iata": "BOM", "name": "Chhatrapati Shivaji Maharaj International Airport", "municipality": "Mumbai", "country": "IN", "latitude": 19.0887, "longitude": 72.8679},
    {"iata": "BLR", "name": "Kempegowda International Airport", "municipality": "Bengaluru", "country": "IN", "latitude": 13.1986, "longitude": 77.7066},
    {"iata": "HYD", "name": "Rajiv Gandhi International Airport", "municipality": "Hyderabad", "country": "IN", "latitude": 17.2403, "longitude": 78.4294},
    {"iata": "MAA", "name": "Chennai International Airport", "municipality": "Chennai", "country": "IN", "latitude": 12.9900, "longitude": 80.1693},
    {"iata": "CCU", "name": "Netaji Subhash Chandra Bose International Airport", "municipality": "Kolkata", "country": "IN", "latitude": 22.6547, "longitude": 88.4467},
    {"iata": "DXB", "name": "Dubai International Airport", "municipality": "Dubai", "country": "AE", "latitude": 25.2528, "longitude": 55.3644},
    {"iata": "DOH", "name": "Hamad International Airport", "municipality": "Doha", "country": "QA", "latitude": 25.2731, "longitude": 51.6081},
    {"iata": "SIN", "name": "Singapore Changi Airport", "municipality": "Singapore", "country": "SG", "latitude": 1.3502, "longitude": 103.9940},
    {"iata": "BKK", "name": "Suvarnabhumi Airport", "municipality": "Bangkok", "country": "TH", "latitude": 13.6811, "longitude": 100.7473},
    {"iata": "LHR", "name": "Heathrow Airport", "municipality": "London", "country": "GB", "latitude": 51.4700, "longitude": -0.4543},
    {"iata": "CDG", "name": "Charles de Gaulle Airport", "municipality": "Paris", "country": "FR", "latitude": 49.0097, "longitude": 2.5479},
    {"iata": "JFK", "name": "John F. Kennedy International Airport", "municipality": "New York", "country": "US", "latitude": 40.6413, "longitude": -73.7781},
    {"iata": "SFO", "name": "San Francisco International Airport", "municipality": "San Francisco", "country": "US", "latitude": 37.6213, "longitude": -122.3790},
    {"iata": "SYD", "name": "Sydney Kingsford Smith Airport", "municipality": "Sydney", "country": "AU", "latitude": -33.9399, "longitude": 151.1753},
]

_lock = threading.Lock()
_airports: list[dict] | None = None


def _load_airports() -> list[dict]:
    global _airports
    if _airports is not None:
        return _airports
    with _lock:
        if _airports is not None:
            return _airports
        rows = list(_FALLBACK_AIRPORTS)
        try:
            response = requests.get(AIRPORTS_URL, timeout=20)
            response.raise_for_status()
            if len(response.content) > 15_000_000:
                raise ValueError("Airport dataset unexpectedly large")
            parsed = []
            for row in csv.DictReader(io.StringIO(response.text)):
                iata = (row.get("iata_code") or "").strip().upper()
                if len(iata) != 3 or row.get("type") not in {"large_airport", "medium_airport", "small_airport"}:
                    continue
                try:
                    lat = float(row["latitude_deg"])
                    lon = float(row["longitude_deg"])
                except (TypeError, ValueError, KeyError):
                    continue
                parsed.append({"iata": iata, "name": row.get("name") or iata, "municipality": row.get("municipality") or "", "country": row.get("iso_country") or "", "latitude": lat, "longitude": lon})
            if parsed:
                rows = parsed
        except Exception:
            pass
        _airports = rows
        return rows


def search_airports(term: str, limit: int = 12) -> list[dict]:
    q = term.strip().lower()
    if len(q) < 2:
        return []
    scored = []
    for airport in _load_airports():
        hay = f"{airport['iata']} {airport['name']} {airport['municipality']} {airport['country']}".lower()
        if q not in hay:
            continue
        score = 0 if airport["iata"].lower().startswith(q) else 1 if airport["municipality"].lower().startswith(q) else 2
        scored.append((score, airport))
    return [item for _, item in sorted(scored, key=lambda pair: (pair[0], pair[1]["iata"]))[:limit]]


def get_airport(iata: str) -> dict | None:
    code = iata.strip().upper()
    return next((row for row in _load_airports() if row["iata"] == code), None)


def haversine_km(a: dict | None, b: dict | None) -> float | None:
    if not a or not b:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, [a["latitude"], a["longitude"], b["latitude"], b["longitude"]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat/2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2) ** 2
    return round(6371 * 2 * math.asin(math.sqrt(value)))


def get_exchange_rate(base: str, quote: str) -> dict:
    base, quote = base.upper(), quote.upper()
    if base == quote:
        return {"base": base, "quote": quote, "rate": 1.0, "source": "Frankfurter", "asOf": date.today().isoformat()}
    try:
        response = requests.get(f"https://api.frankfurter.dev/v2/rate/{base}/{quote}", timeout=12)
        response.raise_for_status()
        data = response.json()
        return {"base": base, "quote": quote, "rate": data.get("rate"), "source": "Frankfurter", "asOf": data.get("date") or date.today().isoformat()}
    except Exception as exc:
        return {"base": base, "quote": quote, "rate": None, "source": "Frankfurter", "error": str(exc)}


def get_weather(airport: dict | None, travel_date: str) -> dict:
    if not airport:
        return {"available": False, "reason": "Destination coordinates unavailable"}
    try:
        target = datetime.fromisoformat(travel_date).date()
    except ValueError:
        return {"available": False, "reason": "Invalid travel date"}
    delta = (target - date.today()).days
    if delta < 0 or delta > 15:
        return {"available": False, "reason": "Open-Meteo forecast is available only within the next 16 days"}
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": airport["latitude"],
                "longitude": airport["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                "timezone": "auto",
                "forecast_days": 16,
            },
            timeout=12,
        )
        response.raise_for_status()
        data = response.json().get("daily") or {}
        dates = data.get("time") or []
        if travel_date not in dates:
            return {"available": False, "reason": "Date is outside the current forecast response"}
        idx = dates.index(travel_date)
        return {
            "available": True,
            "date": travel_date,
            "maxC": (data.get("temperature_2m_max") or [None])[idx],
            "minC": (data.get("temperature_2m_min") or [None])[idx],
            "rainChance": (data.get("precipitation_probability_max") or [None])[idx],
            "weatherCode": (data.get("weather_code") or [None])[idx],
            "source": "Open-Meteo",
        }
    except Exception as exc:
        return {"available": False, "reason": f"Weather source unavailable: {exc}"}
