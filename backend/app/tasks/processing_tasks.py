"""
Асинхронные задачи обработки контрактов
"""
import asyncio
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.agent.orchestrator import AgentOrchestrator
from app.agent.state_manager import StateManager
from app.models.database import SessionLocal, Contract, ContractData, ProcessingHistory
from app.models.enums import ProcessingState, EventStatus
from app.services.document_processor import DocumentProcessor
from app.services.llm_service import LLMService
from app.services.oneс_service import OneCService
from app.services.progress_service import ProgressService
from app.services.storage_service import StorageService
from app.services.validation_service import ValidationService
from app.tasks.celery_app import celery_app
from app.utils.logging import get_logger
from app.utils.json_utils import convert_decimal_for_jsonb

logger = get_logger(__name__)


def get_db_session() -> Session:
    """Получить сессию БД"""
    return SessionLocal()


@celery_app.task(bind=True, name="process_contract_task")
def process_contract_task(self, contract_id: int, document_path: str):
    """
    Асинхронная задача обработки контракта
    
    Args:
        contract_id: ID контракта в БД
        document_path: Путь к файлу документа
    """
    db = get_db_session()
    
    try:
        # Обновляем статус контракта
        contract = db.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            logger.error("Contract not found", contract_id=contract_id)
            return
        
        contract.status = ProcessingState.PROCESSING
        contract.processing_started_at = datetime.utcnow()
        db.commit()
        
        # Инициализируем компоненты
        state_manager = StateManager(redis_client=None, db_session=db)
        doc_processor = DocumentProcessor()
        llm_service = LLMService()
        validation_service = ValidationService()
        oneс_service = OneCService()
        progress_service = ProgressService()

        # Создаем оркестратор
        orchestrator = AgentOrchestrator(
            state_manager=state_manager,
            doc_processor=doc_processor,
            llm_service=llm_service,
            validation_service=validation_service,
            oneс_service=oneс_service,
            progress_service=progress_service
        )
        
        # Запускаем обработку
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            state = loop.run_until_complete(
                orchestrator.process_contract(contract_id, document_path)
            )
            
            # Сохраняем результаты в БД только если обработка успешна и есть валидные данные
            if state.status == ProcessingState.COMPLETED and state.extracted_data:
                try:
                    contract_data = db.query(ContractData).filter(
                        ContractData.contract_id == contract_id
                    ).first()
                    
                    if not contract_data:
                        contract_data = ContractData(contract_id=contract_id)
                        db.add(contract_data)
                    
                    # Заполняем данные только если они есть и не None
                    if state.extracted_data.get("inn"):
                        contract_data.inn = state.extracted_data.get("inn")
                    if state.extracted_data.get("kpp"):
                        contract_data.kpp = state.extracted_data.get("kpp")
                    if state.extracted_data.get("full_name"):
                        contract_data.full_name = state.extracted_data.get("full_name")
                    if state.extracted_data.get("short_name"):
                        contract_data.short_name = state.extracted_data.get("short_name")
                    if state.extracted_data.get("organizational_form"):
                        contract_data.organizational_form = state.extracted_data.get("organizational_form")
                    if state.extracted_data.get("legal_entity_type"):
                        contract_data.legal_entity_type = state.extracted_data.get("legal_entity_type")
                    if state.extracted_data.get("is_supplier") is not None:
                        contract_data.is_supplier = state.extracted_data.get("is_supplier")
                    if state.extracted_data.get("is_buyer") is not None:
                        contract_data.is_buyer = state.extracted_data.get("is_buyer")
                    if state.extracted_data.get("contract_name"):
                        contract_data.contract_name = state.extracted_data.get("contract_name")
                    if state.extracted_data.get("contract_number"):
                        contract_data.contract_number = state.extracted_data.get("contract_number")
                    # Преобразуем Decimal в float для Numeric полей
                    if state.extracted_data.get("contract_price") is not None:
                        price = state.extracted_data.get("contract_price")
                        contract_data.contract_price = float(price) if isinstance(price, Decimal) else price
                    if state.extracted_data.get("vat_percent") is not None:
                        vat = state.extracted_data.get("vat_percent")
                        contract_data.vat_percent = float(vat) if isinstance(vat, Decimal) else vat
                    if state.extracted_data.get("vat_type"):
                        contract_data.vat_type = state.extracted_data.get("vat_type")
                    if state.extracted_data.get("service_description"):
                        contract_data.service_description = state.extracted_data.get("service_description")
                    # Преобразуем Decimal в float для JSONB полей
                    if state.extracted_data.get("services"):
                        contract_data.services = convert_decimal_for_jsonb(state.extracted_data.get("services"))
                    if state.extracted_data.get("all_services"):
                        contract_data.all_services = convert_decimal_for_jsonb(state.extracted_data.get("all_services"))
                    if state.extracted_data.get("locations"):
                        contract_data.locations = convert_decimal_for_jsonb(state.extracted_data.get("locations"))
                    if state.extracted_data.get("responsible_persons"):
                        contract_data.responsible_persons = convert_decimal_for_jsonb(state.extracted_data.get("responsible_persons"))
                    if state.extracted_data.get("customer"):
                        contract_data.customer = convert_decimal_for_jsonb(state.extracted_data.get("customer"))
                    if state.extracted_data.get("contractor"):
                        contract_data.contractor = convert_decimal_for_jsonb(state.extracted_data.get("contractor"))
                    
                    db.commit()
                except Exception as db_error:
                    db.rollback()
                    logger.error("Failed to save contract data", 
                                contract_id=contract_id,
                                error=str(db_error))
                    # Не прерываем выполнение, просто логируем ошибку
            
            # Обновляем статус контракта
            contract.status = state.status
            contract.processing_completed_at = datetime.utcnow()
            if state.error_message:
                contract.error_message = state.error_message
            
            db.commit()
            
            logger.info("Contract processing completed", 
                       contract_id=contract_id,
                       status=state.status.value)
            
        finally:
            # Закрываем progress_service
            try:
                loop.run_until_complete(progress_service.close())
            except Exception:
                pass
            loop.close()

    except Exception as e:
        logger.error("Contract processing failed", 
                    contract_id=contract_id,
                    error=str(e))
        
        # Rollback любых незакоммиченных изменений
        try:
            db.rollback()
        except:
            pass
        
        # Обновляем статус на FAILED
        try:
            contract = db.query(Contract).filter(Contract.id == contract_id).first()
            if contract:
                contract.status = ProcessingState.FAILED
                contract.error_message = str(e)
                contract.processing_completed_at = datetime.utcnow()
                db.commit()
        except Exception as update_error:
            logger.error("Failed to update contract status", 
                        contract_id=contract_id,
                        error=str(update_error))
            db.rollback()
        
        raise
    
    finally:
        db.close()
