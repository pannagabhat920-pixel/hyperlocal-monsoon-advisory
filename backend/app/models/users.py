from sqlalchemy import Column, Integer, String, Boolean, Float, Date, DateTime, ForeignKey, Enum as SQLEnum, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.enums import UserRole, IrrigationSource

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    role = Column(SQLEnum(UserRole), default=UserRole.FARMER, nullable=False, index=True)
    preferred_language = Column(String(10), default="en", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    consent_given_at = Column(DateTime(timezone=True), nullable=True)
    whatsapp_consent = Column(Boolean, default=True, nullable=False)
    sms_consent = Column(Boolean, default=True, nullable=False)
    opted_out_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


    farmer_profile = relationship("FarmerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    jurisdictions = relationship("OfficerJurisdiction", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")


class FarmerProfile(Base):
    __tablename__ = "farmer_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    panchayat_id = Column(Integer, ForeignKey("panchayats.id", ondelete="SET NULL"), nullable=True, index=True)
    crop_type = Column(String(100), nullable=False)
    sowing_date = Column(Date, nullable=True)
    soil_type = Column(String(50), nullable=True)
    irrigation_source = Column(SQLEnum(IrrigationSource), default=IrrigationSource.RAINFED, nullable=False)
    farm_size_acres = Column(Float, nullable=True)
    crop_status = Column(String(50), default="NOT_STARTED", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="farmer_profile")
    panchayat = relationship("Panchayat", back_populates="farmer_profiles")


class OfficerJurisdiction(Base):
    __tablename__ = "officer_jurisdictions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    district_id = Column(Integer, ForeignKey("districts.id", ondelete="CASCADE"), nullable=True, index=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"), nullable=True, index=True)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="jurisdictions")
    block = relationship("Block", back_populates="officer_jurisdictions")


class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    otp_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="refresh_tokens")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(100), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    user = relationship("User", back_populates="audit_logs")
