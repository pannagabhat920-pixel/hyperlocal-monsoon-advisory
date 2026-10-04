from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, Enum as SQLEnum, JSON, Index, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.enums import AdvisorySeverity, AdvisoryApprovalStatus, NotificationChannel, NotificationStatus, DataSource

class AgronomicRule(Base):
    __tablename__ = "agronomic_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_code = Column(String(50), unique=True, nullable=False, index=True)
    crop_type = Column(String(50), nullable=False, index=True)
    growth_stage = Column(String(50), nullable=False)
    trigger_condition_json = Column(JSON, nullable=False)
    advisory_template_en = Column(Text, nullable=False)
    advisory_template_local = Column(JSON, nullable=True) # {"hi": "...", "mr": "..."}
    severity = Column(SQLEnum(AdvisorySeverity), nullable=False, index=True)
    action_type = Column(String(50), nullable=False)
    source_reference = Column(String(255), nullable=False)
    is_approved = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    advisories = relationship("GeneratedAdvisory", back_populates="rule")


class GeneratedAdvisory(Base):
    __tablename__ = "generated_advisories"

    id = Column(Integer, primary_key=True, index=True)
    panchayat_id = Column(Integer, ForeignKey("panchayats.id", ondelete="CASCADE"), nullable=False, index=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False, index=True)
    forecast_id = Column(Integer, ForeignKey("grid_forecasts.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("agronomic_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    crop_type = Column(String(50), nullable=False, index=True)
    language = Column(String(10), default="en", nullable=False)
    headline = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    audio_url = Column(String(255), nullable=True)
    severity = Column(SQLEnum(AdvisorySeverity), nullable=False, index=True)
    approval_status = Column(SQLEnum(AdvisoryApprovalStatus), default=AdvisoryApprovalStatus.PENDING, nullable=False, index=True)
    approved_by_officer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    data_source = Column(SQLEnum(DataSource), default=DataSource.SIMULATED, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    rule = relationship("AgronomicRule", back_populates="advisories")
    forecast = relationship("GridForecast", back_populates="advisories")
    notifications = relationship("NotificationLog", back_populates="advisory", cascade="all, delete-orphan", passive_deletes=True)
    approved_by = relationship("User", foreign_keys=[approved_by_officer_id])

Index("ix_generated_advisories_block_status", GeneratedAdvisory.block_id, GeneratedAdvisory.approval_status)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    advisory_id = Column(Integer, ForeignKey("generated_advisories.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(SQLEnum(NotificationChannel), default=NotificationChannel.SMS, nullable=False)
    message_content = Column(Text, nullable=False)
    dispatch_status = Column(SQLEnum(NotificationStatus), default=NotificationStatus.QUEUED, nullable=False, index=True)
    provider_message_id = Column(String(100), nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    idempotency_key = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    advisory = relationship("GeneratedAdvisory", back_populates="notifications")
    recipient = relationship("User", foreign_keys=[recipient_user_id])

    __table_args__ = (
        UniqueConstraint("recipient_user_id", "advisory_id", "channel", name="uq_notification_recipient_advisory_channel"),
    )
