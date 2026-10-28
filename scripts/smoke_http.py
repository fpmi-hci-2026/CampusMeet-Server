"""End-to-end HTTP check against a running disposable mock (stdlib only)."""
import argparse
import json
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def run(base_url):
    transcript = []

    def call(method, route, token=None, body=None, headers=None, expected=200):
        actual_headers = {"Accept": "application/json", **(headers or {})}
        if token:
            actual_headers["Authorization"] = "Bearer " + token
        if body is not None:
            actual_headers["Content-Type"] = "application/json"
        request = Request(base_url.rstrip("/") + route, data=None if body is None else json.dumps(body).encode(), headers=actual_headers, method=method)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            result = json.loads(raw) if raw else None
            assert response.status == expected, (route, response.status, result)
            transcript.append({"method": method, "route": route, "status": response.status, "body": result})
            return result

    call("GET", "/health")
    events = call("GET", "/events")
    event = events["items"][0]["id"]
    key = "http-smoke-" + uuid.uuid4().hex
    body = {"join_waitlist": True}
    ticket = call("POST", f"/events/{event}/registrations", "demo-artem", body, {"Idempotency-Key": key}, 201)
    assert ticket["status"] == "registered", "Run smoke test on a fresh disposable database"
    replay = call("POST", f"/events/{event}/registrations", "demo-artem", body, {"Idempotency-Key": key}, 201)
    assert replay == ticket
    call("GET", f'/tickets/{ticket["id"]}', "demo-vlad", expected=403)
    call("POST", f"/events/{event}/check-ins", "demo-daria", {"scanned_payload": ticket["ticket_code"], "client_scan_id": key + "-1"}, expected=201)
    call("POST", f"/events/{event}/check-ins", "demo-daria", {"scanned_payload": ticket["ticket_code"], "client_scan_id": key + "-2"}, expected=409)
    call("DELETE", f'/tickets/{ticket["id"]}', "demo-artem", expected=409)
    return transcript


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--output")
    args = parser.parse_args()
    transcript = run(args.base_url)
    if args.output:
        from pathlib import Path
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n")
    print(f"PASS: {len(transcript)} live HTTP requests")
