"""Business invariants, route contracts, HTTP and MCP isolation checks."""
import copy
import importlib.util
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from campusmeet.mcp_server import MCPServer, TOOLS
from campusmeet.mock_api import MockAPI, SPEC, handler_for
from campusmeet.store import ROOT, Store
from campusmeet.validation import Problem, validate

EVENT = "ev-campusmeet-2026"


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "test.sqlite3")
        self.store.initialize()
        self.api = MockAPI(self.store)
        self.artem = self.store.actor("demo-artem")
        self.vlad = self.store.actor("demo-vlad")
        self.kirill = self.store.actor("demo-kirill")
        self.daria = self.store.actor("demo-daria")
        self.maxim = self.store.actor("demo-maxim")

    def register(self, actor=None, key="test-001", waitlist=True):
        return self.store.register(actor or self.artem, EVENT, waitlist, key)

    def error(self, status, function, *args, **kwargs):
        with self.assertRaises(Problem) as caught:
            function(*args, **kwargs)
        self.assertEqual(status, caught.exception.status)
        return caught.exception

    def call(self, method, route, token=None, body=None, headers=None):
        actual = headers or {}
        if token:
            actual["Authorization"] = "Bearer " + token
        return self.api.dispatch(method, "/api/v1" + route, actual, body)


class DomainTests(Fixture):
    def test_register_idempotency_returns_same_ticket(self):
        first = self.register()
        self.assertEqual(first, self.register())
        self.assertEqual(1, len(self.store.tickets(self.artem)))

    def test_idempotency_rejects_body_change(self):
        self.register()
        self.assertEqual("IDEMPOTENCY_CONFLICT", self.error(409, self.register, waitlist=False).code)

    def test_duplicate_registration_under_new_key(self):
        self.register()
        self.error(409, self.register, key="another")

    def test_waitlist_promotes_oldest_and_cancel_is_idempotent(self):
        first = self.register()
        self.register(self.vlad)
        queued = self.register(self.kirill)
        self.assertEqual("waitlisted", queued["status"])
        self.store.cancel(self.artem, first["id"])
        self.store.cancel(self.artem, first["id"])
        self.assertEqual("registered", self.store.ticket(self.kirill, queued["id"])["status"])
        self.assertEqual(0, self.store.event(EVENT)["free_spots"])

    def test_full_event_without_waitlist_is_conflict(self):
        self.register()
        self.register(self.vlad)
        self.error(409, self.register, self.kirill, waitlist=False)

    def test_foreign_ticket_cannot_read_or_cancel(self):
        ticket = self.register()
        self.error(403, self.store.ticket, self.vlad, ticket["id"])
        self.error(403, self.store.cancel, self.vlad, ticket["id"])

    def test_checkin_duplicate_and_scan_replay(self):
        ticket = self.register()
        first = self.store.check_in(self.daria, EVENT, ticket["ticket_code"], "scan-001")
        self.assertEqual(first, self.store.check_in(self.daria, EVENT, ticket["ticket_code"], "scan-001"))
        self.error(409, self.store.check_in, self.daria, EVENT, ticket["ticket_code"], "scan-002")
        logs = self.store.check_ins(self.daria, EVENT)
        self.assertEqual(["GRANTED", "DENIED_ALREADY_USED"], [row["verdict"] for row in logs])

    def test_cancel_used_ticket_forbidden(self):
        ticket = self.register()
        self.store.check_in(self.daria, EVENT, ticket["ticket_code"], "scan-001")
        self.error(409, self.store.cancel, self.artem, ticket["id"])

    def test_attendee_cannot_scan(self):
        ticket = self.register()
        self.error(403, self.store.check_in, self.artem, EVENT, ticket["ticket_code"], "bad-scan")

    def test_concurrent_registration_does_not_overbook(self):
        actors = [self.artem, self.vlad, self.kirill, self.store.actor("demo-viktor"), self.store.actor("demo-sergey")]
        with ThreadPoolExecutor(max_workers=5) as pool:
            tickets = list(pool.map(lambda actor: self.register(actor, actor["id"]), actors))
        self.assertEqual(2, sum(t["status"] == "registered" for t in tickets))
        self.assertEqual(3, sum(t["status"] == "waitlisted" for t in tickets))

    def test_capacity_constraints_reject_event_and_venue_changes(self):
        with self.assertRaises(sqlite3.IntegrityError), self.store.transaction(True) as conn:
            conn.execute("UPDATE events SET capacity_limit=101 WHERE id=?", (EVENT,))
        with self.assertRaises(sqlite3.IntegrityError), self.store.transaction(True) as conn:
            conn.execute("UPDATE venues SET total_capacity=1")
        self.register()
        self.register(self.vlad)
        with self.assertRaises(sqlite3.IntegrityError), self.store.transaction(True) as conn:
            conn.execute("UPDATE events SET capacity_limit=1 WHERE id=?", (EVENT,))

    def test_schema_has_seventeen_tables_and_foreign_keys(self):
        with self.store.transaction() as conn:
            count = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            self.assertEqual(17, count)
            self.assertEqual([], conn.execute("PRAGMA foreign_key_check").fetchall())


class APITests(Fixture):
    def test_catalog_pagination_and_search(self):
        status, result, _ = self.call("GET", "/events?limit=1&page=2")
        self.assertEqual((200, [], 1), (status, result["items"], result["total"]))
        self.assertEqual(1, self.call("GET", "/search?q=CampusMeet")[1]["total"])
        self.error(422, self.call, "GET", "/events?limit=0")
        self.error(422, self.call, "GET", "/events?page=bad")

    def test_protected_route_requires_auth(self):
        self.error(401, self.call, "GET", "/me/tickets")
        self.error(401, self.call, "GET", "/me", "bad-token")

    def test_registration_body_and_idempotency_key_required(self):
        route = f"/events/{EVENT}/registrations"
        self.error(422, self.call, "POST", route, "demo-artem", {"join_waitlist": True})
        self.error(422, self.call, "POST", route, "demo-artem", {"join_waitlist": "true"}, {"Idempotency-Key": "key"})
        self.error(422, self.call, "POST", route, "demo-artem", {"join_waitlist": True, "user_id": "usr-vlad-007"}, {"Idempotency-Key": "key"})

    def test_create_replace_delete_draft_and_optimistic_lock(self):
        data = copy.deepcopy(SPEC["paths"]["/events"]["post"]["requestBody"]["content"]["application/json"]["example"])
        data["slug"] = "new-event"
        data["status"] = "draft"
        data["start_time"] = "2026-11-05T17:00:00+03:00"
        data["end_time"] = "2026-11-05T16:00:00Z"
        status, created, headers = self.call("POST", "/events", "demo-maxim", data)
        self.assertEqual((201, "draft", '"1"'), (status, created["status"], headers["ETag"]))
        self.assertEqual("2026-11-05T14:00:00Z", created["start_time"])
        route = "/events/" + created["id"]
        self.error(404, self.call, "GET", route)
        self.error(428, self.call, "PUT", route, "demo-maxim", data)
        self.error(412, self.call, "PUT", route, "demo-maxim", data, {"If-Match": '"99"'})
        data["status"] = "registration_open"
        self.assertEqual(2, self.call("PUT", route, "demo-maxim", data, {"If-Match": '"1"'})[1]["version"])
        self.assertEqual("registration_open", self.call("GET", route)[1]["status"])
        data["status"] = "draft"
        self.call("PUT", route, "demo-maxim", data, {"If-Match": '"2"'})
        self.assertEqual(204, self.call("DELETE", route, "demo-maxim")[0])

    def test_published_event_not_hard_deleted(self):
        self.error(409, self.call, "DELETE", "/events/" + EVENT, "demo-maxim")

    def test_mock_examples_validate_body_and_role(self):
        route = f"/events/{EVENT}/announcements"
        self.error(403, self.call, "POST", route, "demo-artem", {"title": "Test", "body_text": "Hello"})
        status, result, headers = self.call("POST", route, "demo-maxim", {"title": "Test", "body_text": "Hello"})
        self.assertEqual((202, "queued", "example"), (status, result["status"], headers["X-Mock-Mode"]))

    def test_offline_batch_requires_event_staff(self):
        route = f"/events/{EVENT}/check-in-batches"
        self.error(403, self.call, "POST", route, "demo-artem", {"device_id": "test", "scans": []})

    def test_wallet_clearly_reports_unconfigured(self):
        ticket = self.register()
        self.assertEqual(501, self.call("GET", f'/tickets/{ticket["id"]}/wallet-pass', "demo-artem")[0])

    def test_live_http_json_and_problem_response(self):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.api))
        except PermissionError as exc:
            self.skipTest(f"Environment blocks binding TCP sockets: {exc}")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 3)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        with urlopen(base + "/api/v1/health", timeout=5) as response:
            self.assertEqual("mock", json.load(response)["mode"])
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(base + "/api/v1/auth/token", data=b'{invalid', headers={"Content-Type": "application/json"}), timeout=5)
        self.assertEqual(400, caught.exception.code)
        self.assertEqual("application/problem+json", caught.exception.headers["Content-Type"])
        self.assertEqual("INVALID_JSON", json.load(caught.exception)["code"])

    def test_http_wire_parsing_and_serialization_without_tcp(self):
        class MemorySocket:
            def __init__(self, request):
                self.input = io.BytesIO(request)
                self.output = bytearray()

            def makefile(self, *_args):
                return self.input

            def sendall(self, data):
                self.output.extend(data)

        for request, expected, content_type in [
            (b"GET /api/v1/health HTTP/1.0\r\n\r\n", b"200 OK", b"application/json"),
            (b"POST /api/v1/auth/token HTTP/1.0\r\nContent-Length: 1\r\n\r\n{", b"400 Bad Request", b"application/problem+json"),
            (b"GET /api/v1/me HTTP/1.0\r\n\r\n", b"401 Unauthorized", b"application/problem+json"),
        ]:
            connection = MemorySocket(request)
            handler_for(self.api)(connection, ("127.0.0.1", 0), None)
            header, payload = bytes(connection.output).split(b"\r\n\r\n", 1)
            self.assertIn(expected, header)
            self.assertIn(content_type, header)
            self.assertIn(f"Content-Length: {len(payload)}".encode(), header)
            self.assertIsInstance(json.loads(payload), dict)


class ContractTests(unittest.TestCase):
    def test_all_operations_have_unique_ids_bodies_and_traceability(self):
        ids = []
        for route, methods in SPEC["paths"].items():
            for method, operation in methods.items():
                ids.append(operation["operationId"])
                self.assertTrue(operation["x-use-case"].startswith("UC-"))
                self.assertTrue(operation["x-user-stories"])
                if method in ("post", "put", "patch"):
                    self.assertIn("requestBody", operation, route)
                for media in operation.get("requestBody", {}).get("content", {}).values():
                    validate(media["example"], media["schema"], SPEC)
                for response in operation["responses"].values():
                    for media in response.get("content", {}).values():
                        validate(media["example"], media["schema"], SPEC)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(33, len(ids))

    @unittest.skipUnless(importlib.util.find_spec("jsonschema"), "Install requirements-dev.txt for external JSON Schema validation")
    def test_external_jsonschema_validation_of_every_example(self):
        from jsonschema import Draft4Validator, FormatChecker, RefResolver
        resolver = RefResolver.from_schema(SPEC)
        for definition in SPEC["components"]["schemas"].values():
            Draft4Validator.check_schema(definition)
        for methods in SPEC["paths"].values():
            for operation in methods.values():
                contents = list(operation.get("requestBody", {}).get("content", {}).values())
                contents += [media for response in operation["responses"].values() for media in response.get("content", {}).values()]
                for media in contents:
                    # OpenAPI 3.0 nullable is a dialect keyword, map to JSON Schema.
                    raw = json.dumps(media["schema"])
                    definitions = json.loads(json.dumps(SPEC))
                    for definition in definitions["components"]["schemas"].values():
                        for prop in definition.get("properties", {}).values():
                            if prop.pop("nullable", False):
                                prop["type"] = [prop["type"], "null"]
                    Draft4Validator(json.loads(raw), resolver=RefResolver.from_schema(definitions), format_checker=FormatChecker()).validate(media["example"])

    @unittest.skipUnless(importlib.util.find_spec("openapi_spec_validator"), "Full OAS validator is installed in CI")
    def test_external_openapi_validation(self):
        from openapi_spec_validator import validate as validate_openapi
        validate_openapi(SPEC)


class MCPTests(Fixture):
    def session(self, token="demo-artem"):
        session = MCPServer(self.store, token)
        session.dispatch("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
        session.dispatch("notifications/initialized", {})
        return session

    def test_discovery_tools_resources_prompts(self):
        session = self.session()
        self.assertEqual(5, len(session.dispatch("tools/list", {})["tools"]))
        self.assertEqual(3, len(session.dispatch("resources/list", {})["resources"]))
        self.assertEqual(2, len(session.dispatch("prompts/list", {})["prompts"]))

    def test_tool_argument_does_not_override_identity(self):
        response = self.session().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "register_for_event", "arguments": {"event_id": EVENT, "join_waitlist": True, "idempotency_key": "key", "user_id": "usr-vlad-007"}}})
        self.assertEqual(-32602, response["error"]["code"])

    def test_foreign_ticket_is_tool_error_not_success(self):
        ticket = self.register(self.vlad)
        result = self.session().tool("cancel_ticket", {"ticket_id": ticket["id"]})
        self.assertTrue(result["isError"])
        self.assertEqual("FORBIDDEN", json.loads(result["content"][0]["text"])["code"])

    def test_used_ticket_rejected_and_logged(self):
        ticket = self.register()
        self.store.check_in(self.daria, EVENT, ticket["ticket_code"], "scan-001")
        result = self.session().tool("cancel_ticket", {"ticket_id": ticket["id"]})
        self.assertTrue(result["isError"])
        with self.store.transaction() as conn:
            audit = conn.execute("SELECT * FROM agent_audit_log").fetchone()
            self.assertEqual("TICKET_ALREADY_USED", audit["outcome"])
            self.assertNotIn(ticket["ticket_code"], str(dict(audit)))

    def test_resources_are_scoped_to_current_user(self):
        mine = self.register()
        self.register(self.vlad)
        text = self.session().dispatch("resources/read", {"uri": "tickets://mine"})["contents"][0]["text"]
        self.assertEqual([mine["id"]], [item["id"] for item in json.loads(text)["items"]])

    def test_prompt_requires_argument(self):
        response = self.session().handle({"jsonrpc": "2.0", "id": 1, "method": "prompts/get", "params": {"name": "cancel_registration", "arguments": {}}})
        self.assertEqual(-32602, response["error"]["code"])

    def test_invalid_rpc_batch_is_rejected(self):
        self.assertEqual(-32600, self.session().handle([])["error"]["code"])

    def test_handshake_required(self):
        response = MCPServer(self.store).handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(-32000, response["error"]["code"])

    def test_real_stdio_client(self):
        result = subprocess.run([sys.executable, "scripts/mcp_client.py"], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("18 MCP exchanges", result.stdout)


if __name__ == "__main__":
    unittest.main()
