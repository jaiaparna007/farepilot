from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import analysis_engine


class MockRouter:
    class Active:
        name = "Mock live source"
    active = Active()

    def search(self, query):
        return [
            {"id":"a","price":25000,"currency":"INR","airlines":["Alpha Air"],"stops":0,"durationMinutes":210,"legs":[],"source":"Mock","priceNote":"Test"},
            {"id":"b","price":23000,"currency":"INR","airlines":["Beta Air"],"stops":1,"durationMinutes":330,"legs":[],"source":"Mock","priceNote":"Test"},
            {"id":"c","price":28000,"currency":"INR","airlines":["Gamma Air"],"stops":2,"durationMinutes":440,"legs":[],"source":"Mock","priceNote":"Test"},
        ]

    def scan_dates(self, query):
        return [
            {"departureDate":query["departureDate"],"returnDate":query["returnDate"],"price":23000,"currency":"INR","airlines":["Beta Air"],"stops":1},
            {"departureDate":"2026-09-18","returnDate":"2026-09-25","price":24000,"currency":"INR","airlines":["Alpha Air"],"stops":0},
        ]

    def deals(self, query):
        return [{"destination":"Bangkok","price":18000,"currency":"INR","discountPct":20,"verifiedAt":"2026-08-18T10:00:00Z"}]

    def status(self):
        return [{"name":"Mock","configured":True,"role":"Tests","warning":"None"}]


def run():
    analysis_engine.get_airport = lambda code: {"iata":code,"latitude":20.0,"longitude":70.0}
    analysis_engine.haversine_km = lambda a,b: 2200
    analysis_engine.get_weather = lambda airport, day: {"available":False,"reason":"Test"}
    analysis_engine.get_exchange_rate = lambda base,quote: {"rate":83.0,"base":base,"quote":quote}
    analysis_engine.cross_check_links = lambda query: [{"name":"Check","url":"https://example.com"}]

    query = {"origin":"DEL","destination":"DXB","departureDate":"2026-09-17","returnDate":"2026-09-24","travelers":1,"cabin":"economy","currency":"INR","country":"IN","maxStops":2,"flexDays":2,"bag":"cabin","seat":"standard","tools":["dates","flights","layovers","deals","fees","email","risk","hiddenCity"]}
    report = analysis_engine.build_report(query, MockRouter())

    assert report["ok"] is True
    assert report["activeProvider"] == "Mock live source"
    assert report["sections"]["flights"]["count"] == 3
    assert report["sections"]["flights"]["rows"][0]["price"] == 23000
    assert len(report["sections"]["dates"]["rows"]) == 2
    assert report["sections"]["layovers"]["rows"][0]["stops"] == 1
    assert "Subject:" in report["sections"]["email"]["body"]
    assert report["sections"]["hiddenCity"]["status"] == "ok"
    assert report["tripFacts"]["distanceKm"] == 2200
    print("analysis-tests: ok")


if __name__ == "__main__":
    run()
