"""
Database models for the Revenue Recovery Agent.

Tables:
- cases       : one row per revenue-at-risk case (failed payment / mandate)
- events      : raw incoming Razorpay webhook events (idempotency source of truth)
- actions     : every recovery action taken on a case
- audit_log   : hash-chained, tamper-evident log of every decision/action
"""

import hashlib
import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey
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
    """A single revenue-at-risk case (e.g. one failed subscription charge)."""
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    razorpay_subscription_id = Column(String, nullable=True, index=True)
    razorpay_payment_id = Column(String, nullable=True, index=True)
    customer_id = Column(String, nullable=True, index=True)

    amount = Column(Float, nullable=False, default=0.0)
    decline_reason = Column(String, nullable=True)   # e.g. insufficient_funds, expired_card
    payment_method = Column(String, nullable=True)   # upi, card, netbanking

    status = Column(String, default="open")          # open | recovered | escalated | closed
    retry_attempt_number = Column(Integer, default=0)

    recovered_amount = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    actions = relationship("Action", back_populates="case")
    audit_entries = relationship("AuditLog", back_populates="case")


class Event(Base):
    """Raw incoming Razorpay webhook event — used for idempotent processing."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    razorpay_event_id = Column(String, unique=True, index=True, nullable=False)
    event_type = Column(String, nullable=False)       # payment.failed, subscription.charge.failed, ...
    payload_json = Column(Text, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow)


class Action(Base):
    """A recovery action taken on a case (retry, payment link, escalate, stop)."""
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)

    action_type = Column(String, nullable=False)      # retry | payment_link | escalate | stop
    reason = Column(Text, nullable=True)               # why this action was chosen (EV score etc.)
    outcome = Column(String, nullable=True)             # success | failure | pending

    taken_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="actions")


class AuditLog(Base):
    """
    Hash-chained, tamper-evident audit log.
    Each row's `this_hash` = sha256(previous_hash + description + reason + timestamp).
    Any modification to a past row breaks the chain for all rows after it.
    """
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)

    description = Column(Text, nullable=False)     # what happened
    reason = Column(Text, nullable=True)             # why it happened

    previous_hash = Column(String, nullable=True)
    this_hash = Column(String, nullable=False)

    timestamp = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="audit_entries")


def compute_hash(previous_hash: str, description: str, reason: str, timestamp: str) -> str:
    """Compute a sha256 hash chaining this entry to the previous one."""
    raw = f"{previous_hash or ''}|{description}|{reason or ''}|{timestamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_last_hash(db) -> str | None:
    """Fetch the hash of the most recent audit log entry, or None if the log is empty."""
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    return last.this_hash if last else None


def write_audit_log(db, case_id: int | None, description: str, reason: str | None = None) -> AuditLog:
    """Append a new, hash-chained audit log entry."""
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
    """Create all tables. Safe to call multiple times."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized: revenue_recovery.db")