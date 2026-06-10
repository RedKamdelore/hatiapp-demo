from pydantic import BaseModel, Field, field_validator
from typing import Optional
from config import UserRole


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)
    full_name: Optional[str] = Field(None, max_length=100)
    role: UserRole = UserRole.VOLUNTEER
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Логин не может быть пустым")
        return v


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=1, max_length=50)
    full_name: Optional[str] = Field(None, max_length=100)
    role: Optional[UserRole] = None
    password: Optional[str] = Field(None, min_length=4, max_length=100)


class LoginForm(BaseModel):
    username: str
    password: str


class SlotCreate(BaseModel):
    direction_id: int = Field(..., gt=0)
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    capacity: int = Field(..., gt=0, le=1000)


class DirectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ChatMessageCreate(BaseModel):
    receiver_id: int = Field(..., gt=0)
    text: str = Field(..., min_length=1, max_length=2000)
