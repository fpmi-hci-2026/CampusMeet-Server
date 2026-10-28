PRAGMA foreign_keys = ON;
-- CampusMeet / ЛР4. PostgreSQL 16+. Fresh database, not a migration of schema.sql.
-- Legacy VARCHAR identifiers retained deliberately; all timestamps are UTC-aware.
BEGIN;
CREATE TABLE users (
    id varchar(36) PRIMARY KEY,
    email varchar(255) NOT NULL UNIQUE,
    password_hash text NOT NULL,
    full_name varchar(150) NOT NULL,
    role varchar(24) NOT NULL CHECK (role IN ('attendee','team_lead','speaker','volunteer','organizer','admin')),
    is_active boolean NOT NULL DEFAULT true,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE venues (
    id varchar(36) PRIMARY KEY,
    name varchar(200) NOT NULL,
    address text NOT NULL,
    latitude numeric(10,7) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude numeric(10,7) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    total_capacity integer NOT NULL CHECK (total_capacity > 0)
);
CREATE TABLE events (
    id varchar(36) PRIMARY KEY,
    slug varchar(120) NOT NULL UNIQUE,
    title varchar(200) NOT NULL,
    event_type varchar(20) NOT NULL CHECK (event_type IN ('meetup','hackathon','workshop','lecture','networking')),
    status varchar(24) NOT NULL CHECK (status IN ('draft','published','registration_open','registration_closed','ongoing','completed','cancelled')),
    venue_id varchar(36) NOT NULL REFERENCES venues(id) ON DELETE RESTRICT,
    organizer_user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    capacity_limit integer NOT NULL CHECK (capacity_limit > 0),
    waitlist_enabled boolean NOT NULL DEFAULT true,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    CHECK (end_time > start_time)
);
CREATE INDEX idx_events_catalog ON events(status, start_time);
CREATE INDEX idx_events_organizer ON events(organizer_user_id);
CREATE TABLE event_staff (
    event_id varchar(36) NOT NULL REFERENCES events(id) ON DELETE RESTRICT,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    assignment varchar(20) NOT NULL CHECK (assignment IN ('volunteer','moderator')),
    PRIMARY KEY (event_id, user_id)
);
CREATE TABLE tickets (
    id varchar(36) PRIMARY KEY,
    ticket_code varchar(32) NOT NULL UNIQUE,
    event_id varchar(36) NOT NULL REFERENCES events(id) ON DELETE RESTRICT,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status varchar(20) NOT NULL CHECK (status IN ('registered','waitlisted','checked_in','cancelled','no_show')),
    qr_token_hash varchar(64), -- Reserved for target signed tokens; mock leaves NULL.
    signature_key_id varchar(80), -- Public-key identifier; private key is not stored here.
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (event_id, user_id),
    UNIQUE (id, event_id)
);
CREATE INDEX idx_tickets_event_status ON tickets(event_id, status);
CREATE INDEX idx_tickets_user ON tickets(user_id);
CREATE TABLE waitlist_entries (
    ticket_id varchar(36) PRIMARY KEY REFERENCES tickets(id) ON DELETE RESTRICT,
    queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    promoted_at TEXT,
    offer_expires_at TEXT
);
CREATE TABLE check_in_logs (
    id varchar(36) PRIMARY KEY,
    event_id varchar(36) NOT NULL REFERENCES events(id) ON DELETE RESTRICT,
    ticket_id varchar(36) NOT NULL,
    scanned_by_volunteer_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    client_scan_id varchar(80) NOT NULL UNIQUE,
    verdict varchar(24) NOT NULL CHECK (verdict IN ('GRANTED','DENIED_ALREADY_USED','DENIED_INVALID_STATUS')),
    verification_mode varchar(20) NOT NULL CHECK (verification_mode IN ('online','offline_sync')),
    scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id, event_id) REFERENCES tickets(id, event_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX uq_checkin_granted ON check_in_logs(ticket_id) WHERE verdict = 'GRANTED';
CREATE INDEX idx_checkin_event_time ON check_in_logs(event_id, scanned_at);
CREATE TABLE speaker_proposals (
    id varchar(36) PRIMARY KEY,
    event_id varchar(36) NOT NULL REFERENCES events(id) ON DELETE RESTRICT,
    speaker_user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    topic varchar(200) NOT NULL,
    abstract_text text NOT NULL,
    status varchar(20) NOT NULL CHECK (status IN ('submitted','under_review','accepted','rejected','withdrawn'))
);
CREATE TABLE schedule_items (
    id varchar(36) PRIMARY KEY,
    event_id varchar(36) NOT NULL REFERENCES events(id) ON DELETE RESTRICT,
    speaker_user_id varchar(36) REFERENCES users(id) ON DELETE RESTRICT,
    title varchar(200) NOT NULL,
    room varchar(100) NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    CHECK (end_time > start_time),
    UNIQUE (id, event_id)
);
CREATE INDEX idx_schedule_event_time ON schedule_items(event_id, start_time);
CREATE TABLE personal_schedule (
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    schedule_item_id varchar(36) NOT NULL REFERENCES schedule_items(id) ON DELETE RESTRICT,
    PRIMARY KEY (user_id, schedule_item_id)
);
CREATE TABLE team_matches (
    id varchar(36) PRIMARY KEY,
    event_id varchar(36) NOT NULL REFERENCES events(id) ON DELETE RESTRICT,
    captain_user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    team_name varchar(100) NOT NULL,
    looking_for_roles text NOT NULL,
    max_members integer NOT NULL CHECK (max_members BETWEEN 2 AND 20),
    status varchar(20) NOT NULL CHECK (status IN ('recruiting','team_ready','closed')),
    UNIQUE (id, event_id)
);
CREATE TABLE team_members (
    team_id varchar(36) NOT NULL,
    event_id varchar(36) NOT NULL,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    role_in_team varchar(100) NOT NULL,
    PRIMARY KEY (team_id, user_id),
    UNIQUE (event_id, user_id),
    FOREIGN KEY (team_id, event_id) REFERENCES team_matches(id, event_id) ON DELETE RESTRICT
);
CREATE TABLE team_invitations (
    id varchar(36) PRIMARY KEY,
    team_id varchar(36) NOT NULL REFERENCES team_matches(id) ON DELETE RESTRICT,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status varchar(20) NOT NULL CHECK (status IN ('pending','accepted','rejected')),
    UNIQUE (team_id, user_id)
);
CREATE TABLE emergency_announcements (
    id varchar(36) PRIMARY KEY,
    event_id varchar(36) NOT NULL REFERENCES events(id) ON DELETE RESTRICT,
    author_user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    title varchar(150) NOT NULL,
    body_text text NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE notification_deliveries (
    id varchar(36) PRIMARY KEY,
    announcement_id varchar(36) NOT NULL REFERENCES emergency_announcements(id) ON DELETE RESTRICT,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    channel varchar(12) NOT NULL CHECK (channel IN ('push','telegram','email')),
    status varchar(16) NOT NULL CHECK (status IN ('queued','sent','failed')),
    UNIQUE (announcement_id, user_id, channel)
);
CREATE TABLE agent_audit_log (
    id varchar(36) PRIMARY KEY,
    actor_user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    action varchar(80) NOT NULL,
    target_id varchar(80),
    outcome varchar(30) NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE idempotency_keys (
    actor_user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    operation varchar(120) NOT NULL,
    idempotency_key varchar(80) NOT NULL,
    request_hash varchar(64) NOT NULL,
    response_status integer NOT NULL CHECK (response_status BETWEEN 100 AND 599),
    response_body text NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (actor_user_id, operation, idempotency_key)
);

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
