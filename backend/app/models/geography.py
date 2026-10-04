from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from app.db.session import Base

class State(Base):
    __tablename__ = "states"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    lgd_code = Column(Integer, unique=True, nullable=True, index=True)
    geom = Column(Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True), nullable=True)
    is_synthetic_boundary = Column(Boolean, default=False, nullable=False)

    districts = relationship("District", back_populates="state", cascade="all, delete-orphan")


class District(Base):
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True, index=True)
    state_id = Column(Integer, ForeignKey("states.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    lgd_code = Column(Integer, unique=True, nullable=True, index=True)
    geom = Column(Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True), nullable=True)
    is_synthetic_boundary = Column(Boolean, default=False, nullable=False)

    state = relationship("State", back_populates="districts")
    blocks = relationship("Block", back_populates="district", cascade="all, delete-orphan")


class Block(Base):
    __tablename__ = "blocks"

    id = Column(Integer, primary_key=True, index=True)
    district_id = Column(Integer, ForeignKey("districts.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    lgd_code = Column(Integer, unique=True, nullable=True, index=True)
    geom = Column(Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True), nullable=True)
    is_synthetic_boundary = Column(Boolean, default=False, nullable=False)

    district = relationship("District", back_populates="blocks")
    panchayats = relationship("Panchayat", back_populates="block", cascade="all, delete-orphan")
    officer_jurisdictions = relationship("OfficerJurisdiction", back_populates="block")


class Panchayat(Base):
    __tablename__ = "panchayats"

    id = Column(Integer, primary_key=True, index=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    lgd_code = Column(Integer, unique=True, nullable=True, index=True)
    geom = Column(Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True), nullable=True)
    centroid = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=True)
    is_synthetic_boundary = Column(Boolean, default=False, nullable=False)

    block = relationship("Block", back_populates="panchayats")
    farmer_profiles = relationship("FarmerProfile", back_populates="panchayat")
    forecasts = relationship("GridForecast", back_populates="panchayat")

Index("ix_panchayats_block_id_name", Panchayat.block_id, Panchayat.name)
