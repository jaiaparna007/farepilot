# Free-source research and inclusion decisions

Reviewed 18 August 2026. Provider plans and terms can change; recheck before launch.

| Source | Free access | Key/account | Provides live fares? | Project decision |
|---|---:|---:|---:|---|
| swoop-flights | Yes, open source | No | Yes, via undocumented Google Flights RPCs | Built-in primary no-key engine; experimental and rate-limited |
| fast-flights | Yes, open source | No | Yes, via public Google Flights web data | Evaluated as a fallback; not enabled to avoid duplicate brittle dependencies |
| SerpApi Google Flights | 250 searches/month on researched free plan | Yes | Yes | Optional adapter; deployer must create their own account |
| Skyscanner official API | No per-request fee for approved partners | Partner approval | Yes | Not built in; intended for established businesses and requires approval |
| Travelpayouts/Aviasales | Affiliate access/free data tier | Token/account | Cached or live depending product/access | Not built in without the owner's affiliate account |
| Duffel | Test mode is free | Token/account | Test prices are not realistic | Excluded as a source of production “final” prices |
| Amadeus Self-Service | Portal reported decommissioned 17 July 2026 | Enterprise contact | Enterprise access | Excluded for a new self-service project |
| Aviationstack | 100 requests/month personal free plan | Key/account | No shopping fares; flight status/schedules | Not used for airfare results |
| AirLabs | Limited free package | Key/account | Status/schedules, not comprehensive shopping fares | Not used for airfare results |
| AeroDataBox | Free marketplace plan | Marketplace key/account | Status/schedules | Not used for airfare results |
| OpenSky | Anonymous credits exist | Optional account | No fares | Excluded: operational/live-product use requires written agreement |
| OurAirports | Public domain | No | No | Built in for worldwide airport names and coordinates |
| airportsapi.com | Free/no key | No | No | Evaluated as an airport-data fallback; OurAirports is primary |
| Frankfurter | Free/open source | No | No | Built in for reference FX conversion |
| Open-Meteo | Free no-key non-commercial allowance | No | No | Built in for destination weather within forecast horizon |
| Google Travel Impact Model | Public/free | Google Cloud key | No, emissions only | Not enabled because a key is still required |

## Why there is no “all free APIs” switch

Live airfare is licensed, dynamic inventory. A provider must negotiate airline, OTA or GDS access. Free tiers normally require an account and personal credential; publishing one shared credential inside a public app would be insecure and usually violate provider terms. Therefore this project integrates keyless sources that can legally and technically be included in code, supplies an optional personal-key adapter, and documents the remaining sources instead of pretending that missing coverage exists.

## Primary references

- Swoop: https://github.com/saraswatayu/swoop
- Swoop package: https://pypi.org/project/swoop-flights/
- Fast Flights: https://github.com/AWeirdDev/flights
- SerpApi Google Flights: https://serpapi.com/google-flights-api
- SerpApi pricing: https://serpapi.com/pricing
- Skyscanner partners: https://www.partners.skyscanner.net/product/travel-api
- Duffel test mode: https://duffel.com/docs/api/overview/test-mode/duffel-airways
- OpenSky terms: https://opensky-network.org/about/terms-of-use
- OurAirports data: https://ourairports.com/data/
- Frankfurter docs: https://frankfurter.dev/docs/
- Open-Meteo docs: https://open-meteo.com/en/docs
- Aviationstack pricing: https://aviationstack.com/pricing
