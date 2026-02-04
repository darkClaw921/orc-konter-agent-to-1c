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
    services: Optional[List[dict]] = None  # список услуг из спецификации/таблиц
    all_services: Optional[List[dict]] = None  # все услуги по договору (отдельное извлечение)
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


class CreateIn1CRequest(BaseModel):
    """Запрос на создание контрагента в 1С"""
    contract_data: Optional[dict] = None  # Данные из LLM ответа, если не переданы - берутся из БД


class CreateIn1CResponse(BaseModel):
    """Ответ на создание контрагента в 1С"""
    success: bool
    counterparty_uuid: Optional[str] = None
    agreement_uuid: Optional[str] = None
    error: Optional[str] = None
    message: str


class AddNoteRequest(BaseModel):
    """Запрос на добавление заметки к контрагенту"""
    note_text: str = Field(..., description="Текст заметки для поля 'Представление'")
    comment: Optional[str] = Field(None, description="Дополнительный комментарий для поля 'Комментарий'")


class AddNoteResponse(BaseModel):
    """Ответ на добавление заметки к контрагенту"""
    success: bool
    note_uuid: Optional[str] = None
    error: Optional[str] = None
    message: str


class RefreshServicesResponse(BaseModel):
    """Ответ на обновление услуг"""
    success: bool
    contract_id: int
    services_count: int
    services: Optional[List[dict]] = None
    error: Optional[str] = None
    message: str


class ContractProgressResponse(BaseModel):
    """Ответ с прогрессом обработки контракта"""
    contract_id: int
    stage: str
    stage_name: str
    stage_index: int
    total_stages: int
    stage_progress: int = Field(..., ge=0, le=100, description="Прогресс внутри стадии (0-100)")
    stage_message: Optional[str] = None
    overall_progress: int = Field(..., ge=0, le=100, description="Общий прогресс обработки (0-100)")
    chunks_total: Optional[int] = None
    chunks_processed: Optional[int] = None
    updated_at: Optional[datetime] = None
