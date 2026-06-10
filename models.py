from sqlalchemy import Column, Integer, String, ForeignKey, Date, Time, Boolean, UniqueConstraint, Text, DateTime, Index
from sqlalchemy.orm import relationship
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
    created_at    = Column(DateTime, server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_chat_sender_receiver", "sender_id", "receiver_id"),
        Index("ix_chat_receiver_created", "receiver_id", "created_at"),
    )

    sender      = relationship("User", foreign_keys=[sender_id],   back_populates="sent_messages")
    receiver    = relationship("User", foreign_keys=[receiver_id], back_populates="received_messages")
    reply_to    = relationship("ChatMessage", remote_side=[id], backref="replies")


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
    preferences       = relationship("UserPreference", back_populates="user", cascade="all, delete")


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


class AppSetting(Base):
    """Глобальные настройки приложения (ключ → значение)."""
    __tablename__ = "app_settings"

    key   = Column(String, primary_key=True)
    value = Column(Text, nullable=False, default="")
