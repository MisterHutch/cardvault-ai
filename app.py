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
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>CardVault AI — %(title)s</title>
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#070B14">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="CardVault">
<link rel="apple-touch-icon" href="/static/icons/icon-180.png">
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div class="app-shell">
  <header class="app-header">
    <div class="app-logo">🃏</div>
    <div class="app-brand">Card<span>Vault</span> AI</div>
  </header>
  <nav class="app-nav">
    <a href="/" class="nav-item %(nav_scan)s">
      <span class="nav-icon">🔍</span>Scanner
    </a>
    <a href="/collection" class="nav-item %(nav_coll)s">
      <span class="nav-icon">📦</span>Collection
    </a>
    <a href="/booklets" class="nav-item %(nav_book)s">
      <span class="nav-icon">📖</span>Booklets
    </a>
    <a href="/portfolio" class="nav-item %(nav_port)s">
      <span class="nav-icon">📊</span>Portfolio
    </a>
    <a href="/settings" class="nav-item %(nav_set)s">
      <span class="nav-icon">⚙️</span>Settings
    </a>
  </nav>
  <main class="page-content">%(content)s</main>
  <div id="toast"></div>
  <footer class="app-footer">&copy; 2026 HutchGroup LLC &middot; CardVault AI</footer>
</div>
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
    html = html.replace("%(nav_port)s",  "active" if active == "portfolio"  else "")
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
    <div class="mode-pills">
        <button class="mode-pill active" id="modeBinder" onclick="setMode('binder')">📖 Binder Page (9 cards)</button>
        <button class="mode-pill" id="modeSingle" onclick="setMode('single')">🃏 Single Card</button>
    </div>

    <!-- Upload Zone with explicit buttons — most reliable on iOS Safari -->
    <div class="upload-zone" id="dropZone">
        <div class="upload-icon" id="uploadIcon">📖</div>
        <div class="upload-title" id="uploadTitle">Scan Binder Page</div>
        <div class="upload-sub" id="uploadSub">Choose how to add your photo</div>
        <div style="display:flex;gap:12px;justify-content:center;margin-top:20px;flex-wrap:wrap">
            <button type="button" class="btn btn-primary" id="btnCamera" onclick="openFileInput('camera')">📷 Take Photo</button>
            <button type="button" class="btn btn-ghost" id="btnLibrary" onclick="openFileInput('library')">🖼️ Library</button>
        </div>
    </div>
    <!-- File input lives outside any container — nothing to interfere with it -->
    <input type="file" id="fileInput" accept="image/*" style="opacity:0;position:fixed;top:-9999px;left:-9999px;width:1px;height:1px;font-size:16px">

    <!-- Batch Progress Panel -->
    <div id="batchProgress" style="display:none;margin-top:16px">
        <div class="panel">
            <div class="panel-title">⚡ Batch Scanning</div>
            <div id="batchStatus" style="color:var(--light-purple);font-size:14px;margin-bottom:12px"></div>
            <div class="confidence-track" style="height:14px;border-radius:8px">
                <div id="batchBar" class="confidence-fill" style="width:0%;background:var(--electric-purple);transition:width .4s ease"></div>
            </div>
            <div id="batchPageStatus" style="margin-top:16px;display:grid;gap:8px" ></div>
        </div>
        <div id="batchSavePanel" style="display:none">
            <div class="panel">
                <div class="panel-title">💾 Save Entire Batch</div>
                <div class="form-row" style="margin-bottom:16px">
                    <div class="form-group" style="margin:0">
                        <label class="form-label">Booklet / Binder Name</label>
                        <input class="form-input" id="batchBookletName" placeholder="e.g. My Prizm Binder">
                    </div>
                    <div class="form-group" style="margin:0">
                        <label class="form-label">Starting Page #</label>
                        <input class="form-input" id="batchStartPage" type="number" value="1" min="1">
                    </div>
                </div>
                <div id="batchSummary" style="color:var(--light-purple);font-size:14px;margin-bottom:16px"></div>
                <div style="display:flex;gap:12px;flex-wrap:wrap">
                    <button class="btn btn-primary" onclick="saveBatchAll()">💾 Save All Cards</button>
                    <button class="btn btn-ghost" onclick="resetScanner()">↩ Start Over</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Error display -->
    <div id="errorBox" style="display:none;margin-top:16px;padding:16px;background:rgba(255,68,68,.15);border:2px solid #FF4444;border-radius:12px;color:#FF4444;font-weight:600"></div>

    <!-- Debug console -->
    <div id="debugBox" style="margin-top:12px;background:#0D0628;border:2px solid rgba(123,47,255,.4);border-radius:12px;padding:12px;font-family:monospace;font-size:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <span style="color:var(--electric-purple);font-weight:700">🔍 Debug Log <span style="color:var(--light-purple);font-size:10px">v4.1</span></span>
            <button onclick="copyLog()" style="background:var(--electric-purple);color:white;border:none;border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer">📋 Copy</button>
        </div>
        <div id="debugLog" style="max-height:160px;overflow-y:auto;-webkit-overflow-scrolling:touch;user-select:text;-webkit-user-select:text"></div>
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
var batchFiles = [];
var batchResults = [];  // [{pageIndex, cards:[...identified]}]
var batchCurrent = 0;

// ── Mode selector ──────────────────────────────────────────────────────────
function setMode(mode) {
    currentMode = mode;
    var isBinder = mode === 'binder';
    document.getElementById('modeBinder').className = isBinder ? 'mode-pill active' : 'mode-pill';
    document.getElementById('modeSingle').className = isBinder ? 'mode-pill' : 'mode-pill active';
    document.getElementById('uploadIcon').textContent = isBinder ? '📖' : '🃏';
    document.getElementById('uploadTitle').textContent = isBinder ? 'Scan Binder Page' : 'Scan a Card';
    document.getElementById('uploadSub').textContent = isBinder ? 'Take a photo or pick from library' : 'Take a photo or pick from library';
    document.getElementById('binderInfo').style.display = isBinder ? 'block' : 'none';
    resetScanner();
}

// ── File input — use addEventListener (more reliable than onchange on iOS) ──
var fileInput = document.getElementById('fileInput');
function onFileSelected() {
    dbg('onFileSelected fired. files=' + (fileInput.files ? fileInput.files.length : 'null'));
    if (!fileInput.files || !fileInput.files.length) { dbg('No files — returning'); return; }
    document.getElementById('uploadTitle').textContent = '⏳ Loading…';
    document.getElementById('uploadSub').textContent = fileInput.files.length + ' photo(s) selected';
    if (currentMode === 'binder' && fileInput.files.length > 1) {
        dbg('Batch mode: ' + fileInput.files.length + ' files');
        startBatch(Array.from(fileInput.files));
    } else {
        dbg('Single file: ' + fileInput.files[0].name + ' (' + fileInput.files[0].size + ' bytes)');
        processFile(fileInput.files[0]);
    }
}
fileInput.addEventListener('change', onFileSelected);
fileInput.addEventListener('input',  onFileSelected); // iOS Safari fallback

// ── Drag & drop (desktop) ──────────────────────────────────────────────────
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

function openFileInput(mode) {
    dbg('openFileInput: mode=' + mode);
    // Remove any previous attributes
    fileInput.removeAttribute('capture');
    fileInput.removeAttribute('multiple');
    if (mode === 'camera') {
        fileInput.setAttribute('capture', 'environment');
    }
    if (currentMode === 'binder' && mode === 'library') {
        fileInput.multiple = true;
    }
    fileInput.click();
    dbg('fileInput.click() called');
}
function copyLog() {
    var text = document.getElementById('debugLog').innerText;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function(){ showToast('Log copied!'); });
    } else {
        prompt('Copy this log:', text);
    }
}
function dbg(msg) {
    var log = document.getElementById('debugLog');
    if (!log) return;
    var ts = new Date().toISOString().substr(11,8);
    var line = document.createElement('div');
    line.style.color = '#E8DEFF';
    line.style.borderBottom = '1px solid rgba(123,47,255,.15)';
    line.style.paddingBottom = '3px';
    line.style.marginBottom = '3px';
    line.textContent = ts + ' ' + msg;
    log.appendChild(line);
    log.parentElement.scrollTop = log.parentElement.scrollHeight;
}
function showError(msg) {
    dbg('ERROR: ' + msg);
    var box = document.getElementById('errorBox');
    box.textContent = '❌ ' + msg;
    box.style.display = 'block';
    setTimeout(function(){ box.style.display = 'none'; }, 8000);
}

function processFile(file) {
    dbg('processFile: reading file...');
    currentFile = file;
    document.getElementById('errorBox').style.display = 'none';
    var r = new FileReader();
    r.onerror = function() { showError('Could not read the photo. Try again.'); };
    r.onload = function(e) {
        dbg('FileReader done. Mode=' + currentMode);
        if (currentMode === 'binder') {
            document.getElementById('binderPreview').src = e.target.result;
            document.getElementById('binderResults').style.display = 'block';
            document.getElementById('cardGrid').style.display = 'none';
            dz.style.display = 'none';
            document.getElementById('binderInfo').style.display = 'block';
            dbg('Calling detectCards in 300ms...');
            setTimeout(function(){ detectCards(true); }, 300);
        } else {
            document.getElementById('singlePreview').src = e.target.result;
            document.getElementById('singleResults').style.display = 'block';
            dz.style.display = 'none';
            dbg('Single mode ready — waiting for user input');
        }
    };
    r.readAsDataURL(file);
}

function resetScanner() {
    currentFile = null; detectedCards = []; identifiedCards = [];
    batchFiles = []; batchResults = []; batchCurrent = 0;
    dz.style.display = 'block';
    fileInput.value = '';
    document.getElementById('binderResults').style.display = 'none';
    document.getElementById('singleResults').style.display = 'none';
    document.getElementById('cardGrid').style.display = 'none';
    document.getElementById('saveBatchPanel').style.display = 'none';
    document.getElementById('batchProgress').style.display = 'none';
    document.getElementById('cardGridInner').innerHTML = '';
    document.getElementById('detectStatus').textContent = '';
    document.getElementById('estimatePanel').style.display = 'none';
    if (currentMode === 'binder') document.getElementById('binderInfo').style.display = 'block';
}

// ── BINDER: Detect cards ───────────────────────────────────────────────────
function detectCards(autoIdentify) {
    if (!currentFile) { dbg('detectCards: no currentFile!'); showToast('No image loaded', 'error'); return; }
    dbg('detectCards: calling /api/detect...');
    var btn = document.getElementById('detectBtn');
    var status = document.getElementById('detectStatus');
    btn.disabled = true; btn.textContent = '⏳ Detecting…';
    status.textContent = '🔍 Detecting cards…';
    document.getElementById('cardGrid').style.display = 'none';

    var fd = new FormData();
    fd.append('image', currentFile);

    fetch('/api/detect', {method:'POST', body:fd})
    .then(function(r){return r.json()})
    .then(function(res) {
        btn.disabled = false; btn.textContent = '🔍 Detect Cards';
        dbg('detect response: ' + JSON.stringify(res).substr(0,120));
        if (res.error && (!res.cards || res.cards.length === 0)) {
            showError(res.error);
            status.textContent = '❌ ' + res.error;
            return;
        }
        detectedCards = res.cards || [];
        status.textContent = '✅ Found ' + detectedCards.length + ' card' + (detectedCards.length !== 1 ? 's' : '');
        document.getElementById('cardCount').textContent = '(' + detectedCards.length + ' found)';
        renderCardGrid(detectedCards);
        document.getElementById('cardGrid').style.display = 'block';
        if (autoIdentify && detectedCards.length > 0) {
            status.textContent = '✅ Found ' + detectedCards.length + ' cards — identifying…';
            setTimeout(function(){ identifyAll(true); }, 500);
        } else {
            showToast('Found ' + detectedCards.length + ' cards — tap AI Identify All!');
        }
    })
    .catch(function(e) {
        btn.disabled = false; btn.textContent = '🔍 Detect Cards';
        showError('Detection failed: ' + e.message);
    });
}

function renderCardGrid(cards) {
    var grid = document.getElementById('cardGridInner');
    grid.innerHTML = '';
    cards.forEach(function(card, i) {
        var pos = 'Row ' + (card.row+1) + ', Col ' + (card.col+1);
        var conf = Math.round((card.confidence||0)*100);
        grid.innerHTML += '<div class="card-detect-cell" id="cell-'+i+'" data-idx="'+i+'">' +
            '<img src="/processed/' + card.filename + '" style="width:100%;border-radius:8px;display:block">' +
            '<div style="padding:8px">' +
            '<div style="font-size:11px;color:var(--light-purple);font-weight:700;text-transform:uppercase">' + pos + ' · ' + conf + '% conf</div>' +
            '<div id="card-label-'+i+'" style="font-size:12px;color:var(--off-white);margin-top:4px">Pending AI ID…</div>' +
            '</div></div>';
    });
}

// ── BINDER: Identify all ──────────────────────────────────────────────────
function identifyAll(auto) {
    if (!detectedCards.length) { showToast('Detect cards first', 'error'); return; }
    var btn = document.getElementById('identifyBtn');
    btn.disabled = true; btn.textContent = '⏳ Identifying…';
    if (!auto) showToast('Claude Vision is reading ' + detectedCards.length + ' cards…');

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

// ── BATCH: Process multiple binder pages ──────────────────────────────────
function startBatch(files) {
    batchFiles = files;
    batchResults = [];
    batchCurrent = 0;
    dz.style.display = 'none';
    document.getElementById('binderResults').style.display = 'none';
    document.getElementById('batchProgress').style.display = 'block';
    document.getElementById('batchSavePanel').style.display = 'none';
    // Build page status list
    var ps = document.getElementById('batchPageStatus');
    ps.innerHTML = '';
    files.forEach(function(f, i) {
        ps.innerHTML += '<div id="bpage-'+i+'" style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:rgba(123,47,255,.08);border-radius:8px">' +
            '<span id="bpage-icon-'+i+'">⏳</span>' +
            '<span style="flex:1;font-size:13px;color:var(--light-purple)">Page ' + (i+1) + ' — ' + f.name + '</span>' +
            '<span id="bpage-count-'+i+'" style="font-size:12px;font-weight:700;color:var(--slime-green)"></span>' +
            '</div>';
    });
    processBatchPage();
}

function processBatchPage() {
    if (batchCurrent >= batchFiles.length) {
        finishBatch(); return;
    }
    var i = batchCurrent;
    var pct = Math.round((i / batchFiles.length) * 100);
    document.getElementById('batchBar').style.width = pct + '%';
    document.getElementById('batchStatus').textContent = 'Processing page ' + (i+1) + ' of ' + batchFiles.length + '…';
    document.getElementById('bpage-icon-'+i).textContent = '🔍';

    var fd = new FormData();
    fd.append('image', batchFiles[i]);
    fetch('/api/detect', {method:'POST', body:fd})
    .then(function(r){return r.json()})
    .then(function(res) {
        var cards = res.cards || [];
        document.getElementById('bpage-icon-'+i).textContent = '🤖';
        document.getElementById('bpage-count-'+i).textContent = cards.length + ' cards found';
        if (cards.length === 0) {
            document.getElementById('bpage-icon-'+i).textContent = '⚠️';
            batchResults.push({pageIndex: i, cards: []});
            batchCurrent++; processBatchPage(); return;
        }
        // Identify cards on this page
        return fetch('/api/identify-batch', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({cards: cards})
        }).then(function(r){return r.json()})
        .then(function(idRes) {
            var identified = idRes.results || cards;
            // Log any errors to debug panel
            if (idRes.errors && idRes.errors.length) {
                dbg('identify errors: ' + idRes.errors.slice(0,2).join(' | '));
            }
            document.getElementById('bpage-icon-'+i).textContent = '✅';
            var names = identified.slice(0,3).map(function(c){
                return (c.player_name && c.player_name !== 'Unknown') ? c.player_name : (c.error ? '⚠️'+c.error.substr(0,30) : '?');
            }).filter(Boolean).join(', ');
            document.getElementById('bpage-count-'+i).textContent = identified.length + ' cards — ' + names + (identified.length > 3 ? '…' : '');
            batchResults.push({pageIndex: i, cards: identified});
            batchCurrent++;
            processBatchPage();
        });
    })
    .catch(function(e) {
        document.getElementById('bpage-icon-'+i).textContent = '❌';
        batchResults.push({pageIndex: i, cards: []});
        batchCurrent++; processBatchPage();
    });
}

function finishBatch() {
    document.getElementById('batchBar').style.width = '100%';
    var totalCards = batchResults.reduce(function(s,p){return s+p.cards.length;},0);
    document.getElementById('batchStatus').textContent = '✅ All ' + batchFiles.length + ' pages scanned!';
    document.getElementById('batchSummary').textContent =
        totalCards + ' cards identified across ' + batchFiles.length + ' pages. Set a booklet name and save.';
    document.getElementById('batchSavePanel').style.display = 'block';
    showToast('Done! ' + totalCards + ' cards ready to save.');
}

function saveBatchAll() {
    var booklet = document.getElementById('batchBookletName').value || 'My Collection';
    var startPage = parseInt(document.getElementById('batchStartPage').value) || 1;
    var saves = batchResults.map(function(p, idx) {
        return fetch('/api/save-batch', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({cards: p.cards, booklet_name: booklet, page_number: startPage + p.pageIndex})
        }).then(function(r){return r.json();});
    });
    Promise.all(saves).then(function(results) {
        var total = results.reduce(function(s,r){return s+(r.count||0);},0);
        showToast('✅ Saved ' + total + ' cards to "' + booklet + '"!');
        setTimeout(function(){window.location='/collection';}, 1500);
    }).catch(function(e){ showToast('Save failed: '+e.message,'error'); });
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
dbg('Scanner JS loaded. Setting binder mode...');
setMode('binder');
dbg('Ready. fileInput=' + (fileInput ? 'found' : 'MISSING'));
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


@app.route("/portfolio")
def portfolio_page():
    conn = get_db()

    # Core stats
    total_value  = conn.execute("SELECT COALESCE(SUM(estimated_value),0) FROM cards").fetchone()[0]
    total_cards  = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    rc_count     = conn.execute("SELECT COUNT(*) FROM cards WHERE is_rookie=1").fetchone()[0]
    auto_count   = conn.execute("SELECT COUNT(*) FROM cards WHERE is_auto=1").fetchone()[0]
    numbered_count = conn.execute("SELECT COUNT(*) FROM cards WHERE is_numbered=1").fetchone()[0]
    avg_value    = (total_value / total_cards) if total_cards else 0

    # Top 10 cards by value
    top10 = conn.execute(
        "SELECT player_name, year, set_name, parallel, estimated_value, is_rookie, is_auto, is_numbered, numbering "
        "FROM cards ORDER BY estimated_value DESC LIMIT 10"
    ).fetchall()

    # Sport breakdown
    sports = conn.execute(
        "SELECT sport, COUNT(*) as cnt, COALESCE(SUM(estimated_value),0) as val "
        "FROM cards GROUP BY sport ORDER BY val DESC"
    ).fetchall()

    # Brand breakdown
    brands = conn.execute(
        "SELECT brand, COUNT(*) as cnt, COALESCE(SUM(estimated_value),0) as val "
        "FROM cards GROUP BY brand ORDER BY val DESC LIMIT 8"
    ).fetchall()

    # Grading candidates (raw value > $50)
    grade_candidates = conn.execute(
        "SELECT player_name, year, set_name, parallel, estimated_value, is_rookie "
        "FROM cards WHERE estimated_value > 50 AND (grading_company IS NULL OR grading_company = '') "
        "ORDER BY estimated_value DESC LIMIT 20"
    ).fetchall()

    # Booklet value summary
    booklets = conn.execute(
        "SELECT booklet_name, COUNT(*) as cnt, COALESCE(SUM(estimated_value),0) as val "
        "FROM cards WHERE booklet_name IS NOT NULL AND booklet_name != '' "
        "GROUP BY booklet_name ORDER BY val DESC LIMIT 10"
    ).fetchall()

    conn.close()

    # Build chart data JSON strings
    import json
    sports_labels = json.dumps([s["sport"] or "Unknown" for s in sports])
    sports_values = json.dumps([round(s["val"], 2) for s in sports])
    sports_counts = json.dumps([s["cnt"] for s in sports])
    brand_labels  = json.dumps([b["brand"] or "Unknown" for b in brands])
    brand_values  = json.dumps([round(b["val"], 2) for b in brands])

    # Top-10 HTML rows
    top10_rows = ""
    for i, c in enumerate(top10, 1):
        tags = ""
        if c["is_rookie"]:  tags += '<span class="tag tag-rc">RC</span>'
        if c["is_auto"]:    tags += '<span class="tag tag-auto">Auto</span>'
        if c["is_numbered"] and c["numbering"]: tags += f'<span class="tag tag-numbered">{c["numbering"]}</span>'
        if c["parallel"] and c["parallel"] != "Base": tags += f'<span class="tag tag-parallel">{c["parallel"]}</span>'
        pct = round((c["estimated_value"] / top10[0]["estimated_value"]) * 100) if top10 and top10[0]["estimated_value"] else 0
        top10_rows += f"""
        <div class="port-rank-row">
          <div class="rank-num">#{i}</div>
          <div class="rank-info">
            <div class="rank-player">{c["player_name"]}</div>
            <div class="rank-set">{c["year"]} {c["set_name"]}</div>
            <div style="margin-top:6px">{tags}</div>
          </div>
          <div class="rank-right">
            <div class="rank-value">${c["estimated_value"]:,.0f}</div>
            <div class="rank-bar-wrap"><div class="rank-bar" style="width:{pct}%"></div></div>
          </div>
        </div>"""

    # Grading candidates HTML
    grade_rows = ""
    if grade_candidates:
        for c in grade_candidates:
            grade_rows += f"""
            <div class="grade-row">
              <div class="grade-info">
                <div class="grade-player">{c["player_name"]}</div>
                <div class="grade-set">{c["year"]} {c["set_name"]} — {c["parallel"]}</div>
              </div>
              <div class="grade-value">${c["estimated_value"]:,.0f}</div>
              <div class="grade-rec">{'🔑 PSA it' if c["estimated_value"] > 200 else '⚡ Consider grading'}</div>
            </div>"""
    else:
        grade_rows = '<p style="color:var(--muted);font-size:14px;text-align:center;padding:20px">No cards over $50 yet — keep scanning.</p>'

    # Booklets HTML
    booklet_rows = ""
    if booklets:
        for b in booklets:
            booklet_rows += f"""
            <div class="booklet-row">
              <div>
                <div style="font-weight:600;font-size:14px">📖 {b["booklet_name"]}</div>
                <div style="color:var(--muted);font-size:12px;margin-top:2px">{b["cnt"]} cards</div>
              </div>
              <div style="font-size:1.1rem;font-weight:700;color:var(--slime-green)">${b["val"]:,.0f}</div>
            </div>"""
    else:
        booklet_rows = '<p style="color:var(--muted);font-size:14px;text-align:center;padding:20px">No booklets yet.</p>'

    empty_state = ""
    if total_cards == 0:
        empty_state = """
        <div style="text-align:center;padding:60px 20px;color:var(--muted)">
          <div style="font-size:3rem;margin-bottom:16px">📊</div>
          <div style="font-size:1.1rem;font-weight:600;margin-bottom:8px;color:var(--text)">Portfolio is empty</div>
          <p style="font-size:14px">Scan some cards to see your portfolio dashboard.</p>
          <a href="/" class="btn btn-primary" style="margin-top:20px;display:inline-block">📸 Start Scanning</a>
        </div>"""

    content = f"""
    <h1 class="page-title">Portfolio Dashboard</h1>
    <p class="page-sub">Your collection at a glance — value, highlights, and what to grade.</p>

    {empty_state}

    <!-- KPI Row -->
    <div class="port-kpi-row">
      <div class="port-kpi">
        <div class="port-kpi-label">Total Value</div>
        <div class="port-kpi-value" style="color:var(--slime-green)">${total_value:,.2f}</div>
      </div>
      <div class="port-kpi">
        <div class="port-kpi-label">Cards</div>
        <div class="port-kpi-value">{total_cards:,}</div>
      </div>
      <div class="port-kpi">
        <div class="port-kpi-label">Avg Value</div>
        <div class="port-kpi-value">${avg_value:,.2f}</div>
      </div>
      <div class="port-kpi">
        <div class="port-kpi-label">Rookies</div>
        <div class="port-kpi-value" style="color:var(--turbo-orange)">{rc_count}</div>
      </div>
      <div class="port-kpi">
        <div class="port-kpi-label">Autos</div>
        <div class="port-kpi-value" style="color:var(--electric-purple)">{auto_count}</div>
      </div>
      <div class="port-kpi">
        <div class="port-kpi-label">Numbered</div>
        <div class="port-kpi-value" style="color:var(--radical-yellow)">{numbered_count}</div>
      </div>
    </div>

    <!-- Charts row -->
    <div class="port-charts-row">
      <div class="panel">
        <div class="panel-title">💰 Value by Sport</div>
        <canvas id="chartSport" height="220"></canvas>
      </div>
      <div class="panel">
        <div class="panel-title">🏷️ Value by Brand</div>
        <canvas id="chartBrand" height="220"></canvas>
      </div>
    </div>

    <!-- Top 10 -->
    <div class="panel">
      <div class="panel-title">🏆 Top 10 Cards by Value</div>
      <div class="port-rank-list">
        {top10_rows if top10_rows else '<p style="color:var(--muted);font-size:14px;padding:20px;text-align:center">No cards yet.</p>'}
      </div>
    </div>

    <!-- Grading candidates -->
    <div class="panel">
      <div class="panel-title">🎯 Grading Candidates <span style="font-size:13px;color:var(--muted);font-weight:400">(raw value &gt; $50)</span></div>
      <div class="grade-list">{grade_rows}</div>
    </div>

    <!-- Booklets -->
    <div class="panel">
      <div class="panel-title">📖 Booklets by Value</div>
      <div class="booklet-list">{booklet_rows}</div>
    </div>
    """

    scripts = f"""
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script>
    Chart.defaults.color = 'rgba(255,255,255,0.5)';
    Chart.defaults.borderColor = 'rgba(255,255,255,0.08)';
    const PURPLE = '#7B2FFF';
    const GOLD   = '#F5C842';
    const GREEN  = '#39FF6A';
    const ORANGE = '#FF6B35';
    const COLORS = [PURPLE, GOLD, GREEN, ORANGE, '#FF4D9E', '#00D4FF', '#FF8C42', '#A855F7'];

    // Sport chart
    var sportCtx = document.getElementById('chartSport');
    if(sportCtx) {{
      new Chart(sportCtx, {{
        type: 'doughnut',
        data: {{
          labels: {sports_labels},
          datasets: [{{ data: {sports_values}, backgroundColor: COLORS, borderWidth: 2, borderColor: '#070B14' }}]
        }},
        options: {{
          responsive: true,
          plugins: {{
            legend: {{ position: 'bottom', labels: {{ padding: 16, font: {{ size: 12 }} }} }},
            tooltip: {{ callbacks: {{ label: function(c) {{ return ' $' + c.parsed.toLocaleString(); }} }} }}
          }}
        }}
      }});
    }}

    // Brand chart
    var brandCtx = document.getElementById('chartBrand');
    if(brandCtx) {{
      new Chart(brandCtx, {{
        type: 'bar',
        data: {{
          labels: {brand_labels},
          datasets: [{{
            label: 'Value ($)',
            data: {brand_values},
            backgroundColor: PURPLE,
            borderRadius: 6,
            borderSkipped: false
          }}]
        }},
        options: {{
          responsive: true,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            y: {{ ticks: {{ callback: function(v) {{ return '$' + v.toLocaleString(); }} }} }},
            x: {{ ticks: {{ font: {{ size: 11 }} }} }}
          }}
        }}
      }});
    }}
    </script>
    """

    return render("Portfolio", content, scripts=scripts, active="portfolio")


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


@app.route("/booklets")
def booklets_page():
    booklets = db.list_booklets()
    conn = get_db()

    if not booklets:
        content = """
        <h1 class="page-title">Booklets</h1>
        <p class="page-sub">Your physical binders, organized by page.</p>
        <div class="empty-state">
            <div class="empty-icon">📖</div>
            <div class="empty-title">No Booklets Yet</div>
            <p>Scan a binder page and assign it a booklet name to get started.</p>
            <a href="/" class="btn btn-primary" style="margin-top:16px">📸 Start Scanning</a>
        </div>"""
    else:
        cards_html = '<div class="card-grid">'
        for b in booklets:
            row = conn.execute(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(estimated_value),0) as val FROM cards WHERE booklet_id=?",
                (b.id,)
            ).fetchone()
            count = row["cnt"] if row else 0
            total = row["val"] if row else 0.0

            # Sample up to 3 card names for preview
            sample = conn.execute(
                "SELECT player_name FROM cards WHERE booklet_id=? LIMIT 3", (b.id,)
            ).fetchall()
            preview = ", ".join(r["player_name"] for r in sample if r["player_name"] and r["player_name"] != "Unknown")
            if not preview:
                preview = "No cards identified yet"

            cards_html += f"""
            <a href="/collection?booklet={b.id}" class="card-item">
                <div class="card-thumb" style="font-size:40px">📖</div>
                <div class="card-info">
                    <div class="card-player-name">{b.name or 'Unnamed Booklet'}</div>
                    <div class="card-set-info" style="margin-bottom:8px">{b.sport.title() if b.sport else 'Mixed'} · {count} card{'s' if count != 1 else ''}</div>
                    <div style="font-size:12px;color:var(--light-purple);margin-bottom:12px">{preview}</div>
                    <div class="card-bottom">
                        <div class="card-value">${total:,.2f}</div>
                        <span style="font-size:11px;color:var(--light-purple);font-weight:700">{b.total_pages or '?'} pages</span>
                    </div>
                </div>
            </a>"""
        cards_html += "</div>"

        total_cards = sum(1 for _ in conn.execute("SELECT id FROM cards WHERE booklet_id IS NOT NULL").fetchall())
        content = f"""
        <h1 class="page-title">Booklets</h1>
        <p class="page-sub">Your physical binders, organized by page.</p>
        <div class="stats-bar">
            <div class="stat-card"><div class="stat-number">{len(booklets)}</div><div class="stat-label">Booklets</div></div>
            <div class="stat-card"><div class="stat-number">{total_cards}</div><div class="stat-label">Cards Tracked</div></div>
        </div>
        {cards_html}"""

    conn.close()
    return render("Booklets", content, active="booklets")


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

@app.route("/api/debug-identify", methods=["POST"])
def api_debug_identify():
    """Debug: returns raw Claude response to diagnose identify failures."""
    import anthropic, base64 as b64mod
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    if not api_key:
        return jsonify({"error": "No ANTHROPIC_API_KEY set"})
    if "image" not in request.files:
        return jsonify({"error": "No image"})
    f = request.files["image"]
    img_bytes = f.read()
    img_b64 = b64mod.standard_b64encode(img_bytes).decode()
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role":"user","content":[
                {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":img_b64}},
                {"type":"text","text":"What player is on this sports card? Reply in one sentence."}
            ]}]
        )
        raw = resp.content[0].text
        return jsonify({"raw": raw, "model": "claude-sonnet-4-20250514", "img_size": len(img_bytes)})
    except Exception as e:
        return jsonify({"error": str(e), "type": type(e).__name__})

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
        if not filepath.exists():
            results.append({
                "player_name": "Unknown", "error": f"File not found: {card_info['filename']}",
                "filename": card_info["filename"], "row": card_info.get("row",0), "col": card_info.get("col",0)
            })
            continue
        try:
            ident = identifier.identify_card(str(filepath))
            result = ident.to_dict()
            result["filename"] = card_info["filename"]
            result["row"] = card_info.get("row", 0)
            result["col"] = card_info.get("col", 0)
            results.append(result)
        except Exception as e:
            results.append({
                "player_name": "Unknown", "error": str(e),
                "filename": card_info["filename"], "row": card_info.get("row",0), "col": card_info.get("col",0)
            })
    return jsonify({"results": results, "errors": [r["error"] for r in results if "error" in r]})


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
