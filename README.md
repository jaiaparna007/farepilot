# FarePilot Live

FarePilot Live is the result-producing version of the earlier prompt prototype. A user selects any 1–8 modules and receives a result dashboard rather than a generated prompt.

## What it returns

1. Sampled flexible-date comparison with the three lowest observed combinations
2. Live shopping fares sorted by displayed price
3. One- and two-stop value options
4. Current fare deals when the source exposes them
5. A transparent known/unknown extra-fee breakdown
6. A negotiation email based on the lowest returned fare
7. Itinerary-structure and fare-rule risk analysis
8. A risk-only hidden-city conclusion—never evasion instructions

## Built-in free data sources

- **swoop-flights 0.7.0:** no-key, open-source client for public Google Flights web data. It is unofficial and can change or rate-limit.
- **OurAirports:** public-domain worldwide airport reference data.
- **Frankfurter:** no-key exchange-rate reference data.
- **Open-Meteo:** no-key destination weather when the travel date is within its forecast horizon.
- **Direct cross-check links:** Google Flights, Skyscanner and KAYAK.
- **Optional SerpApi adapter:** only used when the deployer later adds `SERPAPI_KEY`; its free quota requires an individual account.

## Important limitation

There is no single free, keyless and officially licensed API that supplies every worldwide fare, baggage/seat fee, promotion and refund rule. The app therefore:

- never invents missing prices or policies;
- marks partial/unavailable data clearly;
- rate-limits searches to protect free public sources;
- asks the traveler to verify the final airline/OTA checkout total;
- treats the no-key fare engine as experimental rather than guaranteed infrastructure.

For a commercial or high-volume product, obtain a licensed supplier agreement instead of relying on the built-in no-key engine.

## Run with Docker

```bash
docker build -t farepilot-live .
docker run --rm -p 8080:8080 farepilot-live
```

Open `http://localhost:8080`.

## Run with Python

Python 3.10+ is required.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:8080`.

## Deploy on Render

1. Create a GitHub repository and upload this project.
2. In Render, create a new Blueprint and select the repository.
3. Render reads `render.yaml`, builds the Docker image and starts the service.
4. Open `/api/health` to confirm the no-key provider is available.

The hosting provider must allow outbound HTTPS requests. A static Netlify Drop deployment is not enough because live fare retrieval requires a backend.

## Optional free-tier fallback

If you create your own SerpApi account, add `SERPAPI_KEY` in the hosting dashboard. Do not paste or commit the key into the source code. The app automatically prefers the configured SerpApi adapter and otherwise uses the built-in no-key source.

## Safety and reliability controls

- Eight searches per IP per 15 minutes by default
- Twenty-minute in-memory cache
- Maximum five representative date-combination searches
- Strict IATA/date validation
- No booking or payment collection
- No hidden-city evasion guidance

Configure limits with `.env.example` values.

## Preview without the backend

Open `templates/index.html` directly to view a clearly labelled static preview. Preview fares are sample data only; live results require the Python server.
