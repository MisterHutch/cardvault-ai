"""
CardVault AI — Flask Application v4.0 (Merged)
Streetwear v2 design + full module integration.
Modules: database_v2, card_detector, card_identifier_v2, card_value_engine, ebay_integration
Dockerized, eBay sandbox ready.

Author: HutchGroup LLC
"""

import os
import json
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, render_template_string, request, jsonify,
    redirect, url_for, send_file
)
from werkzeug.utils import secure_filename

# Core database (source of truth — preserves existing 400+ card collection)
from database_v2 import CardDatabase, Card, Booklet, PageScan

# Value engine v3.0 (capped multipliers, extracted confidence)
from card_value_engine import (
    CardValueEstimator, CardAttributes, CardCondition,
    Sport, ConfidenceLevel, MockDataFactory
)
from ebay_integration import create_ebay_fetcher, MarketDataFetcher

# Detection & identification (lazy-loaded — graceful when deps missing)
_detector = None
_identifier = None


def get_detector():
    """Lazy-load CardDetector (requires OpenCV)."""
    global _detector
    if _detector is None:
        try:
            from card_detector import CardDetector
            _detector = CardDetector()
            print("[CardVault] OpenCV card detector loaded")
        except ImportError:
            print("[CardVault] OpenCV not available — detection disabled")
    return _detector


def get_identifier():
    """Lazy-load CardIdentifier (requires anthropic SDK + API key)."""
    global _identifier
    if _identifier is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("[CardVault] No ANTHROPIC_API_KEY — identification disabled")
            return None
        try:
            from card_identifier_v2 import CardIdentifier
            _identifier = CardIdentifier(api_key)
            print("[CardVault] Claude Vision identifier loaded")
        except ImportError:
            print("[CardVault] anthropic SDK not available — identification disabled")
    return _identifier

# ============================================================================
# APP CONFIG
# ============================================================================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cardvault-dev-key")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

UPLOAD_DIR = Path("uploads")
PROCESSED_DIR = Path("processed")
UPLOAD_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# Database (database_v2 — preserves existing collection)
DB_PATH = os.environ.get("DB_PATH", "card_collection.db")
db = CardDatabase(DB_PATH)

estimator = CardValueEstimator()

# eBay integration
_cid = os.environ.get("EBAY_CLIENT_ID", "")
_csec = os.environ.get("EBAY_CLIENT_SECRET", "")
if _cid and _csec:
    _sandbox = os.environ.get("EBAY_SANDBOX", "true").lower() == "true"
    market_fetcher = create_ebay_fetcher(_cid, _csec, _sandbox)
    print("[CardVault] eBay connected (%s)" % ("sandbox" if _sandbox else "production"))
else:
    market_fetcher = MarketDataFetcher()
    print("[CardVault] No eBay keys — mock data mode")


# ============================================================================
# FIELD MAPPING: database_v2.Card <-> card_value_engine.CardAttributes
# ============================================================================

CONDITION_MAP = {
    "raw": CardCondition.RAW,
    "gem_mint": CardCondition.GEM_MINT,
    "mint": CardCondition.MINT,
    "nm_plus": CardCondition.NEAR_MINT_PLUS,
    "near_mint": CardCondition.NEAR_MINT,
    "excellent": CardCondition.EXCELLENT,
    "very_good": CardCondition.VERY_GOOD,
    "good": CardCondition.GOOD,
}

SPORT_MAP = {
    "basketball": Sport.BASKETBALL,
    "football": Sport.FOOTBALL,
    "baseball": Sport.BASEBALL,
    "soccer": Sport.SOCCER,
    "hockey": Sport.HOCKEY,
    "other": Sport.OTHER,
}


def db_card_to_value_attrs(card):
    """Translate database_v2.Card fields to CardAttributes for the value engine."""
    sport_str = (card.sport or "other").lower()
    condition_str = (card.condition or "raw").lower().replace(" ", "_")
    year_str = str(card.year or "2024")
    year_int = int(year_str[:4]) if year_str[:4].isdigit() else 2024

    return CardAttributes(
        player=card.player_name or "",
        year=year_int,
        set_name=card.set_name or "",
        card_number=card.card_number or "",
        sport=SPORT_MAP.get(sport_str, Sport.OTHER),
        parallel=card.parallel if card.parallel and card.parallel != "Base" else None,
        serial_number=card.numbering or None,
        autograph=bool(card.is_auto),
        rookie=bool(card.is_rookie),
        insert=False,
        condition=CONDITION_MAP.get(condition_str, CardCondition.RAW),
        graded=bool(getattr(card, "graded", False)),
        grade_value=getattr(card, "grade_value", None),
        grading_company=getattr(card, "grading_company", None),
    )


def request_to_value_attrs(d):
    """Translate API request JSON to CardAttributes for the value engine."""
    year_str = str(d.get("year", "2024"))
    year_int = int(year_str[:4]) if year_str[:4].isdigit() else 2024

    return CardAttributes(
        player=d.get("player") or d.get("player_name", ""),
        year=year_int,
        set_name=d.get("set_name", ""),
        card_number=d.get("card_number", ""),
        sport=SPORT_MAP.get(d.get("sport", "other").lower(), Sport.OTHER),
        parallel=d.get("parallel") if d.get("parallel") and d.get("parallel") != "Base" else None,
        serial_number=d.get("serial_number") or d.get("numbering") or None,
        autograph=bool(d.get("autograph") or d.get("is_auto")),
        rookie=bool(d.get("rookie") or d.get("is_rookie")),
        condition=CONDITION_MAP.get(d.get("condition", "raw").lower(), CardCondition.RAW),
    )


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ============================================================================
# STREETWEAR V2 CSS
# ============================================================================

CSS = """
:root{--hot-pink:#FF2D78;--electric-purple:#7B2FFF;--slime-green:#39FF14;--radical-yellow:#FFE818;--turbo-orange:#FF6B2B;--sky-blue:#00BFFF;--deep-blue:#1A0A4A;--midnight:#0D0628;--white:#FFF;--off-white:#F5F0FF;--light-purple:#E8DEFF;--border-thick:4px;--shadow-block:6px 6px 0px;--shadow-big:8px 8px 0px;--radius-chunky:20px;--radius-block:16px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Rubik',sans-serif;background:var(--midnight);color:var(--off-white);-webkit-font-smoothing:antialiased;min-height:100vh}
.geo-bg{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
.geo-shape{position:absolute;opacity:.04;animation:gfloat 20s ease-in-out infinite}
.geo-shape.circle{border-radius:50%;border:8px solid var(--hot-pink)}
.geo-shape.tri{width:0;height:0;border-left:60px solid transparent;border-right:60px solid transparent;border-bottom:100px solid var(--slime-green)}
.geo-shape:nth-child(1){top:8%;left:5%;width:120px;height:120px}
.geo-shape:nth-child(2){top:50%;right:8%;width:80px;height:80px;border-color:var(--radical-yellow);animation-delay:-5s}
.geo-shape:nth-child(3){bottom:15%;left:12%;animation-delay:-10s}
@keyframes gfloat{0%,100%{transform:translateY(0) rotate(0)}50%{transform:translateY(-20px) rotate(5deg)}}

.app-nav{position:sticky;top:0;z-index:100;background:rgba(13,6,40,.95);backdrop-filter:blur(20px);border-bottom:3px solid var(--electric-purple);padding:0 24px}
.nav-inner{max-width:1200px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;height:64px}
.logo{display:flex;align-items:center;gap:12px;text-decoration:none;color:inherit}
.logo-icon{width:40px;height:40px;background:linear-gradient(135deg,var(--hot-pink),var(--electric-purple));border-radius:10px;border:3px solid var(--white);display:grid;place-items:center;font-family:'Lilita One',cursive;font-size:16px;box-shadow:3px 3px 0 var(--electric-purple)}
.logo-text{font-family:'Lilita One',cursive;font-size:20px}
.logo-text span{color:var(--hot-pink)}
.nav-links{display:flex;gap:8px;list-style:none}
.nav-links a{text-decoration:none;color:var(--light-purple);font-weight:600;font-size:14px;padding:8px 16px;border-radius:10px;transition:all .15s}
.nav-links a:hover,.nav-links a.active{color:var(--white);background:rgba(123,47,255,.2)}
.nav-links a.active{background:var(--electric-purple);box-shadow:3px 3px 0 var(--deep-blue)}

.app-content{position:relative;z-index:1;max-width:1200px;margin:0 auto;padding:32px 24px}
.page-title{font-family:'Lilita One',cursive;font-size:32px;margin-bottom:8px}
.page-sub{color:var(--light-purple);font-size:15px;font-weight:500;margin-bottom:32px}

.panel{background:var(--deep-blue);border:var(--border-thick) solid var(--electric-purple);border-radius:var(--radius-chunky);padding:28px;box-shadow:var(--shadow-block) rgba(123,47,255,.3);transition:all .15s;margin-bottom:20px}
.panel:hover{transform:translate(-2px,-2px);box-shadow:var(--shadow-big) rgba(123,47,255,.4)}
.panel-title{font-family:'Lilita One',cursive;font-size:20px;margin-bottom:16px;display:flex;align-items:center;gap:10px}

.btn{display:inline-flex;align-items:center;gap:8px;padding:12px 24px;border-radius:14px;font-family:'Lilita One',cursive;font-size:16px;cursor:pointer;border:3px solid;transition:all .15s;text-decoration:none;color:var(--white)}
.btn-primary{background:var(--hot-pink);border-color:var(--deep-blue);box-shadow:var(--shadow-block) var(--deep-blue)}
.btn-primary:hover{transform:translate(3px,3px);box-shadow:0 0 0 var(--deep-blue)}
.btn-secondary{background:var(--electric-purple);border-color:var(--deep-blue);box-shadow:var(--shadow-block) var(--deep-blue)}
.btn-secondary:hover{transform:translate(3px,3px);box-shadow:0 0 0 var(--deep-blue)}
.btn-ghost{background:transparent;color:var(--light-purple);border-color:rgba(123,47,255,.3)}
.btn-ghost:hover{background:rgba(123,47,255,.1);color:var(--white)}
.btn-sm{padding:8px 16px;font-size:13px;border-radius:10px}
.btn-danger{background:var(--hot-pink);border-color:var(--deep-blue);box-shadow:var(--shadow-block) var(--deep-blue)}

.upload-zone{border:4px dashed var(--electric-purple);border-radius:var(--radius-chunky);padding:48px;text-align:center;cursor:pointer;transition:all .2s;background:rgba(123,47,255,.05)}
.upload-zone:hover,.upload-zone.dragover{background:rgba(123,47,255,.15);border-color:var(--hot-pink);transform:scale(1.01)}
.upload-icon{font-size:48px;margin-bottom:16px}
.upload-title{font-family:'Lilita One',cursive;font-size:22px;margin-bottom:8px}
.upload-sub{color:var(--light-purple);font-size:14px}

.scan-result{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:24px}
.scan-image-panel{position:relative;overflow:hidden;border-radius:var(--radius-block);border:3px solid var(--electric-purple)}
.scan-image-panel img{width:100%;display:block}

.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px}
.card-item{background:var(--deep-blue);border:3px solid rgba(123,47,255,.3);border-radius:var(--radius-block);overflow:hidden;transition:all .15s;cursor:pointer;text-decoration:none;color:inherit;display:block}
.card-item:hover{border-color:var(--hot-pink);transform:translateY(-4px);box-shadow:var(--shadow-big) rgba(255,45,120,.2)}
.card-thumb{height:160px;background:linear-gradient(135deg,var(--deep-blue),var(--midnight));display:grid;place-items:center;font-size:48px;opacity:.5}
.card-info{padding:16px}
.card-player-name{font-family:'Lilita One',cursive;font-size:18px;margin-bottom:4px}
.card-set-info{font-size:12px;color:var(--light-purple);font-weight:600;margin-bottom:12px}
.card-bottom{display:flex;justify-content:space-between;align-items:center}
.card-value{font-family:'Space Mono',monospace;font-size:18px;font-weight:700;color:var(--slime-green)}
.card-confidence{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;padding:4px 10px;border-radius:6px}
.conf-high{background:var(--slime-green);color:var(--deep-blue)}
.conf-med{background:var(--radical-yellow);color:var(--deep-blue)}
.conf-low{background:var(--turbo-orange);color:var(--white)}

.tag{display:inline-block;padding:4px 10px;border-radius:8px;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:1px;border:2px solid;margin-right:4px;margin-bottom:4px}
.tag-rc{background:var(--sky-blue);color:var(--deep-blue);border-color:var(--electric-purple)}
.tag-auto{background:var(--radical-yellow);color:var(--deep-blue);border-color:var(--turbo-orange)}
.tag-parallel{background:var(--electric-purple);color:var(--white);border-color:var(--hot-pink)}
.tag-numbered{background:var(--slime-green);color:var(--deep-blue);border-color:var(--deep-blue)}
.tag-graded{background:var(--hot-pink);color:var(--white);border-color:var(--deep-blue)}

.confidence-bar{display:flex;align-items:center;gap:12px;margin-top:12px}
.confidence-track{flex:1;height:10px;background:rgba(123,47,255,.2);border-radius:5px;overflow:hidden}
.confidence-fill{height:100%;border-radius:5px;transition:width .5s ease}
.confidence-val{font-family:'Space Mono',monospace;font-weight:700;font-size:14px}

.source-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.source-pill{padding:6px 12px;background:var(--midnight);border:2px solid rgba(123,47,255,.3);border-radius:8px;font-size:12px;font-weight:700}
.source-pill .val{color:var(--slime-green);font-family:'Space Mono',monospace}

.stats-bar{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:32px}
.stat-card{background:var(--deep-blue);border:3px solid rgba(123,47,255,.3);border-radius:var(--radius-block);padding:20px;text-align:center}
.stat-number{font-family:'Lilita One',cursive;font-size:28px;color:var(--slime-green)}
.stat-label{font-size:12px;color:var(--light-purple);font-weight:600;text-transform:uppercase;letter-spacing:1px;margin-top:4px}

.form-group{margin-bottom:16px}
.form-label{display:block;font-weight:700;font-size:13px;margin-bottom:6px;color:var(--light-purple);text-transform:uppercase;letter-spacing:1px}
.form-input,.form-select{width:100%;padding:12px 16px;background:var(--midnight);border:3px solid rgba(123,47,255,.3);border-radius:12px;color:var(--white);font-family:'Rubik',sans-serif;font-size:15px;transition:border-color .2s}
.form-input:focus,.form-select:focus{outline:none;border-color:var(--electric-purple);box-shadow:0 0 0 3px rgba(123,47,255,.2)}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.form-row-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}
.form-check{display:flex;align-items:center;gap:8px;font-weight:600;font-size:14px;cursor:pointer;color:var(--light-purple)}
.form-check input{width:18px;height:18px;accent-color:var(--hot-pink)}

.mult-table{width:100%;border-collapse:collapse;margin-top:12px}
.mult-table th,.mult-table td{padding:10px 14px;text-align:left;border-bottom:2px solid rgba(123,47,255,.15)}
.mult-table th{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:1px;color:var(--light-purple)}
.mult-val{font-family:'Space Mono',monospace;font-weight:700;color:var(--radical-yellow)}

.empty-state{text-align:center;padding:64px 24px;color:var(--light-purple)}
.empty-icon{font-size:64px;margin-bottom:16px;opacity:.5}
.empty-title{font-family:'Lilita One',cursive;font-size:24px;color:var(--white);margin-bottom:8px}

.detail-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px;flex-wrap:wrap;gap:16px}
.detail-value{font-family:'Space Mono',monospace;font-size:36px;font-weight:700;color:var(--slime-green)}
.detail-range{font-size:13px;color:var(--light-purple)}

.toast{position:fixed;bottom:24px;right:24px;padding:16px 24px;border-radius:14px;font-weight:700;font-size:14px;box-shadow:var(--shadow-big) rgba(0,0,0,.3);z-index:999;animation:slideIn .3s ease;display:none}
.toast-success{background:var(--slime-green);color:var(--deep-blue)}
.toast-error{background:#FF4444;color:var(--white)}
@keyframes slideIn{from{transform:translateY(100px);opacity:0}to{transform:translateY(0);opacity:1}}

.loading{display:inline-block;width:24px;height:24px;border:3px solid var(--electric-purple);border-top-color:var(--hot-pink);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

.app-footer{text-align:center;padding:32px;color:var(--light-purple);font-size:13px;border-top:2px solid rgba(123,47,255,.15);margin-top:64px}

@media(max-width:768px){
    .scan-result{grid-template-columns:1fr}
    .stats-bar{grid-template-columns:1fr 1fr}
    .form-row,.form-row-3{grid-template-columns:1fr}
    .nav-links{display:none}
    .card-grid{grid-template-columns:1fr}
    .detail-header{flex-direction:column}
}
"""

# ============================================================================
# BASE TEMPLATE
# ============================================================================

BASE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CardVault AI — %(title)s</title>
<link href="https://fonts.googleapis.com/css2?family=Lilita+One&family=Rubik:wght@400;500;600;700;800;900&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>""" + CSS + """</style>
</head>
<body>
<div class="geo-bg">
    <div class="geo-shape circle"></div>
    <div class="geo-shape circle"></div>
    <div class="geo-shape tri"></div>
</div>
<nav class="app-nav">
    <div class="nav-inner">
        <a href="/" class="logo">
            <div class="logo-icon">CV</div>
            <div class="logo-text">Card<span>Vault</span> AI</div>
        </a>
        <ul class="nav-links">
            <li><a href="/" class="%(nav_scan)s">Scanner</a></li>
            <li><a href="/collection" class="%(nav_coll)s">Collection</a></li>
            <li><a href="/settings" class="%(nav_set)s">Settings</a></li>
        </ul>
    </div>
</nav>
<main class="app-content">%(content)s</main>
<div id="toast" class="toast"></div>
<footer class="app-footer">&copy; 2026 HutchGroup LLC &middot; CardVault AI v3.0</footer>
<script>
function showToast(msg,type){var t=document.getElementById('toast');t.textContent=msg;t.className='toast toast-'+(type||'success');t.style.display='block';setTimeout(function(){t.style.display='none'},3000)}
</script>
%(scripts)s
</body>
</html>"""

def render(title, content, scripts="", active="scan"):
    html = BASE_HTML
    html = html.replace("%(title)s", title)
    html = html.replace("%(content)s", content)
    html = html.replace("%(scripts)s", scripts)
    html = html.replace("%(nav_scan)s", "active" if active == "scan" else "")
    html = html.replace("%(nav_coll)s", "active" if active == "collection" else "")
    html = html.replace("%(nav_set)s", "active" if active == "settings" else "")
    return html

# ============================================================================
# PAGE ROUTES
# ============================================================================

@app.route("/")
def scanner_page():
    content = """
    <h1 class="page-title">Card Scanner</h1>
    <p class="page-sub">Upload a binder page or single card photo for AI identification and valuation.</p>

    <div class="upload-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
        <div class="upload-icon">📸</div>
        <div class="upload-title">Drop Your Card Photo Here</div>
        <div class="upload-sub">or click to browse &middot; JPG, PNG, WEBP up to 16MB</div>
        <input type="file" id="fileInput" accept="image/*" style="display:none" onchange="handleUpload(this)">
    </div>

    <div id="scanResults" style="display:none">
    <div class="scan-result">
        <div class="panel">
            <div class="panel-title">📷 Uploaded Image</div>
            <div class="scan-image-panel"><img id="previewImage" src="" alt="Scanned card"></div>
        </div>
        <div>
            <div class="panel">
                <div class="panel-title">🎯 Card Details</div>
                <div class="form-row">
                    <div class="form-group"><label class="form-label">Player</label><input class="form-input" id="fPlayer" placeholder="e.g. Patrick Mahomes"></div>
                    <div class="form-group"><label class="form-label">Year</label><input class="form-input" id="fYear" type="number" placeholder="2017"></div>
                </div>
                <div class="form-row">
                    <div class="form-group"><label class="form-label">Set</label><input class="form-input" id="fSet" placeholder="e.g. Prizm"></div>
                    <div class="form-group"><label class="form-label">Card #</label><input class="form-input" id="fNumber" placeholder="e.g. 269"></div>
                </div>
                <div class="form-row-3">
                    <div class="form-group"><label class="form-label">Sport</label>
                        <select class="form-select" id="fSport">
                            <option value="football">Football</option><option value="basketball">Basketball</option>
                            <option value="baseball">Baseball</option><option value="soccer">Soccer</option>
                            <option value="hockey">Hockey</option><option value="other">Other</option>
                        </select>
                    </div>
                    <div class="form-group"><label class="form-label">Parallel</label><input class="form-input" id="fParallel" placeholder="e.g. Silver"></div>
                    <div class="form-group"><label class="form-label">Serial #</label><input class="form-input" id="fSerial" placeholder="e.g. 23/99"></div>
                </div>
                <div class="form-row-3">
                    <div class="form-group"><label class="form-check"><input type="checkbox" id="fRookie"> Rookie</label></div>
                    <div class="form-group"><label class="form-check"><input type="checkbox" id="fAuto"> Autograph</label></div>
                    <div class="form-group"><label class="form-label">Condition</label>
                        <select class="form-select" id="fCondition">
                            <option value="raw">Raw</option><option value="gem_mint">Gem Mint</option>
                            <option value="mint">Mint</option><option value="nm_plus">NM+</option>
                            <option value="near_mint">Near Mint</option><option value="excellent">Excellent</option>
                            <option value="good">Good</option>
                        </select>
                    </div>
                </div>
                <div style="display:flex;gap:12px;margin-top:16px">
                    <button class="btn btn-primary" onclick="getEstimate()">💰 Get Value</button>
                    <button class="btn btn-secondary" onclick="saveCard()">💾 Save to Collection</button>
                </div>
            </div>
            <div class="panel" id="estimatePanel" style="display:none">
                <div class="panel-title">💰 Value Estimate</div>
                <div id="estimateContent"></div>
            </div>
        </div>
    </div>
    </div>
    """

    scripts = """<script>
var dz=document.getElementById('dropZone');
['dragenter','dragover'].forEach(function(e){dz.addEventListener(e,function(ev){ev.preventDefault();dz.classList.add('dragover')})});
['dragleave','drop'].forEach(function(e){dz.addEventListener(e,function(ev){ev.preventDefault();dz.classList.remove('dragover')})});
dz.addEventListener('drop',function(ev){if(ev.dataTransfer.files[0])processFile(ev.dataTransfer.files[0])});

function handleUpload(inp){if(inp.files[0])processFile(inp.files[0])}
function processFile(file){
    var r=new FileReader();
    r.onload=function(e){document.getElementById('previewImage').src=e.target.result;document.getElementById('scanResults').style.display='block';dz.style.display='none'};
    r.readAsDataURL(file);
}

function gatherForm(){
    return {
        player:document.getElementById('fPlayer').value,
        year:parseInt(document.getElementById('fYear').value)||2024,
        set_name:document.getElementById('fSet').value,
        card_number:document.getElementById('fNumber').value,
        sport:document.getElementById('fSport').value,
        parallel:document.getElementById('fParallel').value||null,
        serial_number:document.getElementById('fSerial').value||null,
        rookie:document.getElementById('fRookie').checked,
        autograph:document.getElementById('fAuto').checked,
        condition:document.getElementById('fCondition').value
    }
}

function getEstimate(){
    var data=gatherForm();
    if(!data.player){showToast('Enter a player name','error');return}
    fetch('/api/estimate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
    .then(function(r){return r.json()})
    .then(function(res){
        if(res.error){showToast(res.error,'error');return}
        var cc=res.confidence_score>=75?'var(--slime-green)':res.confidence_score>=50?'var(--radical-yellow)':'var(--turbo-orange)';
        var tags='';
        if(data.rookie)tags+='<span class="tag tag-rc">RC</span>';
        if(data.autograph)tags+='<span class="tag tag-auto">Auto</span>';
        if(data.parallel)tags+='<span class="tag tag-parallel">'+data.parallel+'</span>';
        if(data.serial_number)tags+='<span class="tag tag-numbered">'+data.serial_number+'</span>';

        var mrows='';
        if(res.multipliers){for(var k in res.multipliers){if(k[0]!='_')mrows+='<tr><td>'+k+'</td><td class="mult-val">'+res.multipliers[k]+'x</td></tr>';}
        if(res.multipliers._cap_applied)mrows+='<tr><td style="color:var(--turbo-orange)">Cap applied (was '+res.multipliers._uncapped+'x)</td><td class="mult-val">'+res.multipliers._total+'x</td></tr>';}

        var src='';
        if(res.sources){res.sources.forEach(function(s){src+='<div class="source-pill">'+s.source+' <span class="val">$'+s.value.toFixed(2)+'</span></div>'});}

        document.getElementById('estimateContent').innerHTML=
            '<div class="detail-header"><div><div style="font-family:Lilita One,cursive;font-size:28px">'+data.player+'</div>'+
            '<div style="color:var(--light-purple);font-size:13px;font-weight:600">'+data.year+' '+data.set_name+' #'+data.card_number+'</div>'+
            '<div style="margin-top:8px">'+tags+'</div></div>'+
            '<div style="text-align:right"><div class="detail-value">$'+res.estimated_value.toFixed(2)+'</div>'+
            '<div class="detail-range">$'+res.range[0].toFixed(2)+' – $'+res.range[1].toFixed(2)+'</div></div></div>'+
            '<div class="confidence-bar"><span style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px">Confidence</span>'+
            '<div class="confidence-track"><div class="confidence-fill" style="width:'+res.confidence_score+'%;background:'+cc+'"></div></div>'+
            '<span class="confidence-val" style="color:'+cc+'">'+res.confidence_score+'%</span></div>'+
            '<div class="source-row">'+src+'</div>'+
            '<div style="margin-top:20px"><div style="font-family:Lilita One,cursive;font-size:16px;margin-bottom:8px">Multiplier Breakdown</div>'+
            '<table class="mult-table"><thead><tr><th>Factor</th><th>Mult</th></tr></thead><tbody>'+mrows+'</tbody></table></div>'+
            (res.grading_rec?'<div style="margin-top:16px;padding:12px 16px;background:rgba(255,232,24,.1);border:2px solid var(--radical-yellow);border-radius:10px;font-size:14px"><strong>Grading:</strong> '+res.grading_rec+'</div>':'')+
            (res.trend?'<div style="margin-top:12px;padding:12px 16px;background:rgba(57,255,20,.08);border:2px solid rgba(57,255,20,.3);border-radius:10px;font-size:14px"><strong>Trend:</strong> '+res.trend.direction+' ('+res.trend["30_day_change"]+'% 30d)</div>':'');

        document.getElementById('estimatePanel').style.display='block';
        showToast('Value estimate complete!');
    }).catch(function(e){showToast('Error: '+e.message,'error')});
}

function saveCard(){
    var data=gatherForm();
    if(!data.player){showToast('Enter a player name','error');return}
    fetch('/api/card',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
    .then(function(r){return r.json()})
    .then(function(res){
        if(res.error){showToast(res.error,'error');return}
        showToast('Card saved! ID: '+res.id);
    }).catch(function(e){showToast('Error: '+e.message,'error')});
}
</script>"""

    return render("Scanner", content, scripts, "scan")


@app.route("/collection")
def collection_page():
    conn = get_db()
    cards = conn.execute("SELECT * FROM cards ORDER BY created_at DESC").fetchall()
    total_value = conn.execute("SELECT COALESCE(SUM(estimated_value),0) as tv FROM cards").fetchone()["tv"]
    count = len(cards)
    avg_conf = conn.execute("SELECT COALESCE(AVG(confidence_score),0) as ac FROM cards WHERE confidence_score IS NOT NULL").fetchone()["ac"]
    conn.close()

    stats_html = f"""
    <div class="stats-bar">
        <div class="stat-card"><div class="stat-number">{count}</div><div class="stat-label">Cards</div></div>
        <div class="stat-card"><div class="stat-number">${total_value:,.2f}</div><div class="stat-label">Total Value</div></div>
        <div class="stat-card"><div class="stat-number">{avg_conf:.0f}%</div><div class="stat-label">Avg Confidence</div></div>
        <div class="stat-card"><div class="stat-number">4</div><div class="stat-label">Sources</div></div>
    </div>"""

    if not cards:
        cards_html = """
        <div class="empty-state">
            <div class="empty-icon">📦</div>
            <div class="empty-title">No Cards Yet</div>
            <p>Scan your first card to start building your collection.</p>
            <a href="/" class="btn btn-primary" style="margin-top:16px">📸 Start Scanning</a>
        </div>"""
    else:
        cards_html = '<div class="card-grid">'
        for c in cards:
            conf_class = "conf-high" if (c["confidence_score"] or 0) >= 75 else "conf-med" if (c["confidence_score"] or 0) >= 50 else "conf-low"
            val = c["estimated_value"] or 0
            tags = ""
            if c["rookie"]:
                tags += '<span class="tag tag-rc">RC</span>'
            if c["autograph"]:
                tags += '<span class="tag tag-auto">Auto</span>'
            if c["parallel"]:
                tags += f'<span class="tag tag-parallel">{c["parallel"]}</span>'

            cards_html += f"""
            <a href="/card/{c['id']}" class="card-item">
                <div class="card-thumb">🃏</div>
                <div class="card-info">
                    <div class="card-player-name">{c['player']}</div>
                    <div class="card-set-info">{c['year']} {c['set_name']} #{c['card_number']}</div>
                    <div style="margin-bottom:8px">{tags}</div>
                    <div class="card-bottom">
                        <div class="card-value">${val:,.2f}</div>
                        <span class="card-confidence {conf_class}">{c['confidence'] or 'N/A'}</span>
                    </div>
                </div>
            </a>"""
        cards_html += "</div>"

    content = f"""
    <h1 class="page-title">My Collection</h1>
    <p class="page-sub">All your scanned and valued cards in one place.</p>
    {stats_html}{cards_html}
    """
    return render("Collection", content, active="collection")


@app.route("/card/<card_id>")
def card_detail_page(card_id):
    conn = get_db()
    c = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
    conn.close()

    if not c:
        return render("Not Found", '<div class="empty-state"><div class="empty-icon">❌</div><div class="empty-title">Card Not Found</div></div>')

    c = dict(c)  # Convert Row to dict for .get() access
    val = c.get("estimated_value") or 0
    conf = c["confidence_score"] or 0
    cc = "var(--slime-green)" if conf >= 75 else "var(--radical-yellow)" if conf >= 50 else "var(--turbo-orange)"

    tags = ""
    if c["rookie"]:
        tags += '<span class="tag tag-rc">RC</span>'
    if c["autograph"]:
        tags += '<span class="tag tag-auto">Auto</span>'
    if c["parallel"]:
        tags += f'<span class="tag tag-parallel">{c["parallel"]}</span>'
    if c["serial_number"]:
        tags += f'<span class="tag tag-numbered">{c["serial_number"]}</span>'
    if c["graded"]:
        tags += f'<span class="tag tag-graded">{c["grading_company"]} {c["grade_value"]}</span>'

    content = f"""
    <a href="/collection" class="btn btn-ghost btn-sm" style="margin-bottom:20px">← Back to Collection</a>

    <div class="panel">
        <div class="detail-header">
            <div>
                <div style="font-family:'Lilita One',cursive;font-size:32px">{c['player']}</div>
                <div style="color:var(--light-purple);font-size:14px;font-weight:600">{c['year']} {c['set_name']} #{c['card_number']}</div>
                <div style="margin-top:12px">{tags}</div>
            </div>
            <div style="text-align:right">
                <div class="detail-value">${val:,.2f}</div>
                <div class="detail-range">${c['value_range_low'] or 0:,.2f} – ${c['value_range_high'] or 0:,.2f}</div>
            </div>
        </div>

        <div class="confidence-bar">
            <span style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px">Confidence</span>
            <div class="confidence-track"><div class="confidence-fill" style="width:{conf}%;background:{cc}"></div></div>
            <span class="confidence-val" style="color:{cc}">{conf:.0f}%</span>
        </div>

        {f'<div style="margin-top:16px;padding:12px 16px;background:rgba(255,232,24,.1);border:2px solid var(--radical-yellow);border-radius:10px;font-size:14px"><strong>Grading:</strong> {c["grading_rec"]}</div>' if c.get("grading_rec") else ""}
        {f'<div style="margin-top:12px;padding:12px 16px;background:rgba(57,255,20,.08);border:2px solid rgba(57,255,20,.3);border-radius:10px;font-size:14px"><strong>Trend:</strong> {c["market_trend"]}</div>' if c.get("market_trend") else ""}
    </div>

    <div style="display:flex;gap:12px;margin-top:16px">
        <button class="btn btn-primary" onclick="revalue('{card_id}')">🔄 Re-estimate Value</button>
        <button class="btn btn-danger btn-sm" onclick="if(confirm('Delete this card?'))deleteCard('{card_id}')">🗑️ Delete</button>
    </div>
    """

    scripts = f"""<script>
function revalue(id){{
    fetch('/api/card/'+id+'/revalue',{{method:'POST'}})
    .then(function(r){{return r.json()}})
    .then(function(res){{if(res.error)showToast(res.error,'error');else{{showToast('Updated: $'+res.estimated_value.toFixed(2));setTimeout(function(){{location.reload()}},1000)}}}})
    .catch(function(e){{showToast('Error: '+e.message,'error')}});
}}
function deleteCard(id){{
    fetch('/api/card/'+id,{{method:'DELETE'}})
    .then(function(r){{return r.json()}})
    .then(function(res){{showToast('Card deleted');setTimeout(function(){{window.location='/collection'}},1000)}})
    .catch(function(e){{showToast('Error: '+e.message,'error')}});
}}
</script>"""

    return render(c["player"], content, scripts, "collection")


@app.route("/settings")
def settings_page():
    ebay_status = "Connected (sandbox)" if _cid else "Not configured"
    content = f"""
    <h1 class="page-title">Settings</h1>
    <p class="page-sub">Configure API keys and application settings.</p>

    <div class="panel">
        <div class="panel-title">🔑 API Configuration</div>
        <div style="display:grid;gap:12px">
            <div class="form-row">
                <div><span style="font-weight:700;font-size:13px;color:var(--light-purple)">eBay API</span></div>
                <div style="color:{'var(--slime-green)' if _cid else 'var(--turbo-orange)'};font-weight:700">{ebay_status}</div>
            </div>
            <div class="form-row">
                <div><span style="font-weight:700;font-size:13px;color:var(--light-purple)">Value Engine</span></div>
                <div style="color:var(--slime-green);font-weight:700">v3.0 — Refactored</div>
            </div>
            <div class="form-row">
                <div><span style="font-weight:700;font-size:13px;color:var(--light-purple)">Database</span></div>
                <div style="color:var(--slime-green);font-weight:700">{DB_PATH}</div>
            </div>
        </div>
    </div>

    <div class="panel">
        <div class="panel-title">📦 Data Management</div>
        <div style="display:flex;gap:12px">
            <a href="/api/export" class="btn btn-secondary btn-sm">📥 Export CSV</a>
        </div>
    </div>

    <div class="panel">
        <div class="panel-title">ℹ️ Environment Variables</div>
        <div style="background:var(--midnight);border-radius:12px;padding:16px;font-family:'Space Mono',monospace;font-size:13px;line-height:2;color:var(--light-purple)">
            EBAY_CLIENT_ID=your-client-id<br>
            EBAY_CLIENT_SECRET=your-client-secret<br>
            EBAY_SANDBOX=true<br>
            SECRET_KEY=your-secret-key<br>
            DB_PATH=cardvault.db
        </div>
    </div>
    """
    return render("Settings", content, active="settings")

# ============================================================================
# API ROUTES — Detection & Identification
# ============================================================================

@app.route("/api/detect", methods=["POST"])
def api_detect():
    """Detect cards in a binder page image using OpenCV."""
    detector = get_detector()
    if not detector:
        return jsonify({"error": "OpenCV not available", "cards": []}), 200

    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    f = request.files["image"]
    if not f or not allowed_file(f.filename):
        return jsonify({"error": "Invalid file type"}), 400

    filename = secure_filename("%s_%s" % (uuid.uuid4().hex, f.filename))
    filepath = UPLOAD_DIR / filename
    f.save(str(filepath))

    try:
        detected = detector.detect_cards(str(filepath), method="auto")
        cards_out = []
        for card in detected:
            saved_path = card.save(PROCESSED_DIR, prefix="card")
            cards_out.append({
                "filename": saved_path.name,
                "row": card.position[0],
                "col": card.position[1],
                "confidence": card.confidence,
            })
        return jsonify({"cards": cards_out, "total": len(cards_out)})
    except Exception as e:
        return jsonify({"error": str(e), "cards": []}), 200


@app.route("/api/identify", methods=["POST"])
def api_identify():
    """Identify a single card image using Claude Vision."""
    identifier = get_identifier()
    if not identifier:
        return jsonify({"error": "Claude Vision not available — set ANTHROPIC_API_KEY"}), 200

    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    f = request.files["image"]
    if not f or not allowed_file(f.filename):
        return jsonify({"error": "Invalid file type"}), 400

    filename = secure_filename("%s_%s" % (uuid.uuid4().hex, f.filename))
    filepath = UPLOAD_DIR / filename
    f.save(str(filepath))

    try:
        result = identifier.identify_card(str(filepath))
        return jsonify(result.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/identify-batch", methods=["POST"])
def api_identify_batch():
    """Identify multiple detected cards using Claude Vision."""
    identifier = get_identifier()
    if not identifier:
        return jsonify({"error": "Claude Vision not available"}), 200

    data = request.json
    cards_in = data.get("cards", [])
    results = []
    for card_info in cards_in:
        filepath = PROCESSED_DIR / card_info["filename"]
        if filepath.exists():
            try:
                ident = identifier.identify_card(str(filepath))
                result = ident.to_dict()
                result["filename"] = card_info["filename"]
                result["row"] = card_info.get("row", 0)
                result["col"] = card_info.get("col", 0)
                results.append(result)
            except Exception as e:
                results.append({"error": str(e), "filename": card_info["filename"]})
    return jsonify({"results": results})


@app.route("/api/save-batch", methods=["POST"])
def api_save_batch():
    """Save multiple identified cards to the database."""
    data = request.json
    cards_in = data.get("cards", [])
    booklet_name = data.get("booklet_name", "")
    page_number = data.get("page_number", 1)
    saved = 0

    for c in cards_in:
        if c.get("error"):
            continue
        card = Card(
            player_name=c.get("player_name", "Unknown"),
            team=c.get("team", ""), year=c.get("year", ""),
            sport=c.get("sport", ""), position=c.get("position", ""),
            brand=c.get("brand", ""), set_name=c.get("set_name", ""),
            subset=c.get("subset", ""), card_number=c.get("card_number", ""),
            parallel=c.get("parallel", "Base"),
            is_rookie=c.get("is_rookie", False), is_auto=c.get("is_auto", False),
            is_patch=c.get("is_patch", False), is_memorabilia=c.get("is_memorabilia", False),
            is_numbered=c.get("is_numbered", False), numbering=c.get("numbering", ""),
            is_ssp=c.get("is_ssp", False), ssp_type=c.get("ssp_type", ""),
            confidence=c.get("confidence", 0),
            identification_notes=c.get("identification_notes", ""),
            image_path=c.get("filename", ""),
            slot_row=c.get("row", 0), slot_col=c.get("col", 0),
            slot_position=c.get("row", 0) * 3 + c.get("col", 0) + 1,
            booklet_name=booklet_name, page_number=page_number,
        )
        if booklet_name:
            bid, _ = db.get_or_create_booklet(booklet_name, sport=c.get("sport", ""))
            card.booklet_id = bid
        db.add_card(card)
        saved += 1

    return jsonify({"count": saved})


@app.route("/processed/<filename>")
def serve_processed(filename):
    """Serve processed card images."""
    return send_file(PROCESSED_DIR / secure_filename(filename))


# ============================================================================
# API ROUTES — Value Engine & CRUD (backed by database_v2)
# ============================================================================

@app.route("/api/estimate", methods=["POST"])
def api_estimate():
    """Get a value estimate using the v3.0 value engine."""
    try:
        d = request.json
        card = request_to_value_attrs(d)
        market_data = market_fetcher.fetch_all(card)
        est = estimator.estimate_value(card, market_data=market_data, use_mock=not market_data)
        sources = [{"source": dp.source, "value": dp.value, "date": dp.date.isoformat()} for dp in est.data_points[:6]]
        return jsonify({
            "estimated_value": est.estimated_value,
            "confidence": est.confidence.value,
            "confidence_score": est.confidence_score,
            "range": list(est.value_range),
            "multipliers": est.multipliers_applied,
            "grading_rec": est.grading_recommendation,
            "trend": est.market_trends,
            "sources": sources,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/card", methods=["POST"])
def api_save_card():
    """Save a single card to the collection via database_v2."""
    try:
        d = request.json
        card = Card(
            player_name=d.get("player_name") or d.get("player", ""),
            team=d.get("team", ""), year=d.get("year", ""),
            sport=d.get("sport", ""), brand=d.get("brand", ""),
            set_name=d.get("set_name", ""), card_number=d.get("card_number", ""),
            parallel=d.get("parallel", "Base"),
            is_rookie=bool(d.get("is_rookie") or d.get("rookie")),
            is_auto=bool(d.get("is_auto") or d.get("autograph")),
            is_patch=bool(d.get("is_patch")),
            is_numbered=bool(d.get("numbering")),
            numbering=d.get("numbering", ""),
            condition=d.get("condition", "raw"),
            booklet_name=d.get("booklet_name", ""),
        )
        if card.booklet_name:
            bid, _ = db.get_or_create_booklet(card.booklet_name, sport=card.sport)
            card.booklet_id = bid

        # Get estimate and set on card before save
        val_attrs = db_card_to_value_attrs(card)
        est = estimator.estimate_value(val_attrs)
        card.estimated_value = est.estimated_value
        card.confidence = est.confidence_score / 100.0

        card_id = db.add_card(card)
        db.update_card_valuation(
            card_id, est.estimated_value, est.confidence_score,
            est.value_range[0], est.value_range[1],
            est.market_trends.get("direction", "stable"),
            est.grading_recommendation or ""
        )
        return jsonify({"id": card_id, "estimated_value": est.estimated_value})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/card/<int:card_id>", methods=["GET"])
def api_get_card(card_id):
    card = db.get_card(card_id)
    if not card:
        return jsonify({"error": "Not found"}), 404
    return jsonify(card.to_dict())


@app.route("/api/card/<int:card_id>", methods=["DELETE"])
def api_delete_card(card_id):
    db.delete_card(card_id)
    return jsonify({"deleted": card_id})


@app.route("/api/card/<int:card_id>/revalue", methods=["POST"])
def api_revalue_card(card_id):
    """Re-estimate a card's value using current market data."""
    card = db.get_card(card_id)
    if not card:
        return jsonify({"error": "Not found"}), 404

    val_attrs = db_card_to_value_attrs(card)
    market_data = market_fetcher.fetch_all(val_attrs)
    est = estimator.estimate_value(val_attrs, market_data=market_data, use_mock=not market_data)

    db.update_card_valuation(
        card_id, est.estimated_value, est.confidence_score,
        est.value_range[0], est.value_range[1],
        est.market_trends.get("direction", "stable"),
        est.grading_recommendation or ""
    )
    return jsonify({"estimated_value": est.estimated_value, "confidence_score": est.confidence_score})


@app.route("/api/collection")
def api_collection():
    cards = db.search_cards(sort_by="created_at", sort_order="DESC", limit=1000)
    return jsonify([c.to_dict() for c in cards])


@app.route("/api/booklets")
def api_booklets():
    booklets = db.list_booklets()
    return jsonify([b.to_dict() for b in booklets])


@app.route("/api/stats")
def api_stats():
    return jsonify(db.get_collection_stats())


@app.route("/api/search")
def api_search():
    """Full search with database_v2 filter support."""
    return jsonify([c.to_dict() for c in db.search_cards(
        player=request.args.get("player"),
        team=request.args.get("team"),
        year=request.args.get("year"),
        set_name=request.args.get("set_name"),
        sport=request.args.get("sport"),
        brand=request.args.get("brand"),
        booklet_name=request.args.get("booklet"),
        rookies_only=request.args.get("rookies") == "1",
        autos_only=request.args.get("autos") == "1",
        patches_only=request.args.get("patches") == "1",
        numbered_only=request.args.get("numbered") == "1",
        ssp_only=request.args.get("ssp") == "1",
        sort_by=request.args.get("sort", "player_name"),
        sort_order=request.args.get("order", "ASC"),
        limit=int(request.args.get("limit", 100)),
        offset=int(request.args.get("offset", 0)),
    )])


@app.route("/api/export")
def api_export():
    import csv
    import io
    cards = db.search_cards(limit=100000)
    output = io.StringIO()
    if cards:
        columns = [
            'id', 'player_name', 'team', 'year', 'sport', 'brand', 'set_name',
            'parallel', 'card_number', 'is_rookie', 'is_auto', 'is_patch',
            'is_numbered', 'numbering', 'is_ssp', 'condition', 'estimated_value',
            'confidence', 'booklet_name', 'page_number', 'slot_position', 'notes'
        ]
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for c in cards:
            writer.writerow(c.to_dict())
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name="cardvault_export_%s.csv" % datetime.now().strftime('%Y%m%d'),
    )


# ============================================================================
# HEALTH CHECK (Docker / deployment)
# ============================================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "4.0",
        "ebay": bool(_cid),
        "detector": get_detector() is not None,
        "identifier": get_identifier() is not None,
        "db": DB_PATH,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print("[CardVault] Starting v4.0 on port %d" % port)
    app.run(host="0.0.0.0", port=port, debug=debug)
