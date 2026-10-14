import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, ForeignKey, String, Date, DateTime, JSON, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

def now():
    return datetime.now(timezone.utc)

ENV = os.getenv("APP_ENV", "development")
URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "sqlite:///./maternal.db"
if URL.startswith("postgres://"):
    URL = "postgresql+psycopg://" + URL[len("postgres://"):]
elif URL.startswith("postgresql://"):
    URL = "postgresql+psycopg://" + URL[len("postgresql://"):]
if os.getenv("VERCEL") and not URL.startswith("postgresql"):
    raise RuntimeError("Connect PostgreSQL in Vercel and provide DATABASE_URL or POSTGRES_URL")
if ENV == "production" and not URL.startswith("postgresql"):
    raise RuntimeError("Production requires PostgreSQL")
engine = create_engine(URL, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {},
                       pool_pre_ping=True,
                       **({"poolclass": StaticPool} if URL in {"sqlite://", "sqlite:///:memory:"} else {}))
SessionLocal = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="mother")

class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Pregnancy(Base):
    __tablename__ = "pregnancies"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    lmp: Mapped[datetime] = mapped_column(Date)
    label: Mapped[str] = mapped_column(String(100))

class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    pregnancy_id: Mapped[int] = mapped_column(ForeignKey("pregnancies.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    values: Mapped[dict] = mapped_column(JSON)
    units: Mapped[dict] = mapped_column(JSON)

class ModelRegistry(Base):
    __tablename__ = "model_registry"
    version: Mapped[str] = mapped_column(String(100), primary_key=True)
    metadata_json: Mapped[dict] = mapped_column(JSON)

class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    pregnancy_id: Mapped[int] = mapped_column(ForeignKey("pregnancies.id"))
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), unique=True)
    model_version: Mapped[str] = mapped_column(ForeignKey("model_registry.version"))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Guidance(Base):
    __tablename__ = "guidance"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(String(4000))
    stage: Mapped[int]
    category: Mapped[str] = mapped_column(String(20))
    source_url: Mapped[str] = mapped_column(String(500))
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    pregnancy_id: Mapped[int] = mapped_column(ForeignKey("pregnancies.id"))
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    message: Mapped[str] = mapped_column(String(1000))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    resource: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class GuidanceDelivery(Base):
    __tablename__ = "guidance_deliveries"
    __table_args__ = (UniqueConstraint("pregnancy_id", "guidance_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    pregnancy_id: Mapped[int] = mapped_column(ForeignKey("pregnancies.id"))
    guidance_id: Mapped[int] = mapped_column(ForeignKey("guidance.id"))
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
