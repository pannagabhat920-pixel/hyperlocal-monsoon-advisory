from sqlalchemy import Column, Integer, String, Boolean, Float, Date, DateTime, ForeignKey, Enum as SQLEnum, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.enums import DataSource

class GlobalIndices(Base):
    __tablename__ = "global_indices"

    id = Column(Integer, primary_key=True, index=True)
    issue_date = Column(Date, nullable=False, index=True)
    nino34 = Column(Float, nullable=False)
    iod_dmi = Column(Float, nullable=False)
    mjo_phase = Column(Integer, nullable=False)
    mjo_amplitude = Column(Float, nullable=False)
    data_source = Column(SQLEnum(DataSource), default=DataSource.LIVE, nullable=False)
    source_url_oni = Column(String(255), nullable=True)
    source_url_mjo = Column(String(255), nullable=True)
    source_url_dmi = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True, index=True)
    version_tag = Column(String(50), unique=True, nullable=False, index=True)
    model_type = Column(String(50), nullable=False)
    trained_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    metrics_json = Column(JSON, nullable=True)   # None until real hindcast evaluation
    is_active = Column(Boolean, default=True, nullable=False)
    is_trained = Column(Boolean, default=False, nullable=False)  # False until Phase 8+

    forecasts = relationship("GridForecast", back_populates="model_version")


class GridForecast(Base):
    __tablename__ = "grid_forecasts"

    id = Column(Integer, primary_key=True, index=True)
    panchayat_id = Column(Integer, ForeignKey("panchayats.id", ondelete="CASCADE"), nullable=False, index=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_date = Column(Date, nullable=False, index=True)
    target_week_start = Column(Date, nullable=False, index=True)
    target_week_end = Column(Date, nullable=False, index=True)
    lead_week = Column(Integer, nullable=False, index=True) # 1, 2, 3, or 4
    
    onset_prob = Column(Float, nullable=False)
    break_prob = Column(Float, nullable=False)
    excess_rain_prob = Column(Float, nullable=False)
    false_onset_prob = Column(Float, nullable=True, default=0.20)
    break_duration_days_p50 = Column(Float, nullable=True, default=7.0)
    
    p10_rainfall_mm = Column(Float, nullable=False)
    p50_rainfall_mm = Column(Float, nullable=False)
    p90_rainfall_mm = Column(Float, nullable=False)
    
    confidence = Column(Float, nullable=False)
    data_source = Column(SQLEnum(DataSource), default=DataSource.SIMULATED, nullable=False, index=True)

    
    model_version_id = Column(Integer, ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    features_json = Column(JSON, nullable=True)
    shap_values_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    panchayat = relationship("Panchayat", back_populates="forecasts")
    model_version = relationship("ModelVersion", back_populates="forecasts")
    advisories = relationship("GeneratedAdvisory", back_populates="forecast")

Index("ix_grid_forecasts_panchayat_issue_lead", GridForecast.panchayat_id, GridForecast.issue_date, GridForecast.lead_week)
Index("ix_grid_forecasts_block_issue_lead", GridForecast.block_id, GridForecast.issue_date, GridForecast.lead_week)
