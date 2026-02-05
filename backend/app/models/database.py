"""
SQLAlchemy модели базы данных
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.sql import func

from app.config import settings
from app.models.enums import (
    EventStatus,
    GovComType,
    LegalEntityType,
    OneCStatus,
    ProcessingState,
    Role,
    VATType,
)

Base = declarative_base()

# Создание engine и sessionmaker
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Contract(Base):
    """Модель для хранения информации о загруженных контрактах"""
    __tablename__ = "contracts"
    
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid4, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(BigInteger)
    file_hash = Column(String(64))
    status = Column(SQLEnum(ProcessingState), default=ProcessingState.UPLOADED, nullable=False, index=True)
    error_message = Column(Text)
    processing_started_at = Column(DateTime(timezone=True))
    processing_completed_at = Column(DateTime(timezone=True))
    created_by = Column(String(100))
    notes = Column(Text)
    
    # Relationships
    contract_data = relationship("ContractData", back_populates="contract", uselist=False)
    processing_history = relationship("ProcessingHistory", back_populates="contract", cascade="all, delete-orphan")
    validation_results = relationship("ValidationResult", back_populates="contract", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_contracts_status", "status"),
        Index("idx_contracts_created_at", "created_at"),
    )


class ContractData(Base):
    """Модель для хранения извлеченных данных контракта"""
    __tablename__ = "contract_data"
    
    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False, unique=True, index=True)
    inn = Column(String(12), nullable=False, index=True)
    kpp = Column(String(9))
    legal_entity_type = Column(SQLEnum(LegalEntityType), nullable=False)
    full_name = Column(String(500), nullable=False)
    short_name = Column(String(300))
    organizational_form = Column(String(100))
    gov_com_type = Column(SQLEnum(GovComType))
    is_supplier = Column(Boolean)
    is_buyer = Column(Boolean)
    contract_name = Column(String(500))
    contract_number = Column(String(50))
    contract_date = Column(Date)
    contract_price = Column(Numeric(15, 2))
    vat_percent = Column(Numeric(3, 2))
    vat_type = Column(SQLEnum(VATType))
    service_description = Column(Text)
    service_start_date = Column(Date)
    service_end_date = Column(Date)
    locations = Column(JSONB)  # массив адресов оказания услуг
    responsible_persons = Column(JSONB)  # ФИО и контакты ответственных лиц
    services = Column(JSONB)  # список услуг из спецификации/таблиц: name, quantity, unit, unit_price, total_price, description
    all_services = Column(JSONB)  # все услуги по договору (отдельное извлечение): name, quantity, unit, unit_price, total_price, description
    customer = Column(JSONB)  # информация о заказчике (Покупателе): inn, kpp, full_name, short_name, organizational_form, legal_entity_type
    contractor = Column(JSONB)  # информация об исполнителе (Поставщике): inn, kpp, full_name, short_name, organizational_form, legal_entity_type
    payment_terms = Column(Text)
    payment_deferral_days = Column(Integer)  # количество календарных дней отсрочки платежа
    specification_exists = Column(Boolean)
    pricing_method = Column(Text)
    acceptance_procedure = Column(Text)
    reporting_forms = Column(Text)
    task_execution_term = Column(String(100))
    additional_conditions = Column(Text)
    technical_info = Column(Text)
    extraction_confidence = Column(Numeric(3, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    contract = relationship("Contract", back_populates="contract_data")
    counterparty_1c = relationship("Counterparty1C", back_populates="contract_data", uselist=False)
    
    __table_args__ = (
        Index("idx_contract_data_inn", "inn"),
        Index("idx_contract_data_contract_id", "contract_id"),
    )


class ProcessingHistory(Base):
    """Модель для хранения истории обработки контрактов"""
    __tablename__ = "processing_history"
    
    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False, index=True)
    event_type = Column(String(50))  # 'extraction', 'validation', '1c_check', '1c_create', etc
    event_status = Column(SQLEnum(EventStatus), default=EventStatus.SUCCESS, nullable=False)
    event_message = Column(Text)
    event_details = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_by = Column(String(100))
    
    # Relationships
    contract = relationship("Contract", back_populates="processing_history")
    
    __table_args__ = (
        Index("idx_processing_history_contract_id", "contract_id"),
        Index("idx_processing_history_event_type", "event_type"),
    )


class ValidationResult(Base):
    """Модель для хранения результатов валидации"""
    __tablename__ = "validation_results"
    
    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False, index=True)
    test_case_id = Column(Integer)
    test_case_name = Column(String(255))
    expected_result = Column(JSONB)
    actual_result = Column(JSONB)
    match = Column(Boolean)
    mismatched_fields = Column(JSONB)
    validated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    contract = relationship("Contract", back_populates="validation_results")
    
    __table_args__ = (
        Index("idx_validation_results_contract_id", "contract_id"),
    )


class Counterparty1C(Base):
    """Модель для хранения информации о 1С интеграции"""
    __tablename__ = "counterparty_1c"

    id = Column(Integer, primary_key=True, index=True)
    contract_data_id = Column(Integer, ForeignKey("contract_data.id"), nullable=False, unique=True, index=True)
    entity_uuid = Column(String(36))  # UUID контрагента из 1С
    entity_name = Column(String(255))
    agreement_uuid = Column(String(36))  # UUID договора из 1С
    status_1c = Column(SQLEnum(OneCStatus))
    created_in_1c_at = Column(DateTime(timezone=True))
    response_from_1c = Column(JSONB)
    error_from_1c = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    contract_data = relationship("ContractData", back_populates="counterparty_1c")


def get_db():
    """Dependency для получения сессии БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
