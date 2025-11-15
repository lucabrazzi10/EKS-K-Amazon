import os
import random
import time
import uuid
from typing import Generator

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sqlalchemy import (
    create_engine,
    String,
    Float,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
    Session as OrmSession,
)

# -------------------------------------------------------------------
# Database setup
# -------------------------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://rgs:rgs@rgs-postgres:5432/rgsdb",
)


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    external_player_id: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=lambda: time.time())

    wallet: Mapped["WalletAccount"] = relationship(back_populates="player", uselist=False)
    sessions: Mapped[list["Session"]] = relationship(back_populates="player")
    rounds: Mapped[list["GameRound"]] = relationship(back_populates="player")

    __table_args__ = (
        UniqueConstraint("operator_id", "external_player_id", name="uq_player_operator_ext"),
    )


class WalletAccount(Base):
    __tablename__ = "wallet_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), nullable=False)
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    player: Mapped[Player] = relationship(back_populates="wallet")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # session_id
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), nullable=False)
    operator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=lambda: time.time())

    player: Mapped[Player] = relationship(back_populates="sessions")
    rounds: Mapped[list["GameRound"]] = relationship(back_populates="session")


class GameRound(Base):
    __tablename__ = "game_rounds"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # round_id
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    game_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bet_amount: Mapped[float] = mapped_column(Float, nullable=False)
    win_amount: Mapped[float] = mapped_column(Float, nullable=False)
    new_balance: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=lambda: time.time())

    player: Mapped[Player] = relationship(back_populates="rounds")
    session: Mapped[Session] = relationship(back_populates="rounds")


engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[OrmSession, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------------------------------------------------
# FastAPI setup
# -------------------------------------------------------------------

app = FastAPI(title="RGS Core Demo", version="0.2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo only; lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


# -------------------------------------------------------------------
# Schemas
# -------------------------------------------------------------------

class SessionStartRequest(BaseModel):
    operator_id: str
    external_player_id: str
    currency: str = "USD"


class SessionStartResponse(BaseModel):
    session_id: str
    player_id: str
    currency: str
    created_at: float
    balance: float


class SpinRequest(BaseModel):
    session_id: str
    player_id: str
    bet_amount: float
    currency: str = "USD"


class SpinResponse(BaseModel):
    round_id: str
    player_id: str
    game_id: str
    bet_amount: float
    win_amount: float
    new_balance: float
    currency: str
    timestamp: float


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------

@app.get("/health")
def health():
    # Check DB connectivity explicitly
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {"status": "ok", "service": "rgs-core-demo", "db": db_status}


@app.post("/session/start", response_model=SessionStartResponse)
def start_session(payload: SessionStartRequest, db: OrmSession = Depends(get_db)):
    # Create or fetch player
    player = (
        db.query(Player)
        .filter(
            Player.operator_id == payload.operator_id,
            Player.external_player_id == payload.external_player_id,
        )
        .first()
    )

    if not player:
        player = Player(
            id=f"player-{payload.external_player_id}",
            operator_id=payload.operator_id,
            external_player_id=payload.external_player_id,
            currency=payload.currency,
            created_at=time.time(),
        )
        db.add(player)
        db.flush()  # assign id

    # Create or fetch wallet
    wallet = (
        db.query(WalletAccount)
        .filter(WalletAccount.player_id == player.id)
        .first()
    )
    if not wallet:
        wallet = WalletAccount(
            player_id=player.id,
            balance=1000.0,  # demo starting balance
            currency=payload.currency,
        )
        db.add(wallet)

    # Create new session
    session_id = str(uuid.uuid4())
    now = time.time()

    db_session = Session(
        id=session_id,
        player_id=player.id,
        operator_id=payload.operator_id,
        currency=payload.currency,
        active=True,
        created_at=now,
    )
    db.add(db_session)

    db.commit()

    return SessionStartResponse(
        session_id=session_id,
        player_id=player.id,
        currency=payload.currency,
        created_at=now,
        balance=wallet.balance,
    )


@app.post("/games/{game_id}/spin", response_model=SpinResponse)
def spin(game_id: str, payload: SpinRequest, db: OrmSession = Depends(get_db)):
    # Validate session
    db_session = db.query(Session).filter(Session.id == payload.session_id).first()
    if not db_session or not db_session.active:
        raise HTTPException(status_code=400, detail="Invalid or inactive session")

    if db_session.player_id != payload.player_id:
        raise HTTPException(status_code=400, detail="Session / player mismatch")

    # Get wallet with row-level lock
    wallet = (
        db.query(WalletAccount)
        .filter(WalletAccount.player_id == payload.player_id)
        .with_for_update()
        .first()
    )
    if not wallet:
        raise HTTPException(status_code=400, detail="Wallet not found")

    if payload.bet_amount <= 0:
        raise HTTPException(status_code=400, detail="Bet amount must be > 0")

    if wallet.balance < payload.bet_amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Betting logic inside a transaction
    # (SessionLocal already manages transaction boundaries)
    wallet.balance -= payload.bet_amount

    win_amount = 0.0
    if random.random() < 0.3:
        win_amount = payload.bet_amount * random.uniform(1.0, 5.0)

    wallet.balance += win_amount
    new_balance = wallet.balance

    round_id = str(uuid.uuid4())
    ts = time.time()

    game_round = GameRound(
        id=round_id,
        player_id=payload.player_id,
        session_id=payload.session_id,
        game_id=game_id,
        bet_amount=payload.bet_amount,
        win_amount=win_amount,
        new_balance=new_balance,
        currency=payload.currency,
        created_at=ts,
    )
    db.add(game_round)

    db.commit()

    return SpinResponse(
        round_id=round_id,
        player_id=payload.player_id,
        game_id=game_id,
        bet_amount=payload.bet_amount,
        win_amount=win_amount,
        new_balance=new_balance,
        currency=payload.currency,
        timestamp=ts,
    )
