"""Small transactional SQLite store; no process-local authoritative game state."""
import json
import sqlite3
from pathlib import Path

from game_engine import RuleError, advance
from models import SCHEMA_VERSION, new_campaign


class CampaignStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS campaigns (id TEXT PRIMARY KEY, data TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=15)

    def transact(self, campaign_id, wall_now, action=None, expected_revision=None):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
            state = json.loads(row[0]) if row else new_campaign()
            if state.get("schema") != SCHEMA_VERSION:
                raise RuleError("This save uses an unsupported version. Preserve the database before upgrading.")
            original = json.dumps(state, sort_keys=True)
            # Check against the rendered page, then catch up due work atomically before the command.
            if action and expected_revision != state["revision"]:
                raise RuleError("The airfield has changed since this page opened. Review the updated board and try again.")
            now = wall_now + state["clock_offset"]
            advance(state, now)
            if action:
                action(state, now)
            if json.dumps(state, sort_keys=True) != original:
                state["revision"] += 1
            db.execute("INSERT INTO campaigns(id, data) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                       (campaign_id, json.dumps(state)))
            db.commit()
            return state
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
