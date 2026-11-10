"""Transactional SQLite mock shared by REST and MCP. No real QR signing or push."""
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .validation import Problem

ROOT = Path(__file__).resolve().parents[1]
USERS = [
    ("usr-artem-001", "Артём Ковалёв", "attendee", "artem"),
    ("usr-daria-002", "Дарья Мельникова", "volunteer", "daria"),
    ("usr-maxim-003", "Максим Романов", "organizer", "maxim"),
    ("usr-kirill-004", "Кирилл Савицкий", "team_lead", "kirill"),
    ("usr-viktor-005", "Виктор Громов", "speaker", "viktor"),
    ("usr-sergey-006", "Сергей Николаевич Котов", "admin", "sergey"),
    ("usr-vlad-007", "Влад Костылев", "attendee", "vlad"),
]
TOKENS = {"demo-" + name: uid for uid, _, _, name in USERS}


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix):
    return prefix + "-" + uuid.uuid4().hex[:24]


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def transaction(self, write=False):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        conn = self.connect()
        try:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone():
                return
            conn.executescript((ROOT / "database/schema.sqlite.sql").read_text())
        finally:
            conn.close()
        with self.transaction(True) as conn:
            for uid, name, role, alias in USERS:
                conn.execute("INSERT INTO users(id,email,password_hash,full_name,role) VALUES(?,?,?,?,?)", (uid, alias + "@example.invalid", "!demo-disabled", name, role))
            conn.execute("INSERT INTO venues VALUES(?,?,?,?,?,?)", ("ven-bsu-01", "ФПМИ БГУ, 512", "Минск, пр-т Независимости, 4", 53.893009, 27.546879, 100))
            conn.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("ev-campusmeet-2026", "campusmeet-2026", "CampusMeet: AI & Web", "meetup", "registration_open", "ven-bsu-01", "usr-maxim-003", "2026-11-05T14:00:00Z", "2026-11-05T18:00:00Z", 2, True, 1))
            conn.execute("INSERT INTO event_staff VALUES(?,?,?)", ("ev-campusmeet-2026", "usr-daria-002", "volunteer"))

    @staticmethod
    def get(conn, table, identifier):
        # table is always a source-code constant, never supplied by an API caller.
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise Problem(404, "NOT_FOUND", "Объект не найден")
        return dict(row)

    def user(self, user_id):
        with self.transaction() as conn:
            row = self.get(conn, "users", user_id)
            if not row["is_active"]:
                raise Problem(401, "INVALID_TOKEN", "Учетная запись отключена")
            return {k: row[k] for k in ("id", "full_name", "role")}

    def actor(self, token):
        if token not in TOKENS:
            raise Problem(401, "INVALID_TOKEN", "Используйте демонстрационный Bearer-токен из README")
        return self.user(TOKENS[token])

    @staticmethod
    def event_access(conn, actor, event_id, staff=False):
        event = Store.get(conn, "events", event_id)
        if actor["role"] == "admin" or event["organizer_user_id"] == actor["id"]:
            return event
        if staff and conn.execute("SELECT 1 FROM event_staff WHERE event_id=? AND user_id=?", (event_id, actor["id"])).fetchone():
            return event
        raise Problem(403, "FORBIDDEN", "Пользователь не назначен на это мероприятие")

    @staticmethod
    def event_view(conn, event):
        count = conn.execute("SELECT count(*) FROM tickets WHERE event_id=? AND status IN ('registered','checked_in')", (event["id"],)).fetchone()[0]
        return {**event, "waitlist_enabled": bool(event["waitlist_enabled"]), "free_spots": max(0, event["capacity_limit"] - count)}

    @staticmethod
    def ticket_view(ticket):
        fields = ("id", "ticket_code", "event_id", "user_id", "status", "created_at")
        return {**{key: ticket[key] for key in fields}, "qr_payload": ticket["ticket_code"] if ticket["status"] in ("registered", "checked_in") else None}

    def events(self, q="", status="", event_type=""):
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM events WHERE status != 'draft' AND title LIKE ? AND (?='' OR status=?) AND (?='' OR event_type=?) ORDER BY start_time,id", ("%" + q + "%", status, status, event_type, event_type)).fetchall()
            return [self.event_view(conn, dict(row)) for row in rows]

    def event(self, event_id, actor=None):
        with self.transaction() as conn:
            event = self.get(conn, "events", event_id)
            if event["status"] == "draft" and (actor is None or (actor["id"] != event["organizer_user_id"] and actor["role"] != "admin")):
                raise Problem(404, "NOT_FOUND", "Объект не найден")
            return self.event_view(conn, event)

    def save_event(self, actor, data, event_id=None, expected=None):
        if actor["role"] not in ("organizer", "admin"):
            raise Problem(403, "FORBIDDEN", "Требуются права организатора")
        start = datetime.fromisoformat(data["start_time"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(data["end_time"].replace("Z", "+00:00"))
        if end <= start:
            raise Problem(422, "INVALID_INTERVAL", "Окончание должно быть позже начала")
        # SQLite compares TEXT timestamps lexically; normalize offsets first.
        data = {**data, "start_time": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "end_time": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}
        with self.transaction(True) as conn:
            if event_id:
                old = self.event_access(conn, actor, event_id)
                if expected != f'"{old["version"]}"':
                    raise Problem(412, "VERSION_CONFLICT", "Повторно загрузите мероприятие")
                fields = ["title", "slug", "event_type", "status", "venue_id", "start_time", "end_time", "capacity_limit", "waitlist_enabled"]
                conn.execute("UPDATE events SET " + ",".join(f"{key}=?" for key in fields) + ",version=version+1 WHERE id=?", [data[key] for key in fields] + [event_id])
            else:
                event_id = new_id("ev")
                conn.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (event_id, data["slug"], data["title"], data["event_type"], data["status"], data["venue_id"], actor["id"], data["start_time"], data["end_time"], data["capacity_limit"], data["waitlist_enabled"], 1))
            return self.event_view(conn, self.get(conn, "events", event_id))

    def delete_event(self, actor, event_id):
        with self.transaction(True) as conn:
            event = self.event_access(conn, actor, event_id)
            if event["status"] != "draft":
                raise Problem(409, "NOT_A_DRAFT", "Удалять можно только черновик без зависимостей")
            conn.execute("DELETE FROM events WHERE id=?", (event_id,))

    def register(self, actor, event_id, join_waitlist, key):
        operation = "register:" + event_id
        digest = hashlib.sha256(json.dumps({"join_waitlist": join_waitlist}, sort_keys=True).encode()).hexdigest()
        with self.transaction(True) as conn:
            cached = conn.execute("SELECT * FROM idempotency_keys WHERE actor_user_id=? AND operation=? AND idempotency_key=?", (actor["id"], operation, key)).fetchone()
            if cached:
                if cached["request_hash"] != digest:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим телом запроса")
                return json.loads(cached["response_body"])
            event = self.get(conn, "events", event_id)
            if event["status"] != "registration_open":
                raise Problem(409, "REGISTRATION_CLOSED", "Регистрация закрыта")
            ticket = conn.execute("SELECT * FROM tickets WHERE event_id=? AND user_id=?", (event_id, actor["id"])).fetchone()
            if ticket and ticket["status"] != "cancelled":
                raise Problem(409, "ALREADY_REGISTERED", "Вы уже зарегистрированы")
            free = self.event_view(conn, event)["free_spots"]
            if not free and not (join_waitlist and event["waitlist_enabled"]):
                raise Problem(409, "QUOTA_EXHAUSTED", "Мест нет; можно вступить в лист ожидания")
            status = "registered" if free else "waitlisted"
            if ticket:
                ticket_id = ticket["id"]
                conn.execute("UPDATE tickets SET status=?,created_at=? WHERE id=?", (status, now(), ticket_id))
                conn.execute("DELETE FROM waitlist_entries WHERE ticket_id=?", (ticket_id,))
            else:
                ticket_id = new_id("tkt")
                conn.execute("INSERT INTO tickets(id,ticket_code,event_id,user_id,status,created_at) VALUES(?,?,?,?,?,?)", (ticket_id, "DEMO-" + uuid.uuid4().hex[:12].upper(), event_id, actor["id"], status, now()))
            if status == "waitlisted":
                conn.execute("INSERT INTO waitlist_entries(ticket_id,queued_at) VALUES(?,?)", (ticket_id, now()))
            result = self.ticket_view(self.get(conn, "tickets", ticket_id))
            conn.execute("INSERT INTO idempotency_keys(actor_user_id,operation,idempotency_key,request_hash,response_status,response_body) VALUES(?,?,?,?,?,?)", (actor["id"], operation, key, digest, 201, json.dumps(result)))
            return result

    def tickets(self, actor):
        with self.transaction() as conn:
            return [self.ticket_view(row) for row in conn.execute("SELECT * FROM tickets WHERE user_id=? ORDER BY created_at,id", (actor["id"],))]

    def ticket(self, actor, ticket_id):
        with self.transaction() as conn:
            result = self.get(conn, "tickets", ticket_id)
            if result["user_id"] != actor["id"]:
                raise Problem(403, "FORBIDDEN", "Билет принадлежит другому пользователю")
            return self.ticket_view(result)

    def cancel(self, actor, ticket_id):
        with self.transaction(True) as conn:
            ticket = self.get(conn, "tickets", ticket_id)
            if ticket["user_id"] != actor["id"]:
                raise Problem(403, "FORBIDDEN", "Билет принадлежит другому пользователю")
            if ticket["status"] in ("checked_in", "no_show"):
                raise Problem(409, "TICKET_ALREADY_USED", "Использованный билет отменить нельзя")
            if ticket["status"] == "cancelled":
                return
            conn.execute("UPDATE tickets SET status='cancelled' WHERE id=?", (ticket_id,))
            conn.execute("DELETE FROM waitlist_entries WHERE ticket_id=?", (ticket_id,))
            if ticket["status"] == "registered":
                next_ticket = conn.execute("SELECT t.id FROM tickets t JOIN waitlist_entries w ON w.ticket_id=t.id WHERE t.event_id=? AND t.status='waitlisted' ORDER BY w.queued_at,t.id LIMIT 1", (ticket["event_id"],)).fetchone()
                if next_ticket:
                    conn.execute("UPDATE tickets SET status='registered' WHERE id=?", (next_ticket["id"],))
                    conn.execute("UPDATE waitlist_entries SET promoted_at=? WHERE ticket_id=?", (now(), next_ticket["id"]))

    def check_in(self, actor, event_id, payload, scan_id):
        with self.transaction(True) as conn:
            self.event_access(conn, actor, event_id, staff=True)
            cached = conn.execute("SELECT * FROM check_in_logs WHERE client_scan_id=?", (scan_id,)).fetchone()
            if cached:
                ticket = self.get(conn, "tickets", cached["ticket_id"])
                if cached["event_id"] != event_id or ticket["ticket_code"] != payload or cached["scanned_by_volunteer_id"] != actor["id"]:
                    raise Problem(409, "SCAN_ID_CONFLICT", "client_scan_id уже использован")
                if cached["verdict"] != "GRANTED":
                    raise Problem(409, cached["verdict"], "Предыдущая попытка отклонена")
                return dict(cached)
            ticket = conn.execute("SELECT * FROM tickets WHERE ticket_code=? AND event_id=?", (payload, event_id)).fetchone()
            if not ticket:
                raise Problem(404, "TICKET_NOT_FOUND", "Демонстрационный код не найден")
            verdict = "GRANTED" if ticket["status"] == "registered" else "DENIED_ALREADY_USED" if ticket["status"] == "checked_in" else "DENIED_INVALID_STATUS"
            record = {"id": new_id("chk"), "event_id": event_id, "ticket_id": ticket["id"], "scanned_by_volunteer_id": actor["id"], "client_scan_id": scan_id, "verdict": verdict, "verification_mode": "online", "scanned_at": now()}
            conn.execute("INSERT INTO check_in_logs(" + ",".join(record) + ") VALUES(" + ",".join("?" for _ in record) + ")", list(record.values()))
            if verdict == "GRANTED":
                conn.execute("UPDATE tickets SET status='checked_in' WHERE id=?", (ticket["id"],))
        if verdict != "GRANTED":
            raise Problem(409, verdict, "Билет уже использован или имеет неподходящий статус")
        return record

    def check_ins(self, actor, event_id):
        with self.transaction() as conn:
            self.event_access(conn, actor, event_id, staff=True)
            return [dict(row) for row in conn.execute("SELECT * FROM check_in_logs WHERE event_id=? ORDER BY scanned_at,id", (event_id,))]

    def audit(self, actor, action, target_id, outcome):
        with self.transaction(True) as conn:
            conn.execute("INSERT INTO agent_audit_log(id,actor_user_id,action,target_id,outcome) VALUES(?,?,?,?,?)", (new_id("audit"), actor["id"], action, target_id, outcome))
