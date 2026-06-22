# Wall Stage 2: Comments Design

## Goal
Add comments to announcements so authorised users can discuss posts. Comments show the commenter's role, link to their profile, support edit/delete by the author, and trigger notifications.

## User requirements
- Any authenticated user can add a comment to any post.
- Each comment shows: author name, author avatar, author role, comment text, creation time.
- Clicking the author name/avatar opens the commenter's profile (`/profile/<user_id>` or existing profile page).
- Authors can edit their own comments.
- Authors can delete their own comments.
- Admins/leaders can delete any comment (moderation).
- The post author receives a notification (toast + SSE push) when a new comment is added to their post.
- Comments are visible on the single-post page.

## Architecture
- Backend: new `AnnouncementComment` model linked to `Announcement` and `User`. New API endpoints under `/api/announcements/{post_id}/comments` for CRUD.
- Frontend: comment list + form rendered on `announcement.html`. Inline edit/delete buttons shown for the current user (or moderator).
- Notifications: reuse existing SSE `/sse/notify` channel with a new `comment` event type; show toast only if the current user is the post author and not already viewing that post.

## Data model
```python
class AnnouncementComment(Base):
    __tablename__ = 'announcement_comments'

    id: int PK
    announcement_id: int FK -> announcements.id (cascade delete)
    author_id: int FK -> users.id
    content: str
    created_at: datetime
    updated_at: datetime | None
```

## API endpoints
- `GET /api/announcements/{post_id}/comments` — list comments with author info.
- `POST /api/announcements/{post_id}/comments` — create comment.
- `PUT /api/announcements/{post_id}/comments/{comment_id}` — edit own comment.
- `DELETE /api/announcements/{post_id}/comments/{comment_id}` — delete own or moderate.

## Notification payload
```json
{
  "type": "comment",
  "post_id": 123,
  "post_title": "...",
  "comment_id": 456,
  "author_name": "..."
}
```

## Open questions
- Should we paginate comments or show all? (Recommendation: show all for now, simple scroll.)
- Should comment authors receive notifications on replies? (Out of scope for this stage; keep simple.)
