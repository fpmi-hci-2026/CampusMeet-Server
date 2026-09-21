-- =============================================================================
-- CampusMeet / EventHub Database Schema DDL
-- Platform for Local Meetups, Hackathons & QR-Ticket Validation
-- Compatible with PostgreSQL 15+ / SQLite 3
-- Course: Human-Computer Interaction Design (PCHMI), BSU FAMCS 2025-2026
-- =============================================================================

-- Clean up existing tables if re-running
DROP TABLE IF EXISTS check_in_logs;
DROP TABLE IF EXISTS tickets;
DROP TABLE IF EXISTS team_members;
DROP TABLE IF EXISTS team_matches;
DROP TABLE IF EXISTS speaker_proposals;
DROP TABLE IF EXISTS schedule_items;
DROP TABLE IF EXISTS emergency_announcements;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS venues;
DROP TABLE IF EXISTS users;

-- 1. Users Table (Core identity and cross-role profile)
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY, -- UUID v4
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    avatar_url VARCHAR(500),
    phone VARCHAR(30),
    telegram_username VARCHAR(100),
    role VARCHAR(30) NOT NULL DEFAULT 'attendee' CHECK (role IN ('guest', 'attendee', 'team_lead', 'speaker', 'volunteer', 'organizer', 'admin')),
    organization_name VARCHAR(200),
    bio TEXT,
    skills_tags TEXT, -- Comma-separated tags (e.g. "React,Python,ML,UI/UX")
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_telegram ON users(telegram_username);

-- 2. Venues Table (Physical locations integrated with Nominatim OpenStreetMap API)
CREATE TABLE venues (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(200) NOT NULL, -- e.g. "Корпус ФПМИ БГУ, ауд. 512"
    address VARCHAR(300) NOT NULL, -- e.g. "г. Минск, пр-т Независимости, 4"
    latitude NUMERIC(10, 7) NOT NULL, -- From Nominatim API: e.g. 53.8930090
    longitude NUMERIC(10, 7) NOT NULL, -- From Nominatim API: e.g. 27.5468790
    osm_place_id BIGINT,
    building VARCHAR(100),
    room VARCHAR(100),
    total_capacity INT NOT NULL DEFAULT 100,
    navigation_instructions TEXT, -- "5 этаж, налево по коридору мимо деканата"
    floor_map_url VARCHAR(500),
    is_wheelchair_accessible BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_venues_coords ON venues(latitude, longitude);

-- 3. Events Table (Meetups, Hackathons, Workshops)
CREATE TABLE events (
    id VARCHAR(36) PRIMARY KEY,
    slug VARCHAR(120) NOT NULL UNIQUE,
    title VARCHAR(200) NOT NULL,
    short_summary VARCHAR(300) NOT NULL,
    description TEXT NOT NULL,
    event_type VARCHAR(40) NOT NULL CHECK (event_type IN ('meetup', 'hackathon', 'workshop', 'lecture', 'networking')),
    status VARCHAR(30) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'registration_open', 'registration_closed', 'ongoing', 'completed', 'cancelled')),
    venue_id VARCHAR(36) REFERENCES venues(id) ON DELETE SET NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    registration_deadline TIMESTAMP WITH TIME ZONE NOT NULL,
    capacity_limit INT NOT NULL DEFAULT 80,
    waitlist_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    registered_count INT NOT NULL DEFAULT 0,
    checked_in_count INT NOT NULL DEFAULT 0,
    banner_image_url VARCHAR(500),
    organizer_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    is_public BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_slug ON events(slug);
CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_events_start ON events(start_time);
CREATE INDEX idx_events_organizer ON events(organizer_user_id);

-- 4. Schedule Track Items (Detailed timeline / "My Schedule")
CREATE TABLE schedule_items (
    id VARCHAR(36) PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    track_name VARCHAR(100) NOT NULL DEFAULT 'Основной трек',
    title VARCHAR(200) NOT NULL,
    description TEXT,
    speaker_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    speaker_display_name VARCHAR(150),
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    room_override VARCHAR(100),
    is_keynote BOOLEAN NOT NULL DEFAULT FALSE,
    presentation_url VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_schedule_event ON schedule_items(event_id, start_time);

-- 5. Tickets / Registrations Table (Dynamic offline QR-tokens)
CREATE TABLE tickets (
    id VARCHAR(36) PRIMARY KEY,
    ticket_code VARCHAR(32) NOT NULL UNIQUE, -- Human-friendly short code (e.g. "CMP-2026-X89K")
    event_id VARCHAR(36) NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticket_type VARCHAR(40) NOT NULL DEFAULT 'standard' CHECK (ticket_type IN ('standard', 'vip', 'speaker', 'volunteer', 'hackathon_participant')),
    qr_token_hash VARCHAR(64) NOT NULL, -- SHA-256 hash of the dynamic payload: HMAC(secret, ticket_id + event_id + user_id)
    status VARCHAR(30) NOT NULL DEFAULT 'registered' CHECK (status IN ('registered', 'waitlisted', 'checked_in', 'cancelled', 'no_show')),
    waitlist_position INT DEFAULT NULL,
    wallet_pass_serial VARCHAR(100), -- Apple Wallet serial number
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_event_user UNIQUE (event_id, user_id)
);

CREATE INDEX idx_tickets_event_status ON tickets(event_id, status);
CREATE INDEX idx_tickets_qr_token ON tickets(qr_token_hash);
CREATE INDEX idx_tickets_user ON tickets(user_id);

-- 6. Check-in Audit Logs (Ultra-fast optical verification records)
CREATE TABLE check_in_logs (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    event_id VARCHAR(36) NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    scanned_by_volunteer_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    scanned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verification_mode VARCHAR(20) NOT NULL CHECK (verification_mode IN ('online', 'offline_hmac', 'manual_override')),
    device_model VARCHAR(100), -- e.g. "iPhone 15 Pro, iOS 18" or "Pixel 8, Android 15"
    scan_duration_ms INT, -- Measurement of scanning speed for UX metrics (target < 500ms)
    notes TEXT
);

CREATE INDEX idx_checkin_event ON check_in_logs(event_id, scanned_at);
CREATE INDEX idx_checkin_volunteer ON check_in_logs(scanned_by_volunteer_id);

-- 7. Call for Papers (CFP) / Speaker Proposals Table
CREATE TABLE speaker_proposals (
    id VARCHAR(36) PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    speaker_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic VARCHAR(200) NOT NULL,
    abstract_text TEXT NOT NULL,
    target_audience_level VARCHAR(50) NOT NULL DEFAULT 'all' CHECK (target_audience_level IN ('beginner', 'intermediate', 'advanced', 'all')),
    preferred_duration_minutes INT NOT NULL DEFAULT 40,
    presentation_slide_url VARCHAR(500),
    status VARCHAR(30) NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted', 'under_review', 'accepted', 'rejected', 'withdrawn')),
    organizer_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cfp_event_status ON speaker_proposals(event_id, status);

-- 8. Hackathon Team Matchmaking (Smart matchmaking feature from survey)
CREATE TABLE team_matches (
    id VARCHAR(36) PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    captain_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_name VARCHAR(100) NOT NULL,
    project_idea TEXT,
    max_members INT NOT NULL DEFAULT 4,
    current_members_count INT NOT NULL DEFAULT 1,
    looking_for_roles TEXT, -- e.g. "Frontend (React), ML Engineer, UI/UX Designer"
    status VARCHAR(30) NOT NULL DEFAULT 'recruiting' CHECK (status IN ('recruiting', 'team_ready', 'closed')),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_teams_event ON team_matches(event_id, status);

-- 9. Hackathon Team Members
CREATE TABLE team_members (
    id VARCHAR(36) PRIMARY KEY,
    team_id VARCHAR(36) NOT NULL REFERENCES team_matches(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_in_team VARCHAR(100) NOT NULL, -- e.g. "Lead Backend", "UI/UX Designer"
    joined_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_team_user UNIQUE (team_id, user_id)
);

-- 10. Emergency Announcements (1-tap broadcast notifications from survey)
CREATE TABLE emergency_announcements (
    id VARCHAR(36) PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    author_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    title VARCHAR(150) NOT NULL,
    body_text TEXT NOT NULL,
    urgency_level VARCHAR(20) NOT NULL DEFAULT 'info' CHECK (urgency_level IN ('info', 'schedule_change', 'urgent_hall_shift', 'emergency')),
    sent_via_push BOOLEAN NOT NULL DEFAULT TRUE,
    sent_via_telegram BOOLEAN NOT NULL DEFAULT TRUE,
    push_delivered_count INT NOT NULL DEFAULT 0,
    telegram_delivered_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_emergency_event ON emergency_announcements(event_id, created_at);

-- Initial Mock Seed Data for Demonstration
INSERT INTO users (id, email, password_hash, full_name, role, organization_name, bio, skills_tags)
VALUES 
('usr-artem-001', 'artem.fpmi@bsu.by', '$2b$12$e8Yk23...mock', 'Артём Ковалёв', 'attendee', 'ФПМИ БГУ, 3 курс', 'Студент 3 курса, интересуюсь Web и AI митапами', 'TypeScript,React,Python'),
('usr-daria-002', 'daria.vol@bsu.by', '$2b$12$k8Lm45...mock', 'Дарья Мельникова', 'volunteer', 'ФПМИ БГУ, 2 курс', 'Координатор стойки регистрации и логистики', 'Communication,Event Coordination'),
('usr-maxim-003', 'maxim.lead@itclub.by', '$2b$12$p9Qv78...mock', 'Максим Романов', 'organizer', 'BSU Tech Community', 'Основатель студенческого IT-клуба, организатор хакатонов', 'Project Management,Leadership,Go'),
('usr-kirill-004', 'kirill.dev@gmail.com', '$2b$12$w3Rt99...mock', 'Кирилл Савицкий', 'team_lead', 'ФПМИ БГУ, 4 курс', 'Fullstack разработчик, капитан команды хакатона', 'React,Node.js,PostgreSQL,Docker'),
('usr-viktor-005', 'viktor.tech@yandex.by', '$2b$12$q1Wz22...mock', 'Виктор Громов', 'speaker', 'Wargaming / Independent', 'Senior Backend Architect, ментор и докладчик', 'Distributed Systems,Golang,Kafka'),
('usr-sergey-006', 'decanat.sn@bsu.by', '$2b$12$m7Xy55...mock', 'Сергей Николаевич Котов', 'admin', 'Деканат ФПМИ БГУ', 'Заместитель декана по воспитательной работе, куратор клубов', 'Administration,Policy'),
('usr-vlad-007', 'vlad.freebie@mail.ru', '$2b$12$z9Pp11...mock', 'Влад Костылев', 'attendee', 'Студент', 'Любитель бесплатного мерча и пиццы', 'Pizza,Stickers,Freebies');

INSERT INTO venues (id, name, address, latitude, longitude, osm_place_id, building, room, total_capacity, navigation_instructions)
VALUES
('ven-bsu-fpmi-01', 'Главный лекторий ФПМИ БГУ', 'г. Минск, пр-т Независимости, 4', 53.8930090, 27.5468790, 102938475, 'Главный корпус', 'Ауд. 512 (Большая физическая)', 120, 'Вход с университетского дворика, 5 этаж, левое крыло');

INSERT INTO events (id, slug, title, short_summary, description, event_type, status, venue_id, start_time, end_time, registration_deadline, capacity_limit, organizer_user_id)
VALUES
('ev-campusmeet-2026', 'bsu-campus-meet-autumn-2026', 'CampusMeet Minsk: AI & Web Tech Autumn 2026', 'Главный студенческий митап по современным технологиям разработки', 'Ежегодный открытый митап студентов и IT-инженеров ФПМИ БГУ с треками Web-разработки, Machine Learning и презентацией проектов хакатона.', 'meetup', 'registration_open', 'ven-bsu-fpmi-01', '2026-10-15 16:00:00+03', '2026-10-15 20:30:00+03', '2026-10-14 23:59:00+03', 100, 'usr-maxim-003');

INSERT INTO schedule_items (id, event_id, track_name, title, description, speaker_user_id, speaker_display_name, start_time, end_time, is_keynote, presentation_url)
VALUES
('sch-item-01', 'ev-campusmeet-2026', 'Основной трек: Web & AI', 'Открытие CampusMeet 2026 и приветственное слово оргкомитета', 'Приветствие участников, обзор регламента хакатона и представление жюри.', 'usr-maxim-003', 'Максим Романов', '2026-10-15 16:00:00+03', '2026-10-15 16:20:00+03', FALSE, NULL),
('sch-item-02', 'ev-campusmeet-2026', 'Основной трек: Web & AI', 'Архитектура отказоустойчивых распределенных микросервисов на Go и Kafka', 'Паттерны Outbox, Saga, CQRS, Offline-First синхронизация и Zero-Downtime деплой.', 'usr-viktor-005', 'Виктор Громов', '2026-10-15 16:20:00+03', '2026-10-15 17:15:00+03', TRUE, 'https://slides.com/viktorgromov/distributed-arch-2026'),
('sch-item-03', 'ev-campusmeet-2026', 'Основной трек: Web & AI', 'Кофе-брейк, пицца и нетворкинг-биржа команд хакатона', 'Свободное общение, поиск тиммейтов по стеку (Frontend, ML, UI/UX) и менторские консультации.', NULL, 'Оргкомитет', '2026-10-15 17:15:00+03', '2026-10-15 17:50:00+03', FALSE, NULL),
('sch-item-04', 'ev-campusmeet-2026', 'Основной трек: Web & AI', 'Питчи проектов хакатона и награждение победителей', 'Демонстрация прототипов команд, оценка жюри и вручение призов.', 'usr-kirill-004', 'Кирилл Савицкий (AlphaDevs)', '2026-10-15 17:50:00+03', '2026-10-15 20:15:00+03', FALSE, NULL);

INSERT INTO speaker_proposals (id, event_id, speaker_user_id, topic, abstract_text, target_audience_level, preferred_duration_minutes, presentation_slide_url, status, organizer_notes)
VALUES
('spk-prop-01', 'ev-campusmeet-2026', 'usr-viktor-005', 'Архитектура отказоустойчивых распределенных микросервисов на Go и Kafka', 'Практический опыт проектирования масштабируемых систем с высокими требованиями к доступности и минимальным latency.', 'advanced', 45, 'https://slides.com/viktorgromov/distributed-arch-2026', 'accepted', 'Одобрено Максимом Романовым. Ключевой доклад программы.');

INSERT INTO tickets (id, ticket_code, event_id, user_id, ticket_type, qr_token_hash, status, wallet_pass_serial)
VALUES
('tkt-artem-01', 'CMP-2026-X89K', 'ev-campusmeet-2026', 'usr-artem-001', 'standard', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'checked_in', 'PASS-APPLE-CMP-X89K'),
('tkt-kirill-02', 'CMP-2026-K77T', 'ev-campusmeet-2026', 'usr-kirill-004', 'hackathon_participant', 'ca978112ca1bbdcafac231b39a23dc4da78608142961642f61fdf989a41e3a1a', 'registered', NULL),
('tkt-viktor-03', 'CMP-2026-S01V', 'ev-campusmeet-2026', 'usr-viktor-005', 'speaker', '4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce', 'registered', NULL),
('tkt-vlad-04', 'CMP-2026-V07F', 'ev-campusmeet-2026', 'usr-vlad-007', 'standard', '4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a', 'cancelled', NULL);

INSERT INTO check_in_logs (id, ticket_id, event_id, scanned_by_volunteer_id, scanned_at, verification_mode, device_model, scan_duration_ms, notes)
VALUES
('chk-log-01', 'tkt-artem-01', 'ev-campusmeet-2026', 'usr-daria-002', '2026-10-15 15:52:14+03', 'offline_hmac', 'Google Pixel 7, Android 14', 320, 'Успешный проход за 320 мс в автономном режиме без интернета');

INSERT INTO team_matches (id, event_id, captain_user_id, team_name, project_idea, max_members, current_members_count, looking_for_roles, status)
VALUES
('team-alpha-01', 'ev-campusmeet-2026', 'usr-kirill-004', 'AlphaDevs', 'Интеллектуальная система рекомендаций студенческих проектов и стажировок', 4, 2, 'UI/UX Designer, ML Engineer', 'recruiting');

INSERT INTO team_members (id, team_id, user_id, role_in_team)
VALUES
('tm-mem-01', 'team-alpha-01', 'usr-kirill-004', 'Lead Backend / Team Lead'),
('tm-mem-02', 'team-alpha-01', 'usr-artem-001', 'Frontend Developer');

INSERT INTO emergency_announcements (id, event_id, author_user_id, title, body_text, urgency_level, sent_via_push, sent_via_telegram, push_delivered_count, telegram_delivered_count)
VALUES
('emg-ann-01', 'ev-campusmeet-2026', 'usr-maxim-003', 'Внимание: перенос в аудиторию 519', 'В связи с заменой мультимедийного проектора в ауд. 512 открытие митапа и доклады перенесены в ауд. 519 (правое крыло, 5 этаж). Навигация обновлена.', 'urgent_hall_shift', TRUE, TRUE, 82, 75);
