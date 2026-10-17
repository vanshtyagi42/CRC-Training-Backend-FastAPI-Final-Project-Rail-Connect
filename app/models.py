from datetime import date, datetime, time, timezone
from typing import Optional

from pydantic import NaiveDatetime
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Naive UTC time (SQLite stores datetimes without timezone)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_admin: bool = False
    is_active: bool = True
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class Station(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True)  
    name: str                                   
    city: str


class Train(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    number: str = Field(unique=True, index=True)
    name: str
    source_id: int = Field(foreign_key="station.id")
    destination_id: int = Field(foreign_key="station.id")
    departure_time: time
    arrival_time: time
    fare: float
    total_seats: int
    is_active: bool = True


class TrainRun(SQLModel, table=True):
    """One train on one journey date, with its own seat count."""
    __table_args__ = (UniqueConstraint("train_id", "journey_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    train_id: int = Field(foreign_key="train.id", index=True)
    journey_date: date = Field(index=True)
    available_seats: int


class Booking(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    pnr: str = Field(unique=True, index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    run_id: int = Field(foreign_key="trainrun.id", index=True)
    seats: int
    total_fare: float
    status: str = "CONFIRMED"                 
    payment_status: str = "SIMULATED_PAID"
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    cancelled_at: Optional[NaiveDatetime] = None


class RevokedToken(SQLModel, table=True):
    jti: str = Field(primary_key=True)
    expires_at: NaiveDatetime


class PasswordResetToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(index=True)
    expires_at: NaiveDatetime
    used: bool = False 