"""Local MCP client: exercises a real stdio process, records synthetic demo traffic.

Run: python3 scripts/mcp_client.py --output evidence/mcp-session.json
The client is deterministic and does not use an LLM API or claim an Inspector run.
"""
import argparse
import json
import selectors
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def exercise():
    transcript = []
    with tempfile.TemporaryDirectory() as temp:
        process = subprocess.Popen([sys.executable, "-m", "campusmeet.mcp_server", "--db", str(Path(temp) / "mcp.sqlite3")], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)

        def send(method, params=None, notification=False):
            request = {"jsonrpc": "2.0", "method": method, "params": params or {}}
            if not notification:
                request["id"] = len(transcript) + 1
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            entry = {"request": request}
            if not notification:
                if not selector.select(timeout=10):
                    raise TimeoutError("MCP response timeout")
                response = json.loads(process.stdout.readline())
                assert response["id"] == request["id"] and "error" not in response, response
                entry["response"] = response
                result = response["result"]
            else:
                result = None
            transcript.append(entry)
            return result

        try:
            init = send("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "campusmeet-local-client", "version": "1.0.0"}})
            assert init["protocolVersion"] == "2025-11-25"
            send("notifications/initialized", notification=True)
            assert len(send("tools/list")["tools"]) == 5
            assert len(send("resources/list")["resources"]) == 3
            send("resources/templates/list")
            assert len(send("prompts/list")["prompts"]) == 2
            send("resources/read", {"uri": "events://upcoming"})
            send("resources/read", {"uri": "policy://ticket-cancellation"})
            send("prompts/get", {"name": "plan_visit", "arguments": {"interest": "AI"}})
            send("tools/call", {"name": "check_event_capacity", "arguments": {"event_id": "ev-campusmeet-2026"}})
            args = {"event_id": "ev-campusmeet-2026", "join_waitlist": True, "idempotency_key": "mcp-demo-001"}
            registered = send("tools/call", {"name": "register_for_event", "arguments": args})
            assert registered["isError"] is False
            ticket = registered["structuredContent"]
            replay = send("tools/call", {"name": "register_for_event", "arguments": args})
            assert replay["structuredContent"] == ticket
            send("resources/read", {"uri": "tickets://mine"})
            send("resources/read", {"uri": "events://ev-campusmeet-2026"})
            send("prompts/get", {"name": "cancel_registration", "arguments": {"ticket_id": ticket["id"]}})
            send("tools/call", {"name": "get_ticket", "arguments": {"ticket_id": ticket["id"]}})
            cancelled = send("tools/call", {"name": "cancel_ticket", "arguments": {"ticket_id": ticket["id"]}})
            assert cancelled["structuredContent"]["status"] == "cancelled"
            send("ping")
        finally:
            selector.close()
            process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdout.close()
            errors = process.stderr.read()
            process.stderr.close()
            assert process.returncode == 0, errors
    return transcript


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = exercise()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"PASS: {len(result)} MCP exchanges via real stdio subprocess")
