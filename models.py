from sqlalchemy import Column, Integer, String, ForeignKey, Date, Time, Boolean, UniqueConstraint, Text, DateTime, Index, JSON
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from database import Base


class Direction(Base):
    __tablename__ = "directions"

    id          = Column(Integer, primary_key=True)
    name        = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)

    leaders = relationship("DirectionLeader", back_populates="direction", cascade="all, delete")
    slots  = relationship("Slot", back_populates="direction", cascade="all, delete")


class DirectionLeader(Base):
    """Связь многие-ко-многим: направление ↔ руководитель."""
    __tablename__ = "direction_leaders"

    direction_id = Column(Integer, ForeignKey("directions.id"), primary_key=True)
    user_id      = Column(Integer, ForeignKey("users.id"), primary_key=True)

    direction = relationship("Direction", back_populates="leaders")
    user      = relationship("User",     back_populates="led_directions")


class Slot(Base):
    __tablename__ = "slots"

    id           = Column(Integer, primary_key=True)
    direction_id = Column(Integer, ForeignKey("directions.id"), nullable=False, index=True)
    date         = Column(Date, nullable=False, index=True)
    time         = Column(Time, nullable=False)
    capacity     = Column(Integer, nullable=False, default=0)
    description  = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("direction_id", "date", "time", name="uq_slot"),
        Index("ix_slots_date_direction", "date", "direction_id"),
    )

    direction = relationship("Direction", back_populates="slots")
    bookings  = relationship("Booking",   back_populates="slot", cascade="all, delete")


class Booking(Base):
    __tablename__ = "bookings"

    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    slot_id = Column(Integer, ForeignKey("slots.id"), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("user_id", "slot_id", name="uq_booking"),
        Index("ix_bookings_slot_user", "slot_id", "user_id"),
    )

    user = relationship("User", back_populates="bookings")
    slot = relationship("Slot", back_populates="bookings")


class Attendance(Base):
    __tablename__ = "attendance"

    id         = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, unique=True)
    present    = Column(Boolean, default=True)
    marked_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    marked_at  = Column(DateTime, server_default=func.now())

    booking = relationship("Booking")
    marker  = relationship("User", foreign_keys=[marked_by])


class ChatRead(Base):
    __tablename__ = "chat_reads"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    other_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    read_at    = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "other_id", name="uq_chat_read"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id            = Column(Integer, primary_key=True)
    sender_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    receiver_id   = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    text          = Column(Text, nullable=False)
    attachment_url = Column(String, nullable=True)
    reply_to_id   = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    deleted_for   = Column(Text, nullable=True, default="[]")
    payload       = Column(JSON, nullable=True)
    created_at    = Column(DateTime, server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_chat_sender_receiver", "sender_id", "receiver_id"),
        Index("ix_chat_receiver_created", "receiver_id", "created_at"),
    )

    sender      = relationship("User", foreign_keys=[sender_id],   back_populates="sent_messages")
    receiver    = relationship("User", foreign_keys=[receiver_id], back_populates="received_messages")
    reply_to    = relationship("ChatMessage", remote_side=[id], backref="replies")


class ExchangeProposal(Base):
    __tablename__ = "exchange_proposals"

    id                  = Column(Integer, primary_key=True)
    sender_id           = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    receiver_id         = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sender_booking_id   = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    receiver_booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    status              = Column(String, nullable=False, default="pending")
    created_at          = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at          = Column(DateTime, nullable=False)
    resolved_at         = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("sender_id", "receiver_id", "status", name="uq_exchange_sender_receiver_status"),
    )

    sender   = relationship("User", foreign_keys=[sender_id], back_populates="sent_proposals")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_proposals")
    sender_booking   = relationship("Booking", foreign_keys=[sender_booking_id])
    receiver_booking = relationship("Booking", foreign_keys=[receiver_booking_id])


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    target_id  = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action     = Column(String, nullable=False, index=True)
    slot_id    = Column(Integer, ForeignKey("slots.id"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_activity_user_created", "user_id", "created_at"),
    )

    actor  = relationship("User", foreign_keys=[user_id])
    target = relationship("User", foreign_keys=[target_id])
    slot   = relationship("Slot")


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True)
    username      = Column(String, unique=True, index=True, nullable=False)
    full_name     = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role          = Column(String, nullable=False)
    is_active      = Column(Boolean, default=True)
    avatar         = Column(String, nullable=True)
    arrival_date   = Column(Date, nullable=True)
    departure_date = Column(Date, nullable=True)
    checked_in     = Column(Boolean, default=False)

    bookings          = relationship("Booking",        back_populates="user", cascade="all, delete")
    led_directions    = relationship("DirectionLeader", back_populates="user", cascade="all, delete")
    sent_messages     = relationship("ChatMessage",    foreign_keys="ChatMessage.sender_id",   back_populates="sender",   cascade="all, delete")
    received_messages = relationship("ChatMessage",    foreign_keys="ChatMessage.receiver_id", back_populates="receiver", cascade="all, delete")
    sent_proposals    = relationship("ExchangeProposal", foreign_keys="ExchangeProposal.sender_id", back_populates="sender", cascade="all, delete")
    received_proposals = relationship("ExchangeProposal", foreign_keys="ExchangeProposal.receiver_id", back_populates="receiver", cascade="all, delete")
    preferences       = relationship("UserPreference", back_populates="user", cascade="all, delete")
    announcements     = relationship("Announcement", back_populates="author", cascade="all, delete")


class UserPreference(Base):
    """Предпочитаемые направления пользователя — показываются первыми в расписании."""
    __tablename__ = "user_preferences"

    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    direction_id = Column(Integer, ForeignKey("directions.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "direction_id", name="uq_user_pref"),
    )

    user      = relationship("User",      back_populates="preferences")
    direction = relationship("Direction")


class BlockedDay(Base):
    """Заблокированные дни — в эти дни запись невозможна."""
    __tablename__ = "blocked_days"

    id      = Column(Integer, primary_key=True)
    date    = Column(Date, nullable=False, unique=True)
    reason  = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class LoginLog(Base):
    """Логи входов пользователей."""
    __tablename__ = "login_logs"

    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    ip_address  = Column(String, nullable=True)
    mac_address = Column(String, nullable=True)  # Недоступен через HTTP, всегда NULL
    user_agent  = Column(String, nullable=True)
    device_type = Column(String, nullable=True)  # 'mobile', 'desktop', 'tablet'
    created_at  = Column(DateTime, server_default=func.now(), index=True)

    user = relationship("User")


class AdminActionLog(Base):
    """Audit log for mass admin actions."""
    __tablename__ = "admin_action_logs"

    id           = Column(Integer, primary_key=True)
    admin_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action       = Column(String, nullable=False, index=True)
    target_count = Column(Integer, nullable=False, default=0)
    details      = Column(Text, nullable=True)
    ip_address   = Column(String, nullable=True)
    user_agent   = Column(String, nullable=True)
    created_at   = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    admin = relationship("User")


class AppSetting(Base):
    """Глобальные настройки приложения (ключ → значение)."""
    __tablename__ = "app_settings"

    key   = Column(String, primary_key=True)
    value = Column(Text, nullable=False, default="")


class Announcement(Base):
    __tablename__ = "announcements"

    id          = Column(Integer, primary_key=True)
    author_id   = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title       = Column(String, nullable=True)
    content     = Column(Text, nullable=False)
    is_pinned   = Column(Boolean, default=False, index=True)
    created_at  = Column(DateTime, server_default=func.now(), index=True)
    updated_at  = Column(DateTime, server_default=func.now(), onupdate=func.now())

    author = relationship("User", back_populates="announcements")
    attachments = relationship("AnnouncementAttachment", back_populates="announcement", cascade="all, delete", order_by="AnnouncementAttachment.id")
    comments = relationship("AnnouncementComment", back_populates="announcement", cascade="all, delete", order_by="AnnouncementComment.created_at")
    poll = relationship("AnnouncementPoll", back_populates="announcement", uselist=False, cascade="all, delete")
    reactions = relationship("AnnouncementReaction", back_populates="announcement", cascade="all, delete")


class AnnouncementAttachment(Base):
    __tablename__ = "announcement_attachments"

    id              = Column(Integer, primary_key=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False, index=True)
    file_path       = Column(String, nullable=False)
    file_type       = Column(String, nullable=False)
    created_at      = Column(DateTime, server_default=func.now())

    announcement = relationship("Announcement", back_populates="attachments")


class AnnouncementComment(Base):
    __tablename__ = "announcement_comments"

    id              = Column(Integer, primary_key=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False, index=True)
    author_id       = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content         = Column(Text, nullable=False)
    created_at      = Column(DateTime, server_default=func.now(), index=True)
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

    announcement = relationship("Announcement", back_populates="comments")
    author       = relationship("User")


class AnnouncementPoll(Base):
    __tablename__ = "announcement_polls"

    id              = Column(Integer, primary_key=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False, unique=True, index=True)
    question        = Column(String, nullable=False)
    poll_type       = Column(String, nullable=False)
    is_anonymous    = Column(Boolean, default=False)
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

    announcement = relationship("Announcement", back_populates="poll")
    options      = relationship("PollOption", back_populates="poll", cascade="all, delete", order_by="PollOption.sort_order")
    votes        = relationship("PollVote", back_populates="poll", cascade="all, delete")


class PollOption(Base):
    __tablename__ = "poll_options"

    id          = Column(Integer, primary_key=True)
    poll_id     = Column(Integer, ForeignKey("announcement_polls.id"), nullable=False, index=True)
    label       = Column(String, nullable=False)
    sort_order  = Column(Integer, default=0)

    poll = relationship("AnnouncementPoll", back_populates="options")


class PollVote(Base):
    __tablename__ = "poll_votes"

    id          = Column(Integer, primary_key=True)
    poll_id     = Column(Integer, ForeignKey("announcement_polls.id"), nullable=False, index=True)
    option_id   = Column(Integer, ForeignKey("poll_options.id"), nullable=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    text_answer = Column(Text, nullable=True)
    created_at  = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("poll_id", "user_id", "option_id", name="uq_poll_vote_per_option_user"),
    )

    poll   = relationship("AnnouncementPoll", back_populates="votes")
    option = relationship("PollOption")
    user   = relationship("User")


class AnnouncementReaction(Base):
    __tablename__ = "announcement_reactions"

    id              = Column(Integer, primary_key=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reaction        = Column(String, nullable=False)
    created_at      = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("announcement_id", "user_id", "reaction", name="uq_announcement_reaction_user"),
    )

    announcement = relationship("Announcement", back_populates="reactions")
    user         = relationship("User")
