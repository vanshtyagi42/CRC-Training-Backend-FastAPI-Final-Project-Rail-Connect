import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..database import get_session
from ..deps import get_current_user
from ..models import Booking, Train, TrainRun, User, utcnow
from ..schemas import BookingCreate, BookingRead

router = APIRouter(prefix="/bookings", tags=["Bookings"])


def generate_pnr() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(10))


def _to_read(b: Booking, run: TrainRun, train: Train) -> BookingRead:
    return BookingRead(
        pnr=b.pnr,
        run_id=b.run_id,
        train_number=train.number,
        train_name=train.name,
        journey_date=run.journey_date,
        seats=b.seats,
        total_fare=b.total_fare,
        status=b.status,
        payment_status=b.payment_status,
        created_at=b.created_at,
        cancelled_at=b.cancelled_at,
    )


def _has_departed(run: TrainRun, train: Train) -> bool:
    return datetime.combine(run.journey_date, train.departure_time) <= datetime.now()


def _own_booking(session: Session, pnr: str, user: User):
    """Another user's PNR looks exactly like a missing one (404), so PNRs can't be probed."""
    row = session.exec(
        select(Booking, TrainRun, Train)
        .join(TrainRun, Booking.run_id == TrainRun.id)
        .join(Train, TrainRun.train_id == Train.id)
        .where(Booking.pnr == pnr, Booking.user_id == user.id)
    ).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found.")
    return row


@router.post("", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
def book_ticket(
    data: BookingCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    run = session.get(TrainRun, data.run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Journey not found.")
    train = session.get(Train, run.train_id)
    if not train.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This train is not available for booking.")
    if _has_departed(run, train):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This train has already departed.")

    run_id, user_id, seats = run.id, user.id, data.seats
    total_fare = train.fare * seats

    for _ in range(5):  # retry only if a random PNR collides
        try:
            # ONE atomic statement: decrement only if enough seats remain.
            # Two simultaneous requests for the last seat: only one gets rowcount == 1.
            result = session.exec(
                update(TrainRun)
                .where(TrainRun.id == run_id, TrainRun.available_seats >= seats)
                .values(available_seats=TrainRun.available_seats - seats)
            )
            if result.rowcount == 0:
                session.rollback()
                raise HTTPException(status.HTTP_409_CONFLICT, "Not enough seats available.")
            booking = Booking(
                pnr=generate_pnr(),
                user_id=user_id,
                run_id=run_id,
                seats=seats,
                total_fare=total_fare,
                status="CONFIRMED",
                payment_status="SIMULATED_PAID",
            )
            session.add(booking)
            session.commit()  # seat decrement + booking saved together, or neither
            break
        except IntegrityError:
            session.rollback()  # undoes the seat decrement too
    else:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not generate a PNR. Try again.")

    session.refresh(booking)
    session.refresh(run)
    return _to_read(booking, run, train)


@router.get("/{pnr}", response_model=BookingRead)
def view_booking(
    pnr: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    booking, run, train = _own_booking(session, pnr, user)
    return _to_read(booking, run, train)


@router.post("/{pnr}/cancel", response_model=BookingRead)
def cancel_booking(
    pnr: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    booking, run, train = _own_booking(session, pnr, user)
    if _has_departed(run, train):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot cancel after the train has departed.")

    seats, run_id, booking_id = booking.seats, run.id, booking.id

    # Only the request that flips CONFIRMED -> CANCELLED gets rowcount == 1,
    # so seats are released exactly once even if cancel is sent twice.
    result = session.exec(
        update(Booking)
        .where(Booking.id == booking_id, Booking.status == "CONFIRMED")
        .values(status="CANCELLED", cancelled_at=utcnow())
    )
    if result.rowcount == 0:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Booking is already cancelled.")

    session.exec(
        update(TrainRun)
        .where(TrainRun.id == run_id)
        .values(available_seats=TrainRun.available_seats + seats)
    )
    session.commit()  # status change + seat release together

    session.refresh(booking)
    session.refresh(run)
    return _to_read(booking, run, train) 