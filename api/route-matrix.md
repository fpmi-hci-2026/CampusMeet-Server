# Реестр маршрутов и трассируемость API

Сгенерировано `python3 scripts/export_contracts.py`. UC-01..05 сохранены из ЛР3.

| HTTP | Маршрут /api/v1 | operationId | Use Case | User Story | Доступ | Режим |
|:--|:--|:--|:--|:--|:--|:--|
| GET | `/health` | `health` | UC-14 | US-13 | public | stateful |
| POST | `/auth/token` | `demoLogin` | UC-14 | US-13 | public | stateful |
| GET | `/me` | `getProfile` | UC-14 | US-13 | authenticated | stateful |
| GET | `/events` | `listEvents` | UC-06 | US-08 | public | stateful |
| POST | `/events` | `createEvent` | UC-03 | US-05 | organizer | stateful |
| GET | `/events/{event_id}` | `getEvent` | UC-06 | US-08 | public | stateful |
| PUT | `/events/{event_id}` | `replaceEvent` | UC-03 | US-05 | organizer | stateful |
| DELETE | `/events/{event_id}` | `deleteDraft` | UC-03 | US-05 | organizer | stateful |
| POST | `/events/{event_id}/registrations` | `registerAttendee` | UC-01 | US-01,US-06 | authenticated | stateful |
| GET | `/me/tickets` | `listMyTickets` | UC-07 | US-02 | authenticated | stateful |
| GET | `/tickets/{ticket_id}` | `getTicket` | UC-07 | US-02 | owner | stateful |
| DELETE | `/tickets/{ticket_id}` | `cancelTicket` | UC-08 | US-14 | owner | stateful |
| GET | `/events/{event_id}/check-ins` | `listCheckIns` | UC-02 | US-03,US-04 | staff | stateful |
| POST | `/events/{event_id}/check-ins` | `checkIn` | UC-02 | US-03,US-04 | staff | stateful |
| POST | `/events/{event_id}/check-in-batches` | `syncCheckIns` | UC-02 | US-04 | staff | example |
| GET | `/events/{event_id}/schedule` | `getSchedule` | UC-09 | US-11 | public | example |
| PUT | `/events/{event_id}/schedule` | `replaceSchedule` | UC-09 | US-11 | organizer | example |
| PUT | `/me/schedule` | `replacePersonalSchedule` | UC-09 | US-15 | authenticated | example |
| GET | `/events/{event_id}/proposals` | `listProposals` | UC-04 | US-16 | organizer | example |
| POST | `/events/{event_id}/proposals` | `submitProposal` | UC-04 | US-16 | authenticated | example |
| PATCH | `/proposals/{proposal_id}` | `reviewProposal` | UC-04 | US-16 | organizer | example |
| GET | `/events/{event_id}/teams` | `listTeams` | UC-05 | US-07 | public | example |
| POST | `/events/{event_id}/teams` | `createTeam` | UC-05 | US-07 | authenticated | example |
| POST | `/teams/{team_id}/invitations` | `inviteMember` | UC-05 | US-07 | captain | example |
| PATCH | `/team-invitations/{invitation_id}` | `answerInvitation` | UC-05 | US-07 | owner | example |
| GET | `/search` | `search` | UC-06 | US-08 | public | stateful |
| POST | `/events/{event_id}/announcements` | `broadcast` | UC-10 | US-09 | organizer | example |
| GET | `/jobs/{job_id}` | `getJob` | UC-10 | US-09,US-12 | organizer | example |
| GET | `/tickets/{ticket_id}/wallet-pass` | `getWalletPass` | UC-11 | US-10 | owner | stateful |
| POST | `/events/{event_id}/attendance-exports` | `exportAttendance` | UC-12 | US-12 | organizer | example |
| GET | `/venues` | `listVenues` | UC-13 | US-05 | public | stateful |
| GET | `/integrations/geocoding` | `geocode` | UC-13 | US-05 | organizer | example |
| GET | `/integrations/holidays` | `holidays` | UC-13 | US-05 | organizer | example |
