"""
Эндпоинты для работы с контрактами
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_optional_current_user
from app.models.database import get_db, Contract, ContractData, ProcessingHistory
from app.models.enums import ProcessingState
from app.models.schemas import (
    ContractUploadResponse,
    ContractStatusResponse,
    ContractDataResponse,
    ContractListResponse,
    ContractListItem,
    ContractRawTextResponse
)
from app.services.document_validator import DocumentValidator
from app.services.storage_service import StorageService
from app.services.document_processor import DocumentProcessor
from app.tasks.processing_tasks import process_contract_task
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

storage_service = StorageService()


@router.post("/upload", response_model=ContractUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_contract(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Загрузить контракт для обработки"""
    
    # Валидация файла
    if not file.filename or not file.filename.lower().endswith('.docx'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only DOCX files are supported"
        )
    
    try:
        # Читаем содержимое файла
        file_content = await file.read()
        
        # Валидация размера
        if len(file_content) > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size exceeds 50MB limit"
            )
        
        # Сохраняем файл
        file_path, file_hash = storage_service.save_uploaded_file(file_content, file.filename)
        
        # Валидация DOCX файла
        is_valid, error_message = DocumentValidator.validate_file(file_path, file.filename)
        if not is_valid:
            storage_service.delete_file(file_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
        
        # Создаем запись в БД
        contract = Contract(
            original_filename=file.filename,
            file_path=file_path,
            file_size_bytes=len(file_content),
            file_hash=file_hash,
            status=ProcessingState.UPLOADED,
            created_by=current_user.get("username") if current_user else "anonymous"
        )
        db.add(contract)
        db.commit()
        db.refresh(contract)
        
        # Запускаем асинхронную обработку
        try:
            task = process_contract_task.delay(contract.id, file_path)
            logger.info("Contract uploaded and task queued",
                       contract_id=contract.id,
                       filename=file.filename,
                       task_id=task.id,
                       user=current_user.get("username") if current_user else "anonymous")
        except Exception as e:
            logger.error("Failed to queue processing task",
                        contract_id=contract.id,
                        error=str(e),
                        error_type=type(e).__name__)
            # Обновляем статус на failed
            contract.status = ProcessingState.FAILED
            contract.error_message = f"Failed to queue task: {str(e)}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to queue processing task: {str(e)}"
            )
        
        return ContractUploadResponse(
            contract_id=contract.id,
            filename=file.filename,
            status=contract.status.value,
            task_id=task.id,
            created_at=contract.created_at
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to upload contract", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process upload"
        )


@router.get("/{contract_id}/status", response_model=ContractStatusResponse)
async def get_contract_status(
    contract_id: int,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Получить статус обработки контракта"""
    
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found"
        )
    
    return ContractStatusResponse(
        contract_id=contract.id,
        status=contract.status,
        created_at=contract.created_at,
        processing_started_at=contract.processing_started_at,
        processing_completed_at=contract.processing_completed_at,
        error_message=contract.error_message
    )


@router.get("/{contract_id}/data", response_model=ContractDataResponse)
async def get_contract_data(
    contract_id: int,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Получить извлеченные данные контракта"""
    
    contract_data = db.query(ContractData).filter(
        ContractData.contract_id == contract_id
    ).first()
    
    if not contract_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract data not found"
        )
    
    return ContractDataResponse(
        contract_id=contract_data.contract_id,
        inn=contract_data.inn,
        kpp=contract_data.kpp,
        legal_entity_type=contract_data.legal_entity_type.value if contract_data.legal_entity_type else None,
        full_name=contract_data.full_name,
        short_name=contract_data.short_name,
        organizational_form=contract_data.organizational_form,
        is_supplier=contract_data.is_supplier,
        is_buyer=contract_data.is_buyer,
        contract_name=contract_data.contract_name,
        contract_number=contract_data.contract_number,
        contract_date=contract_data.contract_date,
        contract_price=contract_data.contract_price,
        vat_percent=contract_data.vat_percent,
        vat_type=contract_data.vat_type.value if contract_data.vat_type else None,
        service_description=contract_data.service_description,
        service_start_date=contract_data.service_start_date,
        service_end_date=contract_data.service_end_date,
        locations=contract_data.locations,
        responsible_persons=contract_data.responsible_persons,
        customer=contract_data.customer,
        contractor=contract_data.contractor,
        extraction_confidence=contract_data.extraction_confidence
    )


@router.get("/", response_model=ContractListResponse)
async def list_contracts(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[ProcessingState] = None,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Получить список контрактов"""
    
    query = db.query(Contract)
    
    if status_filter:
        query = query.filter(Contract.status == status_filter)
    
    total = query.count()
    contracts = query.order_by(Contract.created_at.desc()).offset(skip).limit(limit).all()
    
    # Формируем список с данными контрагентов
    contract_items = []
    for contract in contracts:
        contract_data = db.query(ContractData).filter(
            ContractData.contract_id == contract.id
        ).first()
        
        contract_items.append(ContractListItem(
            id=contract.id,
            uuid=contract.uuid,
            original_filename=contract.original_filename,
            status=contract.status,
            created_at=contract.created_at,
            updated_at=contract.updated_at,
            inn=contract_data.inn if contract_data else None,
            full_name=contract_data.full_name if contract_data else None
        ))
    
    return ContractListResponse(
        contracts=contract_items,
        total=total,
        skip=skip,
        limit=limit
    )


@router.post("/{contract_id}/retry", response_model=ContractUploadResponse, status_code=status.HTTP_200_OK)
async def retry_contract_processing(
    contract_id: int,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Повторить обработку контракта"""
    
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found"
        )
    
    # Проверяем, что файл существует
    import os
    if not os.path.exists(contract.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract file not found"
        )
    
    # Сбрасываем статус и очищаем ошибки
    contract.status = ProcessingState.UPLOADED
    contract.error_message = None
    contract.processing_started_at = None
    contract.processing_completed_at = None
    db.commit()
    db.refresh(contract)
    
    # Запускаем асинхронную обработку заново
    try:
        task = process_contract_task.delay(contract.id, contract.file_path)
        logger.info("Contract retry queued",
                   contract_id=contract.id,
                   filename=contract.original_filename,
                   task_id=task.id,
                   user=current_user.get("username") if current_user else "anonymous")
    except Exception as e:
        logger.error("Failed to queue retry task",
                    contract_id=contract.id,
                    error=str(e),
                    error_type=type(e).__name__)
        # Возвращаем статус в failed
        contract.status = ProcessingState.FAILED
        contract.error_message = f"Failed to queue retry task: {str(e)}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue retry task: {str(e)}"
        )
    
    return ContractUploadResponse(
        contract_id=contract.id,
        filename=contract.original_filename,
        status=contract.status.value,
        task_id=task.id,
        created_at=contract.created_at
    )


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: int,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Удалить контракт"""
    
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found"
        )
    
    # Удаляем файл
    try:
        storage_service.delete_file(contract.file_path)
    except Exception as e:
        logger.warning("Failed to delete file", file_path=contract.file_path, error=str(e))
    
    # Удаляем запись из БД
    db.delete(contract)
    db.commit()
    
    logger.info("Contract deleted", contract_id=contract_id, user=current_user.get("username") if current_user else "anonymous")
    
    return None


@router.get("/{contract_id}/llm-info")
async def get_llm_info(
    contract_id: int,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Получить информацию о запросах и ответах LLM для контракта"""
    
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found"
        )
    
    # Получаем информацию о запросах LLM из ProcessingHistory
    llm_requests = db.query(ProcessingHistory).filter(
        ProcessingHistory.contract_id == contract_id,
        ProcessingHistory.event_type == 'llm_request'
    ).order_by(ProcessingHistory.created_at.asc()).all()
    
    # Формируем ответ
    requests_info = []
    for req in llm_requests:
        if req.event_details:
            # Преобразуем event_details в словарь, если это еще не словарь
            if isinstance(req.event_details, dict):
                requests_info.append(req.event_details)
            else:
                # Если это JSONB, он уже должен быть словарем
                requests_info.append(dict(req.event_details))
    
    return {
        "contract_id": contract_id,
        "total_requests": len(requests_info),
        "requests": requests_info
    }


@router.get("/{contract_id}/raw-text", response_model=ContractRawTextResponse)
async def get_contract_raw_text(
    contract_id: int,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Получить полный распознанный текст документа"""
    
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found"
        )
    
    # Проверяем, существует ли файл
    import os
    if not os.path.exists(contract.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract file not found"
        )
    
    # Пытаемся получить текст из ProcessingHistory (первые 1000 символов сохраняются)
    processing_history = db.query(ProcessingHistory).filter(
        ProcessingHistory.contract_id == contract_id,
        ProcessingHistory.event_type == 'status_update'
    ).filter(
        ProcessingHistory.event_details['raw_text'].isnot(None)
    ).order_by(ProcessingHistory.created_at.desc()).first()
    
    raw_text = None
    extraction_method = None
    
    if processing_history and processing_history.event_details:
        event_details = processing_history.event_details
        if isinstance(event_details, dict) and 'raw_text' in event_details:
            # Это только первые 1000 символов, нужно получить полный текст
            raw_text = None  # Будем извлекать заново для получения полного текста
    
    # Если текст не найден или это только превью, извлекаем полный текст из документа
    if raw_text is None:
        try:
            doc_processor = DocumentProcessor()
            if doc_processor.load_document(contract.file_path):
                raw_text = doc_processor.extract_text()
                extraction_method = "document_processor"
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to load document"
                )
        except Exception as e:
            logger.error("Failed to extract raw text", 
                        contract_id=contract_id, 
                        error=str(e),
                        error_type=type(e).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to extract text from document: {str(e)}"
            )
    
    if not raw_text:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Raw text not available for this contract"
        )
    
    return ContractRawTextResponse(
        contract_id=contract_id,
        raw_text=raw_text,
        text_length=len(raw_text),
        extraction_method=extraction_method
    )
