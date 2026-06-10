## Goal
- Implement user presence tracking (arrival/departure dates) and update print schedule for A4 landscape with three columns.

## Constraints & Preferences
- Local network only (no internet); SQLite; no HTTPS
- ~100 concurrent users; first-come-first-served slot booking with no waitlists
- User prefers honest "Записываем..." loading state over optimistic UI
- Russian-language UI; must work on phones (Android + iPhone)
- No Service Worker/PWA caching (removed after causing blank screens)
- Day of arrival and day of departure = absence (no shifts)
- Users without dates are considered inactive/blocked

## Progress
### Done
- Cleaned `__pycache__`/`.pyc` and added `.gitignore`
- Created `requirements.txt` and `pyproject.toml` dependencies
- Moved `SECRET_KEY` to `.env` via `pydantic-settings` (`config.py`)
- Removed CSRF (broken for local HTTP login); kept rate limiting (`slowapi`, 10/min on `/login`)
- Added Alembic migrations (initial + indexes + `description` column + `direction_multi_leaders` + `add_login_logs` + `add_arrival_departure_dates_and_checked_in`)
- Added SQLAlchemy indexes on `slots`, `bookings`, `chat_messages`, `activity_log`
- Converted roles to `StrEnum` (`UserRole` in `config.py`)
- Added 2MB avatar upload limit in `profile.py`
- Added logs pagination (`page`, `per_page`, `total_pages`) in `logs.py`/`logs.html`
- Created `schemas.py` with Pydantic models
- Created `tests/conftest.py` + `tests/test_auth.py` + `tests/test_booking.py` (24 tests, 23 passing, 1 skipped)
- Reseeded default users: `ADIMA`/`ADIMA`, `leader1`/`leader123`, `vol1`/`vol123`, `lotos`/`lotos123`
- **Rewrote admin panel** (`admin.html`) with CSS Grid two-column layout (main + 300px sidebar), dark mode support, search, sort by name/username/role/status, mass actions, attendance chart, role distribution stats
- Added `BlockedDay` model/migration and admin UI; integrated blocked day visualization in `schedule.html` (🔒 red background) and `slots.html`; server-side booking prevention in `book_slot()`
- Changed blocked-day picker from `input type="date"` to `select` populated only with loaded schedule dates
- Optimized chat for multiple lotos: volunteers see all lotos messages in one chat; lotos sees all volunteer dialogs; added dynamic WebSocket card creation for new dialogs in `chat_lotos.html`
- Added toast notification system (`showToast()` in `base.html`) with query-param redirects
- Added Web Audio API beep for new chat messages
- Added `attendance_chart` canvas bar chart in `admin.html`
- Added mass-action checkboxes + toolbar in admin user table (`/admin/users/mass-action`)
- Added drag-and-drop Excel import on `import_users.html` and `import_schedule.html`
- Added global 500 exception handler with `templates/error.html` (friendly "😿" page)
- Added nightly SQLite backup script `backup_db.py` (keeps last 7 copies)
- Enabled WAL mode + `pool_pre_ping` in `database.py` for ~100 user concurrency
- Added lotos report Excel export (`/admin/lotos-report`)
- Implemented WebSocket chat (`/ws/chat`) with auto-reconnect and token-based auth fallback
- Implemented SSE notifications (`/sse/notify`) replacing polling
- Added PWA manifest + icons (`static/manifest.json`, `icon-192.png`, `icon-512.png`)
- **Removed Service Worker** (`static/sw.js` deleted) — was caching broken responses causing blank screens; added unregister script in `base.html`
- Fixed QR codes on login page with auto-IP detection; removed broken CSRF JS that blocked form submission
- Added `SELECT FOR UPDATE` + retry logic in `book_slot()` to prevent race conditions
- Added loading state `⟳ Записываем...` on booking/cancel buttons in `slots.html`
- **Fixed booking buttons** — added missing `type="submit"` in `slots.html` forms
- Added `cancel_deadline_ok()` check — cannot cancel booking within 24 hours of slot start
- Optimized polling intervals to 10 seconds (schedule, slots)
- Fixed `base.html` structure (removed stray text outside `<script>` tags)
- Fixed nested forms in `admin.html` (moved mass-action form outside user table)
- Created `CONTEXT.md` — project architecture, stack, patterns documentation for AI assistants
- **Converted Excel schedule** (`Наметки Расписания 26 ГОТОВОЕ.xlsx`) to `schedule_import.xlsx` with 169 entries (6 shifts/day including 07:00 breakfast)
- **Added direction editing** in slots editor (`/admin/slots`): edit name + description inline with API endpoint `/admin/directions/{id}/update`
- **Dark theme support** for `admin_slots.html` — added `.dark` CSS overrides for all card/input/status colors
- **Fixed "lotos" role** in `edit_user.html` and `admin.py` — was being reset to volunteer due to missing `ROLE_LOTOS` in validation tuple
- **Multi-leader directions**: added `DirectionLeader` association table (direction_id + user_id composite PK), replaced `leader_id` on `Direction` with `leaders` relationship
- **Alembic migration `68bb4f72a251`**: migrates existing `leader_id` data to `direction_leaders` table, drops old column
- **Admin multi-leader UI**: chip-style badges with ✕ remove button + dropdown to add leaders; shows "Руководители: Name1, Name2" in schedule
- **Leader panel** (`leader.py`): supports multiple directions per leader; `get_directions()` returns list; all routes check `direction_ids` set
- **Schedule** (`schedule.py`): loads leaders via `joinedload` to prevent N+1
- **Navigation fix**: removed `page-leaving` CSS animation causing blank screens on back button; added `pageshow` event handler with `event.persisted` → `location.reload()` for bfcache recovery; added `NoCacheMiddleware` in `main.py` setting `Cache-Control: no-store` on HTML responses
- **Admin counters**: added `total_capacity` (695) and `total_human_shifts` (690 = volunteers × schedule_days × BOOKINGS_PER_DAY) to stats cards
- **Login logs**: added `LoginLog` model (id, user_id, ip_address, mac_address, user_agent, device_type, created_at); migration `4b5c264aa835`; logs auto-created on successful login via `_log_login()` in `auth.py`; device type detected from User-Agent (mobile/desktop/tablet); admin view at `/admin/login-logs` with pagination
- **Mobile admin redesign**: replaced horizontal-scrolling tables with stacked card layouts on phone; added search filter (`filterMobileUsers()`) for mobile user cards
- **Mobile schedule redesign (Вариант Б)**: horizontal day selector strip (like iPhone calendar) at top; large tappable slot cards below with `active:scale-95` feedback; no horizontal scrolling
- **QR Code Modal**: converted QR display in `/me` from separate page to animated modal popup (`/api/qr/{booking_id}` returns base64 JSON; modal with loading spinner, close on Escape/click-outside)
- **Print Schedule Page** (`/admin/print`): three-column landscape A4 layout; each direction as separate table (no column splitting); date dropdown showing only dates with slots; statistics header; compact print styles (`@media print { size: A4 landscape }`)
- **Day Status Grid**: changed day status badges in `schedule.html` from `flex-wrap` to CSS Grid `repeat(N, 1fr)` for even distribution
- **User Presence Tracking**:
  - Added `arrival_date` (Date), `departure_date` (Date), `checked_in` (Boolean) to `User` model
  - Alembic migration `5de1f51bbe6c` applied successfully
  - `user_is_present(user, target_date)` in `services/booking.py` — returns True only if `arrival_date < target_date < departure_date`
  - `book_slot()` blocks booking outside presence days with message: "Волонтёр ещё не заехал/уже выехал. Обратитесь к Лотосу или руководителю."
  - Admin panel: edit arrival/departure dates in `edit_user.html`; columns in `admin.html` table (Заезд, Отъезд, Прибыл)
  - Logs page (`/logs/day/{date}`): `_get_not_booked()` filters to volunteers physically present on target date; check-in button sets `checked_in = True`
  - Excel import: columns E (arrival) and F (departure) parsed in `import_users.py`
  - Schedule page: toast warnings for presence errors (`error` query param handling)
  - 6 new tests in `tests/test_booking.py::TestPresenceDays` — all passing
- **Logs page bug fix**: `/logs` showed "Расписание не загружено" because `logs_page` passed `dates` but template expected `days`; fixed by building proper `days` structure with total/present/not_booked_count/all_ok
- **Edit user labels**: changed "(не работает)" to "(в этот день нет на смене)" for clarity on arrival/departure date fields
- **Volunteer Excel Import Completed** (`Анкеты Хати 2026 (1).xlsx`):
  - Created `import_ankety.py` script to process volunteer applications
  - Parsed 20 date columns (June–July 2026) from headers
  - Extracted arrival_date = first "Да" day; departure_date = last "Да" day + 1
  - Created **91 new volunteer users** with presence dates
  - Reset passwords for all 91 users and saved to `volunteer_passwords.txt` (username|password|name|arrival|departure)
  - 81 existing volunteers without dates remain in DB (need manual review or deletion)
  - All new users have `is_active=True` and valid date ranges overlapping schedule (9–13 July 2026)
- **Day Coverage Shortage Tracker**:
  - Added shortage calculation to `/logs` and `/admin` pages only (removed from public `/schedule`)
  - **Formula**: `needed_people = ceil(total_capacity / BOOKINGS_PER_DAY)`; `shortage = max(0, needed_people - available_people)`
  - Shows per-day: available people in camp, needed people, shortage count
  - Visual indicators: green "✓ Ок" when enough people, red "-N" with shortage count
  - Admin sidebar: scrollable list of all days with total shortage at bottom
  - Logs page: shows available people, needed people, and shortage in day cards
- **Mobile Logs Page (`/logs/day/{date}`) Redesign**:
  - Fixed cramped booking form on mobile: elements now stack vertically on small screens
  - Volunteer card: `flex-col` on mobile → `sm:flex-row` on desktop
  - Booking form: full-width selects + button on mobile → inline layout on `sm+`
  - Button and selects use `w-full` on mobile, `sm:w-auto` on desktop
  - Avatar + name remain in one row, form drops below on narrow screens
  - **Long usernames**: added `truncate max-w-[90px]` to prevent overflow
  - **Check-in toggle**: button now toggles `checked_in` state (POST `/logs/user/{id}/toggle-check-in`)
  - **Check-in button contrast**: gray outline when unchecked, green filled when checked
  - **Search by name/username**: added live filter input above volunteer list with `data-search` attribute
- **Permanent Role ("Бессменные")**:
  - Added `PERMANENT = "permanent"` to `UserRole` StrEnum
  - Added `ROLE_PERMANENT` constant in `config.py`
  - **No shift booking required**: added to `NO_LIMIT_ROLES` alongside admin/leader/lotos
  - **Not counted for shift coverage**: excluded from "people in camp" calculations for shortage tracker (they work separately)
  - **Admin UI**: teal-colored badges, listed in role distribution stats
  - **Edit user**: available in role dropdown as "Бессменный"
  - **Auth**: redirects to `/schedule` after login
  - **Import**: accepted in Excel import (`ALLOWED_ROLES`)

### In Progress
- (none)

### Blocked
- (none)

## Key Decisions
- Removed CSRF entirely because `starlette-csrf` cookie-based flow failed over HTTP local network and blocked all logins; rate limiting retained as brute-force protection
- Used `select` dropdown for blocked days instead of calendar input to prevent scrolling through irrelevant dates
- Chat uses WebSocket (realtime) with polling fallback instead of pure polling
- Notifications use SSE instead of polling to reduce server load
- **No Service Worker / PWA caching** — caused blank screens on navigation; kept manifest.json only for install icon
- **No optimistic UI for booking** — user prefers honest "Записываем..." with disabled button
- SQLite `SELECT FOR UPDATE` + retry with exponential backoff chosen over PostgreSQL for simplicity in local network
- Skeleton loading removed from `schedule.html` because it blocked real content display
- Admin panel uses `max-width: 1400px` centered container with CSS Grid `1fr 300px` columns; flexbox proved unreliable with wide tables
- **Multi-leader directions**: one-to-many via `DirectionLeader` association table rather than array column, for SQLAlchemy compatibility and clean cascading deletes
- **No MAC address in logs**: impossible to obtain via HTTP (L7); field exists in schema but always NULL; would require native app or router access
- **Mobile schedule uses day selector strip**: more compact than full cards, large tap targets prevent misclicks, familiar calendar UX pattern
- **Arrival/departure days = absence**: strict inequality `arrival < target < departure`; days without dates default to always-present (backward compatibility)
- **Print uses three columns**: CSS Grid `repeat(3, 1fr)` in landscape A4; each direction is separate `<table>` with `<caption>` to prevent splitting across columns
- **Users without arrival/departure dates are blocked** (is_active = False) per admin request for volunteer import
- **Volunteer import logic**: first "Да" = arrival_date; last "Да" + 1 day = departure_date; users with no "Да" answers blocked; users completely outside schedule range blocked

- **PWA Offline Support (Service Worker)**:
  - Service Worker (`/sw.js`): caches static assets (Cache First), API responses (Network First), HTML pages (Network First with fallback)
  - Pre-cached critical pages: `/`, `/schedule`, `/me` on install
  - Offline banner: red banner "📡 Нет связи · Вы не в лагере" when offline
  - Auto-reload: only when transitioning from offline to online (not on every page load)
  - Action buttons disabled when offline with tooltip "Доступно только в лагере"
  - Overlay on forms: "⚠️ Только в лагере" overlay on booking/cancel forms
  - NoCacheMiddleware: allows `/static/` assets to be cached (excluded from no-cache headers)
  - Chat caching: last 50 messages stored in Service Worker cache
  - Offline fallback page: generic "Нет связи" page if no cached version available

- **PWA Offline Support (Service Worker)**:
  - Service Worker (`/sw.js`): caches static assets only (CSS, JS, icons)
  - **No HTML caching**: prevents showing stale/outdated data when offline
  - **Offline page**: beautiful "📡 Нет связи" page with auto-retry every 5 seconds
  - **Auto-reload**: page reloads automatically when connection restored
  - Offline banner: red banner "📡 Нет связи · Вы не в лагере" when offline
  - Action buttons disabled when offline with tooltip "Доступно только в лагере"
  - Overlay on forms: "⚠️ Только в лагере" overlay on booking/cancel forms
  - NoCacheMiddleware: allows `/static/` assets to be cached

## Next Steps
1. Test offline mode: visit `/schedule` online, wait for background caching, disconnect WiFi, open any day — should work
2. Verify all schedule days are cached after visiting main schedule page
3. Test auto-reload: reconnect WiFi, page should reload automatically
4. Verify booking buttons are blocked when offline
5. Test Service Worker update mechanism
6. Monitor cache size on mobile devices

## Critical Context
- Database is `app.db` (SQLite); WAL mode enabled; migrations via Alembic
- `models.py` includes `BlockedDay`, `Direction.description`, `DirectionLeader` (direction_id + user_id composite PK), `LoginLog` (ip, user_agent, device_type), `User.arrival_date`, `User.departure_date`, `User.checked_in`
- Default login: `ADIMA`/`ADIMA` (admin)
- Toast system reads `?toast=MSG&toast_type=success|error` from URL, shows floating banner, then cleans URL via `history.replaceState`
- Chat sound uses `AudioContext` oscillator (no external files); only plays for incoming messages not from current user
- WebSocket auth tries cookie first, falls back to `?token=` query param
- `book_slot()` uses `with_for_update()` + up to 3 retries with exponential backoff to prevent overbooking; also checks `BlockedDay` and `user_is_present()` before allowing booking
- `cancel_booking()` checks `cancel_deadline_ok()` — returns False if less than 24 hours before slot start
- Polling intervals: schedule 10s, slots 10s, chat WebSocket primary with 5s fallback
- Tests: 23 passing, 1 skipped (rate limit on `test_book_no_slots_endpoint`)
- Admin sort URL parameter: `?sort=name_asc|name_desc|username_asc|username_desc|role_asc|role_desc|status_asc|status_desc`
- **NoCacheMiddleware** in `main.py` sets `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` on all HTML/redirect responses
- `pageshow` event in `base.html` triggers `location.reload()` when `event.persisted` (bfcache recovery)
- Login logs page: `/admin/login-logs`, 50 entries per page, shows time, user, IP, device type (📱 mobile / 💻 desktop / 📟 tablet), user agent
- **Mobile user search**: `filterMobileUsers()` filters `.mobile-user-card` elements by `data-search` attribute (name + username + role)
- **QR modal**: fetch `/api/qr/{booking_id}` → returns `{qr_b64, booking_id, direction, date, time}`; displayed in centered modal with spinner, close on Escape/click-outside
- **Print schedule**: `@page { size: A4 landscape; margin: 6mm; }`; `.three-columns { grid-template-columns: repeat(3, 1fr); }`; each direction is separate `<table class="dir-table">` with `<caption class="dir-caption">`
- **Volunteer passwords**: saved in `volunteer_passwords.txt` (pipe-delimited: username|password|full_name|arrival_date|departure_date); 91 entries total
- **Current DB stats**: 91 volunteers with dates + 11 leaders/lotos with dates = 102 users with presence tracking; 80 volunteers total after deduplication cleanup
