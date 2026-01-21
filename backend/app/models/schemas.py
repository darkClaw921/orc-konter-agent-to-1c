"""
Pydantic схемы для API
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ProcessingState


class ContractUploadResponse(BaseModel):
    """Ответ на загрузку контракта"""
    contract_id: int
    filename: str
    status: str
    task_id: Optional[str] = None
    created_at: datetime


class ContractStatusResponse(BaseModel):
    """Ответ со статусом обработки контракта"""
    contract_id: int
    status: ProcessingState
    created_at: datetime
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class ContractDataResponse(BaseModel):
    """Ответ с извлеченными данными контракта"""
    contract_id: int
    inn: str
    kpp: Optional[str] = None
    legal_entity_type: str
    full_name: str
    short_name: Optional[str] = None
    organizational_form: Optional[str] = None
    is_supplier: Optional[bool] = None
    is_buyer: Optional[bool] = None
    contract_name: Optional[str] = None
    contract_number: Optional[str] = None
    contract_date: Optional[date] = None
    contract_price: Optional[Decimal] = None
    vat_percent: Optional[Decimal] = None
    vat_type: Optional[str] = None
    service_description: Optional[str] = None
    service_start_date: Optional[date] = None
    service_end_date: Optional[date] = None
    locations: Optional[List[dict]] = None
    responsible_persons: Optional[List[dict]] = None
    customer: Optional[dict] = None  # информация о заказчике (Покупателе)
    contractor: Optional[dict] = None  # информация об исполнителе (Поставщике)
    extraction_confidence: Optional[Decimal] = None


class ContractListItem(BaseModel):
    """Элемент списка контрактов"""
    id: int
    uuid: UUID
    original_filename: str
    status: ProcessingState
    created_at: datetime
    updated_at: datetime
    inn: Optional[str] = None
    full_name: Optional[str] = None


class ContractListResponse(BaseModel):
    """Ответ со списком контрактов"""
    contracts: List[ContractListItem]
    total: int
    skip: int
    limit: int


class ContractRawTextResponse(BaseModel):
    """Ответ с полным распознанным текстом документа"""
    contract_id: int
    raw_text: str
    text_length: int
    extraction_method: Optional[str] = None


class OneCInfoResponse(BaseModel):
    """Ответ с информацией о работе с 1С"""
    contract_id: int
    searched_inn: Optional[str] = None
    found_counterparty: Optional[dict] = None
    counterparty_uuid: Optional[str] = None
    counterparty_name: Optional[str] = None
    status_1c: Optional[str] = None
    created_in_1c_at: Optional[datetime] = None
    response_from_1c: Optional[dict] = None
    error_from_1c: Optional[str] = None
    was_found: bool = False
    was_created: bool = False
