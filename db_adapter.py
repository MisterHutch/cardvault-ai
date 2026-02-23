"""
CardVault DB Adapter
Unified interface for SQLite (dev/local) and MySQL (production/Railway).
Handles ? → %s conversion and schema differences transparently.
"""

import os
import re
import sqlite3


def _fix_sql_for_mysql(sql):
    """Convert SQLite SQL to MySQL-compatible SQL."""
    # Parameterized query placeholders
    sql = sql.replace("?", "%s")
    # AUTOINCREMENT (SQLite) → AUTO_INCREMENT (MySQL)
    sql = re.sub(r'\bAUTOINCREMENT\b', 'AUTO_INCREMENT', sql, flags=re.IGNORECASE)
    # INTEGER PRIMARY KEY → INT PRIMARY KEY (MySQL doesn't like INTEGER for PK with AUTO_INCREMENT)
    sql = re.sub(r'\bINTEGER PRIMARY KEY AUTO_INCREMENT\b',
                 'INT AUTO_INCREMENT PRIMARY KEY', sql, flags=re.IGNORECASE)
    # BOOLEAN → TINYINT(1)
    sql = re.sub(r'\bBOOLEAN\b', 'TINYINT(1)', sql, flags=re.IGNORECASE)
    # TEXT NOT NULL DEFAULT '' → VARCHAR(255) NOT NULL DEFAULT '' for indexed cols
    # (MySQL needs explicit lengths for indexed TEXT — we keep TEXT for non-indexed)
    return sql


class _MySQLCursor:
    """Wraps a PyMySQL cursor to auto-convert SQLite syntax."""
    def __init__(self, cursor):
        self._cur = cursor

    def execute(self, sql, params=None):
        sql = _fix_sql_for_mysql(sql)
        if params:
            return self._cur.execute(sql, params)
        return self._cur.execute(sql)

    def executemany(self, sql, params=None):
        sql = _fix_sql_for_mysql(sql)
        return self._cur.executemany(sql, params or [])

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany(size)

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._cur.close()

    def close(self):
        self._cur.close()


class _MySQLConnection:
    """Wraps a PyMySQL connection to behave like sqlite3.Connection."""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        # Use DictCursor so rows are accessible by column name (like sqlite3.Row)
        import pymysql.cursors
        return _MySQLCursor(self._conn.cursor(pymysql.cursors.DictCursor))

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *args):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


def get_connection():
    """
    Returns a DB connection based on environment.
    - DATABASE_URL set (MySQL): returns _MySQLConnection
    - Otherwise: returns sqlite3 connection (existing behavior)
    """
    db_url = os.environ.get("DATABASE_URL", "")

    if db_url and ("mysql" in db_url.lower() or "mysql" in db_url.lower()):
        try:
            import pymysql
            import urllib.parse as urlparse

            parsed = urlparse.urlparse(db_url)
            conn = pymysql.connect(
                host=parsed.hostname,
                port=parsed.port or 3306,
                user=parsed.username,
                password=parsed.password,
                database=parsed.path.lstrip("/"),
                charset="utf8mb4",
                autocommit=False,
            )
            print(f"[DB] Connected to MySQL: {parsed.hostname}/{parsed.path.lstrip('/')}")
            return _MySQLConnection(conn)
        except ImportError:
            print("[DB] WARNING: pymysql not installed, falling back to SQLite")
        except Exception as e:
            print(f"[DB] WARNING: MySQL connection failed ({e}), falling back to SQLite")

    # SQLite fallback
    from flask import g
    import app as app_module
    db_path = getattr(app_module, "DB_PATH", "card_collection.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def is_mysql():
    """Check if running with MySQL."""
    db_url = os.environ.get("DATABASE_URL", "")
    return bool(db_url and "mysql" in db_url.lower())
