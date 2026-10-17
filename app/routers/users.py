from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..database import get_session
from ..deps import get_current_user
from ..models import Booking, Train, TrainRun, User
from ..schemas import BookingRead, UserRead

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserRead)
def my_profile(user: User = Depends(get_current_user)):
    return user


@router.get("/me/bookings", response_model=list[BookingRead])
def my_bookings(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Only the logged-in user's own bookings."""
    rows = session.exec(
        select(Booking, TrainRun, Train)
        .join(TrainRun, Booking.run_id == TrainRun.id)
        .join(Train, TrainRun.train_id == Train.id)
        .where(Booking.user_id == user.id)
        .order_by(Booking.created_at.desc())
    ).all()
    return [
        BookingRead(
            pnr=b.pnr,
            run_id=b.run_id,
            train_number=t.number,
            train_name=t.name,
            journey_date=r.journey_date,
            seats=b.seats,
            total_fare=b.total_fare,
            status=b.status,
            payment_status=b.payment_status,
            created_at=b.created_at,
            cancelled_at=b.cancelled_at,
        )
        for b, r, t in rows
    ] 