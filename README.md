# CardVault AI v4.0
Sports card scanning, AI identification, and valuation platform.
## Architecture

| Module | Purpose |
|--------|---------|
| `app.py` | Flask web app — 20 endpoints, streetwear v2 UI |
| `database_v2.py` | SQLite with booklet/page/slot tracking (source of truth) |
| `card_detector.py` | OpenCV binder page → individual card extraction |
| `card_identifier_v2.py` | Claude Vision API card identification |
| `card_value_engine.py` | v3.0 value estimation with capped multipliers |
| `ebay_integration.py` | eBay OAuth + Finding/Browse API pricing |

## Quick Start (Local)
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000
## Docker
```bash
docker compose up --build
```

## Environment Variables
Copy `.env.example` to `.env` and fill in your keys. All are optional — the app runs in mock/demo mode without them.
## API Endpoints
**Pages:** `/`, `/collection`, `/card/<id>`, `/booklets`, `/booklet/<id>`, `/settings`
**Detection & ID:** `POST /api/detect`, `POST /api/identify`, `POST /api/identify-batch`, `POST /api/save-batch`
**CRUD:** `POST /api/card`, `GET /api/card/<id>`, `DELETE /api/card/<id>`, `POST /api/card/<id>/revalue`
**Data:** `/api/collection`, `/api/booklets`, `/api/stats`, `/api/search`, `/api/export`
**Ops:** `/health`
## Migration

If you have an existing `card_collection.db` from a previous version, just copy it into the project folder. The app runs a safe `ALTER TABLE` migration on startup — adds new columns, never modifies or deletes existing data.
--------------------------------------------------------
HutchGroup LLC © 2026
