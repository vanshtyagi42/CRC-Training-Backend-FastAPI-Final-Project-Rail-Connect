from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


# Auth / users
class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72) 


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_admin: bool
    created_at: datetime


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)


class MessageResponse(BaseModel):
    message: str


# Stations
class StationCreate(BaseModel):
    code: str = Field(min_length=2, max_length=6)
    name: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=100)


class StationRead(BaseModel):
    id: int
    code: str
    name: str
    city: str


# Trains
class TrainCreate(BaseModel):
    number: str = Field(min_length=3, max_length=10)
    name: str = Field(min_length=2, max_length=100)
    source_id: int
    destination_id: int
    departure_time: time
    arrival_time: time
    fare: float = Field(gt=0)
    total_seats: int = Field(gt=0, le=2000)

    @model_validator(mode="after")
    def check_route(self):
        if self.source_id == self.destination_id:
            raise ValueError("Source and destination stations must be different")
        return self


class TrainUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    source_id: Optional[int] = None
    destination_id: Optional[int] = None
    departure_time: Optional[time] = None
    arrival_time: Optional[time] = None
    fare: Optional[float] = Field(default=None, gt=0)
    total_seats: Optional[int] = Field(default=None, gt=0, le=2000)


class TrainRead(BaseModel):
    id: int
    number: str
    name: str
    source_id: int
    destination_id: int
    departure_time: time
    arrival_time: time
    fare: float
    total_seats: int
    is_active: bool


# Train runs (train + journey date)
class RunCreate(BaseModel):
    journey_date: date
    available_seats: Optional[int] = Field(default=None, ge=0)  


class SeatUpdate(BaseModel):
    available_seats: int = Field(ge=0)


class RunRead(BaseModel):
    id: int
    train_id: int
    journey_date: date
    available_seats: int


# Search
class SearchResult(BaseModel):
    run_id: int
    train_number: str
    train_name: str
    source: str
    destination: str
    journey_date: date
    departure_time: time
    arrival_time: time
    fare: float
    available_seats: int


class SearchResponse(BaseModel):
    message: str
    results: list[SearchResult]


# Bookings
class BookingCreate(BaseModel):
    run_id: int
    seats: int = Field(ge=1, le=6)


class BookingRead(BaseModel):
    pnr: str
    run_id: int
    train_number: str
    train_name: str
    journey_date: date
    seats: int
    total_fare: float
    status: str
    payment_status: str
    created_at: datetime
    cancelled_at: Optional[datetime] = None