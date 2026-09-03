import hashlib
import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./revenue_recovery.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Case(Base):
    # Tracks failed payment and recovery lifecycle
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    razorpay_subscription_id = Column(String, nullable=True, index=True)
    razorpay_payment_id = Column(String, nullable=True, index=True)
    customer_id = Column(String, nullable=True, index=True)

    amount = Column(Float, nullable=False, default=0.0)
    decline_reason = Column(String, nullable=True)
    payment_method = Column(String, nullable=True)

    status = Column(String, default="open")
    opt_out = Column(Boolean, default=False)
    retry_attempt_number = Column(Integer, default=0)

    recovered_amount = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    actions = relationship("Action", back_populates="case")
    audit_entries = relationship("AuditLog", back_populates="case")


class Event(Base):
    # Ingested webhook events for idempotency verification
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    razorpay_event_id = Column(String, unique=True, index=True, nullable=False)
    event_type = Column(String, nullable=False)
    payload_json = Column(Text, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow)


class Action(Base):
    # Records recovery actions taken per case
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)

    action_type = Column(String, nullable=False)
    reason = Column(Text, nullable=True)
    outcome = Column(String, nullable=True)

    taken_at = Column(DateTime, default=datetime.utcnow)
    case = relationship("Case", back_populates="actions")


class AuditLog(Base):
    # Tamper-evident SHA-256 hash-chained ledger
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)

    description = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)

    previous_hash = Column(String, nullable=True)
    this_hash = Column(String, nullable=False)

    timestamp = Column(DateTime, default=datetime.utcnow)
    case = relationship("Case", back_populates="audit_entries")


class PromiseToPay(Base):
    # Tracks customer payment commitments parsed by NLP
    __tablename__ = "promise_to_pay"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)

    promise_date = Column(String, nullable=True)
    promise_amount = Column(Float, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)
    customer_message = Column(Text, nullable=True)
    llm_summary = Column(Text, nullable=True)

    extracted_at = Column(DateTime, default=datetime.utcnow)
    fulfilled = Column(Boolean, default=False)
    case = relationship("Case")


def compute_hash(previous_hash: str, description: str, reason: str, timestamp: str) -> str:
    # Compute SHA-256 chaining hash
    raw = f"{previous_hash or ''}|{description}|{reason or ''}|{timestamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_last_hash(db) -> str | None:
    # Fetch previous audit hash
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    return last.this_hash if last else None


def write_audit_log(db, case_id: int | None, description: str, reason: str | None = None) -> AuditLog:
    # Append hash-chained audit entry
    prev_hash = get_last_hash(db)
    ts = datetime.utcnow()
    this_hash = compute_hash(prev_hash, description, reason, ts.isoformat())

    entry = AuditLog(
        case_id=case_id,
        description=description,
        reason=reason,
        previous_hash=prev_hash,
        this_hash=this_hash,
        timestamp=ts,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def init_db():
    # Initialize database tables
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        try:
            from sqlalchemy import text
            result = conn.execute(text("PRAGMA table_info(cases)")).fetchall()
            existing_columns = [row[1] for row in result]
            if "opt_out" not in existing_columns and len(existing_columns) > 0:
                conn.execute(text("ALTER TABLE cases ADD COLUMN opt_out BOOLEAN DEFAULT 0"))
                conn.commit()
        except Exception:
            pass


def get_db():
    # FastAPI dependency yielding session
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized: revenue_recovery.db")