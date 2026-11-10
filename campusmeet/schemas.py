"""Pydantic v2 schemas for CampusMeet REST API."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class ProblemDetails(BaseModel):
    status: int
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0-lab7"
    database: str = "connected"
    timestamp: str


class TokenRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    user_id: str
    role: str
    full_name: str


class VenueResponse(BaseModel):
    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    total_capacity: int


class EventBase(BaseModel):
    title: str
    slug: str
    event_type: str = Field(default="meetup", description="meetup | hackathon | workshop")
    status: str = Field(default="registration_open", description="draft | registration_open | closed | completed")
    venue_id: str
    start_time: str
    end_time: str
    capacity_limit: int = Field(ge=1)
    waitlist_enabled: bool = True


class EventCreate(EventBase):
    pass


class EventResponse(EventBase):
    id: str
    organizer_user_id: str
    free_spots: int
    waitlist_enabled: bool
    version: int


class EventListResponse(BaseModel):
    items: List[EventResponse]
    total: int
    page: int
    limit: int


class RegistrationRequest(BaseModel):
    join_waitlist: bool = True


class TicketResponse(BaseModel):
    id: str
    ticket_code: str
    event_id: str
    user_id: str
    status: str = Field(description="registered | waitlisted | checked_in | cancelled")
    created_at: str
    qr_payload: Optional[str] = None
    hmac_token: Optional[str] = None


class TicketListResponse(BaseModel):
    items: List[TicketResponse]
    total: int


class CheckInRequest(BaseModel):
    client_scan_id: str
    scanned_payload: Optional[str] = None
    payload: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_payload(cls, data: Any) -> Any:
        if isinstance(data, dict):
            p = data.get("scanned_payload") or data.get("payload")
            if not p:
                raise ValueError("Field 'scanned_payload' or 'payload' is required and cannot be empty")
            data["scanned_payload"] = p
            data["payload"] = p
        return data


class CheckInResponse(BaseModel):
    id: str
    event_id: str
    ticket_id: str
    scanned_by_volunteer_id: str
    client_scan_id: str
    verdict: str
    verification_mode: str = "online"
    scanned_at: str
