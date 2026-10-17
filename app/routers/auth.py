from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..config import settings
from ..database import get_session
from ..deps import get_token_payload
from ..models import PasswordResetToken, RevokedToken, User, utcnow
from ..schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserRead,
)
from ..security import (
    create_access_token,
    generate_reset_token,
    hash_password,
    hash_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Accounts"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, session: Session = Depends(get_session)):
    email = data.email.lower()
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(name=data.name.strip(), email=email, hashed_password=hash_password(data.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == data.email.lower())).first()
    # same message for wrong email or wrong password, so attackers can't find valid emails
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is deactivated.")
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/logout", response_model=MessageResponse)
def logout(payload: dict = Depends(get_token_payload), session: Session = Depends(get_session)):
    """JWTs are stateless, so we store the token's jti in a revocation table.
    deps.py rejects any token whose jti is in that table."""
    if not session.get(RevokedToken, payload["jti"]):
        session.add(
            RevokedToken(
                jti=payload["jti"],
                expires_at=utcnow() + timedelta(minutes=settings.access_token_minutes),
            )
        )
        session.commit()
    return MessageResponse(message="Logged out successfully.")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(data: ForgotPasswordRequest, session: Session = Depends(get_session)):
    generic = "If that email is registered, a password reset link has been sent."
    user = session.exec(select(User).where(User.email == data.email.lower())).first()
    if user and user.is_active:
        token = generate_reset_token()
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),   # only the hash is stored
                expires_at=utcnow() + timedelta(minutes=settings.reset_token_minutes),
            )
        )
        session.commit()
        # DEV EMAIL SIMULATION: the "email" is printed in the server console
        print("\n=== DEV EMAIL (simulated) ===")
        print(f"To: {user.email}")
        print(f"Reset token: {token}")
        print(f"Valid for {settings.reset_token_minutes} minutes, single use.")
        print("=============================\n")
    return MessageResponse(message=generic)   # same reply whether or not the email exists


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(data: ResetPasswordRequest, session: Session = Depends(get_session)):
    record = session.exec(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(data.token))
    ).first()
    if not record or record.used or record.expires_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reset token is invalid, expired or already used.")
    user = session.get(User, record.user_id)
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reset token is invalid, expired or already used.")
    user.hashed_password = hash_password(data.new_password)
    record.used = True          # single use
    session.add(user)
    session.add(record)
    session.commit()
    return MessageResponse(message="Password reset successful. You can now log in.") 