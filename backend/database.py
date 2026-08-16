"""
Project Zara — SQLite Database Module
======================================
Async SQLite database for storing sensor readings, risk assessments, and alerts.
Uses aiosqlite for non-blocking I/O compatible with FastAPI's async architecture.
"""

import aiosqlite
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from config import DB_PATH, DATA_DIR, DATA_RETENTION_DAYS


# =============================================================================
# SCHEMA
# =============================================================================
SCHEMA_SQL = """
-- Raw sensor readings from LoRa packets
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    soil_moisture_1 REAL,          -- Shallow depth (%)
    soil_moisture_2 REAL,          -- Mid depth (%)
    soil_moisture_3 REAL,          -- Deep depth (%)
    tilt_x REAL,                   -- MPU6050 X-axis (degrees)
    tilt_y REAL,                   -- MPU6050 Y-axis (degrees)
    temperature REAL,              -- BME280 (°C)
    humidity REAL,                 -- BME280 (%)
    pressure REAL,                 -- BME280 (hPa)
    rainfall REAL,                 -- Tipping bucket (mm)
    raw_packet TEXT,               -- Original hex packet for debugging
    is_valid INTEGER DEFAULT 1     -- 0 if failed validation
);

-- Computed risk assessments
CREATE TABLE IF NOT EXISTS risk_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    reading_id INTEGER REFERENCES sensor_readings(id),
    risk_level TEXT NOT NULL,          -- SAFE, CAUTION, WARNING, DANGER
    composite_score REAL NOT NULL,     -- 0-100
    rainfall_score REAL,
    soil_moisture_score REAL,
    slope_movement_score REAL,
    environmental_score REAL,
    rainfall_1hr REAL,
    rainfall_3hr REAL,
    rainfall_24hr REAL,
    rainfall_72hr REAL,
    details TEXT                        -- JSON with full breakdown
);

-- Alert history
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    risk_level TEXT NOT NULL,
    message TEXT NOT NULL,
    assessment_id INTEGER REFERENCES risk_assessments(id),
    acknowledged INTEGER DEFAULT 0,
    acknowledged_at TEXT,
    acknowledged_by TEXT
);

-- System event log
CREATE TABLE IF NOT EXISTS system_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    level TEXT NOT NULL,               -- INFO, WARNING, ERROR
    source TEXT NOT NULL,              -- Module that generated the log
    message TEXT NOT NULL
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON sensor_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_risk_timestamp ON risk_assessments(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(acknowledged);
"""


# =============================================================================
# DATABASE CONNECTION MANAGER
# =============================================================================
class Database:
    """Async SQLite database manager for Project Zara."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Initialize database connection and create tables."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")  # Better concurrent reads
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()

    async def close(self):
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    # -------------------------------------------------------------------------
    # SENSOR READINGS
    # -------------------------------------------------------------------------
    async def insert_reading(self, data: dict) -> int:
        """Insert a new sensor reading. Returns the row ID."""
        sql = """
            INSERT INTO sensor_readings
            (soil_moisture_1, soil_moisture_2, soil_moisture_3,
             tilt_x, tilt_y, temperature, humidity, pressure,
             rainfall, raw_packet, is_valid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = await self._db.execute(sql, (
            data.get("soil_moisture_1"),
            data.get("soil_moisture_2"),
            data.get("soil_moisture_3"),
            data.get("tilt_x"),
            data.get("tilt_y"),
            data.get("temperature"),
            data.get("humidity"),
            data.get("pressure"),
            data.get("rainfall"),
            data.get("raw_packet"),
            data.get("is_valid", 1),
        ))
        await self._db.commit()
        return cursor.lastrowid

    async def get_latest_reading(self) -> Optional[dict]:
        """Get the most recent sensor reading."""
        sql = "SELECT * FROM sensor_readings WHERE is_valid = 1 ORDER BY id DESC LIMIT 1"
        async with self._db.execute(sql) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_readings(self, hours: int = 24, limit: int = 500) -> list[dict]:
        """Get sensor readings for the last N hours."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        sql = """
            SELECT * FROM sensor_readings
            WHERE is_valid = 1 AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        async with self._db.execute(sql, (since, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_rainfall_sum(self, hours: int) -> float:
        """Get cumulative rainfall for the last N hours."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        sql = """
            SELECT COALESCE(SUM(rainfall), 0) as total
            FROM sensor_readings
            WHERE is_valid = 1 AND timestamp >= ?
        """
        async with self._db.execute(sql, (since,)) as cursor:
            row = await cursor.fetchone()
            return float(row["total"]) if row else 0.0

    # -------------------------------------------------------------------------
    # RISK ASSESSMENTS
    # -------------------------------------------------------------------------
    async def insert_assessment(self, data: dict) -> int:
        """Insert a risk assessment result. Returns the row ID."""
        sql = """
            INSERT INTO risk_assessments
            (reading_id, risk_level, composite_score,
             rainfall_score, soil_moisture_score,
             slope_movement_score, environmental_score,
             rainfall_1hr, rainfall_3hr, rainfall_24hr, rainfall_72hr,
             details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = await self._db.execute(sql, (
            data.get("reading_id"),
            data["risk_level"],
            data["composite_score"],
            data.get("rainfall_score"),
            data.get("soil_moisture_score"),
            data.get("slope_movement_score"),
            data.get("environmental_score"),
            data.get("rainfall_1hr"),
            data.get("rainfall_3hr"),
            data.get("rainfall_24hr"),
            data.get("rainfall_72hr"),
            json.dumps(data.get("details", {})),
        ))
        await self._db.commit()
        return cursor.lastrowid

    async def get_latest_assessment(self) -> Optional[dict]:
        """Get the most recent risk assessment."""
        sql = "SELECT * FROM risk_assessments ORDER BY id DESC LIMIT 1"
        async with self._db.execute(sql) as cursor:
            row = await cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("details"):
                    result["details"] = json.loads(result["details"])
                return result
            return None

    async def get_assessments(self, hours: int = 24, limit: int = 200) -> list[dict]:
        """Get risk assessments for the last N hours."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        sql = """
            SELECT * FROM risk_assessments
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        async with self._db.execute(sql, (since, limit)) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                r = dict(row)
                if r.get("details"):
                    r["details"] = json.loads(r["details"])
                results.append(r)
            return results

    # -------------------------------------------------------------------------
    # ALERTS
    # -------------------------------------------------------------------------
    async def insert_alert(self, risk_level: str, message: str,
                           assessment_id: Optional[int] = None) -> int:
        """Insert a new alert. Returns the row ID."""
        sql = """
            INSERT INTO alerts (risk_level, message, assessment_id)
            VALUES (?, ?, ?)
        """
        cursor = await self._db.execute(sql, (risk_level, message, assessment_id))
        await self._db.commit()
        return cursor.lastrowid

    async def get_alerts(self, limit: int = 50,
                         unacknowledged_only: bool = False) -> list[dict]:
        """Get recent alerts, optionally only unacknowledged ones."""
        where = "WHERE acknowledged = 0" if unacknowledged_only else ""
        sql = f"""
            SELECT * FROM alerts
            {where}
            ORDER BY id DESC
            LIMIT ?
        """
        async with self._db.execute(sql, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def acknowledge_alert(self, alert_id: int, by: str = "operator"):
        """Mark an alert as acknowledged."""
        sql = """
            UPDATE alerts
            SET acknowledged = 1,
                acknowledged_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                acknowledged_by = ?
            WHERE id = ?
        """
        await self._db.execute(sql, (by, alert_id))
        await self._db.commit()

    # -------------------------------------------------------------------------
    # SYSTEM LOG
    # -------------------------------------------------------------------------
    async def log(self, level: str, source: str, message: str):
        """Insert a system log entry."""
        sql = "INSERT INTO system_log (level, source, message) VALUES (?, ?, ?)"
        await self._db.execute(sql, (level, source, message))
        await self._db.commit()

    # -------------------------------------------------------------------------
    # MAINTENANCE
    # -------------------------------------------------------------------------
    async def cleanup_old_data(self):
        """Remove data older than DATA_RETENTION_DAYS."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=DATA_RETENTION_DAYS)).isoformat()
        for table in ["sensor_readings", "risk_assessments", "alerts", "system_log"]:
            await self._db.execute(
                f"DELETE FROM {table} WHERE timestamp < ?", (cutoff,)
            )
        await self._db.execute("VACUUM")
        await self._db.commit()

    async def clear_all_data(self):
        """Wipe all local database tables."""
        for table in ["sensor_readings", "risk_assessments", "alerts", "system_log"]:
            await self._db.execute(f"DELETE FROM {table}")
        await self._db.execute("VACUUM")
        await self._db.commit()

    # -------------------------------------------------------------------------
    # STATISTICS
    # -------------------------------------------------------------------------
    async def get_stats(self) -> dict:
        """Get database statistics."""
        stats = {}
        for table in ["sensor_readings", "risk_assessments", "alerts"]:
            async with self._db.execute(f"SELECT COUNT(*) as cnt FROM {table}") as cursor:
                row = await cursor.fetchone()
                stats[f"{table}_count"] = row["cnt"]
        return stats


# Global database instance
db = Database()
