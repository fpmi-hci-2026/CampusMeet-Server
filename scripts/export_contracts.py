"""Deterministic OpenAPI, route matrix and Bruno exports. Run from repository root."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required, "additionalProperties": False}


def string(**kwargs):
    return {"type": "string", "minLength": 1, **kwargs}


def array(items):
    return {"type": "array", "items": items}


ID = string(maxLength=36, pattern=r"^[A-Za-z0-9_-]+$")
INT = {"type": "integer", "minimum": 1}
TIME = string(format="date-time")
BOOL = {"type": "boolean"}
REF = lambda name: {"$ref": "#/components/schemas/" + name}
SCHEMAS = {
    "EventInput": obj({"title": string(maxLength=200), "slug": string(maxLength=120, pattern="^[a-z0-9-]+$"), "event_type": string(enum=["meetup", "hackathon", "workshop", "lecture", "networking"]), "venue_id": ID, "start_time": TIME, "end_time": TIME, "capacity_limit": INT, "waitlist_enabled": BOOL}),
    "Event": obj({"id": ID, "title": string(), "slug": string(), "event_type": string(), "status": string(), "venue_id": ID, "organizer_user_id": ID, "start_time": TIME, "end_time": TIME, "capacity_limit": INT, "waitlist_enabled": BOOL, "version": INT, "free_spots": {"type": "integer", "minimum": 0}}),
    "Ticket": obj({"id": ID, "ticket_code": string(), "event_id": ID, "user_id": ID, "status": string(enum=["registered", "waitlisted", "checked_in", "cancelled", "no_show"]), "created_at": TIME}),
    "User": obj({"id": ID, "full_name": string(), "role": string()}),
    "Login": obj({"demo_user": ID}),
    "Token": obj({"access_token": string(), "token_type": string(enum=["bearer"])}),
    "Registration": obj({"join_waitlist": BOOL}),
    "CheckInInput": obj({"scanned_payload": string(maxLength=4096), "client_scan_id": string(maxLength=80)}),
    "CheckIn": obj({"id": ID, "ticket_id": ID, "event_id": ID, "verdict": string(enum=["GRANTED", "DENIED_ALREADY_USED", "DENIED_INVALID_STATUS"]), "scanned_at": TIME, "client_scan_id": string(), "scanned_by_volunteer_id": ID, "verification_mode": string(enum=["online", "offline_sync"])}),
    "ScheduleItem": obj({"id": ID, "title": string(), "room": string(), "start_time": TIME, "end_time": TIME}),
    "ScheduleInput": obj({"items": array(REF("ScheduleItem"))}),
    "PersonalSchedule": obj({"schedule_item_ids": array(ID)}),
    "ProposalInput": obj({"topic": string(maxLength=200), "abstract_text": string(maxLength=10000)}),
    "Proposal": obj({"id": ID, "event_id": ID, "speaker_user_id": ID, "topic": string(), "abstract_text": string(), "status": string(enum=["submitted", "under_review", "accepted", "rejected", "withdrawn"])}),
    "Review": obj({"status": string(enum=["accepted", "rejected"])}),
    "TeamInput": obj({"team_name": string(maxLength=100), "looking_for_roles": string(), "max_members": {"type": "integer", "minimum": 2, "maximum": 20}}),
    "Team": obj({"id": ID, "event_id": ID, "captain_user_id": ID, "team_name": string(), "looking_for_roles": string(), "max_members": INT, "status": string()}),
    "InvitationInput": obj({"user_id": ID}),
    "Invitation": obj({"id": ID, "team_id": ID, "user_id": ID, "status": string()}),
    "AnnouncementInput": obj({"title": string(maxLength=150), "body_text": string(maxLength=2000)}),
    "ExportInput": obj({"format": string(enum=["xlsx"])}),
    "CheckInBatchInput": obj({"device_id": string(maxLength=80), "scans": array(REF("CheckInInput"))}),
    "CheckInBatchResult": obj({"received": {"type": "integer", "minimum": 0}, "note": string()}),
    "Job": obj({"id": ID, "status": string(enum=["queued", "completed", "failed"]), "download_url": {"type": "string", "nullable": True}}),
    "Venue": obj({"id": ID, "name": string(), "address": string(), "total_capacity": INT, "latitude": {"type": "number"}, "longitude": {"type": "number"}}),
    "GeoResult": obj({"display_name": string(), "latitude": {"type": "number"}, "longitude": {"type": "number"}}),
    "Holiday": obj({"date": string(format="date"), "local_name": string()}),
    "Wallet": obj({"provider": string(enum=["apple", "google"]), "status": string(enum=["not_configured"])}),
    "Health": obj({"status": string(enum=["ok"]), "mode": string(enum=["mock"])}),
    "SearchResult": obj({"id": ID, "type": string(enum=["event"]), "title": string()}),
    "Problem": obj({"type": string(), "title": string(), "status": {"type": "integer"}, "detail": string(), "instance": string(), "code": string()}),
}
SCHEMAS["EventInput"]["properties"]["status"] = string(enum=["draft", "published", "registration_open", "registration_closed", "ongoing", "completed", "cancelled"])
SCHEMAS["EventInput"]["required"].append("status")
SCHEMAS["Ticket"]["properties"]["qr_payload"] = {"type": "string", "nullable": True, "description": "Target signed QR payload; local mock returns a synthetic DEMO-* code for registered/checked_in, null otherwise. No real cryptography."}
SCHEMAS["Ticket"]["required"].append("qr_payload")
for name in ["Event", "Ticket", "CheckIn", "Proposal", "Team", "Venue", "SearchResult", "ScheduleItem", "Holiday"]:
    SCHEMAS[name + "Page"] = obj({"items": array(REF(name)), "total": {"type": "integer", "minimum": 0}, "page": INT, "limit": {"type": "integer", "minimum": 1, "maximum": 100}})

EVENT = {"id": "ev-campusmeet-2026", "title": "CampusMeet: AI & Web", "slug": "campusmeet-2026", "event_type": "meetup", "status": "registration_open", "venue_id": "ven-bsu-01", "organizer_user_id": "usr-maxim-003", "start_time": "2026-11-05T14:00:00Z", "end_time": "2026-11-05T18:00:00Z", "capacity_limit": 2, "waitlist_enabled": True, "version": 1, "free_spots": 2}
EXAMPLES = {
    "Event": EVENT,
    "EventInput": {k: EVENT[k] for k in SCHEMAS["EventInput"]["properties"]},
    "Ticket": {"id": "tkt-example-01", "ticket_code": "DEMO-EXAMPLE", "qr_payload": "DEMO-EXAMPLE", "event_id": EVENT["id"], "user_id": "usr-artem-001", "status": "registered", "created_at": "2026-10-27T08:00:00Z"},
    "User": {"id": "usr-artem-001", "full_name": "Артём Ковалёв", "role": "attendee"},
    "Login": {"demo_user": "usr-artem-001"}, "Token": {"access_token": "demo-artem", "token_type": "bearer"},
    "Registration": {"join_waitlist": True},
    "CheckInInput": {"scanned_payload": "DEMO-EXAMPLE", "client_scan_id": "scan-example-001"},
    "CheckIn": {"id": "chk-example-01", "ticket_id": "tkt-example-01", "event_id": EVENT["id"], "verdict": "GRANTED", "scanned_at": "2026-11-05T13:55:00Z", "client_scan_id": "scan-example-001", "scanned_by_volunteer_id": "usr-daria-002", "verification_mode": "online"},
    "ScheduleItem": {"id": "sch-item-01", "title": "Архитектура Offline-First", "room": "512", "start_time": "2026-11-05T14:00:00Z", "end_time": "2026-11-05T15:00:00Z"},
    "PersonalSchedule": {"schedule_item_ids": ["sch-item-01"]},
    "ProposalInput": {"topic": "Offline-First", "abstract_text": "Проектирование автономных клиентов"},
    "Proposal": {"id": "proposal-01", "event_id": EVENT["id"], "speaker_user_id": "usr-viktor-005", "topic": "Offline-First", "abstract_text": "Проектирование автономных клиентов", "status": "submitted"},
    "Review": {"status": "accepted"},
    "TeamInput": {"team_name": "AlphaDevs", "looking_for_roles": "UI/UX, ML", "max_members": 4},
    "Team": {"id": "team-alpha-01", "event_id": EVENT["id"], "captain_user_id": "usr-kirill-004", "team_name": "AlphaDevs", "looking_for_roles": "UI/UX, ML", "max_members": 4, "status": "recruiting"},
    "InvitationInput": {"user_id": "usr-artem-001"},
    "Invitation": {"id": "invite-01", "team_id": "team-alpha-01", "user_id": "usr-artem-001", "status": "pending"},
    "AnnouncementInput": {"title": "Смена аудитории", "body_text": "Начало в аудитории 519"},
    "ExportInput": {"format": "xlsx"},
    "CheckInBatchInput": {"device_id": "volunteer-device-01", "scans": [{"scanned_payload": "DEMO-EXAMPLE", "client_scan_id": "scan-offline-001"}]},
    "CheckInBatchResult": {"received": 1, "note": "Contract example; offline reconciliation is not implemented in MVP"},
    "Job": {"id": "job-01", "status": "queued", "download_url": None},
    "Venue": {"id": "ven-bsu-01", "name": "ФПМИ БГУ, 512", "address": "Минск, пр-т Независимости, 4", "total_capacity": 100, "latitude": 53.893009, "longitude": 27.546879},
    "GeoResult": {"display_name": "Белорусский государственный университет", "latitude": 53.893009, "longitude": 27.546879},
    "Holiday": {"date": "2026-01-01", "local_name": "Новый год"},
    "Wallet": {"provider": "apple", "status": "not_configured"},
    "Health": {"status": "ok", "mode": "mock"},
    "SearchResult": {"id": EVENT["id"], "type": "event", "title": EVENT["title"]},
    "Problem": {"type": "about:blank", "title": "Conflict", "status": 409, "detail": "Билет уже использован", "instance": "/api/v1/tickets/tkt-example-01", "code": "TICKET_ALREADY_USED"},
}
EXAMPLES["ScheduleInput"] = {"items": [EXAMPLES["ScheduleItem"]]}
for name in list(SCHEMAS):
    if name.endswith("Page"):
        EXAMPLES[name] = {"items": [EXAMPLES[name[:-4]]], "total": 1, "page": 1, "limit": 20}

# UC-01..05 retain their original meanings from ЛР3. New cases extend, not renumber.
# method, route, operationId, UC, US, role, request schema, response schema, success, mode
ROUTES = [
    ("get", "/health", "health", "UC-14", "US-13", "public", None, "Health", 200, "stateful"),
    ("post", "/auth/token", "demoLogin", "UC-14", "US-13", "public", "Login", "Token", 200, "stateful"),
    ("get", "/me", "getProfile", "UC-14", "US-13", "authenticated", None, "User", 200, "stateful"),
    ("get", "/events", "listEvents", "UC-06", "US-08", "public", None, "EventPage", 200, "stateful"),
    ("post", "/events", "createEvent", "UC-03", "US-05", "organizer", "EventInput", "Event", 201, "stateful"),
    ("get", "/events/{event_id}", "getEvent", "UC-06", "US-08", "public", None, "Event", 200, "stateful"),
    ("put", "/events/{event_id}", "replaceEvent", "UC-03", "US-05", "organizer", "EventInput", "Event", 200, "stateful"),
    ("delete", "/events/{event_id}", "deleteDraft", "UC-03", "US-05", "organizer", None, None, 204, "stateful"),
    ("post", "/events/{event_id}/registrations", "registerAttendee", "UC-01", "US-01,US-06", "authenticated", "Registration", "Ticket", 201, "stateful"),
    ("get", "/me/tickets", "listMyTickets", "UC-07", "US-02", "authenticated", None, "TicketPage", 200, "stateful"),
    ("get", "/tickets/{ticket_id}", "getTicket", "UC-07", "US-02", "owner", None, "Ticket", 200, "stateful"),
    ("delete", "/tickets/{ticket_id}", "cancelTicket", "UC-08", "US-14", "owner", None, None, 204, "stateful"),
    ("get", "/events/{event_id}/check-ins", "listCheckIns", "UC-02", "US-03,US-04", "staff", None, "CheckInPage", 200, "stateful"),
    ("post", "/events/{event_id}/check-ins", "checkIn", "UC-02", "US-03,US-04", "staff", "CheckInInput", "CheckIn", 201, "stateful"),
    ("post", "/events/{event_id}/check-in-batches", "syncCheckIns", "UC-02", "US-04", "staff", "CheckInBatchInput", "CheckInBatchResult", 202, "example"),
    ("get", "/events/{event_id}/schedule", "getSchedule", "UC-09", "US-11", "public", None, "ScheduleItemPage", 200, "example"),
    ("put", "/events/{event_id}/schedule", "replaceSchedule", "UC-09", "US-11", "organizer", "ScheduleInput", "ScheduleInput", 200, "example"),
    ("put", "/me/schedule", "replacePersonalSchedule", "UC-09", "US-15", "authenticated", "PersonalSchedule", "PersonalSchedule", 200, "example"),
    ("get", "/events/{event_id}/proposals", "listProposals", "UC-04", "US-16", "organizer", None, "ProposalPage", 200, "example"),
    ("post", "/events/{event_id}/proposals", "submitProposal", "UC-04", "US-16", "authenticated", "ProposalInput", "Proposal", 201, "example"),
    ("patch", "/proposals/{proposal_id}", "reviewProposal", "UC-04", "US-16", "organizer", "Review", "Proposal", 200, "example"),
    ("get", "/events/{event_id}/teams", "listTeams", "UC-05", "US-07", "public", None, "TeamPage", 200, "example"),
    ("post", "/events/{event_id}/teams", "createTeam", "UC-05", "US-07", "authenticated", "TeamInput", "Team", 201, "example"),
    ("post", "/teams/{team_id}/invitations", "inviteMember", "UC-05", "US-07", "captain", "InvitationInput", "Invitation", 201, "example"),
    ("patch", "/team-invitations/{invitation_id}", "answerInvitation", "UC-05", "US-07", "owner", "Review", "Invitation", 200, "example"),
    ("get", "/search", "search", "UC-06", "US-08", "public", None, "SearchResultPage", 200, "stateful"),
    ("post", "/events/{event_id}/announcements", "broadcast", "UC-10", "US-09", "organizer", "AnnouncementInput", "Job", 202, "example"),
    ("get", "/jobs/{job_id}", "getJob", "UC-10", "US-09,US-12", "organizer", None, "Job", 200, "example"),
    ("get", "/tickets/{ticket_id}/wallet-pass", "getWalletPass", "UC-11", "US-10", "owner", None, "Wallet", 501, "stateful"),
    ("post", "/events/{event_id}/attendance-exports", "exportAttendance", "UC-12", "US-12", "organizer", "ExportInput", "Job", 202, "example"),
    ("get", "/venues", "listVenues", "UC-13", "US-05", "public", None, "VenuePage", 200, "stateful"),
    ("get", "/integrations/geocoding", "geocode", "UC-13", "US-05", "organizer", None, "GeoResult", 200, "example"),
    ("get", "/integrations/holidays", "holidays", "UC-13", "US-05", "organizer", None, "HolidayPage", 200, "example"),
]


def export():
    spec = {"openapi": "3.0.3", "info": {"title": "CampusMeet API — ЛР4", "version": "2.0.0", "description": "Contract-first API. Stateful registration/check-in MVP + example-only endpoints. Local demo tokens are not JWT. X-Mock-Mode reports stateful/example. Production API will use JWT. Wallet requires provider credentials and returns 501."}, "servers": [{"url": "http://127.0.0.1:8000/api/v1", "description": "Локальный mock"}], "security": [{"bearerAuth": []}], "paths": {}, "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "description": "Demo: demo-artem, demo-vlad, demo-kirill, demo-daria, demo-maxim, demo-viktor, demo-sergey"}}, "schemas": SCHEMAS}}
    matrix = ["# Реестр маршрутов и трассируемость API", "", "Сгенерировано `python3 scripts/export_contracts.py`. UC-01..05 сохранены из ЛР3.", "", "| HTTP | Маршрут /api/v1 | operationId | Use Case | User Story | Доступ | Режим |", "|:--|:--|:--|:--|:--|:--|:--|"]
    bruno = ROOT / "api/bruno"
    (bruno / "environments").mkdir(parents=True, exist_ok=True)
    for generated in bruno.glob("[0-9][0-9]-*.bru"):
        generated.unlink()
    (bruno / "bruno.json").write_text(json.dumps({"version": "1", "name": "CampusMeet Lab4", "type": "collection", "ignore": ["node_modules", ".git"]}, indent=2) + "\n")
    (bruno / "environments/Local.bru").write_text("vars {\n  baseUrl: http://127.0.0.1:8000/api/v1\n  token: demo-artem\n}\n")
    postman = {"info": {"name": "CampusMeet Lab4", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"}, "variable": [{"key": "baseUrl", "value": "http://127.0.0.1:8000/api/v1"}, {"key": "token", "value": "demo-artem"}], "item": []}
    for i, (method, route, opid, uc, us, role, req, res, status, mode) in enumerate(ROUTES, 1):
        params = [{"name": name, "in": "path", "required": True, "schema": ID} for name in re.findall(r"{(.*?)}", route)]
        if res and res.endswith("Page"):
            params += [{"name": "page", "in": "query", "schema": {**INT, "default": 1}}, {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}]
        if opid in ("listEvents", "search", "geocode"):
            params.append({"name": "q", "in": "query", "required": opid != "listEvents", "schema": string(maxLength=200)})
        if opid == "listEvents":
            params += [{"name": "status", "in": "query", "schema": SCHEMAS["Event"]["properties"]["status"]}, {"name": "event_type", "in": "query", "schema": SCHEMAS["EventInput"]["properties"]["event_type"]}]
        if opid == "holidays":
            params += [{"name": "year", "in": "query", "required": True, "schema": {"type": "integer", "minimum": 2020, "maximum": 2100}}, {"name": "country", "in": "query", "schema": string(enum=["BY"], default="BY")}]
        if opid == "getWalletPass":
            params.append({"name": "provider", "in": "query", "schema": string(enum=["apple", "google"], default="apple")})
        if opid == "registerAttendee":
            params.append({"name": "Idempotency-Key", "in": "header", "required": True, "schema": string(maxLength=80)})
        if opid == "replaceEvent":
            params.append({"name": "If-Match", "in": "header", "required": True, "schema": string(pattern='^"[0-9]+"$'), "description": "Quoted event version, e.g. \"1\""})
        responses = {str(status): {"description": {200: "Успешно", 201: "Создано", 202: "Поставлено в очередь (в mock без фоновой доставки)", 204: "Удалено / отменено", 501: "Провайдер Wallet не настроен"}[status]}}
        if res:
            responses[str(status)]["content"] = {"application/json": {"schema": REF(res), "example": EXAMPLES[res]}}
        for error, title in [(400, "Некорректный JSON"), (401, "Требуется токен"), (403, "Нет доступа"), (404, "Не найдено"), (409, "Конфликт состояния / идемпотентности"), (412, "Версия изменилась"), (422, "Ошибка валидации"), (428, "Отсутствует If-Match"), (429, "Превышен лимит запросов (целевой API)")]:
            responses[str(error)] = {"description": title, "content": {"application/problem+json": {"schema": REF("Problem"), "example": {**EXAMPLES["Problem"], "status": error, "title": title}}}}
        operation = {"operationId": opid, "summary": opid, "tags": [route.split('/')[1]], "description": f"{uc}; {us}. Access: {role}. Mock mode: {mode}.", "x-use-case": uc, "x-user-stories": us.split(','), "x-role": role, "x-mock-mode": mode, "parameters": params, "responses": responses}
        if role == "public":
            operation["security"] = []
        if req:
            operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": REF(req), "example": EXAMPLES[req]}}}
        spec["paths"].setdefault(route, {})[method] = operation
        matrix.append(f"| {method.upper()} | `{route}` | `{opid}` | {uc} | {us} | {role} | {mode} |")
        url = "{{baseUrl}}" + route
        for name, value in {"event_id": EVENT["id"], "ticket_id": "tkt-example-01", "proposal_id": "proposal-01", "team_id": "team-alpha-01", "invitation_id": "invite-01", "job_id": "job-01"}.items():
            url = url.replace("{" + name + "}", value)
        query_values = {"q": "CampusMeet", "year": "2026", "country": "BY"}
        query = [p["name"] + "=" + query_values[p["name"]] for p in params if p["in"] == "query" and p.get("required")]
        if query:
            url += "?" + "&".join(query)
        headers = {"Accept": "application/json"}
        if role != "public":
            token = "demo-maxim" if role == "organizer" else "demo-daria" if role == "staff" else "demo-kirill" if role == "captain" else "{{token}}"
            headers["Authorization"] = "Bearer " + token
        if req:
            headers["Content-Type"] = "application/json"
        if opid == "registerAttendee":
            headers["Idempotency-Key"] = "bruno-registration-001"
        if opid == "replaceEvent":
            headers["If-Match"] = '"1"'
        bru = f"meta {{\n  name: {opid}\n  type: http\n  seq: {i}\n}}\n\n{method} {{\n  url: {url}\n  body: {'json' if req else 'none'}\n  auth: none\n}}\n\nheaders {{\n" + "".join(f"  {k}: {v}\n" for k, v in headers.items()) + "}\n"
        if req:
            bru += "\nbody:json {\n" + "\n".join("  " + line for line in json.dumps(EXAMPLES[req], ensure_ascii=False, indent=2).splitlines()) + "\n}\n"
        bru += f"\ndocs {{\n  {uc}; {us}. Mock: {mode}. Expected HTTP {status}.\n  Ticket examples are placeholders: use an id/code returned by registration.\n}}\n"
        (bruno / f"{i:02}-{opid}.bru").write_text(bru)
        request = {"method": method.upper(), "header": [{"key": k, "value": v} for k, v in headers.items()], "url": url, "description": operation["description"]}
        if req:
            request["body"] = {"mode": "raw", "raw": json.dumps(EXAMPLES[req], ensure_ascii=False, indent=2), "options": {"raw": {"language": "json"}}}
        postman["item"].append({"name": opid, "request": request})
    (ROOT / "api/openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    (ROOT / "api/route-matrix.md").write_text("\n".join(matrix) + "\n")
    (ROOT / "api/CampusMeet.postman_collection.json").write_text(json.dumps(postman, ensure_ascii=False, indent=2) + "\n")
    print(f"Exported {len(ROUTES)} operations, {len(SCHEMAS)} schemas")


if __name__ == "__main__":
    export()
