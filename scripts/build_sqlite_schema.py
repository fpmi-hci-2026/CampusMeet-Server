"""Export the MVP SQLite physical model from PostgreSQL table definitions."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def export():
    sql = (ROOT / "database/schema.postgresql.sql").read_text().split("-- Cross-row constraints")[0]
    sql = re.sub(r"\btimestamptz\b", "TEXT", sql, flags=re.I)
    sql = "PRAGMA foreign_keys = ON;\n" + sql + """
CREATE TRIGGER trg_event_capacity_insert BEFORE INSERT ON events
BEGIN
 SELECT RAISE(ABORT, 'Event exceeds venue capacity')
 WHERE NEW.capacity_limit > (SELECT total_capacity FROM venues WHERE id = NEW.venue_id);
END;
CREATE TRIGGER trg_event_capacity_update BEFORE UPDATE ON events
BEGIN
 SELECT RAISE(ABORT, 'Event exceeds venue capacity')
 WHERE NEW.capacity_limit > (SELECT total_capacity FROM venues WHERE id = NEW.venue_id);
 SELECT RAISE(ABORT, 'Event capacity below allocated seats')
 WHERE NEW.capacity_limit < (SELECT count(*) FROM tickets WHERE event_id = NEW.id AND status IN ('registered','checked_in'));
END;
CREATE TRIGGER trg_venue_capacity BEFORE UPDATE ON venues
BEGIN
 SELECT RAISE(ABORT, 'Venue capacity below event limit')
 WHERE EXISTS (SELECT 1 FROM events WHERE venue_id = NEW.id AND capacity_limit > NEW.total_capacity);
END;
COMMIT;
"""
    (ROOT / "database/schema.sqlite.sql").write_text(sql)


if __name__ == "__main__":
    export()
