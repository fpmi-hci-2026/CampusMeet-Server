"""Comprehensive pytest test suite for Laboratory Work No. 7 (CampusMeet API & Services)."""
import uuid
import pytest
from fastapi.testclient import TestClient

from campusmeet.app import app
from campusmeet.crypto import sign_ticket, verify_ticket_signature
from campusmeet.store import Store


@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory):
    temp_dir = tmp_path_factory.mktemp("lab7_test_data")
    db_file = temp_dir / "test_campusmeet.db"
    return db_file


@pytest.fixture(autouse=True)
def setup_isolated_store(test_db_path):
    """Ensure each test runs with an initialized database."""
    test_store = Store(test_db_path)
    test_store.initialize()
    test_store.seed_demo_events()
    # Patch the global store in app
    import campusmeet.app
    original_store = campusmeet.app.store
    campusmeet.app.store = test_store
    yield test_store
    campusmeet.app.store = original_store


@pytest.fixture
def client():
    return TestClient(app)


# ==========================================
# 1. СИСТЕМНЫЕ И АВТОРИЗАЦИОННЫЕ ТЕСТЫ
# ==========================================

def test_health_check(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert data["version"] == "1.0.0-lab7"
    assert "timestamp" in data


def test_auth_token_for_roles(client):
    # Test for attendee
    res1 = client.post("/api/v1/auth/token", json={"username": "artem"})
    assert res1.status_code == 200
    assert res1.json()["access_token"] == "demo-artem"
    assert res1.json()["role"] == "attendee"

    # Test for organizer
    res2 = client.post("/api/v1/auth/token", json={"role": "organizer"})
    assert res2.status_code == 200
    assert res2.json()["access_token"] == "demo-maxim"
    assert res2.json()["role"] == "organizer"

    # Test for volunteer
    res3 = client.post("/api/v1/auth/token", json={"username": "daria"})
    assert res3.status_code == 200
    assert res3.json()["access_token"] == "demo-daria"
    assert res3.json()["role"] == "volunteer"


# ==========================================
# 2. МЕРОПРИЯТИЯ (EVENTS)
# ==========================================

def test_list_events(client):
    res = client.get("/api/v1/events")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["limit"] == 20
    first = data["items"][0]
    assert "id" in first
    assert "title" in first
    assert "free_spots" in first


def test_filter_events_by_type(client):
    res = client.get("/api/v1/events?event_type=hackathon")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) >= 1
    assert all(it["event_type"] == "hackathon" for it in items)


def test_get_single_event(client):
    res = client.get("/api/v1/events/ev-campusmeet-2026")
    assert res.status_code == 200
    event = res.json()
    assert event["id"] == "ev-campusmeet-2026"
    assert event["capacity_limit"] == 2
    assert "free_spots" in event


def test_get_nonexistent_event(client):
    res = client.get("/api/v1/events/ev-does-not-exist")
    assert res.status_code == 404
    assert res.json()["code"] == "NOT_FOUND"


def test_create_event_organizer_permission(client):
    new_event = {
        "title": "Spring Kotlin Meetup",
        "slug": "spring-kotlin-meetup-" + uuid.uuid4().hex[:6],
        "event_type": "meetup",
        "status": "registration_open",
        "venue_id": "ven-bsu-01",
        "start_time": "2026-11-25T14:00:00Z",
        "end_time": "2026-11-25T17:00:00Z",
        "capacity_limit": 80,
        "waitlist_enabled": True
    }
    # Organizer Maxim
    res = client.post(
        "/api/v1/events",
        json=new_event,
        headers={"Authorization": "Bearer demo-maxim"}
    )
    assert res.status_code == 201
    created = res.json()
    assert created["title"] == "Spring Kotlin Meetup"
    assert created["free_spots"] == 80


def test_create_event_forbidden_for_attendee(client):
    new_event = {
        "title": "Unauthorized Event",
        "slug": "unauthorized-event-" + uuid.uuid4().hex[:6],
        "event_type": "meetup",
        "status": "registration_open",
        "venue_id": "ven-bsu-01",
        "start_time": "2026-11-25T14:00:00Z",
        "end_time": "2026-11-25T17:00:00Z",
        "capacity_limit": 50,
        "waitlist_enabled": True
    }
    # Attendee Artem
    res = client.post(
        "/api/v1/events",
        json=new_event,
        headers={"Authorization": "Bearer demo-artem"}
    )
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


# ==========================================
# 3. АУДИТОРИИ (VENUES)
# ==========================================

def test_venues_endpoints(client):
    res = client.get("/api/v1/venues")
    assert res.status_code == 200
    venues = res.json()
    assert len(venues) >= 1
    assert any(v["id"] == "ven-bsu-01" for v in venues)

    single = client.get("/api/v1/venues/ven-bsu-01")
    assert single.status_code == 200
    assert "ФПМИ БГУ" in single.json()["name"]


# ==========================================
# 4. РЕГИСТРАЦИЯ, КВОТЫ И БИЛЕТЫ (TICKETS & WAITLIST)
# ==========================================

def test_attendee_registration_and_hmac_ticket(client):
    # Artem registers for campusmeet-2026
    reg_res = client.post(
        "/api/v1/events/ev-campusmeet-2026/registrations",
        json={"join_waitlist": True},
        headers={
            "Authorization": "Bearer demo-artem",
            "Idempotency-Key": "test-reg-artem-01"
        }
    )
    assert reg_res.status_code == 201
    ticket = reg_res.json()
    assert ticket["status"] == "registered"
    assert ticket["event_id"] == "ev-campusmeet-2026"
    assert "v1." in ticket["qr_payload"]
    assert "v1." in ticket["hmac_token"]
    assert verify_ticket_signature(ticket["qr_payload"], "ev-campusmeet-2026")


def test_duplicate_registration_rejected(client):
    # Second registration without cancellation must fail
    res = client.post(
        "/api/v1/events/ev-campusmeet-2026/registrations",
        json={"join_waitlist": True},
        headers={
            "Authorization": "Bearer demo-artem",
            "Idempotency-Key": "test-reg-artem-dup"
        }
    )
    assert res.status_code == 409
    assert res.json()["code"] == "ALREADY_REGISTERED"


def test_idempotency_replay(client):
    # Same key and same payload returns cached 201 response
    res = client.post(
        "/api/v1/events/ev-campusmeet-2026/registrations",
        json={"join_waitlist": True},
        headers={
            "Authorization": "Bearer demo-artem",
            "Idempotency-Key": "test-reg-artem-01"
        }
    )
    assert res.status_code == 201
    assert res.json()["user_id"] == "usr-artem-001"


def test_get_my_tickets_and_single(client):
    res = client.get("/api/v1/me/tickets", headers={"Authorization": "Bearer demo-artem"})
    assert res.status_code == 200
    tickets = res.json()["items"]
    assert len(tickets) >= 1
    tkt_id = tickets[0]["id"]

    single_res = client.get(f"/api/v1/tickets/{tkt_id}", headers={"Authorization": "Bearer demo-artem"})
    assert single_res.status_code == 200
    assert single_res.json()["id"] == tkt_id


def test_waitlist_and_automatic_promotion(client):
    """Capacity limit is 2. Artem already holds spot 1. Fill spot 2, then waitlist spot 3."""
    # Spot 2: Vlad
    res2 = client.post(
        "/api/v1/events/ev-campusmeet-2026/registrations",
        json={"join_waitlist": True},
        headers={"Authorization": "Bearer demo-vlad"}
    )
    assert res2.status_code == 201
    assert res2.json()["status"] == "registered"

    # Spot 3: Kirill (Capacity exhausted -> goes to waitlist)
    res3 = client.post(
        "/api/v1/events/ev-campusmeet-2026/registrations",
        json={"join_waitlist": True},
        headers={"Authorization": "Bearer demo-kirill"}
    )
    assert res3.status_code == 201
    assert res3.json()["status"] == "waitlisted"

    # Artem cancels his registered ticket -> Kirill should automatically be promoted to registered
    artem_tkt_id = client.get("/api/v1/me/tickets", headers={"Authorization": "Bearer demo-artem"}).json()["items"][0]["id"]
    cancel_res = client.delete(f"/api/v1/tickets/{artem_tkt_id}", headers={"Authorization": "Bearer demo-artem"})
    assert cancel_res.status_code == 204

    # Verify Kirill was promoted
    kirill_tkt_id = res3.json()["id"]
    promoted_tkt = client.get(f"/api/v1/tickets/{kirill_tkt_id}", headers={"Authorization": "Bearer demo-kirill"}).json()
    assert promoted_tkt["status"] == "registered"
    assert "v1." in promoted_tkt["qr_payload"]


# ==========================================
# 5. ЧЕКИН И ВАЛИДАЦИЯ ПРОХОДА (CHECK-IN)
# ==========================================

def test_check_in_flow_granted_and_duplicate_denied(client):
    # Vlad holds registered ticket for ev-campusmeet-2026
    vlad_tkt = client.get("/api/v1/me/tickets", headers={"Authorization": "Bearer demo-vlad"}).json()["items"][0]
    payload = vlad_tkt["qr_payload"]

    # Daria is authorized volunteer
    scan_id = f"test-scan-{uuid.uuid4().hex[:8]}"
    checkin_res = client.post(
        "/api/v1/events/ev-campusmeet-2026/check-ins",
        json={"client_scan_id": scan_id, "payload": payload},
        headers={"Authorization": "Bearer demo-daria"}
    )
    assert checkin_res.status_code == 201
    data = checkin_res.json()
    assert data["verdict"] == "GRANTED"
    assert data["event_id"] == "ev-campusmeet-2026"
    assert data["ticket_id"] == vlad_tkt["id"]

    # Duplicate scan attempt with new scan_id must be rejected with 409 Conflict
    dup_scan_id = f"test-scan-{uuid.uuid4().hex[:8]}"
    dup_res = client.post(
        "/api/v1/events/ev-campusmeet-2026/check-ins",
        json={"client_scan_id": dup_scan_id, "payload": payload},
        headers={"Authorization": "Bearer demo-daria"}
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["code"] == "DENIED_ALREADY_USED"


def test_check_in_invalid_payload_rejected(client):
    res = client.post(
        "/api/v1/events/ev-campusmeet-2026/check-ins",
        json={"client_scan_id": "test-invalid-scan", "payload": "v1.fake-tkt.fake-usr.bad-signature"},
        headers={"Authorization": "Bearer demo-daria"}
    )
    assert res.status_code == 404
    assert res.json()["code"] == "TICKET_NOT_FOUND"


def test_check_in_forbidden_for_non_volunteer(client):
    res = client.post(
        "/api/v1/events/ev-campusmeet-2026/check-ins",
        json={"client_scan_id": "test-forbidden", "payload": "DEMO-001"},
        headers={"Authorization": "Bearer demo-artem"}
    )
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


def test_check_in_with_scanned_payload_contract_field(client):
    """Проверка обратной совместимости поля scanned_payload из контракта OpenAPI и smoke_http.py."""
    # Регистрация нового билета на хакатон
    scan_tkt = client.post(
        "/api/v1/events/ev-hackathon-2026/registrations",
        json={"join_waitlist": False},
        headers={"Authorization": "Bearer demo-artem", "Idempotency-Key": f"key-smoke-{uuid.uuid4().hex[:8]}"}
    ).json()

    res = client.post(
        "/api/v1/events/ev-hackathon-2026/check-ins",
        json={"client_scan_id": f"scan-{uuid.uuid4().hex[:8]}", "scanned_payload": scan_tkt["ticket_code"]},
        headers={"Authorization": "Bearer demo-daria"}
    )
    assert res.status_code == 201
    assert res.json()["verdict"] == "GRANTED"


def test_list_check_ins_log(client):
    res = client.get("/api/v1/events/ev-campusmeet-2026/check-ins", headers={"Authorization": "Bearer demo-daria"})
    assert res.status_code == 200
    logs = res.json()
    assert isinstance(logs, list)
    assert len(logs) >= 1
    assert logs[0]["verdict"] == "GRANTED"


# ==========================================
# 6. КРИПТОГРАФИЧЕСКИЕ ЮНИТ-ТЕСТЫ
# ==========================================

def test_crypto_signing_and_tamper_detection():
    sig = sign_ticket("tkt-123", "usr-456", "ev-789")
    assert sig.startswith("v1.tkt-123.usr-456.")
    assert verify_ticket_signature(sig, "ev-789") is True

    # Tampered event_id
    assert verify_ticket_signature(sig, "ev-different-event") is False

    # Tampered signature
    tampered = sig[:-4] + "ffff"
    assert verify_ticket_signature(tampered, "ev-789") is False

    # Malformed strings
    assert verify_ticket_signature("random_unstructured_string", "ev-789") is False
    assert verify_ticket_signature("", "ev-789") is False
