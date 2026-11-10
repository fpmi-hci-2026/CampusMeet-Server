"""OpenAPI-driven HTTP mock. Run: python3 -m campusmeet.mock_api."""
import argparse
import json
import os
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .store import ROOT, Store, TOKENS
from .validation import Problem, validate

SPEC = json.loads((ROOT / "api/openapi.json").read_text())


def paged(items, query):
    page, limit = int(query.get("page", "1")), int(query.get("limit", "20"))
    return {"items": items[(page - 1) * limit:page * limit], "total": len(items), "page": page, "limit": limit}


class MockAPI:
    def __init__(self, store):
        self.store = store

    def dispatch(self, method, path, headers=None, body=None):
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        parsed = urlsplit(path)
        if parsed.path == "/openapi.json":
            return 200, SPEC, {"X-Mock-Mode": "contract"}
        route_path = parsed.path.removeprefix("/api/v1")
        operation, variables = None, None
        for template, methods in SPEC["paths"].items():
            pattern = re.sub(r"{([^}]+)}", r"(?P<\1>[^/]+)", template)
            match = re.fullmatch(pattern, route_path) if parsed.path.startswith("/api/v1/") else None
            if match and method.lower() in methods:
                operation, variables = methods[method.lower()], match.groupdict()
                break
        if operation is None:
            raise Problem(404, "ROUTE_NOT_FOUND", "Маршрут не найден")
        actor = None
        authorization = headers.get("authorization", "")
        if authorization or operation.get("security") != []:
            if not authorization.startswith("Bearer "):
                raise Problem(401, "MISSING_TOKEN", "Требуется Bearer-токен")
            actor = self.store.actor(authorization[7:])
        query_multi = parse_qs(parsed.query, keep_blank_values=True)
        if any(len(values) != 1 for values in query_multi.values()):
            raise Problem(422, "VALIDATION_ERROR", "Повторяющиеся query-параметры запрещены")
        query = {k: values[0] for k, values in query_multi.items()}
        for param in operation["parameters"]:
            source = variables if param["in"] == "path" else headers if param["in"] == "header" else query
            name = param["name"].lower() if param["in"] == "header" else param["name"]
            if name not in source:
                if param.get("required"):
                    raise Problem(428 if name == "if-match" else 422, "MISSING_PARAMETER", name + " обязателен")
                continue
            value = source[name]
            if param["schema"].get("type") == "integer":
                try:
                    value = int(value)
                except ValueError as exc:
                    raise Problem(422, "VALIDATION_ERROR", name + ": ожидается integer") from exc
            validate(value, param["schema"], SPEC, name)
        if "requestBody" in operation:
            validate(body, operation["requestBody"]["content"]["application/json"]["schema"], SPEC)
        role, opid = operation["x-role"], operation["operationId"]
        event_id = variables.get("event_id")
        if role == "organizer":
            if actor["role"] not in ("organizer", "admin"):
                raise Problem(403, "FORBIDDEN", "Требуются права организатора")
            if event_id:
                with self.store.transaction() as conn:
                    self.store.event_access(conn, actor, event_id)
        if event_id and opid not in ("getEvent", "replaceEvent", "deleteDraft"):
            self.store.event(event_id, actor)
        if role == "staff":
            with self.store.transaction() as conn:
                self.store.event_access(conn, actor, event_id, staff=True)
        if role == "owner" and "ticket_id" in variables:
            self.store.ticket(actor, variables["ticket_id"])
        if role == "captain" and actor["role"] != "team_lead":
            raise Problem(403, "FORBIDDEN", "Требуются права капитана")
        mode = operation["x-mock-mode"]
        response_headers = {"X-Mock-Mode": mode}
        success = next(int(code) for code in operation["responses"] if int(code) < 300 or int(code) == 501)
        if mode == "example":
            response = operation["responses"][str(success)]["content"]["application/json"]["example"]
            return success, response, response_headers
        if opid == "health":
            result = {"status": "ok", "mode": "mock"}
        elif opid == "demoLogin":
            self.store.user(body["demo_user"])
            token = next(token for token, uid in TOKENS.items() if uid == body["demo_user"])
            result = {"access_token": token, "token_type": "bearer"}
        elif opid == "getProfile":
            result = actor
        elif opid == "listEvents":
            result = paged(self.store.events(query.get("q", ""), query.get("status", ""), query.get("event_type", "")), query)
        elif opid == "getEvent":
            result = self.store.event(event_id, actor)
            response_headers["ETag"] = f'"{result["version"]}"'
        elif opid in ("createEvent", "replaceEvent"):
            result = self.store.save_event(actor, body, event_id, headers.get("if-match"))
            response_headers["ETag"] = f'"{result["version"]}"'
            if opid == "createEvent":
                response_headers["Location"] = "/api/v1/events/" + result["id"]
        elif opid == "deleteDraft":
            self.store.delete_event(actor, event_id)
            result = None
        elif opid == "registerAttendee":
            result = self.store.register(actor, event_id, body["join_waitlist"], headers["idempotency-key"])
            response_headers["Location"] = "/api/v1/tickets/" + result["id"]
        elif opid == "listMyTickets":
            result = paged(self.store.tickets(actor), query)
        elif opid == "getTicket":
            result = self.store.ticket(actor, variables["ticket_id"])
        elif opid == "cancelTicket":
            self.store.cancel(actor, variables["ticket_id"])
            result = None
        elif opid == "checkIn":
            result = self.store.check_in(actor, event_id, body["scanned_payload"], body["client_scan_id"])
        elif opid == "listCheckIns":
            result = paged(self.store.check_ins(actor, event_id), query)
        elif opid == "search":
            result = paged([{"id": row["id"], "type": "event", "title": row["title"]} for row in self.store.events(query["q"])], query)
        elif opid == "listVenues":
            with self.store.transaction() as conn:
                result = paged([dict(row) for row in conn.execute("SELECT * FROM venues ORDER BY id")], query)
        elif opid == "getWalletPass":
            result = {"provider": query.get("provider", "apple"), "status": "not_configured"}
        else:
            raise Problem(501, "NOT_IMPLEMENTED", opid)
        return success, result, response_headers


def handler_for(api):
    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type,Idempotency-Key,If-Match")
            self.end_headers()

        def respond(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 65536:
                    raise Problem(422, "BODY_TOO_LARGE", "Максимум 64 KiB")
                body = json.loads(self.rfile.read(length)) if length else None
                status, result, headers = api.dispatch(self.command, self.path, dict(self.headers), body)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                problem = Problem(400, "INVALID_JSON", "Некорректное тело запроса")
                status, result, headers = problem.status, problem.as_dict(self.path), {}
            except Problem as exc:
                status, result, headers = exc.status, exc.as_dict(self.path), {}
            except sqlite3.IntegrityError:
                problem = Problem(409, "DATA_CONFLICT", "Нарушено ограничение целостности")
                status, result, headers = problem.status, problem.as_dict(self.path), {}
            payload = b"" if status == 204 else json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/problem+json" if "code" in (result or {}) else "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Expose-Headers", "ETag,Location,X-Mock-Mode")
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = respond
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--db", type=Path, default=ROOT / "data/mock.sqlite3")
    args = parser.parse_args()
    store = Store(args.db)
    store.initialize()
    server = ThreadingHTTPServer((args.host, args.port), handler_for(MockAPI(store)))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
