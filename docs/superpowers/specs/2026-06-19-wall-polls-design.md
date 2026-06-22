# Wall Stage 3: Polls / Surveys Design

## Goal
Allow any authorised user to attach a poll to an announcement post. Polls support single-choice, multiple-choice, and free-text answers, with live results shown to voters.

## User requirements
- Any authenticated user can create a poll when creating or editing a post.
- A poll belongs to one announcement.
- Poll options support three answer types:
  - **single** — choose exactly one option (radio)
  - **multiple** — choose any number of options (checkbox)
  - **text** — free-text answer
- The post author chooses poll type when creating it.
- Any authenticated user can vote once per poll.
- Results are visible immediately after voting (and to the post author at any time).
- Voters can change their vote.
- The post author and moderators can delete the poll or reset its votes.

## Architecture
- Backend: new `AnnouncementPoll` and `PollVote` models. New API endpoints under `/api/announcements/{post_id}/poll` for CRUD and voting.
- Frontend: poll builder inside the create/edit post form; poll renderer and voting UI on the single-post page and in the feed preview.

## Data model

### AnnouncementPoll
```python
class AnnouncementPoll(Base):
    __tablename__ = "announcement_polls"

    id              = Column(Integer, primary_key=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False, unique=True, index=True)
    question        = Column(String, nullable=False)
    poll_type       = Column(String, nullable=False)  # "single", "multiple", "text"
    is_anonymous    = Column(Boolean, default=False)
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

    announcement = relationship("Announcement", back_populates="poll")
    options      = relationship("PollOption", back_populates="poll", cascade="all, delete", order_by="PollOption.id")
```

### PollOption
```python
class PollOption(Base):
    __tablename__ = "poll_options"

    id          = Column(Integer, primary_key=True)
    poll_id     = Column(Integer, ForeignKey("announcement_polls.id"), nullable=False, index=True)
    label       = Column(String, nullable=False)
    sort_order  = Column(Integer, default=0)

    poll = relationship("AnnouncementPoll", back_populates="options")
```

### PollVote
```python
class PollVote(Base):
    __tablename__ = "poll_votes"

    id            = Column(Integer, primary_key=True)
    poll_id       = Column(Integer, ForeignKey("announcement_polls.id"), nullable=False, index=True)
    option_id     = Column(Integer, ForeignKey("poll_options.id"), nullable=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    text_answer   = Column(Text, nullable=True)
    created_at    = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("poll_id", "user_id", "option_id", name="uq_poll_vote_per_option_user"),
    )
```

## API endpoints
- `GET /api/announcements/{post_id}/poll` — get poll with options and aggregated results.
- `POST /api/announcements/{post_id}/poll` — create a poll (post author only, when editing post).
- `PUT /api/announcements/{post_id}/poll` — update poll question/type/options (post author only before first vote).
- `DELETE /api/announcements/{post_id}/poll` — delete poll (post author or moderator).
- `POST /api/announcements/{post_id}/poll/vote` — submit or replace vote.
- `DELETE /api/announcements/{post_id}/poll/vote` — remove own vote.

## Frontend
- Create/edit post form: toggle «Добавить опрос», question input, type selector, dynamic option list.
- Single-post page: render poll; if not voted — show form; if voted — show results + button «Изменить голос».
- Feed preview: show small «Опрос» badge on posts with polls.

## Open questions / decisions
- Anonymous vs public votes: default anonymous. For single/multiple we show counts only; for text we show answers only to post author if anonymous.
- One vote per user overall for the poll. For multiple-choice, a vote is a set of option selections.
- Editing a poll is allowed only before any votes are cast.

## Out of scope
- Poll deadlines / closing
- Poll notifications (can reuse comment notification if needed later)
- Image options
