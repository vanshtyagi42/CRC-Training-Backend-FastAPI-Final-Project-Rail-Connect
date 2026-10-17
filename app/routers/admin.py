from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..database import get_session
from ..deps import require_admin
from ..models import Booking, Station, Train, TrainRun
from ..schemas import (
    RunCreate,
    RunRead,
    SeatUpdate,
    StationCreate,
    StationRead,
    TrainCreate,
    TrainRead,
    TrainUpdate,
)

# every route in this router is admin-only (401 if not logged in, 403 if not admin)
router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


def _get_station_or_404(session: Session, station_id: int) -> Station:
    station = session.get(Station, station_id)
    if not station:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Station {station_id} not found.")
    return station


def _get_train_or_404(session: Session, train_id: int) -> Train:
    train = session.get(Train, train_id)
    if not train:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Train {train_id} not found.")
    return train


# ---------------- Stations ----------------
@router.post("/stations", response_model=StationRead, status_code=status.HTTP_201_CREATED)
def add_station(data: StationCreate, session: Session = Depends(get_session)):
    code = data.code.strip().upper()
    if session.exec(select(Station).where(Station.code == code)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Station code '{code}' already exists.")
    station = Station(code=code, name=data.name.strip(), city=data.city.strip())
    session.add(station)
    session.commit()
    session.refresh(station)
    return station


@router.get("/stations", response_model=list[StationRead])
def list_stations(session: Session = Depends(get_session)):
    return session.exec(select(Station).order_by(Station.code)).all()


# ---------------- Trains ----------------
@router.post("/trains", response_model=TrainRead, status_code=status.HTTP_201_CREATED)
def add_train(data: TrainCreate, session: Session = Depends(get_session)):
    _get_station_or_404(session, data.source_id)
    _get_station_or_404(session, data.destination_id)
    number = data.number.strip()
    if session.exec(select(Train).where(Train.number == number)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Train number '{number}' already exists.")
    train = Train(
        number=number,
        name=data.name.strip(),
        source_id=data.source_id,
        destination_id=data.destination_id,
        departure_time=data.departure_time,
        arrival_time=data.arrival_time,
        fare=data.fare,
        total_seats=data.total_seats,
    )
    session.add(train)
    session.commit()
    session.refresh(train)
    return train


@router.get("/trains", response_model=list[TrainRead])
def list_trains(session: Session = Depends(get_session)):
    return session.exec(select(Train).order_by(Train.number)).all()


@router.put("/trains/{train_id}", response_model=TrainRead)
def update_train(train_id: int, data: TrainUpdate, session: Session = Depends(get_session)):
    train = _get_train_or_404(session, train_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields provided to update.")

    new_source = changes.get("source_id", train.source_id)
    new_dest = changes.get("destination_id", train.destination_id)
    if new_source == new_dest:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Source and destination must be different.")
    if "source_id" in changes:
        _get_station_or_404(session, new_source)
    if "destination_id" in changes:
        _get_station_or_404(session, new_dest)

    for key, value in changes.items():
        setattr(train, key, value)
    session.add(train)
    session.commit()
    session.refresh(train)
    return train


@router.patch("/trains/{train_id}/deactivate", response_model=TrainRead)
def deactivate_train(train_id: int, session: Session = Depends(get_session)):
    train = _get_train_or_404(session, train_id)
    if not train.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Train is already deactivated.")
    train.is_active = False
    session.add(train)
    session.commit()
    session.refresh(train)
    return train


@router.patch("/trains/{train_id}/activate", response_model=TrainRead)
def activate_train(train_id: int, session: Session = Depends(get_session)):
    train = _get_train_or_404(session, train_id)
    train.is_active = True
    session.add(train)
    session.commit()
    session.refresh(train)
    return train


# ---------------- Runs (train + journey date, with seats) ----------------
@router.post("/trains/{train_id}/runs", response_model=RunRead, status_code=status.HTTP_201_CREATED)
def add_run(train_id: int, data: RunCreate, session: Session = Depends(get_session)):
    train = _get_train_or_404(session, train_id)
    seats = data.available_seats if data.available_seats is not None else train.total_seats
    if seats > train.total_seats:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Available seats cannot exceed the train's total seats ({train.total_seats}).",
        )
    run = TrainRun(train_id=train.id, journey_date=data.journey_date, available_seats=seats)
    session.add(run)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A run for {data.journey_date} already exists for this train."
        )
    session.refresh(run)
    return run


@router.get("/trains/{train_id}/runs", response_model=list[RunRead])
def list_runs(train_id: int, session: Session = Depends(get_session)):
    _get_train_or_404(session, train_id)
    return session.exec(
        select(TrainRun).where(TrainRun.train_id == train_id).order_by(TrainRun.journey_date)
    ).all()


@router.patch("/runs/{run_id}/seats", response_model=RunRead)
def update_seats(run_id: int, data: SeatUpdate, session: Session = Depends(get_session)):
    """Set the number of seats still available for a run.
    It can't exceed the train's capacity minus seats already booked (that would oversell)."""
    run = session.get(TrainRun, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Run {run_id} not found.")
    train = session.get(Train, run.train_id)

    # seats already held by confirmed bookings
    booked = session.exec(
        select(Booking.seats).where(Booking.run_id == run_id, Booking.status == "CONFIRMED")
    ).all()
    booked_total = sum(booked)
    max_available = train.total_seats - booked_total
    if data.available_seats > max_available:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only {max_available} seats can be available: capacity {train.total_seats}, "
            f"{booked_total} already booked.",
        )

    # atomic single-statement update (safe if a booking happens at the same moment)
    session.exec(
        update(TrainRun).where(TrainRun.id == run_id).values(available_seats=data.available_seats)
    )
    session.commit()
    session.refresh(run)
    return run 