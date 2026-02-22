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
import sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # Load .env before any os.environ.get() calls

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

def get_db():
    """Raw SQLite connection (row_factory=Row so columns are accessible by name)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
# BASE TEMPLATE  (CSS & shared JS live in static/ — edit those files freely)
# ============================================================================

BASE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CardVault AI — %(title)s</title>
<link href="https://fonts.googleapis.com/css2?family=Lilita+One&family=Rubik:wght@400;500;600;700;800;900&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/style.css">
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
            <li><a href="/booklets" class="%(nav_book)s">Booklets</a></li>
            <li><a href="/settings" class="%(nav_set)s">Settings</a></li>
        </ul>
    </div>
</nav>
<main class="app-content">%(content)s</main>
<div id="toast" class="toast"></div>
<footer class="app-footer">&copy; 2026 HutchGroup LLC &middot; CardVault AI v4.0</footer>
<script src="/static/app.js"></script>
%(scripts)s
</body>
</html>"""

def render(title, content, scripts="", active="scan"):
    html = BASE_HTML
    html = html.replace("%(title)s", title)
    html = html.replace("%(content)s", content)
    html = html.replace("%(scripts)s", scripts)
    html = html.replace("%(nav_scan)s",  "active" if active == "scan"       else "")
    html = html.replace("%(nav_coll)s",  "active" if active == "collection" else "")
    html = html.replace("%(nav_book)s",  "active" if active == "booklets"   else "")
    html = html.replace("%(nav_set)s",   "active" if active == "settings"   else "")
    return html

# ============================================================================
# PAGE ROUTES
# ============================================================================

@app.route("/")
def scanner_page():
    content = """
    <h1 class="page-title">Card Scanner</h1>
    <p class="page-sub">Scan a full binder page (9 cards) or a single card — AI identifies everything automatically.</p>

    <!-- Mode Selector -->
    <div style="display:flex;gap:12px;margin-bottom:24px">
        <button class="btn btn-primary" id="modeBinder" onclick="setMode('binder')">📖 Binder Page (9 cards)</button>
        <button class="btn btn-ghost" id="modeSingle" onclick="setMode('single')">🃏 Single Card</button>
    </div>

    <!-- Upload Zone -->
    <div class="upload-zone" id="dropZone" style="position:relative">
        <div class="upload-icon" id="uploadIcon">📖</div>
        <div class="upload-title" id="uploadTitle">Drop Your Binder Page Here</div>
        <div class="upload-sub" id="uploadSub">Full 3×3 page photo · JPG, PNG, WEBP up to 16MB</div>
        <input type="file" id="fileInput" accept="image/*"
               style="position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;font-size:0"
               onchange="handleUpload(this)">
    </div>

    <!-- Binder Info Bar -->
    <div id="binderInfo" style="display:none;margin-top:16px">
        <div class="panel" style="padding:16px">
            <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
                <div class="form-group" style="margin:0;flex:1;min-width:180px">
                    <label class="form-label">Booklet / Binder Name</label>
                    <input class="form-input" id="binderName" placeholder="e.g. My Prizm Collection">
                </div>
                <div class="form-group" style="margin:0;width:120px">
                    <label class="form-label">Page #</label>
                    <input class="form-input" id="pageNumber" type="number" value="1" min="1">
                </div>
            </div>
        </div>
    </div>

    <!-- ===== BINDER PAGE RESULTS ===== -->
    <div id="binderResults" style="display:none;margin-top:24px">

        <!-- Preview + Detect -->
        <div class="panel">
            <div class="panel-title">📷 Binder Page Preview</div>
            <img id="binderPreview" src="" alt="Binder page" style="max-width:100%;border-radius:10px;margin-bottom:16px">
            <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
                <button class="btn btn-primary" id="detectBtn" onclick="detectCards()">🔍 Detect Cards</button>
                <span id="detectStatus" style="color:var(--light-purple);font-size:14px"></span>
            </div>
        </div>

        <!-- Card Grid (populated after detect) -->
        <div id="cardGrid" style="display:none">
            <div class="panel">
                <div class="panel-title" style="display:flex;justify-content:space-between;align-items:center">
                    <span>🎯 Detected Cards <span id="cardCount" style="color:var(--light-purple);font-size:16px"></span></span>
                    <button class="btn btn-secondary btn-sm" id="identifyBtn" onclick="identifyAll()">🤖 AI Identify All</button>
                </div>
                <div id="cardGridInner" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:16px"></div>
            </div>

            <!-- Save Batch -->
            <div class="panel" id="saveBatchPanel" style="display:none">
                <div class="panel-title">💾 Save to Collection</div>
                <p style="color:var(--light-purple);font-size:14px;margin-bottom:16px">Review cards above, then save the full page to your collection.</p>
                <button class="btn btn-primary" onclick="saveBatch()">💾 Save All Cards</button>
                <button class="btn btn-ghost" style="margin-left:12px" onclick="resetScanner()">↩ Scan Another Page</button>
            </div>
        </div>
    </div>

    <!-- ===== SINGLE CARD RESULTS ===== -->
    <div id="singleResults" style="display:none;margin-top:24px">
        <div class="scan-result">
            <div class="panel">
                <div class="panel-title">📷 Card Preview</div>
                <div class="scan-image-panel"><img id="singlePreview" src="" alt="Card"></div>
                <button class="btn btn-secondary" style="margin-top:12px;width:100%" id="singleIdentifyBtn" onclick="identifySingle()">🤖 AI Identify</button>
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
                    <div class="form-row">
                        <div class="form-group"><label class="form-label">Sport</label>
                            <select class="form-select" id="fSport">
                                <option value="football">Football</option><option value="basketball">Basketball</option>
                                <option value="baseball">Baseball</option><option value="soccer">Soccer</option>
                                <option value="hockey">Hockey</option><option value="other">Other</option>
                            </select>
                        </div>
                        <div class="form-group"><label class="form-label">Parallel</label><input class="form-input" id="fParallel" placeholder="e.g. Silver"></div>
                    </div>
                    <div class="form-row">
                        <div class="form-group"><label class="form-label">Serial #</label><input class="form-input" id="fSerial" placeholder="e.g. 23/99"></div>
                        <div class="form-group"><label class="form-label">Condition</label>
                            <select class="form-select" id="fCondition">
                                <option value="raw">Raw</option><option value="gem_mint">Gem Mint</option>
                                <option value="mint">Mint</option><option value="nm_plus">NM+</option>
                                <option value="near_mint">Near Mint</option><option value="excellent">Excellent</option>
                                <option value="good">Good</option>
                            </select>
                        </div>
                    </div>
                    <div style="display:flex;gap:12px;margin-top:8px">
                        <label class="form-check"><input type="checkbox" id="fRookie"> Rookie</label>
                        <label class="form-check"><input type="checkbox" id="fAuto"> Autograph</label>
                        <label class="form-check"><input type="checkbox" id="fPatch"> Patch</label>
                    </div>
                    <div style="display:flex;gap:12px;margin-top:16px;flex-wrap:wrap">
                        <button class="btn btn-primary" onclick="getEstimate()">💰 Get Value</button>
                        <button class="btn btn-secondary" onclick="saveCard()">💾 Save to Collection</button>
                        <button class="btn btn-ghost" onclick="resetScanner()">↩ Scan Another</button>
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
var currentMode = 'binder';
var currentFile = null;
var detectedCards = [];
var identifiedCards = [];

// ── Mode selector ──────────────────────────────────────────────────────────
function setMode(mode) {
    currentMode = mode;
    var isBinder = mode === 'binder';
    document.getElementById('modeBinder').className = isBinder ? 'btn btn-primary' : 'btn btn-ghost';
    document.getElementById('modeSingle').className = isBinder ? 'btn btn-ghost' : 'btn btn-primary';
    document.getElementById('uploadIcon').textContent = isBinder ? '📖' : '🃏';
    document.getElementById('uploadTitle').textContent = isBinder ? 'Drop Your Binder Page Here' : 'Drop Your Card Photo Here';
    document.getElementById('uploadSub').textContent = isBinder ? 'Full 3×3 page photo · JPG, PNG, WEBP up to 16MB' : 'Single card · JPG, PNG, WEBP up to 16MB';
    document.getElementById('binderInfo').style.display = isBinder ? 'block' : 'none';
    resetScanner();
}

// ── Drag & drop ────────────────────────────────────────────────────────────
var dz = document.getElementById('dropZone');
['dragenter','dragover'].forEach(function(e){
    dz.addEventListener(e,function(ev){ev.preventDefault();ev.stopPropagation();dz.classList.add('dragover')});
});
['dragleave','drop'].forEach(function(e){
    dz.addEventListener(e,function(ev){ev.preventDefault();ev.stopPropagation();dz.classList.remove('dragover')});
});
dz.addEventListener('drop',function(ev){
    ev.preventDefault();ev.stopPropagation();
    dz.classList.remove('dragover');
    var f = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
    if(f) processFile(f);
});

function handleUpload(inp){ if(inp && inp.files && inp.files[0]) processFile(inp.files[0]); }

function processFile(file) {
    currentFile = file;
    var r = new FileReader();
    r.onload = function(e) {
        if (currentMode === 'binder') {
            document.getElementById('binderPreview').src = e.target.result;
            document.getElementById('binderResults').style.display = 'block';
            document.getElementById('cardGrid').style.display = 'none';
        } else {
            document.getElementById('singlePreview').src = e.target.result;
            document.getElementById('singleResults').style.display = 'block';
        }
        dz.style.display = 'none';
        document.getElementById('binderInfo').style.display = currentMode === 'binder' ? 'block' : 'none';
    };
    r.readAsDataURL(file);
}

function resetScanner() {
    currentFile = null; detectedCards = []; identifiedCards = [];
    dz.style.display = 'block';
    document.getElementById('fileInput').value = '';
    document.getElementById('binderResults').style.display = 'none';
    document.getElementById('singleResults').style.display = 'none';
    document.getElementById('cardGrid').style.display = 'none';
    document.getElementById('saveBatchPanel').style.display = 'none';
    document.getElementById('cardGridInner').innerHTML = '';
    document.getElementById('detectStatus').textContent = '';
    document.getElementById('estimatePanel').style.display = 'none';
    if (currentMode === 'binder') document.getElementById('binderInfo').style.display = 'block';
}

// ── BINDER: Detect cards ───────────────────────────────────────────────────
function detectCards() {
    if (!currentFile) { showToast('No image loaded', 'error'); return; }
    var btn = document.getElementById('detectBtn');
    var status = document.getElementById('detectStatus');
    btn.disabled = true; btn.textContent = '⏳ Detecting…';
    status.textContent = 'Running OpenCV card detection…';

    var fd = new FormData();
    fd.append('image', currentFile);

    fetch('/api/detect', {method:'POST', body:fd})
    .then(function(r){return r.json()})
    .then(function(res) {
        btn.disabled = false; btn.textContent = '🔍 Detect Cards';
        if (res.error && res.cards && res.cards.length === 0) {
            showToast(res.error, 'error');
            status.textContent = '❌ ' + res.error;
            return;
        }
        detectedCards = res.cards || [];
        status.textContent = '✅ Found ' + detectedCards.length + ' cards';
        document.getElementById('cardCount').textContent = '(' + detectedCards.length + ' found)';
        renderCardGrid(detectedCards);
        document.getElementById('cardGrid').style.display = 'block';
        showToast('Detected ' + detectedCards.length + ' cards — click AI Identify All!');
    })
    .catch(function(e) {
        btn.disabled = false; btn.textContent = '🔍 Detect Cards';
        showToast('Detection failed: ' + e.message, 'error');
        status.textContent = '❌ ' + e.message;
    });
}

function renderCardGrid(cards) {
    var grid = document.getElementById('cardGridInner');
    grid.innerHTML = '';
    cards.forEach(function(card, i) {
        var pos = 'Row ' + (card.row+1) + ', Col ' + (card.col+1);
        var conf = Math.round((card.confidence||0)*100);
        grid.innerHTML += '<div class="card-detect-cell" id="cell-'+i+'" data-idx="'+i+'">' +
            '<img src="/processed/' + card.filename + '" style="width:100%;border-radius:8px;display:block" onerror="this.src=\'\';">' +
            '<div style="padding:8px">' +
            '<div style="font-size:11px;color:var(--light-purple);font-weight:700;text-transform:uppercase">' + pos + ' · ' + conf + '% conf</div>' +
            '<div id="card-label-'+i+'" style="font-size:12px;color:var(--off-white);margin-top:4px">Pending AI ID…</div>' +
            '</div></div>';
    });
}

// ── BINDER: Identify all ──────────────────────────────────────────────────
function identifyAll() {
    if (!detectedCards.length) { showToast('Detect cards first', 'error'); return; }
    var btn = document.getElementById('identifyBtn');
    btn.disabled = true; btn.textContent = '⏳ Identifying…';
    showToast('Claude Vision is reading ' + detectedCards.length + ' cards…');

    fetch('/api/identify-batch', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({cards: detectedCards})
    })
    .then(function(r){return r.json()})
    .then(function(res) {
        btn.disabled = false; btn.textContent = '🤖 AI Identify All';
        identifiedCards = res.results || [];
        identifiedCards.forEach(function(card, i) {
            var label = document.getElementById('card-label-'+i);
            if (!label) return;
            if (card.error) {
                label.innerHTML = '<span style="color:var(--turbo-orange)">⚠ ' + card.error + '</span>';
                return;
            }
            var tags = '';
            if (card.is_rookie) tags += '<span class="tag tag-rc" style="font-size:9px;padding:1px 5px">RC</span>';
            if (card.is_auto)   tags += '<span class="tag tag-auto" style="font-size:9px;padding:1px 5px">Auto</span>';
            if (card.is_numbered) tags += '<span class="tag tag-numbered" style="font-size:9px;padding:1px 5px">' + (card.numbering||'Numbered') + '</span>';
            label.innerHTML = '<strong>' + (card.player_name||'Unknown') + '</strong> ' + tags +
                '<br><span style="color:var(--light-purple)">' + (card.year||'') + ' ' + (card.set_name||'') + '</span>' +
                (card.parallel && card.parallel !== 'Base' ? '<br><span style="color:var(--radical-yellow);font-size:11px">' + card.parallel + '</span>' : '');
        });
        document.getElementById('saveBatchPanel').style.display = 'block';
        showToast('All ' + identifiedCards.length + ' cards identified!');
    })
    .catch(function(e) {
        btn.disabled = false; btn.textContent = '🤖 AI Identify All';
        showToast('Identification failed: ' + e.message, 'error');
    });
}

// ── BINDER: Save batch ────────────────────────────────────────────────────
function saveBatch() {
    var booklet = document.getElementById('binderName').value || 'My Collection';
    var page = parseInt(document.getElementById('pageNumber').value) || 1;
    var cards = identifiedCards.length ? identifiedCards : detectedCards.map(function(c){return c;});

    fetch('/api/save-batch', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({cards: cards, booklet_name: booklet, page_number: page})
    })
    .then(function(r){return r.json()})
    .then(function(res) {
        showToast('✅ Saved ' + res.count + ' cards to "' + booklet + '" page ' + page + '!');
        setTimeout(function(){window.location='/collection'},1500);
    })
    .catch(function(e){ showToast('Save failed: ' + e.message, 'error'); });
}

// ── SINGLE: AI Identify ───────────────────────────────────────────────────
function identifySingle() {
    if (!currentFile) { showToast('No image loaded', 'error'); return; }
    var btn = document.getElementById('singleIdentifyBtn');
    btn.disabled = true; btn.textContent = '⏳ Identifying…';

    var fd = new FormData();
    fd.append('image', currentFile);

    fetch('/api/identify', {method:'POST', body:fd})
    .then(function(r){return r.json()})
    .then(function(res) {
        btn.disabled = false; btn.textContent = '🤖 AI Identify';
        if (res.error) { showToast(res.error, 'error'); return; }
        document.getElementById('fPlayer').value  = res.player_name || '';
        document.getElementById('fYear').value    = res.year || '';
        document.getElementById('fSet').value     = res.set_name || '';
        document.getElementById('fNumber').value  = res.card_number || '';
        document.getElementById('fParallel').value= res.parallel && res.parallel!=='Base' ? res.parallel : '';
        document.getElementById('fSerial').value  = res.numbering || '';
        document.getElementById('fRookie').checked = !!res.is_rookie;
        document.getElementById('fAuto').checked   = !!res.is_auto;
        document.getElementById('fPatch').checked  = !!res.is_patch;
        var sportSel = document.getElementById('fSport');
        if (res.sport) {
            for (var i=0;i<sportSel.options.length;i++) {
                if (sportSel.options[i].value.toLowerCase()===res.sport.toLowerCase()) { sportSel.selectedIndex=i; break; }
            }
        }
        showToast('Card identified: ' + (res.player_name||'Unknown'));
    })
    .catch(function(e) {
        btn.disabled = false; btn.textContent = '🤖 AI Identify';
        showToast('Identify failed: ' + e.message, 'error');
    });
}

// ── SINGLE: Value estimate ────────────────────────────────────────────────
function gatherForm(){
    return {
        player: document.getElementById('fPlayer').value,
        year: parseInt(document.getElementById('fYear').value)||2024,
        set_name: document.getElementById('fSet').value,
        card_number: document.getElementById('fNumber').value,
        sport: document.getElementById('fSport').value,
        parallel: document.getElementById('fParallel').value||null,
        serial_number: document.getElementById('fSerial').value||null,
        rookie: document.getElementById('fRookie').checked,
        autograph: document.getElementById('fAuto').checked,
        condition: document.getElementById('fCondition').value
    };
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
            (res.grading_rec?'<div style="margin-top:16px;padding:12px 16px;background:rgba(255,232,24,.1);border:2px solid var(--radical-yellow);border-radius:10px;font-size:14px"><strong>Grading Rec:</strong> '+res.grading_rec+'</div>':'')+
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
        showToast('✅ Card saved! ID: '+res.id);
        setTimeout(function(){window.location='/collection'},1500);
    }).catch(function(e){showToast('Error: '+e.message,'error')});
}

// Init
setMode('binder');
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
            conf = c["confidence_score"] or c["confidence"] or 0
            conf_class = "conf-high" if conf >= 75 else "conf-med" if conf >= 50 else "conf-low"
            val = c["estimated_value"] or 0
            tags = ""
            if c["is_rookie"]:
                tags += '<span class="tag tag-rc">RC</span>'
            if c["is_auto"]:
                tags += '<span class="tag tag-auto">Auto</span>'
            if c["parallel"] and c["parallel"] != "Base":
                tags += f'<span class="tag tag-parallel">{c["parallel"]}</span>'
            if c["is_numbered"] and c["numbering"]:
                tags += f'<span class="tag tag-numbered">{c["numbering"]}</span>'

            cards_html += f"""
            <a href="/card/{c['id']}" class="card-item">
                <div class="card-thumb">🃏</div>
                <div class="card-info">
                    <div class="card-player-name">{c['player_name']}</div>
                    <div class="card-set-info">{c['year']} {c['set_name']} #{c['card_number']}</div>
                    <div style="margin-bottom:8px">{tags}</div>
                    <div class="card-bottom">
                        <div class="card-value">${val:,.2f}</div>
                        <span class="card-confidence {conf_class}">{conf:.0f}%</span>
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
    conf = c.get("confidence_score") or c.get("confidence") or 0
    cc = "var(--slime-green)" if conf >= 75 else "var(--radical-yellow)" if conf >= 50 else "var(--turbo-orange)"

    tags = ""
    if c.get("is_rookie"):
        tags += '<span class="tag tag-rc">RC</span>'
    if c.get("is_auto"):
        tags += '<span class="tag tag-auto">Auto</span>'
    if c.get("is_patch"):
        tags += '<span class="tag tag-auto">Patch</span>'
    if c.get("parallel") and c.get("parallel") != "Base":
        tags += f'<span class="tag tag-parallel">{c["parallel"]}</span>'
    if c.get("is_numbered") and c.get("numbering"):
        tags += f'<span class="tag tag-numbered">{c["numbering"]}</span>'
    if c.get("is_ssp"):
        tags += f'<span class="tag tag-graded">SSP</span>'

    player = c.get("player_name") or "Unknown"

    content = f"""
    <a href="/collection" class="btn btn-ghost btn-sm" style="margin-bottom:20px">← Back to Collection</a>

    <div class="panel">
        <div class="detail-header">
            <div>
                <div style="font-family:'Lilita One',cursive;font-size:32px">{player}</div>
                <div style="color:var(--light-purple);font-size:14px;font-weight:600">{c.get('year','')} {c.get('set_name','')} #{c.get('card_number','')}</div>
                <div style="margin-top:4px;color:var(--light-purple);font-size:13px">{c.get('team','')} · {c.get('sport','').title()}</div>
                <div style="margin-top:12px">{tags}</div>
            </div>
            <div style="text-align:right">
                <div class="detail-value">${val:,.2f}</div>
                <div class="detail-range">${c.get('value_range_low') or 0:,.2f} – ${c.get('value_range_high') or 0:,.2f}</div>
            </div>
        </div>

        <div class="confidence-bar">
            <span style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px">Confidence</span>
            <div class="confidence-track"><div class="confidence-fill" style="width:{conf}%;background:{cc}"></div></div>
            <span class="confidence-val" style="color:{cc}">{conf:.0f}%</span>
        </div>

        {f'<div style="margin-top:16px;padding:12px 16px;background:rgba(255,232,24,.1);border:2px solid var(--radical-yellow);border-radius:10px;font-size:14px"><strong>Grading Rec:</strong> {c["grading_rec"]}</div>' if c.get("grading_rec") else ""}
        {f'<div style="margin-top:12px;padding:12px 16px;background:rgba(57,255,20,.08);border:2px solid rgba(57,255,20,.3);border-radius:10px;font-size:14px"><strong>AI Notes:</strong> {c["identification_notes"]}</div>' if c.get("identification_notes") else ""}
        {f'<div style="margin-top:12px;padding:12px 16px;background:rgba(0,191,255,.08);border:2px solid rgba(0,191,255,.3);border-radius:10px;font-size:13px;color:var(--light-purple)">📖 {c.get("booklet_name","")}, Page {c.get("page_number","?")} · Slot {c.get("slot_position","?")}</div>' if c.get("booklet_name") else ""}
    </div>

    <div style="display:flex;gap:12px;margin-top:16px;flex-wrap:wrap">
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

    return render(player, content, scripts, "collection")


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
