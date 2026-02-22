"""
Sports Card Collection Database - Enhanced Version
SQLite-based storage with booklet/binder location tracking.

Author: HutchGroup LLC
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
import json


@dataclass
class Booklet:
    """Represents a physical booklet/binder in the collection."""
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    sport: str = ""  # Can pre-set sport for all cards in booklet
    total_pages: int = 0
    created_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "sport": self.sport,
            "total_pages": self.total_pages,
            "created_at": self.created_at
        }


@dataclass
class PageScan:
    """Represents a scanned page from a booklet."""
    id: Optional[int] = None
    booklet_id: int = 0
    booklet_name: str = ""  # Denormalized for easy display
    page_number: int = 0
    original_image_path: str = ""
    scan_date: str = ""
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "booklet_id": self.booklet_id,
            "booklet_name": self.booklet_name,
            "page_number": self.page_number,
            "original_image_path": self.original_image_path,
            "scan_date": self.scan_date,
            "notes": self.notes
        }


@dataclass
class Card:
    """Represents a card in the collection with full location tracking."""
    id: Optional[int] = None
    
    # Card Identity
    player_name: str = ""
    team: str = ""
    year: str = ""
    sport: str = ""
    position: str = ""
    
    # Card Details
    brand: str = ""  # Panini, Topps, etc.
    set_name: str = ""  # Prizm, Mosaic, Select, etc.
    subset: str = ""  # Base, Insert name, etc.
    card_number: str = ""
    parallel: str = "Base"  # Silver, Gold, Red, etc.
    
    # Special Attributes (KEY REQUIREMENTS)
    is_rookie: bool = False
    is_auto: bool = False
    is_patch: bool = False
    is_memorabilia: bool = False
    is_numbered: bool = False
    numbering: str = ""  # e.g., "/99", "/25"
    is_ssp: bool = False  # Short Print
    ssp_type: str = ""  # Case hit, low serial, specific parallel
    
    # AI Identification
    confidence: float = 0.0
    identification_notes: str = ""
    
    # Physical Location (KEY REQUIREMENT)
    booklet_id: Optional[int] = None
    booklet_name: str = ""
    page_id: Optional[int] = None
    page_number: int = 0
    slot_position: int = 0  # 1-9 for 3x3 grid
    slot_row: int = 0  # 0-2
    slot_col: int = 0  # 0-2
    
    # Image
    image_path: str = ""
    
    # Optional tracking
    condition: str = ""
    estimated_value: float = 0.0
    purchase_price: float = 0.0
    purchase_date: str = ""
    notes: str = ""
    
    # Value engine fields (added by migration)
    confidence_score: float = 0.0
    value_range_low: float = 0.0
    value_range_high: float = 0.0
    market_trend: str = ""
    grading_rec: str = ""
    grading_company: str = ""
    grade_value: Optional[float] = None
    graded: int = 0
    
    # Metadata
    created_at: str = ""
    updated_at: str = ""
    
    def get_location_string(self) -> str:
        """Get human-readable location string."""
        if self.booklet_name and self.page_number:
            return f"{self.booklet_name}, Page {self.page_number}, Slot {self.slot_position}"
        return "Location not set"
    
    def get_slot_description(self) -> str:
        """Get slot position as readable description."""
        row_names = ["Top", "Middle", "Bottom"]
        col_names = ["Left", "Center", "Right"]
        if 0 <= self.slot_row <= 2 and 0 <= self.slot_col <= 2:
            return f"{row_names[self.slot_row]} {col_names[self.slot_col]}"
        return f"Slot {self.slot_position}"
    
    def get_special_attributes(self) -> List[str]:
        """Get list of special attributes for display."""
        attrs = []
        if self.is_rookie:
            attrs.append("RC")
        if self.is_auto:
            attrs.append("AUTO")
        if self.is_patch:
            attrs.append("PATCH")
        if self.is_memorabilia and not self.is_patch:
            attrs.append("MEMO")
        if self.is_numbered and self.numbering:
            attrs.append(self.numbering)
        if self.is_ssp:
            attrs.append(f"SSP{': ' + self.ssp_type if self.ssp_type else ''}")
        return attrs
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "player_name": self.player_name,
            "team": self.team,
            "year": self.year,
            "sport": self.sport,
            "position": self.position,
            "brand": self.brand,
            "set_name": self.set_name,
            "subset": self.subset,
            "card_number": self.card_number,
            "parallel": self.parallel,
            "is_rookie": self.is_rookie,
            "is_auto": self.is_auto,
            "is_patch": self.is_patch,
            "is_memorabilia": self.is_memorabilia,
            "is_numbered": self.is_numbered,
            "numbering": self.numbering,
            "is_ssp": self.is_ssp,
            "ssp_type": self.ssp_type,
            "confidence": self.confidence,
            "identification_notes": self.identification_notes,
            "booklet_id": self.booklet_id,
            "booklet_name": self.booklet_name,
            "page_id": self.page_id,
            "page_number": self.page_number,
            "slot_position": self.slot_position,
            "slot_row": self.slot_row,
            "slot_col": self.slot_col,
            "location": self.get_location_string(),
            "slot_description": self.get_slot_description(),
            "special_attributes": self.get_special_attributes(),
            "image_path": self.image_path,
            "condition": self.condition,
            "estimated_value": self.estimated_value,
            "purchase_price": self.purchase_price,
            "purchase_date": self.purchase_date,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    def summary(self) -> str:
        """Generate a human-readable summary line."""
        parts = []
        if self.year:
            parts.append(self.year)
        if self.brand:
            parts.append(self.brand)
        if self.set_name:
            parts.append(self.set_name)
        if self.parallel and self.parallel != "Base":
            parts.append(self.parallel)
        if self.player_name:
            parts.append(self.player_name)
        
        attrs = self.get_special_attributes()
        if attrs:
            parts.append(f"({', '.join(attrs)})")
        
        return " ".join(parts) if parts else "Unknown Card"


class CardDatabase:
    """
    Enhanced SQLite database manager with booklet tracking.
    """
    
    def __init__(self, db_path: str = "card_collection.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Booklets table - physical binders/booklets
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS booklets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                sport TEXT,
                total_pages INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Page scans table - each scanned page
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS page_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booklet_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                original_image_path TEXT,
                scan_date TEXT DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (booklet_id) REFERENCES booklets(id),
                UNIQUE(booklet_id, page_number)
            )
        """)
        
        # Cards table - enhanced with location tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Card Identity
                player_name TEXT NOT NULL,
                team TEXT,
                year TEXT,
                sport TEXT,
                position TEXT,
                
                -- Card Details
                brand TEXT,
                set_name TEXT,
                subset TEXT,
                card_number TEXT,
                parallel TEXT DEFAULT 'Base',
                
                -- Special Attributes
                is_rookie BOOLEAN DEFAULT 0,
                is_auto BOOLEAN DEFAULT 0,
                is_patch BOOLEAN DEFAULT 0,
                is_memorabilia BOOLEAN DEFAULT 0,
                is_numbered BOOLEAN DEFAULT 0,
                numbering TEXT,
                is_ssp BOOLEAN DEFAULT 0,
                ssp_type TEXT,
                
                -- AI Identification
                confidence REAL DEFAULT 0,
                identification_notes TEXT,
                
                -- Physical Location
                booklet_id INTEGER,
                booklet_name TEXT,
                page_id INTEGER,
                page_number INTEGER,
                slot_position INTEGER,
                slot_row INTEGER,
                slot_col INTEGER,
                
                -- Image
                image_path TEXT,
                
                -- Optional tracking
                condition TEXT,
                estimated_value REAL DEFAULT 0,
                purchase_price REAL DEFAULT 0,
                purchase_date TEXT,
                notes TEXT,
                
                -- Metadata
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (booklet_id) REFERENCES booklets(id),
                FOREIGN KEY (page_id) REFERENCES page_scans(id)
            )
        """)
        
        # Create indexes for common searches
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_player ON cards(player_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_team ON cards(team)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_year ON cards(year)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_set ON cards(set_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_sport ON cards(sport)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_rookie ON cards(is_rookie)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_auto ON cards(is_auto)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_patch ON cards(is_patch)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_ssp ON cards(is_ssp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_booklet ON cards(booklet_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cards_booklet_name ON cards(booklet_name)")
        
        # === MIGRATION: Value engine columns (safe — only adds if missing) ===
        # These columns support the v3.0 value engine integration
        _new_cols = [
            ("confidence_score", "REAL"),
            ("value_range_low", "REAL"),
            ("value_range_high", "REAL"),
            ("market_trend", "TEXT"),
            ("grading_rec", "TEXT"),
            ("grading_company", "TEXT"),
            ("grade_value", "REAL"),
            ("graded", "INTEGER DEFAULT 0"),
        ]
        existing = {row[1] for row in cursor.execute("PRAGMA table_info(cards)").fetchall()}
        for col_name, col_type in _new_cols:
            if col_name not in existing:
                cursor.execute(f"ALTER TABLE cards ADD COLUMN {col_name} {col_type}")
        
        # Value history table — tracks re-valuations over time
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS value_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER,
                estimated_value REAL,
                confidence_score REAL,
                recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (card_id) REFERENCES cards(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    # ==================== BOOKLET OPERATIONS ====================
    
    def create_booklet(self, name: str, description: str = "", sport: str = "") -> int:
        """Create a new booklet/binder."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO booklets (name, description, sport)
                VALUES (?, ?, ?)
            """, (name, description, sport))
            booklet_id = cursor.lastrowid
            conn.commit()
            return booklet_id
        except sqlite3.IntegrityError:
            # Booklet already exists, return existing ID
            cursor.execute("SELECT id FROM booklets WHERE name = ?", (name,))
            return cursor.fetchone()[0]
        finally:
            conn.close()
    
    def get_booklet(self, booklet_id: int) -> Optional[Booklet]:
        """Get a booklet by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM booklets WHERE id = ?", (booklet_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return Booklet(**dict(row))
        return None
    
    def get_booklet_by_name(self, name: str) -> Optional[Booklet]:
        """Get a booklet by name."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM booklets WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return Booklet(**dict(row))
        return None
    
    def get_or_create_booklet(self, name: str, description: str = "", sport: str = "") -> Tuple[int, bool]:
        """Get existing booklet or create new one. Returns (id, was_created)."""
        existing = self.get_booklet_by_name(name)
        if existing:
            return existing.id, False
        return self.create_booklet(name, description, sport), True
    
    def list_booklets(self) -> List[Booklet]:
        """List all booklets."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT b.*, 
                   (SELECT COUNT(*) FROM cards WHERE booklet_id = b.id) as card_count,
                   (SELECT MAX(page_number) FROM page_scans WHERE booklet_id = b.id) as max_page
            FROM booklets b
            ORDER BY b.name
        """)
        
        booklets = []
        for row in cursor.fetchall():
            b = Booklet(**{k: row[k] for k in ['id', 'name', 'description', 'sport', 'total_pages', 'created_at']})
            b.total_pages = row['max_page'] or 0
            booklets.append(b)
        
        conn.close()
        return booklets
    
    def update_booklet(self, booklet_id: int, name: str = None, description: str = None, sport: str = None) -> bool:
        """Update a booklet's details."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if sport is not None:
            updates.append("sport = ?")
            params.append(sport)
        
        if not updates:
            return False
        
        params.append(booklet_id)
        cursor.execute(f"UPDATE booklets SET {', '.join(updates)} WHERE id = ?", params)
        
        # Also update booklet_name in cards if name changed
        if name is not None:
            cursor.execute("UPDATE cards SET booklet_name = ? WHERE booklet_id = ?", (name, booklet_id))
        
        conn.commit()
        conn.close()
        return True
    
    # ==================== PAGE SCAN OPERATIONS ====================
    
    def add_page_scan(self, booklet_id: int, page_number: int, image_path: str, notes: str = "") -> int:
        """Add a page scan record."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO page_scans (booklet_id, page_number, original_image_path, notes)
                VALUES (?, ?, ?, ?)
            """, (booklet_id, page_number, image_path, notes))
            page_id = cursor.lastrowid
            conn.commit()
            return page_id
        except sqlite3.IntegrityError:
            # Page already exists, update it
            cursor.execute("""
                UPDATE page_scans 
                SET original_image_path = ?, notes = ?, scan_date = CURRENT_TIMESTAMP
                WHERE booklet_id = ? AND page_number = ?
            """, (image_path, notes, booklet_id, page_number))
            cursor.execute("""
                SELECT id FROM page_scans WHERE booklet_id = ? AND page_number = ?
            """, (booklet_id, page_number))
            page_id = cursor.fetchone()[0]
            conn.commit()
            return page_id
        finally:
            conn.close()
    
    def get_page_scan(self, booklet_id: int, page_number: int) -> Optional[PageScan]:
        """Get a page scan by booklet and page number."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT ps.*, b.name as booklet_name
            FROM page_scans ps
            JOIN booklets b ON ps.booklet_id = b.id
            WHERE ps.booklet_id = ? AND ps.page_number = ?
        """, (booklet_id, page_number))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return PageScan(**dict(row))
        return None
    
    # ==================== CARD OPERATIONS ====================
    
    def add_card(self, card: Card) -> int:
        """Add a card to the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO cards (
                player_name, team, year, sport, position,
                brand, set_name, subset, card_number, parallel,
                is_rookie, is_auto, is_patch, is_memorabilia, is_numbered, numbering, is_ssp, ssp_type,
                confidence, identification_notes,
                booklet_id, booklet_name, page_id, page_number, slot_position, slot_row, slot_col,
                image_path, condition, estimated_value, purchase_price, purchase_date, notes,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            card.player_name, card.team, card.year, card.sport, card.position,
            card.brand, card.set_name, card.subset, card.card_number, card.parallel,
            card.is_rookie, card.is_auto, card.is_patch, card.is_memorabilia, 
            card.is_numbered, card.numbering, card.is_ssp, card.ssp_type,
            card.confidence, card.identification_notes,
            card.booklet_id, card.booklet_name, card.page_id, card.page_number,
            card.slot_position, card.slot_row, card.slot_col,
            card.image_path, card.condition, card.estimated_value, 
            card.purchase_price, card.purchase_date, card.notes,
            now, now
        ))
        
        card_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return card_id
    
    def update_card(self, card: Card) -> bool:
        """Update an existing card."""
        if card.id is None:
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE cards SET
                player_name = ?, team = ?, year = ?, sport = ?, position = ?,
                brand = ?, set_name = ?, subset = ?, card_number = ?, parallel = ?,
                is_rookie = ?, is_auto = ?, is_patch = ?, is_memorabilia = ?,
                is_numbered = ?, numbering = ?, is_ssp = ?, ssp_type = ?,
                confidence = ?, identification_notes = ?,
                booklet_id = ?, booklet_name = ?, page_id = ?, page_number = ?,
                slot_position = ?, slot_row = ?, slot_col = ?,
                image_path = ?, condition = ?, estimated_value = ?,
                purchase_price = ?, purchase_date = ?, notes = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            card.player_name, card.team, card.year, card.sport, card.position,
            card.brand, card.set_name, card.subset, card.card_number, card.parallel,
            card.is_rookie, card.is_auto, card.is_patch, card.is_memorabilia,
            card.is_numbered, card.numbering, card.is_ssp, card.ssp_type,
            card.confidence, card.identification_notes,
            card.booklet_id, card.booklet_name, card.page_id, card.page_number,
            card.slot_position, card.slot_row, card.slot_col,
            card.image_path, card.condition, card.estimated_value,
            card.purchase_price, card.purchase_date, card.notes,
            datetime.now().isoformat(), card.id
        ))
        
        conn.commit()
        conn.close()
        return True
    
    def get_card(self, card_id: int) -> Optional[Card]:
        """Get a card by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return Card(**dict(row))
        return None
    
    def delete_card(self, card_id: int) -> bool:
        """Delete a card from the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        conn.commit()
        conn.close()
        return True
    
    def search_cards(
        self,
        # Text search
        player: Optional[str] = None,
        team: Optional[str] = None,
        year: Optional[str] = None,
        set_name: Optional[str] = None,
        sport: Optional[str] = None,
        brand: Optional[str] = None,
        parallel: Optional[str] = None,
        
        # Location search
        booklet_name: Optional[str] = None,
        booklet_id: Optional[int] = None,
        
        # Attribute filters
        rookies_only: bool = False,
        autos_only: bool = False,
        patches_only: bool = False,
        memorabilia_only: bool = False,
        numbered_only: bool = False,
        ssp_only: bool = False,
        
        # Sorting and pagination
        sort_by: str = "player_name",
        sort_order: str = "ASC",
        limit: int = 100,
        offset: int = 0
    ) -> List[Card]:
        """
        Search cards with various filters.
        This is the main search function that supports all the required queries.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        conditions = []
        params = []
        
        # Text searches (LIKE for partial matching)
        if player:
            conditions.append("player_name LIKE ?")
            params.append(f"%{player}%")
        if team:
            conditions.append("team LIKE ?")
            params.append(f"%{team}%")
        if year:
            conditions.append("year LIKE ?")
            params.append(f"%{year}%")
        if set_name:
            conditions.append("set_name LIKE ?")
            params.append(f"%{set_name}%")
        if sport:
            conditions.append("sport LIKE ?")
            params.append(f"%{sport}%")
        if brand:
            conditions.append("brand LIKE ?")
            params.append(f"%{brand}%")
        if parallel:
            conditions.append("parallel LIKE ?")
            params.append(f"%{parallel}%")
        
        # Location searches
        if booklet_name:
            conditions.append("booklet_name LIKE ?")
            params.append(f"%{booklet_name}%")
        if booklet_id:
            conditions.append("booklet_id = ?")
            params.append(booklet_id)
        
        # Attribute filters
        if rookies_only:
            conditions.append("is_rookie = 1")
        if autos_only:
            conditions.append("is_auto = 1")
        if patches_only:
            conditions.append("is_patch = 1")
        if memorabilia_only:
            conditions.append("(is_patch = 1 OR is_memorabilia = 1)")
        if numbered_only:
            conditions.append("is_numbered = 1")
        if ssp_only:
            conditions.append("is_ssp = 1")
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Validate sort column
        valid_sorts = ["player_name", "team", "year", "set_name", "created_at", 
                       "booklet_name", "page_number", "confidence"]
        if sort_by not in valid_sorts:
            sort_by = "player_name"
        
        sort_order = "DESC" if sort_order.upper() == "DESC" else "ASC"
        
        cursor.execute(f"""
            SELECT * FROM cards 
            WHERE {where_clause}
            ORDER BY {sort_by} {sort_order}
            LIMIT ? OFFSET ?
        """, params + [limit, offset])
        
        cards = [Card(**dict(row)) for row in cursor.fetchall()]
        conn.close()
        
        return cards
    
    def count_cards(self, **kwargs) -> int:
        """Count cards matching search criteria."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        conditions = []
        params = []
        
        for key, value in kwargs.items():
            if value is not None and value is not False:
                if key in ['rookies_only', 'autos_only', 'patches_only', 'numbered_only', 'ssp_only']:
                    field_map = {
                        'rookies_only': 'is_rookie',
                        'autos_only': 'is_auto',
                        'patches_only': 'is_patch',
                        'numbered_only': 'is_numbered',
                        'ssp_only': 'is_ssp'
                    }
                    conditions.append(f"{field_map[key]} = 1")
                elif key in ['player', 'team', 'year', 'set_name', 'sport', 'booklet_name']:
                    conditions.append(f"{key if key != 'player' else 'player_name'} LIKE ?")
                    params.append(f"%{value}%")
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        cursor.execute(f"SELECT COUNT(*) FROM cards WHERE {where_clause}", params)
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def get_cards_by_booklet(self, booklet_id: int) -> List[Card]:
        """Get all cards in a booklet, organized by page."""
        return self.search_cards(booklet_id=booklet_id, sort_by="page_number", limit=1000)
    
    def get_cards_by_page(self, booklet_id: int, page_number: int) -> List[Card]:
        """Get all cards on a specific page."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM cards 
            WHERE booklet_id = ? AND page_number = ?
            ORDER BY slot_position
        """, (booklet_id, page_number))
        
        cards = [Card(**dict(row)) for row in cursor.fetchall()]
        conn.close()
        return cards
    
    # ==================== STATISTICS ====================
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the collection."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        # Total counts
        cursor.execute("SELECT COUNT(*) FROM cards")
        stats["total_cards"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM booklets")
        stats["total_booklets"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT page_id) FROM cards WHERE page_id IS NOT NULL")
        stats["total_pages_scanned"] = cursor.fetchone()[0]
        
        # Special attributes
        cursor.execute("SELECT COUNT(*) FROM cards WHERE is_rookie = 1")
        stats["rookie_cards"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cards WHERE is_auto = 1")
        stats["auto_cards"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cards WHERE is_patch = 1 OR is_memorabilia = 1")
        stats["patch_memo_cards"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cards WHERE is_numbered = 1")
        stats["numbered_cards"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cards WHERE is_ssp = 1")
        stats["ssp_cards"] = cursor.fetchone()[0]
        
        # Value
        cursor.execute("SELECT SUM(estimated_value) FROM cards")
        stats["total_estimated_value"] = cursor.fetchone()[0] or 0
        
        # Lists
        cursor.execute("SELECT DISTINCT sport FROM cards WHERE sport IS NOT NULL AND sport != '' ORDER BY sport")
        stats["sports"] = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT set_name FROM cards WHERE set_name IS NOT NULL AND set_name != '' ORDER BY set_name")
        stats["sets"] = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT booklet_name FROM cards WHERE booklet_name IS NOT NULL AND booklet_name != '' ORDER BY booklet_name")
        stats["booklets"] = [row[0] for row in cursor.fetchall()]
        
        # Top players
        cursor.execute("""
            SELECT player_name, COUNT(*) as count 
            FROM cards 
            WHERE player_name IS NOT NULL AND player_name != ''
            GROUP BY player_name 
            ORDER BY count DESC 
            LIMIT 10
        """)
        stats["top_players"] = [(row[0], row[1]) for row in cursor.fetchall()]
        
        # Top teams
        cursor.execute("""
            SELECT team, COUNT(*) as count 
            FROM cards 
            WHERE team IS NOT NULL AND team != ''
            GROUP BY team 
            ORDER BY count DESC 
            LIMIT 10
        """)
        stats["top_teams"] = [(row[0], row[1]) for row in cursor.fetchall()]
        
        # Cards by booklet
        cursor.execute("""
            SELECT booklet_name, COUNT(*) as count 
            FROM cards 
            WHERE booklet_name IS NOT NULL AND booklet_name != ''
            GROUP BY booklet_name 
            ORDER BY booklet_name
        """)
        stats["cards_by_booklet"] = [(row[0], row[1]) for row in cursor.fetchall()]
        
        # Average confidence
        cursor.execute("SELECT AVG(confidence) FROM cards WHERE confidence > 0")
        stats["avg_confidence"] = cursor.fetchone()[0] or 0
        
        conn.close()
        return stats
    
    # ==================== VALUE ENGINE INTEGRATION ====================
    
    def update_card_valuation(self, card_id: int, estimated_value: float,
                               confidence_score: float = 0.0,
                               value_range_low: float = 0.0,
                               value_range_high: float = 0.0,
                               market_trend: str = "",
                               grading_rec: str = "") -> bool:
        """Update a card's value fields and record in history."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE cards SET
                estimated_value = ?,
                confidence_score = ?,
                value_range_low = ?,
                value_range_high = ?,
                market_trend = ?,
                grading_rec = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            estimated_value, confidence_score,
            value_range_low, value_range_high,
            market_trend, grading_rec,
            datetime.now().isoformat(), card_id
        ))
        
        # Record in history
        cursor.execute("""
            INSERT INTO value_history (card_id, estimated_value, confidence_score)
            VALUES (?, ?, ?)
        """, (card_id, estimated_value, confidence_score))
        
        conn.commit()
        conn.close()
        return True
    
    def get_value_history(self, card_id: int) -> List[Dict[str, Any]]:
        """Get value history for a card."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM value_history 
            WHERE card_id = ? 
            ORDER BY recorded_at DESC
        """, (card_id,))
        
        history = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return history
    
    # ==================== EXPORT ====================
    
    def export_to_csv(self, output_path: str, **filters):
        """Export the collection to CSV with optional filters."""
        import csv
        
        cards = self.search_cards(**filters, limit=100000)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            if not cards:
                return 0
            
            # Define columns for export
            columns = [
                'id', 'player_name', 'team', 'year', 'sport', 'position',
                'brand', 'set_name', 'subset', 'card_number', 'parallel',
                'is_rookie', 'is_auto', 'is_patch', 'is_memorabilia',
                'is_numbered', 'numbering', 'is_ssp', 'ssp_type',
                'confidence', 'booklet_name', 'page_number', 'slot_position',
                'location', 'condition', 'estimated_value', 'notes'
            ]
            
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            
            for card in cards:
                row = card.to_dict()
                writer.writerow(row)
        
        return len(cards)


if __name__ == "__main__":
    # Test the enhanced database
    db = CardDatabase("test_enhanced.db")
    
    # Create a booklet
    booklet_id = db.create_booklet("Football Rookies 2021", "All my 2021 football rookie cards", "Football")
    print(f"Created booklet: {booklet_id}")
    
    # Add a page scan
    page_id = db.add_page_scan(booklet_id, 1, "/path/to/scan.jpg")
    print(f"Added page scan: {page_id}")
    
    # Add a test card with full location
    test_card = Card(
        player_name="Kyle Pitts",
        team="Atlanta Falcons",
        year="2021",
        sport="Football",
        position="TE",
        brand="Panini",
        set_name="Score",
        parallel="Red",
        is_rookie=True,
        confidence=0.92,
        booklet_id=booklet_id,
        booklet_name="Football Rookies 2021",
        page_id=page_id,
        page_number=1,
        slot_position=6,
        slot_row=1,
        slot_col=2
    )
    
    card_id = db.add_card(test_card)
    print(f"Added card: {card_id}")
    
    # Search test
    results = db.search_cards(team="Falcons")
    print(f"Found {len(results)} Falcons cards")
    
    results = db.search_cards(rookies_only=True)
    print(f"Found {len(results)} rookie cards")
    
    # Get stats
    stats = db.get_collection_stats()
    print(f"Stats: {stats}")
    
    # Cleanup
    import os
    os.remove("test_enhanced.db")
    print("✓ All tests passed!")
