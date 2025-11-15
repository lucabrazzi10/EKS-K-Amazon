import os
import random
import time
import uuid
from typing import Generator, Optional, List

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
    sessions: Mapped[List["Session"]] = relationship(back_populates="player")
    rounds: Mapped[List["GameRound"]] = relationship(back_populates="player")

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
    rounds: Mapped[List["GameRound"]] = relationship(back_populates="session")


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
# Slot game config (Option B)
# -------------------------------------------------------------------

# 3 rows, 5 reels
SLOT_ROWS = 3
SLOT_REELS = 5

# Symbols: 10, J, Q, K, A, W (wild/high), S (scatter)
SLOT_SYMBOLS = ["10", "J", "Q", "K", "A", "W", "S"]
SLOT_WEIGHTS = [10, 8, 7, 6, 5, 2, 2]  # 10 is most common, W/S rare

# Simple paytable: multiplier applied on *line bet*
PAYTABLE = {
    "10": {3: 1.0, 4: 2.0, 5: 4.0},
    "J":  {3: 2.0, 4: 4.0, 5: 8.0},
    "Q":  {3: 3.0, 4: 6.0, 5: 12.0},
    "K":  {3: 4.0, 4: 8.0, 5: 16.0},
    "A":  {3: 5.0, 4: 10.0, 5: 20.0},
    "W":  {3: 8.0, 4: 16.0, 5: 32.0},
}

SCATTER_SYMBOL = "S"
# Multiplier on total bet for scatters anywhere
SCATTER_PAY = {
    3: 2.0,
    4: 5.0,
    5: 20.0,  # 5 or more uses 5's multiplier
}

# 5 simple paylines (row, col)
PAYLINES = [
    # Top row
    [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)],
    # Middle row
    [(1, 0), (1, 1), (1, 2), (1, 3), (1, 4)],
    # Bottom row
    [(2, 0), (2, 1), (2, 2), (2, 3), (2, 4)],
    # V shape
    [(0, 0), (1, 1), (2, 2), (1, 3), (0, 4)],
    # Inverted V
    [(2, 0), (1, 1), (0, 2), (1, 3), (2, 4)],
]


# -------------------------------------------------------------------
# FastAPI setup
# -------------------------------------------------------------------

app = FastAPI(title="RGS Core Demo", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo only
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

    # Option B extras (for UI / debugging)
    grid: Optional[List[List[str]]] = None
    line_wins: Optional[List[str]] = None
    scatter_count: Optional[int] = None


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------

@app.get("/health")
def health():
    # Basic DB connectivity check
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
        db.flush()

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
    try:
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

        # Debit bet
        wallet.balance -= payload.bet_amount

        # ----------------------------------------------------------
        # Option B slot engine: build grid, evaluate paylines
        # ----------------------------------------------------------
        # Generate 3x5 grid of symbols
        grid: List[List[str]] = []
        for _row in range(SLOT_ROWS):
            row_symbols = random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=SLOT_REELS)
            grid.append(row_symbols)

        line_bet = payload.bet_amount / len(PAYLINES)
        total_line_win = 0.0
        line_win_messages: List[str] = []

        # Evaluate each payline (3+ of same symbol from left)
        for idx, line in enumerate(PAYLINES):
            line_symbols = [grid[r][c] for (r, c) in line]
            base_symbol = line_symbols[0]

            # No line wins on scatters or unknown symbols
            if base_symbol == SCATTER_SYMBOL or base_symbol not in PAYTABLE:
                continue

            count = 1
            for symbol in line_symbols[1:]:
                if symbol == base_symbol:
                    count += 1
                else:
                    break

            if count >= 3 and count in PAYTABLE[base_symbol]:
                line_win = line_bet * PAYTABLE[base_symbol][count]
                total_line_win += line_win
                line_win_messages.append(
                    f"Line {idx + 1}: {base_symbol} x{count} pays {line_win:.2f}"
                )

        # Scatter evaluation (anywhere on screen)
        scatter_count = sum(1 for row in grid for symbol in row if symbol == SCATTER_SYMBOL)
        scatter_win = 0.0
        if scatter_count >= 3:
            applicable_keys = [k for k in SCATTER_PAY.keys() if k <= scatter_count]
            if applicable_keys:
                best = max(applicable_keys)
                scatter_win = payload.bet_amount * SCATTER_PAY[best]
                line_win_messages.append(
                    f"Scatter: {scatter_count}x {SCATTER_SYMBOL} pays {scatter_win:.2f}"
                )

        win_amount = total_line_win + scatter_win

        # Apply win
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
            grid=grid,
            line_wins=line_win_messages or None,
            scatter_count=scatter_count,
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Spin error: {e}")
