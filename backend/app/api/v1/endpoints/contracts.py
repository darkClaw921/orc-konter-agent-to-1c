"""
Эндпоинты для работы с контрактами
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_optional_current_user
from app.models.database import get_db, Contract, ContractData, ProcessingHistory, Counterparty1C
from app.models.enums import ProcessingState, OneCStatus, EventStatus
from app.models.schemas import (
    ContractUploadResponse,
    ContractStatusResponse,
    ContractDataResponse,
    ContractListResponse,
    ContractListItem,
    ContractRawTextResponse,
    OneCInfoResponse,
    CreateIn1CRequest,
    CreateIn1CResponse,
    AddNoteRequest,
    AddNoteResponse,
    RefreshServicesResponse,
    ContractProgressResponse,
)
from app.services.document_validator import DocumentValidator
from app.services.storage_service import StorageService
from app.services.document_processor import DocumentProcessor
from app.services.oneс_service import OneCService
from app.services.llm_service import LLMService
from app.services.progress_service import ProgressService
from app.tasks.processing_tasks import process_contract_task
from app.utils.logging import get_logger
from app.utils.json_utils import convert_decimal_for_jsonb

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


@router.get("/{contract_id}/progress", response_model=ContractProgressResponse)
async def get_contract_progress(
    contract_id: int,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Получить прогресс обработки контракта"""

    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found"
        )

    # Получаем прогресс из Redis
    progress_service = ProgressService()
    try:
        progress_data = await progress_service.get_progress(contract_id)

        if progress_data:
            return ContractProgressResponse(
                contract_id=progress_data['contract_id'],
                stage=progress_data['stage'],
                stage_name=progress_data['stage_name'],
                stage_index=progress_data['stage_index'],
                total_stages=progress_data['total_stages'],
                stage_progress=progress_data['stage_progress'],
                stage_message=progress_data.get('stage_message'),
                overall_progress=progress_data['overall_progress'],
                chunks_total=progress_data.get('chunks_total'),
                chunks_processed=progress_data.get('chunks_processed'),
                updated_at=progress_data.get('updated_at')
            )

        # Если данных в Redis нет, формируем ответ на основе статуса из БД
        stage = contract.status.value
        stage_names = ProgressService.STAGE_NAMES
        stage_order = ProgressService.STAGE_ORDER

        stage_index = stage_order.index(stage) + 1 if stage in stage_order else 0

        # Для завершённых или упавших контрактов показываем 100% или 0%
        if stage == 'completed':
            overall_progress = 100
            stage_progress = 100
        elif stage == 'failed':
            overall_progress = 0
            stage_progress = 0
        else:
            overall_progress = progress_service._calculate_overall_progress(stage, 100)
            stage_progress = 100

        return ContractProgressResponse(
            contract_id=contract_id,
            stage=stage,
            stage_name=stage_names.get(stage, stage),
            stage_index=stage_index,
            total_stages=len(stage_order),
            stage_progress=stage_progress,
            stage_message=stage_names.get(stage, stage),
            overall_progress=overall_progress,
            chunks_total=None,
            chunks_processed=None,
            updated_at=contract.updated_at.isoformat() if contract.updated_at else None
        )
    finally:
        await progress_service.close()


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
        services=contract_data.services,
        all_services=contract_data.all_services,
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


@router.get("/{contract_id}/1c-info", response_model=OneCInfoResponse)
async def get_1c_info(
    contract_id: int,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Получить информацию о работе с 1С для контракта"""
    
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found"
        )
    
    # Получаем данные контракта для ИНН
    contract_data = db.query(ContractData).filter(
        ContractData.contract_id == contract_id
    ).first()
    
    searched_inn = None
    if contract_data:
        searched_inn = contract_data.inn
    
    # Получаем информацию о контрагенте в 1С
    counterparty_1c = None
    if contract_data:
        counterparty_1c = db.query(Counterparty1C).filter(
            Counterparty1C.contract_data_id == contract_data.id
        ).first()
    
    # Получаем информацию из истории обработки о проверке и создании
    check_history = db.query(ProcessingHistory).filter(
        ProcessingHistory.contract_id == contract_id,
        ProcessingHistory.event_type == '1c_check'
    ).order_by(ProcessingHistory.created_at.desc()).first()
    
    create_history = db.query(ProcessingHistory).filter(
        ProcessingHistory.contract_id == contract_id,
        ProcessingHistory.event_type == '1c_create'
    ).order_by(ProcessingHistory.created_at.desc()).first()
    
    # Используем информацию из истории обработки для поиска
    search_inn_from_history = searched_inn
    error_from_check = None
    if check_history and check_history.event_details:
        search_details = check_history.event_details
        if isinstance(search_details, dict):
            search_inn_from_history = search_details.get('inn') or search_inn_from_history
            error_from_check = search_details.get('error')
    
    # Формируем информацию о найденном контрагенте
    found_counterparty = None
    if counterparty_1c:
        # Если есть response_from_1c, используем его
        if counterparty_1c.response_from_1c:
            found_counterparty = counterparty_1c.response_from_1c
        # Иначе формируем из базовых данных
        elif counterparty_1c.entity_uuid:
            found_counterparty = {
                'uuid': counterparty_1c.entity_uuid,
                'name': counterparty_1c.entity_name
            }
    
    # Если нет данных в Counterparty1C, но есть в истории поиска, используем их
    if not found_counterparty and check_history and check_history.event_details:
        search_details = check_history.event_details
        if isinstance(search_details, dict) and search_details.get('found') and search_details.get('counterparty_data'):
            found_counterparty = search_details.get('counterparty_data')
    
    # Проверяем, был ли найден контрагент (если есть UUID, значит был найден или создан)
    was_found = False
    was_created = False
    
    # Проверяем по истории поиска
    if check_history and check_history.event_details:
        search_details = check_history.event_details
        if isinstance(search_details, dict):
            if search_details.get('found'):
                was_found = True
    
    # Проверяем по Counterparty1C
    if counterparty_1c and counterparty_1c.entity_uuid:
        # Если есть UUID, проверяем статус
        if counterparty_1c.status_1c:
            if counterparty_1c.status_1c == OneCStatus.CREATED:
                was_created = True
            elif counterparty_1c.status_1c == OneCStatus.UPDATED:
                was_found = True  # Обновлен = был найден
        else:
            # Если UUID есть, но статуса нет, считаем что найден
            was_found = True
    
    # Проверяем по истории создания
    if create_history and create_history.event_details:
        create_details = create_history.event_details
        if isinstance(create_details, dict):
            if create_details.get('created'):
                was_created = True
    
    # Используем ИНН из истории поиска, если он там есть
    final_searched_inn = search_inn_from_history or searched_inn
    
    # Получаем ошибку из истории создания, если есть
    error_from_create = None
    if create_history and create_history.event_details:
        create_details = create_history.event_details
        if isinstance(create_details, dict):
            error_from_create = create_details.get('error')
    
    # Объединяем ошибки из проверки и создания
    # ВАЖНО: Если контрагент успешно создан (was_created=True), не показываем ошибку проверки,
    # так как она не критична - контрагент все равно был создан успешно
    # Ошибка проверки может быть только информационной, если создание прошло успешно
    if was_created:
        # Если контрагент создан, показываем только ошибку создания (если есть)
        final_error = error_from_create or (counterparty_1c.error_from_1c if counterparty_1c else None)
    else:
        # Если контрагент не создан, показываем все ошибки
        final_error = error_from_check or error_from_create or (counterparty_1c.error_from_1c if counterparty_1c else None)
    
    return OneCInfoResponse(
        contract_id=contract_id,
        searched_inn=final_searched_inn,
        found_counterparty=found_counterparty,
        counterparty_uuid=counterparty_1c.entity_uuid if counterparty_1c else None,
        counterparty_name=counterparty_1c.entity_name if counterparty_1c else None,
        status_1c=counterparty_1c.status_1c.value if counterparty_1c and counterparty_1c.status_1c else None,
        created_in_1c_at=counterparty_1c.created_in_1c_at if counterparty_1c else None,
        response_from_1c=counterparty_1c.response_from_1c if counterparty_1c else None,
        error_from_1c=final_error,
        was_found=was_found,
        was_created=was_created
    )


@router.post("/{contract_id}/create-in-1c", response_model=CreateIn1CResponse, status_code=status.HTTP_200_OK)
async def create_counterparty_in_1c(
    contract_id: int,
    request: CreateIn1CRequest,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Создать контрагента в 1С с данными из LLM ответа или из БД
    
    Если contract_data передан в запросе, используются эти данные.
    Иначе данные берутся из ContractData в БД.
    """
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
    
    # Получаем данные контракта
    contract_data_dict = None
    
    if request.contract_data:
        # Используем данные из запроса (из LLM ответа)
        # ВАЖНО: Всегда используем customer (заказчик), как при обычной обработке
        llm_data = request.contract_data

        # Логируем входящие данные для отладки
        logger.info("Received LLM data for 1C creation",
                   contract_id=contract_id,
                   llm_data_keys=list(llm_data.keys()) if isinstance(llm_data, dict) else None,
                   contract_number=llm_data.get('contract_number') if isinstance(llm_data, dict) else None,
                   contract_date=llm_data.get('contract_date') if isinstance(llm_data, dict) else None)

        # Определяем источник данных контрагента
        # Приоритет: customer -> корневые поля (legacy формат)
        counterparty_source = None
        role = 'Заказчик'
        
        # Сначала пытаемся использовать customer (заказчик)
        if llm_data.get('customer') and isinstance(llm_data.get('customer'), dict):
            customer = llm_data.get('customer')
            if customer.get('inn'):
                counterparty_source = customer
                role = 'Заказчик'
                logger.info("Using customer data from LLM response", contract_id=contract_id)
        
        # Если customer не найден или не имеет inn, используем корневые поля (legacy формат)
        if not counterparty_source and llm_data.get('inn'):
            counterparty_source = llm_data
            role = llm_data.get('role', 'Заказчик')
            logger.info("Using root data from LLM response (legacy format)", contract_id=contract_id)
        
        if counterparty_source:
            # Формируем данные контрагента из выбранного источника
            contract_data_dict = {
                'inn': counterparty_source.get('inn'),
                'kpp': counterparty_source.get('kpp'),
                'full_name': counterparty_source.get('full_name'),
                'short_name': counterparty_source.get('short_name'),
                'legal_entity_type': counterparty_source.get('legal_entity_type'),
                'organizational_form': counterparty_source.get('organizational_form'),
                'role': role,
                'is_supplier': False,  # Всегда создаем заказчика
                'is_buyer': True,      # Всегда создаем заказчика
                # Дополнительные поля из корневого объекта
                'contract_name': llm_data.get('contract_name'),
                'contract_number': llm_data.get('contract_number'),
                'contract_date': llm_data.get('contract_date'),
                'contract_price': llm_data.get('contract_price'),
                'vat_percent': llm_data.get('vat_percent'),
                'vat_type': llm_data.get('vat_type'),
                'service_description': llm_data.get('service_description'),
                'services': llm_data.get('services'),
                'all_services': llm_data.get('all_services'),  # Услуги из шага 3.5
                'service_start_date': llm_data.get('service_start_date'),
                'service_end_date': llm_data.get('service_end_date'),
                'locations': llm_data.get('locations') or llm_data.get('service_locations'),
                'responsible_persons': llm_data.get('responsible_persons'),
                'customer': llm_data.get('customer'),
                'contractor': llm_data.get('contractor'),
                'payment_terms': llm_data.get('payment_terms'),
                'acceptance_procedure': llm_data.get('acceptance_procedure'),
                'specification_exists': llm_data.get('specification_exists'),
                'pricing_method': llm_data.get('pricing_method'),
                'reporting_forms': llm_data.get('reporting_forms'),
                'additional_conditions': llm_data.get('additional_conditions'),
                'technical_info': llm_data.get('technical_info'),
                'task_execution_term': llm_data.get('task_execution_term'),
            }

            # Дополняем данные из БД, если чего-то не хватает в LLM ответе
            # (некоторые поля могут отсутствовать в ответе агрегации)
            contract_data_db = db.query(ContractData).filter(
                ContractData.contract_id == contract_id
            ).first()

            if contract_data_db:
                # Дополняем отсутствующие поля из БД
                if not contract_data_dict.get('all_services') and contract_data_db.all_services:
                    contract_data_dict['all_services'] = contract_data_db.all_services
                    logger.info("Loaded all_services from database", contract_id=contract_id)

                if not contract_data_dict.get('contract_number') and contract_data_db.contract_number:
                    contract_data_dict['contract_number'] = contract_data_db.contract_number
                    logger.info("Loaded contract_number from database", contract_id=contract_id, contract_number=contract_data_db.contract_number)

                if not contract_data_dict.get('contract_date') and contract_data_db.contract_date:
                    contract_data_dict['contract_date'] = contract_data_db.contract_date.isoformat() if contract_data_db.contract_date else None
                    logger.info("Loaded contract_date from database", contract_id=contract_id, contract_date=contract_data_dict['contract_date'])

                if not contract_data_dict.get('contract_price') and contract_data_db.contract_price:
                    contract_data_dict['contract_price'] = float(contract_data_db.contract_price)

                if not contract_data_dict.get('service_start_date') and contract_data_db.service_start_date:
                    contract_data_dict['service_start_date'] = contract_data_db.service_start_date.isoformat()

                if not contract_data_dict.get('service_end_date') and contract_data_db.service_end_date:
                    contract_data_dict['service_end_date'] = contract_data_db.service_end_date.isoformat()

            logger.info("Using contract data from LLM response",
                       contract_id=contract_id,
                       has_inn=bool(contract_data_dict.get('inn')),
                       has_all_services=bool(contract_data_dict.get('all_services')),
                       contract_number=contract_data_dict.get('contract_number'),
                       contract_date=contract_data_dict.get('contract_date'),
                       role=role,
                       counterparty_source='customer' if llm_data.get('customer') else 'root')
        else:
            logger.warning("Could not determine counterparty from LLM data", 
                          contract_id=contract_id,
                          has_customer=bool(llm_data.get('customer')),
                          has_root_inn=bool(llm_data.get('inn')))
    else:
        # Берем данные из БД
        contract_data_db = db.query(ContractData).filter(
            ContractData.contract_id == contract_id
        ).first()
        
        if not contract_data_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contract data not found. Please provide contract_data in request or ensure contract was processed."
            )
        
        # Преобразуем данные из БД в словарь
        contract_data_dict = {
            'inn': contract_data_db.inn,
            'kpp': contract_data_db.kpp,
            'full_name': contract_data_db.full_name,
            'short_name': contract_data_db.short_name,
            'legal_entity_type': contract_data_db.legal_entity_type.value if contract_data_db.legal_entity_type else None,
            'organizational_form': contract_data_db.organizational_form,
            'is_supplier': contract_data_db.is_supplier,
            'is_buyer': contract_data_db.is_buyer,
            'contract_name': contract_data_db.contract_name,
            'contract_number': contract_data_db.contract_number,
            'contract_date': contract_data_db.contract_date.isoformat() if contract_data_db.contract_date else None,
            'contract_price': float(contract_data_db.contract_price) if contract_data_db.contract_price else None,
            'vat_percent': float(contract_data_db.vat_percent) if contract_data_db.vat_percent else None,
            'vat_type': contract_data_db.vat_type.value if contract_data_db.vat_type else None,
            'service_description': contract_data_db.service_description,
            'services': contract_data_db.services,
            'all_services': contract_data_db.all_services,  # Услуги из шага 3.5
            'service_start_date': contract_data_db.service_start_date.isoformat() if contract_data_db.service_start_date else None,
            'service_end_date': contract_data_db.service_end_date.isoformat() if contract_data_db.service_end_date else None,
            'locations': contract_data_db.locations,
            'responsible_persons': contract_data_db.responsible_persons,
            'customer': contract_data_db.customer,
            'contractor': contract_data_db.contractor,
        }

        # Определяем роль на основе is_supplier/is_buyer
        if contract_data_db.is_supplier:
            contract_data_dict['role'] = 'Поставщик'
        elif contract_data_db.is_buyer:
            contract_data_dict['role'] = 'Заказчик'

        logger.info("Using contract data from database",
                   contract_id=contract_id,
                   has_all_services=bool(contract_data_db.all_services))
    
    # Проверяем наличие данных и ИНН
    if not contract_data_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract contract data. Please ensure contract_data contains 'inn' field or 'customer'/'contractor' objects with 'inn' field."
        )
    
    inn = contract_data_dict.get('inn')
    if not inn:
        # Пробуем найти ИНН в customer или contractor
        customer = contract_data_dict.get('customer')
        contractor = contract_data_dict.get('contractor')
        
        if customer and isinstance(customer, dict) and customer.get('inn'):
            inn = customer.get('inn')
            # Обновляем данные из customer
            contract_data_dict.update({
                'inn': customer.get('inn'),
                'kpp': customer.get('kpp') or contract_data_dict.get('kpp'),
                'full_name': customer.get('full_name') or contract_data_dict.get('full_name'),
                'short_name': customer.get('short_name') or contract_data_dict.get('short_name'),
                'legal_entity_type': customer.get('legal_entity_type') or contract_data_dict.get('legal_entity_type'),
                'organizational_form': customer.get('organizational_form') or contract_data_dict.get('organizational_form'),
                'role': 'Заказчик',
                'is_buyer': True
            })
            logger.info("Extracted INN from customer object", contract_id=contract_id, inn=inn)
        elif contractor and isinstance(contractor, dict) and contractor.get('inn'):
            inn = contractor.get('inn')
            # Обновляем данные из contractor
            contract_data_dict.update({
                'inn': contractor.get('inn'),
                'kpp': contractor.get('kpp') or contract_data_dict.get('kpp'),
                'full_name': contractor.get('full_name') or contract_data_dict.get('full_name'),
                'short_name': contractor.get('short_name') or contract_data_dict.get('short_name'),
                'legal_entity_type': contractor.get('legal_entity_type') or contract_data_dict.get('legal_entity_type'),
                'organizational_form': contractor.get('organizational_form') or contract_data_dict.get('organizational_form'),
                'role': 'Поставщик',
                'is_supplier': True
            })
            logger.info("Extracted INN from contractor object", contract_id=contract_id, inn=inn)
    
    if not inn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contract data must contain 'inn' field. Check that 'inn' is present in root, 'customer', or 'contractor' object."
        )
    
    # Получаем raw_text из файла
    raw_text = None
    try:
        doc_processor = DocumentProcessor()
        if doc_processor.load_document(contract.file_path):
            raw_text = doc_processor.extract_text()
    except Exception as e:
        logger.warning("Failed to extract raw text for 1C creation", 
                      contract_id=contract_id, 
                      error=str(e))
    
    # Создаем контрагента в 1С
    oneс_service = OneCService()
    create_error = None
    counterparty_uuid = None
    agreement_uuid = None
    entity_data = None
    
    try:
        created_result = await oneс_service.create_counterparty(
            contract_data_dict,
            contract.file_path,
            raw_text=raw_text
        )
        
        if created_result and isinstance(created_result, dict):
            counterparty_uuid = created_result.get('uuid')
            entity_data = created_result.get('entity')
            agreement_uuid = created_result.get('agreement_uuid')
            
            if counterparty_uuid:
                # Сохраняем информацию о создании в ProcessingHistory и Counterparty1C
                create_result_details = {
                    'inn': contract_data_dict.get('inn'),
                    'created': True,
                    'counterparty_uuid': counterparty_uuid,
                    'agreement_uuid': agreement_uuid,
                    'error': None
                }
                
                history_entry = ProcessingHistory(
                    contract_id=contract_id,
                    event_type='1c_create',
                    event_status=EventStatus.SUCCESS,
                    event_message="Создание контрагента в 1С (через API)",
                    event_details=create_result_details
                )
                db.add(history_entry)
                
                # Сохраняем данные в Counterparty1C
                contract_data_db = db.query(ContractData).filter(
                    ContractData.contract_id == contract_id
                ).first()
                
                if contract_data_db:
                    # Извлекаем наименование из entity_data
                    entity_name = None
                    if entity_data:
                        entity_name = (
                            entity_data.get('Description') or
                            entity_data.get('Наименование') or
                            entity_data.get('НаименованиеПолное') or
                            contract_data_dict.get('full_name') or
                            contract_data_dict.get('short_name')
                        )
                    
                    # Проверяем, существует ли уже запись
                    counterparty_1c = db.query(Counterparty1C).filter(
                        Counterparty1C.contract_data_id == contract_data_db.id
                    ).first()
                    
                    if counterparty_1c:
                        # Обновляем существующую запись
                        counterparty_1c.entity_uuid = counterparty_uuid
                        counterparty_1c.entity_name = entity_name
                        counterparty_1c.status_1c = OneCStatus.CREATED
                        counterparty_1c.created_in_1c_at = datetime.utcnow()
                        counterparty_1c.response_from_1c = entity_data
                        counterparty_1c.error_from_1c = None
                    else:
                        # Создаем новую запись
                        counterparty_1c = Counterparty1C(
                            contract_data_id=contract_data_db.id,
                            entity_uuid=counterparty_uuid,
                            entity_name=entity_name,
                            status_1c=OneCStatus.CREATED,
                            created_in_1c_at=datetime.utcnow(),
                            response_from_1c=entity_data
                        )
                        db.add(counterparty_1c)
                    
                    db.commit()
                    logger.info("Counterparty created in 1C via API",
                               contract_id=contract_id,
                               counterparty_uuid=counterparty_uuid,
                               agreement_uuid=agreement_uuid)
            else:
                create_error = "Failed to create counterparty: no UUID returned"
                logger.error("Failed to create counterparty - no UUID", contract_id=contract_id)
        else:
            create_error = "Failed to create counterparty: invalid response"
            logger.error("Failed to create counterparty - invalid response", contract_id=contract_id)
            
    except Exception as e:
        create_error = str(e)
        logger.error("Failed to create counterparty in 1C",
                    contract_id=contract_id,
                    error=create_error,
                    error_type=type(e).__name__,
                    exc_info=True)
        
        # Сохраняем ошибку в ProcessingHistory
        create_result_details = {
            'inn': contract_data_dict.get('inn'),
            'created': False,
            'counterparty_uuid': None,
            'error': create_error
        }
        
        history_entry = ProcessingHistory(
            contract_id=contract_id,
            event_type='1c_create',
            event_status=EventStatus.ERROR,
            event_message=f"Создание контрагента в 1С (через API) - ошибка: {create_error}",
            event_details=create_result_details
        )
        db.add(history_entry)
        db.commit()
    
    if counterparty_uuid:
        return CreateIn1CResponse(
            success=True,
            counterparty_uuid=counterparty_uuid,
            agreement_uuid=agreement_uuid,
            error=None,
            message=f"Контрагент успешно создан в 1С. UUID: {counterparty_uuid}" + 
                   (f", договор создан: {agreement_uuid}" if agreement_uuid else "")
        )
    else:
        return CreateIn1CResponse(
            success=False,
            counterparty_uuid=None,
            agreement_uuid=None,
            error=create_error or "Unknown error",
            message=f"Ошибка при создании контрагента в 1С: {create_error or 'Unknown error'}"
        )


@router.post("/counterparty/{counterparty_uuid}/note", response_model=AddNoteResponse, status_code=status.HTTP_200_OK)
async def add_note_to_counterparty(
    counterparty_uuid: str,
    request: AddNoteRequest,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Добавить заметку к контрагенту в 1С
    
    Args:
        counterparty_uuid: UUID контрагента в 1С (из пути URL)
        request: Данные заметки (note_text, comment)
        current_user: Текущий пользователь (опционально)
        db: Сессия базы данных
        
    Returns:
        AddNoteResponse с результатом операции
    """
    onec_service = OneCService()
    
    try:
        result = await onec_service.add_note_to_counterparty(
            counterparty_uuid=counterparty_uuid,
            note_text=request.note_text,
            comment=request.comment
        )
        
        if result and result.get('created'):
            note_uuid = result.get('uuid')
            logger.info("Note added to counterparty via API",
                       counterparty_uuid=counterparty_uuid,
                       note_uuid=note_uuid,
                       user=current_user.get("username") if current_user else "anonymous")
            
            return AddNoteResponse(
                success=True,
                note_uuid=note_uuid,
                error=None,
                message=f"Заметка успешно добавлена к контрагенту. UUID заметки: {note_uuid}"
            )
        else:
            error_msg = "Failed to add note: invalid response from MCP service"
            logger.error("Failed to add note - invalid response",
                        counterparty_uuid=counterparty_uuid)
            
            return AddNoteResponse(
                success=False,
                note_uuid=None,
                error=error_msg,
                message=f"Ошибка при добавлении заметки: {error_msg}"
            )
            
    except Exception as e:
        error_msg = str(e)
        logger.error("Failed to add note to counterparty",
                    counterparty_uuid=counterparty_uuid,
                    error=error_msg,
                    error_type=type(e).__name__,
                    exc_info=True)
        
        return AddNoteResponse(
            success=False,
            note_uuid=None,
            error=error_msg,
            message=f"Ошибка при добавлении заметки к контрагенту: {error_msg}"
        )


@router.post("/{contract_id}/refresh-services", response_model=RefreshServicesResponse, status_code=status.HTTP_200_OK)
async def refresh_services(
    contract_id: int,
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Обновить список услуг из документа через LLM

    Повторно извлекает все услуги из документа с помощью специализированного промпта.
    """
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

    # Извлекаем текст из документа
    doc_processor = DocumentProcessor()
    if not doc_processor.load_document(contract.file_path):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load document"
        )

    raw_text = doc_processor.extract_text()

    # Определяем чанки
    max_single_request_size = 64000
    document_size = len(raw_text)

    if document_size <= max_single_request_size:
        chunks = [raw_text]
    else:
        chunks = doc_processor.get_chunks_for_llm()

    # Извлекаем услуги через LLM
    llm_service = LLMService()
    services = []
    error_msg = None

    try:
        services = await llm_service.extract_services_from_chunks(chunks)

        # Сохраняем информацию о запросе в ProcessingHistory
        request_info = {
            "request_type": "services_extraction",
            "chunks_count": len(chunks),
            "services_count": len(services),
            "timestamp": datetime.utcnow().isoformat(),
            "status": "success"
        }

        history_entry = ProcessingHistory(
            contract_id=contract_id,
            event_type='llm_request',
            event_status=EventStatus.SUCCESS,
            event_message=f"Извлечение услуг (через API): найдено {len(services)} услуг",
            event_details=request_info
        )
        db.add(history_entry)

        # Обновляем all_services в ContractData
        contract_data = db.query(ContractData).filter(
            ContractData.contract_id == contract_id
        ).first()

        if contract_data:
            # Обновляем поле all_services с преобразованием Decimal в float
            contract_data.all_services = convert_decimal_for_jsonb(services)
            db.commit()

        logger.info("Services refreshed via API",
                   contract_id=contract_id,
                   services_count=len(services),
                   user=current_user.get("username") if current_user else "anonymous")

    except Exception as e:
        error_msg = str(e)
        logger.error("Failed to refresh services",
                    contract_id=contract_id,
                    error=error_msg,
                    error_type=type(e).__name__,
                    exc_info=True)

        # Сохраняем ошибку в ProcessingHistory
        request_info = {
            "request_type": "services_extraction",
            "chunks_count": len(chunks),
            "timestamp": datetime.utcnow().isoformat(),
            "status": "error",
            "error": error_msg
        }

        history_entry = ProcessingHistory(
            contract_id=contract_id,
            event_type='llm_request',
            event_status=EventStatus.ERROR,
            event_message=f"Извлечение услуг (через API) - ошибка: {error_msg}",
            event_details=request_info
        )
        db.add(history_entry)
        db.commit()

    if error_msg:
        return RefreshServicesResponse(
            success=False,
            contract_id=contract_id,
            services_count=0,
            services=None,
            error=error_msg,
            message=f"Ошибка при извлечении услуг: {error_msg}"
        )

    return RefreshServicesResponse(
        success=True,
        contract_id=contract_id,
        services_count=len(services),
        services=services,
        error=None,
        message=f"Успешно извлечено {len(services)} услуг из документа"
    )
