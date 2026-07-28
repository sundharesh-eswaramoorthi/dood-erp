from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Party(Base):
    __tablename__ = "party"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(BigInteger, index=True)
    branch_id: Mapped[int] = mapped_column(BigInteger, index=True)
    party_code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    party_type: Mapped[str] = mapped_column(String(20), default="customer")
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(20), nullable=True)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PartyContact(Base):
    __tablename__ = "party_contact"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(BigInteger)
    branch_id: Mapped[int] = mapped_column(BigInteger)
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id"))
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class PartyAddress(Base):
    __tablename__ = "party_address"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(BigInteger)
    branch_id: Mapped[int] = mapped_column(BigInteger)
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id"))
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    line1: Mapped[str] = mapped_column(String(200))
    line2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    place_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class PartyDocument(Base):
    __tablename__ = "party_document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(BigInteger)
    branch_id: Mapped[int] = mapped_column(BigInteger)
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id"))
    doc_type: Mapped[str] = mapped_column(String(40))
    file_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(400))
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    uploaded_by: Mapped[int] = mapped_column(BigInteger)
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PartyGstRegistration(Base):
    __tablename__ = "party_gst_registration"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(BigInteger)
    branch_id: Mapped[int] = mapped_column(BigInteger)
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id"))
    gstin: Mapped[str] = mapped_column(String(20))
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
