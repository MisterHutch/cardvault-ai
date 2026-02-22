# CardVault AI 🃏

**AI-powered sports card scanning, identification, and valuation.**

Built by [HutchGroup LLC](https://hutchgroupllc.com) — Streetwear v2 design aesthetic.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Flask](https://img.shields.io/badge/Flask-3.1-green)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)
![eBay API](https://img.shields.io/badge/eBay_API-Integrated-orange)

---

## What It Does

- **Scan** binder pages or single cards via photo upload
- **Identify** player, year, set, parallel, and special attributes
- **Value** cards using multi-source weighted pricing (eBay sold, 130point, PSA, Beckett)
- **Track** your collection with confidence scoring and market trend analysis
- **Export** collection data as CSV

## Architecture

```
Camera Input → OpenCV Detection → Claude Vision ID → Multi-Source Pricing → SQLite
                                                           ↓
                                              Flask API → Streetwear v2 UI
```

### Components

| File | Lines | Purpose |
|------|-------|---------|
| `app.py` | Flask web app — 13 routes, streetwear v2 UI |
| `card_value_engine.py` | Value estimation engine v3.0 — refactored |
| `ebay_integration.py` | eBay OAuth + sold listings fetcher |

### Key Design Decisions

- **Capped compound multipliers** — Prevents unrealistic value inflation when RC + Auto + Serial + Parallel stack
- **Explicit sport field** — No more guessing sport from set name (Prizm is used across sports)
- **Deterministic mock data** — Uses `hashlib` not `hash()` for cross-session consistency
- **Extracted confidence calculator** — Testable, 5 weighted factors
- **Mock fallback** — Works without API keys, gracefully degrades

## Quick Start

### Docker (Recommended)

```bash
git clone https://github.com/hutchgroupllc/cardvault-ai.git
cd cardvault-ai
cp .env.example .env
# Edit .env with your eBay API keys (optional)

docker compose up -d
# Open http://localhost:5000
```

### Local

```bash
pip install -r requirements.txt

# Optional: eBay API
export EBAY_CLIENT_ID=your-client-id
export EBAY_CLIENT_SECRET=your-client-secret
export EBAY_SANDBOX=true

python app.py
# Open http://localhost:5000
```

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | Scanner interface |
| `GET` | `/collection` | Collection browser |
| `GET` | `/card/<id>` | Card detail page |
| `GET` | `/settings` | Configuration |
| `POST` | `/api/estimate` | Get value estimate |
| `POST` | `/api/card` | Save card to collection |
| `GET` | `/api/card/<id>` | Get card JSON |
| `DELETE` | `/api/card/<id>` | Delete card |
| `POST` | `/api/card/<id>/revalue` | Re-estimate value |
| `GET` | `/api/collection` | List all cards |
| `GET` | `/api/stats` | Collection stats |
| `GET` | `/api/export` | CSV export |
| `GET` | `/health` | Health check |

## Value Engine v3.0

### Multi-Source Pricing

| Source | Weight | Status |
|--------|--------|--------|
| eBay Sold Listings | 35% | ✅ Live (sandbox) |
| 130point.com | 20% | 🔲 Planned |
| PWCC | 15% | 🔲 Planned |
| COMC | 10% | 🔲 Planned |
| Beckett | 8% | 🔲 Planned |
| PSA APR | 7% | 🔲 Planned |
| SportLots | 5% | 🔲 Planned |

### Multiplier System (Capped at 25x)

| Factor | Range | Example |
|--------|-------|---------|
| Condition/Grade | 0.4x – 3.5x | PSA 10 = 3.0x |
| Rookie | 1.5x | RC designation |
| Autograph | 2.5x | On-card or sticker |
| Scarcity | 1.1x – 50x | /25 = 3.5x |
| Parallel | 1.2x – 50x | Superfractor = 50x |
| Era | 0.3x – 2.5x | Vintage = 2.5x |
| Sport Market | 0.9x – 1.2x | Soccer = 1.2x |

## Roadmap

- [x] Value estimation engine v3.0
- [x] eBay API integration (sandbox)
- [x] Flask app with streetwear v2 design
- [x] Docker containerization
- [ ] Claude Vision card identification
- [ ] OpenCV binder page detection
- [ ] eBay production API keys
- [ ] Real 130point / PSA / Beckett integration
- [ ] MCP server architecture
- [ ] Deploy to hutchgroupllc.com

## License

Proprietary — HutchGroup LLC © 2026
