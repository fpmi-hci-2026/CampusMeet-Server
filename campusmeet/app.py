"""FastAPI server for CampusMeet (Lab 7)."""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .schemas import (
    CheckInRequest,
    CheckInResponse,
    EventCreate,
    EventListResponse,
    EventResponse,
    HealthResponse,
    RegistrationRequest,
    TicketListResponse,
    TicketResponse,
    TokenRequest,
    TokenResponse,
    VenueResponse,
)
from .store import ROOT, Store, USERS
from .validation import Problem

DB_PATH = Path(os.getenv("CAMPUSMEET_DB", ROOT / "database/campusmeet.db"))
store = Store(DB_PATH)
store.initialize()
store.seed_demo_events()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database schema and initial seed data exist
    store.initialize()
    yield


app = FastAPI(
    title="CampusMeet API",
    version="1.0.0-lab7",
    description="CampusMeet backend service implementing Laboratory Work No. 7 requirements for FPMI BSU.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
)

# Enable CORS for all local and deployed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Problem)
async def problem_exception_handler(request: Request, exc: Problem):
    return JSONResponse(
        status_code=exc.status,
        content={"status": exc.status, "code": exc.code, "message": exc.detail, "detail": exc.detail},
    )


def get_store() -> Store:
    return store


def get_actor(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Resolve authenticated user from Bearer token."""
    if not authorization:
        return None
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return store.actor(token)
    except Problem:
        return None


def require_actor(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Require valid authenticated actor."""
    if not authorization or not authorization.startswith("Bearer "):
        raise Problem(401, "MISSING_TOKEN", "Требуется Bearer-токен авторизации")
    token = authorization.removeprefix("Bearer ").strip()
    return store.actor(token)


# ==========================================
# 1. СИСТЕМНЫЕ ЭНДПОИНТЫ И АВТОРИЗАЦИЯ
# ==========================================

@app.get("/api/v1/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Проверка доступности API и состояния подключения к базе данных."""
    with store.transaction() as conn:
        conn.execute("SELECT 1").fetchone()
    return {
        "status": "ok",
        "version": "1.0.0-lab7",
        "database": "connected",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@app.post("/api/v1/auth/token", response_model=TokenResponse, tags=["Auth"])
def login_for_token(payload: TokenRequest):
    """
    Получение авторизационного Bearer-токена.
    Поддерживает вход по имени персоны (artem, maxim, daria, kirill) или роли (organizer, volunteer, attendee).
    """
    target_alias = payload.username or payload.role or "artem"
    # Match by alias or role
    found = None
    for uid, name, role, alias in USERS:
        if target_alias in (alias, role, uid) or (payload.username and payload.username.lower().startswith(alias)):
            found = (uid, name, role, alias)
            break
    if not found:
        # Default to artem
        found = USERS[0]
    uid, name, role, alias = found
    token = f"demo-{alias}"
    return {
        "access_token": token,
        "token_type": "Bearer",
        "user_id": uid,
        "role": role,
        "full_name": name,
    }


# ==========================================
# 2. МЕРОПРИЯТИЯ (EVENTS)
# ==========================================

@app.get("/api/v1/events", response_model=EventListResponse, tags=["Events"])
def list_events(
    q: str = Query("", description="Поисковая строка"),
    status: str = Query("", description="Фильтр по статусу (registration_open, closed, completed)"),
    event_type: str = Query("", description="Фильтр по типу (meetup, hackathon, workshop)"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Получение постраничного каталога мероприятий с фильтрацией."""
    all_events = store.events(q=q, status=status, event_type=event_type)
    start = (page - 1) * limit
    paged = all_events[start:start + limit]
    return {
        "items": paged,
        "total": len(all_events),
        "page": page,
        "limit": limit,
    }


@app.get("/api/v1/events/{event_id}", response_model=EventResponse, tags=["Events"])
def get_event(event_id: str, actor: Optional[Dict[str, Any]] = Depends(get_actor)):
    """Детальная информация о мероприятии по его идентификатору."""
    return store.event(event_id, actor=actor)


@app.post("/api/v1/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED, tags=["Events"])
def create_event(data: EventCreate, actor: Dict[str, Any] = Depends(require_actor)):
    """Создание нового мероприятия организатором."""
    return store.save_event(actor, data.model_dump())


# ==========================================
# 3. РЕГИСТРАЦИЯ И БИЛЕТЫ (TICKETS & REGISTRATION)
# ==========================================

@app.post("/api/v1/events/{event_id}/registrations", response_model=TicketResponse, status_code=status.HTTP_201_CREATED, tags=["Registration"])
def register_attendee(
    event_id: str,
    data: Optional[RegistrationRequest] = None,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    actor: Dict[str, Any] = Depends(require_actor),
):
    """
    Регистрация слушателя на мероприятие.
    При исчерпании квоты автоматически ставит в лист ожидания (Waitlist).
    Поддерживает идемпотентность через заголовок Idempotency-Key.
    """
    join_waitlist = data.join_waitlist if data else True
    key = idempotency_key or f"auto-{actor['id']}-{event_id}"
    return store.register(actor, event_id, join_waitlist, key)


@app.get("/api/v1/me/tickets", response_model=TicketListResponse, tags=["Tickets"])
def get_my_tickets(actor: Dict[str, Any] = Depends(require_actor)):
    """Получение списка билетов текущего авторизованного пользователя."""
    items = store.tickets(actor)
    return {"items": items, "total": len(items)}


@app.get("/api/v1/tickets/{ticket_id}", response_model=TicketResponse, tags=["Tickets"])
def get_ticket(ticket_id: str, actor: Dict[str, Any] = Depends(require_actor)):
    """Просмотр билета с криптографическим токеном HMAC-SHA256."""
    return store.ticket(actor, ticket_id)


@app.delete("/api/v1/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tickets"])
def cancel_ticket(ticket_id: str, actor: Dict[str, Any] = Depends(require_actor)):
    """
    Отмена билета.
    При отмене активного билета первый слушатель из листа ожидания автоматически переводится в статус registered.
    """
    store.cancel(actor, ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==========================================
# 4. ЧЕКИН И ВЕРИФИКАЦИЯ (CHECK-IN)
# ==========================================

@app.post("/api/v1/events/{event_id}/check-ins", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED, tags=["CheckIn"])
def check_in_ticket(
    event_id: str,
    data: CheckInRequest,
    actor: Dict[str, Any] = Depends(require_actor),
):
    """
    Верификация билета волонтером на входе.
    Проверяет HMAC-подпись или код билета, защищает от повторного прохода (HTTP 409).
    """
    return store.check_in(actor, event_id, data.payload, data.client_scan_id)


@app.get("/api/v1/events/{event_id}/check-ins", response_model=List[CheckInResponse], tags=["CheckIn"])
def list_event_check_ins(event_id: str, actor: Dict[str, Any] = Depends(require_actor)):
    """Журнал сканирований на мероприятии для организатора и волонтеров."""
    return store.check_ins(actor, event_id)


# ==========================================
# 5. АУДИТОРИИ (VENUES)
# ==========================================

@app.get("/api/v1/venues", response_model=List[VenueResponse], tags=["Venues"])
def list_venues():
    """Справочник университетских аудиторий и площадок."""
    return store.venues()


@app.get("/api/v1/venues/{venue_id}", response_model=VenueResponse, tags=["Venues"])
def get_venue(venue_id: str):
    """Получение детальной информации об аудитории."""
    return store.venue(venue_id)


# ==========================================
# 6. СТАТИЧЕСКИЕ КЛИЕНТСКИЕ МОДУЛИ И РЕДИРЕКТЫ
# ==========================================

WEB_DIR = ROOT / "web"
MOBILE_DIR = ROOT / "mobile"

if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

if MOBILE_DIR.exists():
    app.mount("/mobile", StaticFiles(directory=str(MOBILE_DIR), html=True), name="mobile")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/web/")
