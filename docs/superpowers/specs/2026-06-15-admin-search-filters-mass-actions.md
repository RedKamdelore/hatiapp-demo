# Admin Panel: Search, Filters & Mass Actions

## Goal
Improve the admin panel (`/admin`) so the administrator can quickly find the right group of users and perform bulk operations on them: filters by role, status and direction, plus bulk role changes and direction assignment/removal.

## Context
- Project folder: `C:\Users\Administrator\Desktop\САМОПАЛ\Hatiapp_cowork_OPENCODE`
- Current admin panel already has:
  - Client-side search by full name / username
  - Column sorting
  - Bulk activate / deactivate / delete via `POST /admin/users/mass-action`
  - Checkboxes and a hidden form
- Users can have roles: `admin`, `leader`, `lotos`, `volunteer`, `permanent`
- Leaders are linked to directions via `DirectionLeader`
- Volunteers may have preferred directions via `UserPreference` and actual bookings via `Booking`

## Requirements

### Filters
1. **Role filter** — dropdown: all / admin / leader / lotos / volunteer / permanent
2. **Status filter** — dropdown: all / active / blocked
3. **Direction filter** — dropdown: all + list of existing directions
   - For `leader` users: match against their `led_directions`
   - For `volunteer` users: match against their `preferences` **or** their `bookings`
   - For other roles: no match unless a direction is not selected
4. All filters are client-side for now (current user base fits in memory)
5. Search remains client-side by full name / username / role
6. Filter state should be reflected in the visible rows count label

### Mass Actions
1. Keep existing mass actions: activate, deactivate, delete
2. Add **Change role** — select target role (`leader`, `lotos`, `volunteer`, `permanent`; **not** `admin`)
3. Add **Add to direction** — select direction, then:
   - For `leader`: create `DirectionLeader` link
   - For `volunteer`: create `UserPreference` link
   - For other roles: no-op (can show an info message)
4. Add **Remove from direction** — select direction, then:
   - For `leader`: delete matching `DirectionLeader` link
   - For `volunteer`: delete matching `UserPreference` link
   - Other roles: no-op
5. Admin users must never be deleted or deactivated by mass actions (existing behavior)
6. Changing role of a user must keep the change within allowed roles

## Design

### Backend
- Extend `POST /admin/users/mass-action` in `routers/admin.py`
- Add hidden form field `direction_id` and `new_role` for role-change / direction actions
- Actions:
  - `activate` / `deactivate` / `delete` — existing logic
  - `change_role` — update role for non-admin users; reject `admin` target
  - `add_to_direction` — add link based on current role
  - `remove_from_direction` — remove link based on current role
- Preserve toast redirect with count

### Frontend
- Add filter controls in `templates/admin.html` next to the search box
- Add `data-role`, `data-status`, `data-directions` attributes to each row
- Direction data attribute format: comma-separated direction IDs from all relevant relations
- Add new mass-action buttons/dropdowns:
  - "Change role" with `<select name="new_role">`
  - "Add to direction" with `<select name="direction_id">`
  - "Remove from direction" with `<select name="direction_id">`
- Keep hidden form pattern; JS will copy `direction_id` / `new_role` into the form before submit
- Mobile user cards (`mobile-user-card`) must also get matching data attributes and filtering support

### Data Flow
1. Admin checks users
2. Selects action and required secondary value (role / direction)
3. JS injects hidden inputs for selected user IDs and the secondary value
4. Form submits to `/admin/users/mass-action`
5. Server processes, commits, redirects to `/admin` with success toast

## Edge Cases
- No users selected → show error toast (existing behavior)
- Selected admin + deactivate/delete → admin is skipped (existing behavior)
- Direction added to volunteer who already has it as preference → unique constraint; silently skip
- Leader removed from direction where they are not assigned → silently skip
- Mass role change to `admin` → server rejects / ignores
- Mobile view: filters collapse or wrap; cards update same as table rows

## Testing Strategy
- Unit tests in `tests/test_admin_mass_actions.py`:
  - Mass activate / deactivate / delete
  - Mass change role excludes `admin` target
  - Mass add to direction for leader creates `DirectionLeader`
  - Mass add to direction for volunteer creates `UserPreference`
  - Mass remove from direction removes the link
  - Admin user cannot be deleted/deactivated
- Verify UI renders filter controls and data attributes (smoke via admin page HTML)

## Out of Scope
- Server-side pagination or search
- Export filtered user list
- Undo for mass actions
- Audit log entries for mass actions
