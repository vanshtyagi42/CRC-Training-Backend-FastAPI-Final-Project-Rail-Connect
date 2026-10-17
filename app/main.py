from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import Session, select

from .config import settings
from .database import create_db_and_tables, engine
from .models import User
from .routers import admin, auth, bookings, trains, users
from .security import hash_password


def seed_admin() -> None:
    """Create the first admin from .env if none exists.
    Registration can never create an admin, so this is the only way in."""
    with Session(engine) as session:
        exists = session.exec(select(User).where(User.is_admin == True)).first()  # noqa: E712
        if not exists:
            session.add(
                User(
                    name=settings.admin_name,
                    email=settings.admin_email.lower(),
                    hashed_password=hash_password(settings.admin_password),
                    is_admin=True,
                )
            )
            session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    seed_admin()
    yield


app = FastAPI(
    title="RailConnect",
    description="A mini railway booking backend built with FastAPI.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(trains.router)
app.include_router(bookings.router)


@app.get("/", tags=["Health"])
def root():
    return {"message": "RailConnect API is running. Open /docs to try it."}