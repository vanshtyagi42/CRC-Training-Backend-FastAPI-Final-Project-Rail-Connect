from datetime import date as date_type, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from ..database import get_session
from ..models import Station, Train, TrainRun
from ..schemas import SearchResponse, SearchResult

router = APIRouter(prefix="/trains", tags=["Search"])


def _station_by_code(session: Session, code: str) -> Station:
    station = session.exec(select(Station).where(Station.code == code.strip().upper())).first()
    if not station:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Station '{code.upper()}' not found.")
    return station


@router.get("/search", response_model=SearchResponse)
def search_trains(
    source: str = Query(min_length=2, max_length=6, description="Station code, e.g. NDLS"),
    destination: str = Query(min_length=2, max_length=6, description="Station code, e.g. CNB"),
    journey_date: date_type = Query(alias="date", description="YYYY-MM-DD"),
    session: Session = Depends(get_session),
):
    if source.strip().upper() == destination.strip().upper():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Source and destination must be different.")
    if journey_date < date_type.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Journey date cannot be in the past.")

    src = _station_by_code(session, source)
    dst = _station_by_code(session, destination)

    rows = session.exec(
        select(TrainRun, Train)
        .join(Train, TrainRun.train_id == Train.id)
        .where(
            Train.source_id == src.id,
            Train.destination_id == dst.id,
            Train.is_active == True,  # noqa: E712
            TrainRun.journey_date == journey_date,
        )
        .order_by(Train.departure_time)
    ).all()

    now = datetime.now()
    results = [
        SearchResult(
            run_id=run.id,
            train_number=train.number,
            train_name=train.name,
            source=src.name,
            destination=dst.name,
            journey_date=run.journey_date,
            departure_time=train.departure_time,
            arrival_time=train.arrival_time,
            fare=train.fare,
            available_seats=run.available_seats,
        )
        for run, train in rows
        if datetime.combine(run.journey_date, train.departure_time) > now  # hide departed trains
    ]

    if not results:
        return SearchResponse(message="No trains found for this route and date.", results=[])
    return SearchResponse(message=f"{len(results)} train(s) found.", results=results) 