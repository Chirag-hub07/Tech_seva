"""SQLAlchemy declarative models strictly representing the 6 verified database tables.

CRITICAL ARCHITECTURE RULES:
- Tables use PostgreSQL GENERATED ALWAYS AS IDENTITY primary keys.
- Preserves JSONB column types for flexible biometric and event data.
- Enforces validated constraints matching the existing database schema.
- Does NOT invent unverified columns (e.g. kit_id or patient status).
- Models are mapped to existing tables; Base.metadata.create_all() MUST NOT be run.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Boolean,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import relationship

from backend.app.database import Base


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    """Compile PostgreSQL JSONB column type to generic JSON for SQLite test engines."""
    return "JSON"


class Patient(Base):
    """Patient master record table representing participating COPD subjects."""

    __tablename__ = "patients"

    id = Column(Integer, Identity(always=True), primary_key=True)
    participant_id = Column(String(64), unique=True, nullable=False, index=True)
    country = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=True)

    # Relationships
    sensor_measurements = relationship(
        "SensorMeasurement",
        back_populates="patient",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    clinical_assessments = relationship(
        "ClinicalAssessment",
        back_populates="patient",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    exacerbations = relationship(
        "Exacerbation",
        back_populates="patient",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    predictions = relationship(
        "Prediction",
        back_populates="patient",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    alerts = relationship(
        "Alert",
        back_populates="patient",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Patient(id={self.id}, participant_id='{self.participant_id}', country='{self.country}')>"


class SensorMeasurement(Base):
    """High-frequency sensor telemetry records from the 8 TOLIFE streams."""

    __tablename__ = "sensor_measurements"

    # Permitted sensor types: BRI, EI, MI, PEI, PRVI, SHRI, SII, SQI
    VALID_SENSOR_TYPES = ("BRI", "EI", "MI", "PEI", "PRVI", "SHRI", "SII", "SQI")

    id = Column(Integer, Identity(always=True), primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    sensor_type = Column(String(16), nullable=False, index=True)
    measured_at = Column(DateTime(timezone=True), nullable=False, index=True)
    measurements = Column(JSONB, nullable=False)
    validity_flags = Column(JSONB, nullable=True)
    is_valid = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"sensor_type IN {tuple(VALID_SENSOR_TYPES)}",
            name="check_valid_sensor_type",
        ),
        Index("idx_sensor_patient_time", "patient_id", "sensor_type", "measured_at"),
    )

    patient = relationship("Patient", back_populates="sensor_measurements")

    def __repr__(self) -> str:
        return f"<SensorMeasurement(id={self.id}, patient_id={self.patient_id}, sensor='{self.sensor_type}')>"


class ClinicalAssessment(Base):
    """Periodic clinical visit assessments (T1 through T5)."""

    __tablename__ = "clinical_assessments"

    VALID_VISIT_TYPES = ("T1", "T2", "T3", "T4", "T5")

    id = Column(Integer, Identity(always=True), primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    visit_date = Column(Date, nullable=False)
    visit_type = Column(String(16), nullable=False)
    clinical_data = Column(JSONB, nullable=True)
    source_record_id = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"visit_type IN {tuple(VALID_VISIT_TYPES)}",
            name="check_valid_visit_type",
        ),
        Index("idx_clinical_patient_source", "patient_id", "source_record_id"),
    )

    patient = relationship("Patient", back_populates="clinical_assessments")

    def __repr__(self) -> str:
        return f"<ClinicalAssessment(id={self.id}, patient_id={self.patient_id}, visit='{self.visit_type}')>"


class Exacerbation(Base):
    """Clinical exacerbation events recorded for participants."""

    __tablename__ = "exacerbations"

    VALID_SEVERITIES = ("Moderate", "Severe")

    id = Column(Integer, Identity(always=True), primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    event_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    severity = Column(String(32), nullable=False)
    source_event_id = Column(String(128), nullable=True)
    event_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"severity IN {tuple(VALID_SEVERITIES)}",
            name="check_valid_exacerbation_severity",
        ),
        Index("idx_exacerbation_patient_source", "patient_id", "source_event_id"),
    )

    patient = relationship("Patient", back_populates="exacerbations")

    def __repr__(self) -> str:
        return f"<Exacerbation(id={self.id}, patient_id={self.patient_id}, severity='{self.severity}')>"


class Prediction(Base):
    """ML-generated forward exacerbation risk predictions."""

    __tablename__ = "predictions"

    id = Column(Integer, Identity(always=True), primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    prediction_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    risk_probability = Column(Float, nullable=False)
    risk_level = Column(String(32), nullable=False)
    prediction_horizon_days = Column(Integer, nullable=False)
    input_window_start = Column(DateTime(timezone=True), nullable=True)
    input_window_end = Column(DateTime(timezone=True), nullable=True)
    model_version = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "risk_probability >= 0.0 AND risk_probability <= 1.0",
            name="check_prediction_probability_range",
        ),
        CheckConstraint(
            "prediction_horizon_days > 0",
            name="check_prediction_horizon_positive",
        ),
        CheckConstraint(
            "input_window_end >= input_window_start OR input_window_end IS NULL OR input_window_start IS NULL",
            name="check_prediction_window_order",
        ),
    )

    patient = relationship("Patient", back_populates="predictions")
    alerts = relationship("Alert", back_populates="prediction")

    def __repr__(self) -> str:
        return f"<Prediction(id={self.id}, patient_id={self.patient_id}, prob={self.risk_probability})>"


class Alert(Base):
    """Clinical risk alerts generated based on model predictions or threshold events."""

    __tablename__ = "alerts"

    VALID_STATUSES = ("pending", "acknowledged", "resolved")
    VALID_LEVELS = ("LOW", "MEDIUM", "HIGH")

    id = Column(Integer, Identity(always=True), primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    prediction_id = Column(Integer, ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True, index=True)
    alert_level = Column(String(32), nullable=False)
    status = Column(String(32), default="pending", nullable=False)
    message = Column(String(512), nullable=False)
    deduplication_key = Column(String(128), unique=True, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"status IN {tuple(VALID_STATUSES)}",
            name="check_valid_alert_status",
        ),
    )

    patient = relationship("Patient", back_populates="alerts")
    prediction = relationship("Prediction", back_populates="alerts")

    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, patient_id={self.patient_id}, level='{self.alert_level}', status='{self.status}')>"
