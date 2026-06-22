# Announcements Stage 1 — Basic Posts

## Goal
Add a public announcements feed where any authenticated user can create posts with optional title, text, and image/video attachments. Pinned posts stay at the top. Each post has its own page at `/a/{id}`. Moderators can pin, edit, or delete any post.

## Acceptance Criteria
- Authenticated users can create posts with optional title, content, and attachments.
- Posts support image and video attachments.
- Pinned posts always appear first in the feed, capped at 3.
- Feed supports pagination (load more).
- Each post has a dedicated page at `/a/{id}`.
- Authors, admins, lotos, and leaders can edit/delete a post; editing is inline on the post page.
- Admins, lotos, and leaders can pin/unpin posts.
- New posts trigger SSE `announcement` event for all online users and a toast/badge.
- All endpoints have tests.

## File Structure
- `models.py` — add `Announcement` and `AnnouncementAttachment`
- `alembic/versions/...` — migration for new tables
- `routers/announcements.py` — API routes for CRUD + pin
- `templates/announcements.html` — feed page
- `templates/announcement.html` — single post page
- `templates/base.html` — add navigation tab
- `static/sw.js` — handle `announcement` SSE notifications
- `tests/test_announcements.py` — tests

## Data Model

```python
class Announcement(Base):
    __tablename__ = "announcements"
    id          = Column(Integer, primary_key=True)
    author_id   = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title       = Column(String, nullable=True)
    content     = Column(Text, nullable=False)
    is_pinned   = Column(Boolean, default=False, index=True)
    created_at  = Column(DateTime, server_default=func.now(), index=True)
    updated_at  = Column(DateTime, server_default=func.now(), onupdate=func.now())

    author = relationship("User")
    attachments = relationship("AnnouncementAttachment", cascade="all, delete", order_by="AnnouncementAttachment.id")

class AnnouncementAttachment(Base):
    __tablename__ = "announcement_attachments"
    id              = Column(Integer, primary_key=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False, index=True)
    file_path       = Column(String, nullable=False)
    file_type       = Column(String, nullable=False)  # 'image' | 'video'
    created_at      = Column(DateTime, server_default=func.now())
```

## Permissions
- Create: any authenticated user
- Edit/delete: author OR admin OR lotos OR leader
- Pin/unpin: admin OR lotos OR leader
- Max 3 pinned posts

## Endpoints
- `GET /announcements` — feed HTML
- `GET /api/announcements?limit=10&offset=0` — feed JSON
- `GET /a/{id}` — single post HTML
- `GET /api/announcements/{id}` — single post JSON
- `POST /api/announcements` — create post (multipart/form-data)
- `PUT /api/announcements/{id}` — edit post (multipart/form-data)
- `DELETE /api/announcements/{id}` — delete post
- `POST /api/announcements/{id}/pin` — pin/unpin toggle

## Attachments
- Stored in `static/uploads/announcements/`
- Filenames: `{uuid}{ext}`
- Image MIMEs: image/jpeg, image/png, image/gif, image/webp
- Video MIMEs: video/mp4, video/quicktime, video/webm
- Max image size: 100 MB
- Max video size: 2 GB

## Notifications
- `POST /api/announcements` calls `sse_manager.broadcast({"type": "announcement", "post_id": id, "title": ...})`
- `base.html` SSE listener handles `announcement` events and shows toast + badge if not on `/announcements` or `/a/*`

## UI
- New bottom nav tab "Объявления" for all authenticated users
- Feed shows pinned cards first, then chronological
- Card click navigates to `/a/{id}`
- "Новый пост" modal on feed page
- Inline editing on post page

## Tests
- `test_create_announcement`
- `test_edit_announcement_by_author`
- `test_edit_announcement_by_moderator`
- `test_edit_announcement_by_other_fails`
- `test_delete_announcement`
- `test_pin_unpin_authorized`
- `test_pin_unpin_unauthorized_fails`
- `test_max_three_pinned`
- `test_feed_pagination`
- `test_single_post_page`
- `test_image_attachment_validation`
- `test_video_attachment_validation`
