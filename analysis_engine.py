from __future__ import annotations

from datetime import datetime
from typing import Any

from open_data import get_airport, get_exchange_rate, get_weather, haversine_km
from providers import ProviderError, ProviderRouter, cross_check_links

TOOL_LABELS = {
    "dates": "Optimal Dates",
    "flights": "All Flights",
    "layovers": "Smart Layovers",
    "deals": "Deals",
    "fees": "Extra Fees",
    "email": "Negotiation Email",
    "risk": "Flexibility & Risk",
    "hiddenCity": "Hidden-city Risk",
}


def _money(value: Any, currency: str) -> str:
    if value is None:
        return "price unavailable"
    return f"{currency} {float(value):,.0f}"


def _duration(minutes: int | None) -> str:
    if not minutes:
        return "Unknown"
    return f"{minutes // 60}h {minutes % 60}m"


def _flight_summary(flight: dict) -> dict:
    return {
        "id": flight.get("id"),
        "price": flight.get("price"),
        "currency": flight.get("currency"),
        "priceText": _money(flight.get("price"), flight.get("currency", "")),
        "airlines": flight.get("airlines") or [],
        "stops": flight.get("stops", 0),
        "durationMinutes": flight.get("durationMinutes", 0),
        "durationText": _duration(flight.get("durationMinutes")),
        "legs": flight.get("legs") or [],
        "source": flight.get("source"),
        "priceNote": flight.get("priceNote"),
    }


def _fees_section(flights: list[dict], query: dict) -> dict:
    bag = query.get("bag", "cabin")
    seat = query.get("seat", "standard")
    rows = []
    for flight in flights[:3]:
        unknown = ["Checked-bag amount", "Paid seat amount", "Payment-method fee", "Change/cancellation charge"]
        rows.append(
            {
                "flight": " / ".join(flight.get("airlines") or ["Flight option"]),
                "displayedFare": flight.get("price"),
                "currency": flight.get("currency"),
                "requestedBag": bag,
                "requestedSeat": seat,
                "known": ["Displayed shopping total", "Required taxes shown by the shopping source"],
                "unknown": unknown,
                "recommendation": "Open the airline checkout and compare the final payable amount before entering payment details.",
            }
        )
    return {
        "status": "partial" if rows else "unavailable",
        "title": "Extra-fee breakdown",
        "rows": rows,
        "warning": "There is no free, worldwide, standard API for airline baggage and seat fees. Unknown amounts are deliberately not invented.",
    }


def _email_section(flights: list[dict], query: dict) -> dict:
    if not flights:
        return {"status": "unavailable", "title": "Price negotiation email", "reason": "No live fare was available to reference."}
    best = flights[0]
    airline = ", ".join(best.get("airlines") or ["Airline support"])
    fare = _money(best.get("price"), best.get("currency", query.get("currency", "INR")))
    subject = f"Request to review fare for {query['origin']}–{query['destination']}"
    body = (
        f"Subject: {subject}\n\n"
        f"Hello {airline} team,\n\n"
        f"I am planning travel from {query['origin']} to {query['destination']} on {query['departureDate']}"
        f" and found a current comparison fare of {fare}. Before booking, could you please confirm whether you can match this price or apply any eligible direct-booking, loyalty, student, card, or route promotion?\n\n"
        "I understand that availability and fare rules can change, and I can share the timestamped comparison and itinerary details if needed. I would prefer to book directly if the final all-in price and conditions are competitive.\n\n"
        "Thank you for reviewing my request.\n"
        "Kind regards,\n[Your name]"
    )
    return {"status": "ok", "title": "Price negotiation email", "subject": subject, "body": body, "basedOn": fare}


def _risk_section(flights: list[dict]) -> dict:
    rows = []
    for flight in flights[:5]:
        stops = int(flight.get("stops") or 0)
        score = 35 + stops * 15
        notes = []
        if stops == 0:
            notes.append("Nonstop itinerary reduces missed-connection exposure.")
        else:
            notes.append(f"{stops} stop(s): connection disruption risk is higher.")
        notes.append("Refundability and change fees are not exposed by the no-key shopping source; verify fare rules before payment.")
        rows.append({"flight": " / ".join(flight.get("airlines") or ["Option"]), "price": flight.get("price"), "currency": flight.get("currency"), "riskScore": min(score, 90), "riskLevel": "Low" if score < 45 else "Medium" if score < 70 else "High", "notes": notes})
    return {"status": "partial" if rows else "unavailable", "title": "Flexibility and financial risk", "rows": rows, "warning": "Risk score covers itinerary structure only; fare-rule risk remains unknown until the airline publishes the selected fare conditions."}


def _hidden_city_section(flights: list[dict], query: dict) -> dict:
    has_connections = any((f.get("stops") or 0) > 0 for f in flights)
    checked_bag = query.get("bag") == "checked"
    reasons = [
        "Airlines may prohibit throwaway or hidden-city ticketing in their contract of carriage.",
        "Skipping a segment can cancel every remaining segment on the same ticket.",
        "Checked baggage is normally tagged to the ticketed destination, not the intended stopover.",
        "Irregular operations can reroute the passenger and remove the intended stopover.",
        "Loyalty-account action, fare recovery, or future service restrictions are possible.",
    ]
    verdict = "Not suitable" if checked_bag or query.get("returnDate") else "High-risk and not recommended without written confirmation from the airline"
    return {
        "status": "ok",
        "title": "Hidden-city risk conclusion",
        "potentiallyApplicable": bool(has_connections and not checked_bag and not query.get("returnDate")),
        "verdict": verdict,
        "reasons": reasons,
        "note": "The system does not provide rule-evasion or booking instructions. It evaluates risk only.",
    }


def build_report(query: dict, router: ProviderRouter | None = None) -> dict:
    router = router or ProviderRouter()
    selected = query.get("tools") or list(TOOL_LABELS)
    selected = [item for item in selected if item in TOOL_LABELS]
    if not selected:
        selected = ["flights"]

    search_needed = bool(set(selected) & {"flights", "layovers", "fees", "email", "risk", "hiddenCity"})
    flights: list[dict] = []
    errors: list[str] = []
    if search_needed:
        try:
            flights = router.search(query)
            flights = sorted(flights, key=lambda item: (item.get("price") is None, item.get("price") or 10**12))
        except ProviderError as exc:
            errors.append(str(exc))

    sections: dict[str, dict] = {}
    if "dates" in selected:
        try:
            rows = router.scan_dates(query)
            sections["dates"] = {"status": "ok" if rows else "unavailable", "title": "Best date combinations", "rows": rows[:3], "testedCombinations": len(rows), "note": "To protect free public sources, the scan samples up to five representative combinations rather than every possible pair."}
        except ProviderError as exc:
            sections["dates"] = {"status": "unavailable", "title": "Best date combinations", "reason": str(exc)}
    if "flights" in selected:
        sections["flights"] = {"status": "ok" if flights else "unavailable", "title": "Live flight comparison", "rows": [_flight_summary(f) for f in flights[:12]], "count": len(flights), "warning": "Prices are volatile. Confirm the final airline/OTA checkout total before purchase."}
    if "layovers" in selected:
        candidates = [f for f in flights if 1 <= int(f.get("stops") or 0) <= 2]
        candidates.sort(key=lambda f: ((f.get("price") or 10**12), f.get("durationMinutes") or 10**9))
        sections["layovers"] = {"status": "ok" if candidates else "unavailable", "title": "Smart layover routes", "rows": [_flight_summary(f) for f in candidates[:6]], "note": "Transit visa, airport changes and minimum-connection rules must still be checked with official sources."}
    if "deals" in selected:
        deal_rows = router.deals(query)
        sections["deals"] = {"status": "ok" if deal_rows else "unavailable", "title": "Current fare deals", "rows": deal_rows, "warning": "These are route fares or price drops, not verified promo codes. No worldwide keyless promo-code database exists."}
    if "fees" in selected:
        sections["fees"] = _fees_section(flights, query)
    if "email" in selected:
        sections["email"] = _email_section(flights, query)
    if "risk" in selected:
        sections["risk"] = _risk_section(flights)
    if "hiddenCity" in selected:
        sections["hiddenCity"] = _hidden_city_section(flights, query)

    origin_airport = get_airport(query["origin"])
    destination_airport = get_airport(query["destination"])
    distance = haversine_km(origin_airport, destination_airport)
    weather = get_weather(destination_airport, query["departureDate"])
    fx = get_exchange_rate("USD", query.get("currency", "INR"))

    return {
        "ok": bool(flights or any(section.get("status") == "ok" for section in sections.values())),
        "query": query,
        "generatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "activeProvider": router.active.name,
        "bestFare": _flight_summary(flights[0]) if flights else None,
        "flightCount": len(flights),
        "sections": sections,
        "tripFacts": {"origin": origin_airport, "destination": destination_airport, "distanceKm": distance, "weather": weather, "usdRate": fx},
        "sources": router.status(),
        "crossCheckLinks": cross_check_links(query),
        "errors": errors,
        "limitations": [
            "No single free, keyless and licensed service provides every worldwide fare, fee, promotion and policy.",
            "The built-in no-key price engine uses public Google Flights web data through an independent open-source library and may change or rate-limit.",
            "Airline rules, baggage fees and refunds must be confirmed on the airline's official checkout or policy page.",
        ],
    }
