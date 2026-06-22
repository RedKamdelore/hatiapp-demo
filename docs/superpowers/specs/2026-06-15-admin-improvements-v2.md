# Admin Panel Improvements: Mobile Mass Actions, Audit Logs, URL Filters, Direction Management

## Goal
Extend the admin panel with four independent improvements: mobile bulk actions, an audit log for mass actions, filter state in the URL, and in-place direction editing/deletion.

## Context
- Project folder: `C:\Users\Administrator\Desktop\САМОПАЛ\Hatiapp_cowork_OPENCODE`
- Recent work added client-side filters (role/status/direction) and bulk actions (activate/deactivate/delete/change-role/add-to-direction/remove-from-direction) to the desktop admin table.
- Mobile view uses `.mobile-user-card` elements with search but no bulk actions.
- `ActivityLog` exists but is not suitable for admin audit; a dedicated `AdminActionLog` table is required.
- `Direction` already has `name` and `description` columns; deletion currently cascades to slots and leaders.

## Requirements

### 1. Mobile Mass Actions
- Add a checkbox to the left of each `.mobile-user-card`.
- Add a "Select all" checkbox in the mobile panel header.
- Show a fixed bottom action bar when at least one card is selected.
- Action bar contains the same buttons as desktop: activate, deactivate, delete, change role, add to direction, remove from direction.
- Tapping a card (outside the checkbox) still navigates to the profile.
- The existing hidden form `#mass-action-form` submits the same payload for desktop and mobile.

### 2. Audit Log for Mass Actions
- Create new model `AdminActionLog`:
  - `id: Integer PK`
  - `admin_id: Integer FK → users.id`
  - `action: String`
  - `target_count: Integer`
  - `details: Text` (JSON string)
  - `ip_address: String`
  - `user_agent: String`
  - `created_at: DateTime`
- Create Alembic migration.
- In `mass_action_users`, after a successful action, insert one `AdminActionLog` row with:
  - `action`, `admin_id` from session, list of `user_ids`, `new_role`/`direction_id` when relevant, request IP/user-agent.
- Add read-only page `/admin/action-logs` accessible only to admins, showing latest actions first with pagination (50 per page).

### 3. Filter State in URL
- When any filter or search changes, update the URL query string: `?q=...&role=...&status=...&direction=...&sort=...`.
- On page load, read the query string and apply values to filter controls and rows/cards.
- Sorting links already use `?sort=...`; ensure filters are preserved when sorting.
- Use `history.replaceState` to avoid adding history entries on every keystroke.

### 4. Direction Management
- In the admin panel, next to each direction name, add edit (pencil) and delete (trash) buttons.
- **Edit:** modal with inputs for name and description; submit to `POST /admin/direction/{id}/edit`.
- **Delete:** confirmation modal listing:
  - Number of slots that will be deleted
  - Number of bookings attached to those slots
  - Number of linked leaders
  - Number of linked volunteer preferences
- Endpoint `POST /admin/direction/{id}/delete` already exists; add validation that returns the counts above for the confirmation modal.
- New endpoint `POST /admin/direction/{id}/edit` updates name/description; reject duplicate names.

## Design

### Data Model
```python
class AdminActionLog(Base):
    __tablename__ = "admin_action_logs"
    id         = Column(Integer, primary_key=True)
    admin_id   = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action     = Column(String, nullable=False, index=True)
    target_count = Column(Integer, nullable=False, default=0)
    details    = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)

    admin = relationship("User")
```

### Backend Changes
- `models.py` — add `AdminActionLog`.
- `alembic/versions/..._add_admin_action_logs.py` — migration.
- `routers/admin.py`:
  - Extend `mass_action_users` to write one audit log row.
  - Add `/admin/direction/{id}/edit`.
  - Add `/admin/direction/{id}/delete-info` returning deletion impact counts (used by modal).
  - Add `/admin/action-logs` route and pass logs to new template.
- `templates/admin.html` — add mobile checkboxes/bottom bar, edit/delete direction buttons/modals, filter URL sync.
- `templates/action_logs.html` — new page.

### Frontend Changes
- Mobile checkboxes use same `name="user_ids"` and `value="{{ u.id }}"` as desktop.
- Bottom action bar mirrors desktop `#mass-actions` but is fixed to bottom on small screens.
- JS `syncFiltersFromURL()` reads query params on load.
- JS `updateURLFilters()` writes query params on filter change.
- Direction edit/delete modals in `admin.html` `modals` block (follow base.html pattern).

## Edge Cases
- Mobile and desktop checkboxes share state? Use separate checkboxes but same form submission.
- Selecting all on mobile selects only visible (filtered) cards.
- Audit log insert happens after DB commit or in same transaction; if audit write fails, mass action should still succeed (log is secondary).
- Empty direction name or duplicate name rejected with toast error.
- Direction delete confirmation warns about cascaded data loss.

## Testing Strategy
- `tests/test_admin_audit_logs.py`:
  - Mass action creates one `AdminActionLog` row.
  - Log contains correct action, admin_id, target_count, details.
  - `/admin/action-logs` renders for admin, redirects non-admin.
- `tests/test_admin_directions.py`:
  - Edit direction name/description.
  - Reject duplicate name.
  - Delete-info endpoint returns correct counts.
  - Delete direction removes it and cascades slots.
- `tests/test_admin_filters_url.py`:
  - `/admin?q=...&role=...` renders with filters pre-applied.
- `tests/test_admin_mobile_mass_actions.py`:
  - Smoke test that mobile cards contain checkboxes and bottom bar markup.

## Out of Scope
- Real-time audit log streaming
- Export audit logs
- Server-side pagination/filtration for user table
- Soft-delete for directions
