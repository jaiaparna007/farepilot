from __future__ import annotations

import importlib.util
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import requests


class ProviderError(RuntimeError):
    pass


def _attr(obj: Any, *names: str, default=None):
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _plain(value: Any):
    if is_dataclass(value):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return {k: _plain(v) for k, v in vars(value).items() if not k.startswith("_")}
    return str(value)


def _code(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(_attr(value, "iata", "iata_code", "code", "value", default=value))


def _number(value: Any):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _google_link(query: dict) -> str:
    phrase = f"Flights from {query['origin']} to {query['destination']} on {query['departureDate']}"
    if query.get("returnDate"):
        phrase += f" returning {query['returnDate']}"
    params = {"q": phrase, "curr": query.get("currency", "INR"), "hl": "en"}
    return "https://www.google.com/travel/flights?" + urlencode(params)


def cross_check_links(query: dict) -> list[dict]:
    dep = query["departureDate"].replace("-", "")[2:]
    ret = (query.get("returnDate") or "").replace("-", "")[2:]
    origin = query["origin"].lower()
    destination = query["destination"].lower()
    sky_path = f"https://www.skyscanner.com/transport/flights/{origin}/{destination}/{dep}/"
    if ret:
        sky_path += f"{ret}/"
    kayak = f"https://www.kayak.com/flights/{query['origin']}-{query['destination']}/{query['departureDate']}"
    if query.get("returnDate"):
        kayak += f"/{query['returnDate']}"
    kayak += "?sort=bestflight_a"
    return [
        {"name": "Google Flights", "url": _google_link(query)},
        {"name": "Skyscanner", "url": sky_path},
        {"name": "KAYAK", "url": kayak},
    ]


class SwoopProvider:
    name = "Swoop / Google Flights public web data"
    key_required = False
    official = False

    def available(self) -> bool:
        return importlib.util.find_spec("swoop") is not None

    def search(self, query: dict) -> list[dict]:
        if not self.available():
            raise ProviderError(
                "swoop-flights is not installed. Deploy with requirements.txt or run pip install -r requirements.txt."
            )
        try:
            from swoop import SORT_CHEAPEST, search

            result = search(
                query["origin"],
                query["destination"],
                query["departureDate"],
                return_date=query.get("returnDate") or None,
                cabin=query.get("cabin", "economy").lower().replace(" ", "-"),
                adults=int(query.get("travelers", 1)),
                max_stops=query.get("maxStops"),
                sort=SORT_CHEAPEST,
                country=query.get("country", "IN"),
                timeout=45,
                retries=1,
            )
        except Exception as exc:
            raise ProviderError(f"No-key flight engine failed: {exc}") from exc

        currency = _attr(result, "currency", default=query.get("currency", "INR"))
        normalized = []
        for rank, option in enumerate((_attr(result, "results", default=[]) or [])[:25], start=1):
            legs_out = []
            airlines: list[str] = []
            total_stops = 0
            total_minutes = 0
            emissions = None
            for leg in _attr(option, "legs", default=[]) or []:
                itinerary = _attr(leg, "itinerary")
                if itinerary is None:
                    continue
                names = list(_attr(itinerary, "airline_names", default=[]) or [])
                airlines.extend(str(name) for name in names if name)
                stops = int(_attr(itinerary, "stop_count", default=0) or 0)
                minutes = int(_attr(itinerary, "travel_time", default=0) or 0)
                total_stops = max(total_stops, stops)
                total_minutes += minutes
                emissions = emissions or _attr(itinerary, "carbon_emissions")
                segments = []
                for flight in _attr(itinerary, "flights", default=[]) or []:
                    segments.append(
                        {
                            "flightNumber": str(_attr(flight, "flight_number", "number", default="")),
                            "airline": str(_attr(flight, "airline_name", "airline", default="")),
                            "origin": _code(_attr(flight, "departure_airport", "origin")),
                            "destination": _code(_attr(flight, "arrival_airport", "destination")),
                            "departure": str(_attr(flight, "departure_time", "departure_datetime", default="")),
                            "arrival": str(_attr(flight, "arrival_time", "arrival_datetime", default="")),
                            "aircraft": str(_attr(flight, "aircraft", default="")),
                        }
                    )
                legs_out.append(
                    {
                        "origin": str(_attr(leg, "origin", default=query["origin"])),
                        "destination": str(_attr(leg, "destination", default=query["destination"])),
                        "date": str(_attr(leg, "date", default="")),
                        "stops": stops,
                        "durationMinutes": minutes,
                        "segments": segments,
                    }
                )
            price = _number(_attr(option, "price"))
            option_currency = _attr(option, "currency", default=currency)
            normalized.append(
                {
                    "id": f"swoop-{rank}",
                    "rank": rank,
                    "price": price,
                    "currency": str(option_currency or currency or query.get("currency", "INR")),
                    "airlines": list(dict.fromkeys(airlines)) or ["Airline shown at checkout"],
                    "stops": total_stops,
                    "durationMinutes": total_minutes,
                    "carbonEmissions": _plain(emissions),
                    "legs": legs_out,
                    "selector": str(_attr(option, "selector", default="")),
                    "source": self.name,
                    "sourceType": "unofficial-no-key",
                    "priceNote": "Shopping total shown by the source; optional bags, seats and payment fees may be extra.",
                }
            )
        return sorted(normalized, key=lambda item: (item["price"] is None, item["price"] or 10**12))

    def scan_dates(self, query: dict) -> list[dict]:
        flex = max(1, min(int(query.get("flexDays", 2)), 7))
        departure = datetime.fromisoformat(query["departureDate"]).date()
        return_date = datetime.fromisoformat(query["returnDate"]).date() if query.get("returnDate") else None
        offsets = list(dict.fromkeys([0, -flex, flex, -(flex // 2 or 1), flex // 2 or 1]))
        rows = []
        for offset in offsets[:5]:
            q = dict(query)
            q["departureDate"] = (departure + timedelta(days=offset)).isoformat()
            if return_date:
                q["returnDate"] = (return_date + timedelta(days=offset)).isoformat()
            try:
                options = self.search(q)
            except ProviderError as exc:
                rows.append({"departureDate": q["departureDate"], "returnDate": q.get("returnDate"), "error": str(exc)})
                continue
            if options:
                best = options[0]
                rows.append(
                    {
                        "departureDate": q["departureDate"],
                        "returnDate": q.get("returnDate"),
                        "price": best["price"],
                        "currency": best["currency"],
                        "airlines": best["airlines"],
                        "stops": best["stops"],
                        "durationMinutes": best["durationMinutes"],
                        "source": best["source"],
                    }
                )
        return sorted(rows, key=lambda item: (item.get("price") is None, item.get("price") or 10**12))

    def deals(self, query: dict) -> list[dict]:
        if not self.available():
            return []
        try:
            from swoop import deals

            result = deals(query["origin"])
            out = []
            for item in (_attr(result, "deals", default=[]) or [])[:8]:
                out.append(
                    {
                        "destination": str(_attr(item, "destination_city", "destination", default="")),
                        "price": _number(_attr(item, "price")),
                        "currency": str(_attr(item, "currency", default=query.get("currency", "INR"))),
                        "discountPct": _number(_attr(item, "discount_pct", default=None)),
                        "source": self.name,
                        "verifiedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                        "note": "Fare deal, not a promo code. Recheck before booking.",
                    }
                )
            return out
        except Exception:
            return []


class SerpApiProvider:
    name = "SerpApi Google Flights"
    key_required = True
    official = False

    def available(self) -> bool:
        return bool(os.getenv("SERPAPI_KEY"))

    def search(self, query: dict) -> list[dict]:
        key = os.getenv("SERPAPI_KEY")
        if not key:
            raise ProviderError("SERPAPI_KEY is not configured")
        params = {
            "engine": "google_flights",
            "api_key": key,
            "departure_id": query["origin"],
            "arrival_id": query["destination"],
            "outbound_date": query["departureDate"],
            "currency": query.get("currency", "INR"),
            "hl": "en",
            "adults": int(query.get("travelers", 1)),
            "travel_class": {"economy": 1, "premium economy": 2, "business": 3, "first": 4}.get(query.get("cabin", "economy").lower(), 1),
        }
        if query.get("returnDate"):
            params["return_date"] = query["returnDate"]
            params["type"] = 1
        else:
            params["type"] = 2
        response = requests.get("https://serpapi.com/search.json", params=params, timeout=55)
        response.raise_for_status()
        payload = response.json()
        rows = (payload.get("best_flights") or []) + (payload.get("other_flights") or [])
        out = []
        for rank, row in enumerate(rows[:25], start=1):
            flights = row.get("flights") or []
            airlines = list(dict.fromkeys(f.get("airline") for f in flights if f.get("airline")))
            segments = [
                {
                    "flightNumber": f.get("flight_number", ""),
                    "airline": f.get("airline", ""),
                    "origin": (f.get("departure_airport") or {}).get("id", ""),
                    "destination": (f.get("arrival_airport") or {}).get("id", ""),
                    "departure": (f.get("departure_airport") or {}).get("time", ""),
                    "arrival": (f.get("arrival_airport") or {}).get("time", ""),
                    "aircraft": f.get("airplane", ""),
                }
                for f in flights
            ]
            out.append(
                {
                    "id": f"serpapi-{rank}",
                    "rank": rank,
                    "price": _number(row.get("price")),
                    "currency": query.get("currency", "INR"),
                    "airlines": airlines or ["Airline shown at checkout"],
                    "stops": max(0, len(flights) - 1),
                    "durationMinutes": int(row.get("total_duration") or 0),
                    "carbonEmissions": row.get("carbon_emissions"),
                    "legs": [{"origin": query["origin"], "destination": query["destination"], "date": query["departureDate"], "stops": max(0, len(flights)-1), "durationMinutes": int(row.get("total_duration") or 0), "segments": segments}],
                    "source": self.name,
                    "sourceType": "free-tier-key",
                    "priceNote": "Google Flights shopping result via SerpApi; optional fees may be extra.",
                }
            )
        return sorted(out, key=lambda item: (item["price"] is None, item["price"] or 10**12))


class ProviderRouter:
    def __init__(self):
        self.swoop = SwoopProvider()
        self.serpapi = SerpApiProvider()

    @property
    def active(self):
        return self.serpapi if self.serpapi.available() else self.swoop

    def search(self, query: dict) -> list[dict]:
        return self.active.search(query)

    def scan_dates(self, query: dict) -> list[dict]:
        if self.active is self.swoop:
            return self.swoop.scan_dates(query)
        # Keep the free-tier request count controlled: five calls maximum.
        return self.swoop.scan_dates(query) if self.swoop.available() else []

    def deals(self, query: dict) -> list[dict]:
        return self.swoop.deals(query)

    def status(self) -> list[dict]:
        return [
            {"id": "swoop", "name": self.swoop.name, "configured": self.swoop.available(), "keyRequired": False, "role": "Live shopping prices", "warning": "Unofficial public-web integration; may change or rate-limit."},
            {"id": "serpapi", "name": self.serpapi.name, "configured": self.serpapi.available(), "keyRequired": True, "role": "Optional live-price fallback", "warning": "Free quota requires a personal account key."},
            {"id": "ourairports", "name": "OurAirports", "configured": True, "keyRequired": False, "role": "Global airport reference data", "warning": "Community-maintained public-domain data."},
            {"id": "frankfurter", "name": "Frankfurter", "configured": True, "keyRequired": False, "role": "Currency conversion", "warning": "Reference rates, not card settlement rates."},
            {"id": "openmeteo", "name": "Open-Meteo", "configured": True, "keyRequired": False, "role": "Destination weather", "warning": "Forecast availability is limited to the provider horizon."},
        ]
