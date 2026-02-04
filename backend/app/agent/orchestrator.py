"""
Оркестрация обработки контракта
"""
import json
import traceback
from datetime import datetime
from typing import Dict, Any, List

from app.agent.state_manager import AgentState, StateManager
from app.models.enums import ProcessingState, EventStatus, OneCStatus
from app.models.database import ProcessingHistory, Counterparty1C, ContractData, Contract
from app.services.document_processor import DocumentProcessor
from app.services.llm_service import LLMService
from app.services.progress_service import ProgressService
from app.services.prompts import EXTRACT_CONTRACT_DATA_PROMPT, MERGE_CHUNKS_DATA_PROMPT
from app.services.validation_service import ValidationService
from app.utils.logging import get_logger
from typing import Optional

logger = get_logger(__name__)


class AgentOrchestrator:
    """Главный оркестратор для обработки контрактов"""

    def __init__(self,
                 state_manager: StateManager,
                 doc_processor: DocumentProcessor,
                 llm_service: LLMService,
                 validation_service: ValidationService,
                 oneс_service=None,
                 progress_service: Optional[ProgressService] = None):
        self.state_manager = state_manager
        self.doc_processor = doc_processor
        self.llm_service = llm_service
        self.validation_service = validation_service
        self.oneс_service = oneс_service
        self.progress_service = progress_service
    
    async def process_contract(self, contract_id: int, document_path: str) -> AgentState:
        """
        Главный pipeline обработки контракта
        """
        state = AgentState(
            contract_id=contract_id,
            status=ProcessingState.UPLOADED,
            document_path=document_path
        )

        try:
            # Инициализируем прогресс
            await self._update_progress(contract_id, 'uploaded', 100, 'Файл загружен')

            # Шаг 1: Загрузить документ
            await self._load_document(state)

            # Шаг 2: Извлечь текст
            await self._extract_text(state)

            # Шаг 3: Извлечь данные контракта с помощью LLM
            await self._extract_contract_data(state)

            # Шаг 3.5: Извлечь все услуги отдельным запросом
            await self._extract_all_services(state)

            # Шаг 4: Валидировать извлеченные данные
            await self._validate_data(state)

            # Шаг 5: Проверить наличие в 1С (если сервис доступен)
            if self.oneс_service:
                await self._check_existing_in_1c(state)

                # Шаг 6: Создать контрагента в 1С
                await self._create_counterparty_in_1c(state)

            # Шаг 7: Завершить обработку
            state.status = ProcessingState.COMPLETED
            await self._update_progress(contract_id, 'completed', 100, 'Обработка завершена')

        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error("Contract processing failed", 
                        contract_id=contract_id,
                        error=str(e),
                        error_type=type(e).__name__,
                        error_traceback=error_traceback,
                        state_status=state.status.value if hasattr(state, 'status') else None)
            state.status = ProcessingState.FAILED
            state.error_message = str(e)
        
        finally:
            await self.state_manager.save_state(state)
            # Очищаем прогресс после завершения
            if self.progress_service:
                try:
                    await self.progress_service.clear_progress(contract_id)
                except Exception:
                    pass

        return state

    async def _update_progress(
        self,
        contract_id: int,
        stage: str,
        stage_progress: int = 0,
        message: Optional[str] = None,
        chunks_total: Optional[int] = None,
        chunks_processed: Optional[int] = None
    ) -> None:
        """Обновить прогресс обработки"""
        if self.progress_service:
            try:
                await self.progress_service.update_progress(
                    contract_id=contract_id,
                    stage=stage,
                    stage_progress=stage_progress,
                    message=message,
                    chunks_total=chunks_total,
                    chunks_processed=chunks_processed
                )
            except Exception as e:
                logger.warning("Failed to update progress",
                             contract_id=contract_id,
                             error=str(e))

    async def _load_document(self, state: AgentState):
        """Загрузить DOCX документ"""
        logger.info("Loading document", contract_id=state.contract_id)
        await self._update_progress(state.contract_id, 'document_loaded', 0, 'Загрузка документа...')

        if not self.doc_processor.load_document(state.document_path):
            raise Exception(f"Failed to load document: {state.document_path}")

        await self._update_progress(state.contract_id, 'document_loaded', 100, 'Документ загружен')
        await self.state_manager.update_status(
            state.contract_id,
            ProcessingState.DOCUMENT_LOADED
        )
    
    async def _extract_text(self, state: AgentState):
        """Извлечь текст из документа"""
        logger.info("Extracting text", contract_id=state.contract_id)
        await self._update_progress(state.contract_id, 'text_extracted', 0, 'Извлечение текста...')

        state.raw_text = self.doc_processor.extract_text()

        await self._update_progress(state.contract_id, 'text_extracted', 100, 'Текст извлечён')
        await self.state_manager.update_status(
            state.contract_id,
            ProcessingState.TEXT_EXTRACTED,
            raw_text=state.raw_text[:1000] if state.raw_text else None  # сохраняем первые 1000 символов
        )
    
    def _build_chunk_context(self, extracted_data: Dict[str, Any]) -> str:
        """
        Формирует контекстный блок с полной информацией о договоре из предыдущих чанков для добавления в текущий чанк
        
        Args:
            extracted_data: Словарь с извлеченными данными из предыдущих чанков
            
        Returns:
            Структурированный текст с полной информацией о договоре
        """
        if not extracted_data:
            return ""
        
        context_parts = []
        context_parts.append("=== КОНТЕКСТ ИЗ ПРЕДЫДУЩИХ ЧАНКОВ ===\n")
        
        # Секция ОСНОВНАЯ ИНФОРМАЦИЯ О ДОГОВОРЕ
        contract_info = []
        if extracted_data.get('contract_name'):
            contract_info.append(f"- Название договора: {extracted_data['contract_name']}")
        if extracted_data.get('contract_number'):
            contract_info.append(f"- Номер договора: {extracted_data['contract_number']}")
        if extracted_data.get('contract_date'):
            contract_info.append(f"- Дата договора: {extracted_data['contract_date']}")
        if extracted_data.get('contract_price'):
            contract_info.append(f"- Цена договора: {extracted_data['contract_price']}")
        if extracted_data.get('vat_type'):
            contract_info.append(f"- Тип НДС: {extracted_data['vat_type']}")
        if extracted_data.get('vat_percent'):
            contract_info.append(f"- Процент НДС: {extracted_data['vat_percent']}")
        
        if contract_info:
            context_parts.append("ОСНОВНАЯ ИНФОРМАЦИЯ О ДОГОВОРЕ:")
            context_parts.extend(contract_info)
            context_parts.append("")
        
        # Секция ОПИСАНИЕ УСЛУГ/ТОВАРОВ
        if extracted_data.get('service_description'):
            context_parts.append("ОПИСАНИЕ УСЛУГ/ТОВАРОВ:")
            service_desc = extracted_data['service_description']
            # Ограничиваем длину описания для контекста
            if isinstance(service_desc, str) and len(service_desc) > 500:
                service_desc = service_desc[:500] + "..."
            context_parts.append(f"- {service_desc}")
            context_parts.append("")

        # Секция ДАТЫ ОКАЗАНИЯ УСЛУГ
        service_dates = []
        if extracted_data.get('service_start_date'):
            service_dates.append(f"- Начало периода услуг: {extracted_data['service_start_date']}")
        if extracted_data.get('service_end_date'):
            service_dates.append(f"- Окончание периода услуг: {extracted_data['service_end_date']}")
        
        if service_dates:
            context_parts.append("ДАТЫ ОКАЗАНИЯ УСЛУГ:")
            context_parts.extend(service_dates)
            context_parts.append("")
        
        # Секция УСЛОВИЯ ОПЛАТЫ
        if extracted_data.get('payment_terms'):
            context_parts.append("УСЛОВИЯ ОПЛАТЫ:")
            payment_terms = extracted_data['payment_terms']
            # Ограничиваем длину для контекста
            if isinstance(payment_terms, str) and len(payment_terms) > 300:
                payment_terms = payment_terms[:300] + "..."
            context_parts.append(f"- {payment_terms}")
            context_parts.append("")
        
        # Секция ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ
        additional_info = []
        if extracted_data.get('acceptance_procedure'):
            acceptance = extracted_data['acceptance_procedure']
            if isinstance(acceptance, str) and len(acceptance) > 200:
                acceptance = acceptance[:200] + "..."
            additional_info.append(f"- Порядок приема-сдачи: {acceptance}")
        if extracted_data.get('specification_exists') is not None:
            spec_exists = "Да" if extracted_data['specification_exists'] else "Нет"
            additional_info.append(f"- Наличие спецификации: {spec_exists}")
        if extracted_data.get('pricing_method'):
            pricing = extracted_data['pricing_method']
            if isinstance(pricing, str) and len(pricing) > 200:
                pricing = pricing[:200] + "..."
            additional_info.append(f"- Порядок ценообразования: {pricing}")
        if extracted_data.get('reporting_forms'):
            reporting = extracted_data['reporting_forms']
            if isinstance(reporting, str) and len(reporting) > 200:
                reporting = reporting[:200] + "..."
            additional_info.append(f"- Формы отчетности: {reporting}")
        if extracted_data.get('additional_conditions'):
            conditions = extracted_data['additional_conditions']
            if isinstance(conditions, str) and len(conditions) > 200:
                conditions = conditions[:200] + "..."
            additional_info.append(f"- Дополнительные условия: {conditions}")
        
        if additional_info:
            context_parts.append("ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ:")
            context_parts.extend(additional_info)
            context_parts.append("")
        
        # Секция КОНТРАГЕНТЫ
        counterparty_info = []
        
        # Информация о заказчике
        customer = extracted_data.get('customer')
        if isinstance(customer, dict):
            customer_info = []
            if customer.get('inn'):
                customer_info.append(f"ИНН: {customer['inn']}")
            if customer.get('full_name'):
                customer_info.append(f"Полное наименование: {customer['full_name']}")
            if customer.get('short_name'):
                customer_info.append(f"Краткое наименование: {customer['short_name']}")
            if customer.get('organizational_form'):
                customer_info.append(f"ОПФ: {customer['organizational_form']}")
            if customer.get('kpp'):
                customer_info.append(f"КПП: {customer['kpp']}")
            if customer_info:
                counterparty_info.append("ЗАКАЗЧИК:")
                counterparty_info.extend([f"  {info}" for info in customer_info])
        
        # Информация об исполнителе
        contractor = extracted_data.get('contractor')
        if isinstance(contractor, dict):
            contractor_info = []
            if contractor.get('inn'):
                contractor_info.append(f"ИНН: {contractor['inn']}")
            if contractor.get('full_name'):
                contractor_info.append(f"Полное наименование: {contractor['full_name']}")
            if contractor.get('short_name'):
                contractor_info.append(f"Краткое наименование: {contractor['short_name']}")
            if contractor.get('organizational_form'):
                contractor_info.append(f"ОПФ: {contractor['organizational_form']}")
            if contractor.get('kpp'):
                contractor_info.append(f"КПП: {contractor['kpp']}")
            if contractor_info:
                counterparty_info.append("ИСПОЛНИТЕЛЬ:")
                counterparty_info.extend([f"  {info}" for info in contractor_info])
        
        # Старая логика для обратной совместимости (если нет customer/contractor)
        if not counterparty_info:
            if extracted_data.get('inn'):
                counterparty_info.append(f"- ИНН: {extracted_data['inn']}")
            if extracted_data.get('full_name'):
                counterparty_info.append(f"- Полное наименование: {extracted_data['full_name']}")
            if extracted_data.get('short_name'):
                counterparty_info.append(f"- Краткое наименование: {extracted_data['short_name']}")
            if extracted_data.get('organizational_form'):
                counterparty_info.append(f"- Организационно-правовая форма: {extracted_data['organizational_form']}")
            if extracted_data.get('kpp'):
                counterparty_info.append(f"- КПП: {extracted_data['kpp']}")
            
            # Роли
            roles = []
            if extracted_data.get('is_supplier'):
                roles.append("Поставщик")
            if extracted_data.get('is_buyer'):
                roles.append("Покупатель")
            if roles:
                counterparty_info.append(f"- Роль: {', '.join(roles)}")
        
        if counterparty_info:
            context_parts.append("КОНТРАГЕНТЫ:")
            context_parts.extend(counterparty_info)
            context_parts.append("")
        
        # Секция АГЕНТЫ И ОТВЕТСТВЕННЫЕ ЛИЦА
        responsible_persons = extracted_data.get('responsible_persons', [])
        if not isinstance(responsible_persons, list):
            responsible_persons = []
        
        if responsible_persons:
            context_parts.append("АГЕНТЫ И ОТВЕТСТВЕННЫЕ ЛИЦА:")
            for idx, person in enumerate(responsible_persons, start=1):
                if isinstance(person, dict):
                    person_info = []
                    if person.get('name'):
                        person_info.append(f"  {idx}. ФИО: {person['name']}")
                    if person.get('position'):
                        person_info.append(f"     Должность: {person['position']}")
                    if person.get('phone'):
                        person_info.append(f"     Телефон: {person['phone']}")
                    if person.get('email'):
                        person_info.append(f"     Email: {person['email']}")
                    if person_info:
                        context_parts.extend(person_info)
            context_parts.append("")
        
        # Секция КОНТАКТНАЯ ИНФОРМАЦИЯ
        contact_info = []
        
        # Собираем все телефоны из ответственных лиц
        phones = []
        for person in responsible_persons:
            if isinstance(person, dict) and person.get('phone'):
                phones.append(person['phone'])
        if phones:
            contact_info.append(f"- Телефоны: {', '.join(set(phones))}")
        
        # Собираем все email из ответственных лиц
        emails = []
        for person in responsible_persons:
            if isinstance(person, dict) and person.get('email'):
                emails.append(person['email'])
        if emails:
            contact_info.append(f"- Email: {', '.join(set(emails))}")
        
        # Адреса из locations
        locations = extracted_data.get('locations', []) or extracted_data.get('service_locations', [])
        if not isinstance(locations, list):
            locations = []
        
        addresses = []
        for location in locations:
            if isinstance(location, dict):
                if location.get('address'):
                    addresses.append(location['address'])
                elif location.get('city') or location.get('region'):
                    addr_parts = []
                    if location.get('city'):
                        addr_parts.append(location['city'])
                    if location.get('region'):
                        addr_parts.append(location['region'])
                    if location.get('postal_code'):
                        addr_parts.append(location['postal_code'])
                    if addr_parts:
                        addresses.append(', '.join(addr_parts))
        
        if addresses:
            contact_info.append(f"- Адреса: {'; '.join(set(addresses))}")
        
        if contact_info:
            context_parts.append("КОНТАКТНАЯ ИНФОРМАЦИЯ:")
            context_parts.extend(contact_info)
            context_parts.append("")
        
        context_parts.append("=== ТЕКСТ ТЕКУЩЕГО ЧАНКА ===\n")
        
        return "\n".join(context_parts)
    
    async def _extract_contract_data(self, state: AgentState):
        """Извлечь данные контракта с помощью LLM"""
        logger.info("Extracting contract data", contract_id=state.contract_id)
        await self._update_progress(state.contract_id, 'data_extracted', 0, 'Начало извлечения данных...')
        
        # Инициализируем список запросов LLM если его еще нет
        if state.llm_requests is None:
            state.llm_requests = []
        
        # Проверяем размер документа
        if not state.raw_text:
            state.raw_text = self.doc_processor.extract_text()
        
        # Максимальный размер для одного запроса: ~8000 токенов = 32000 символов
        max_single_request_size = 64000
        document_size = len(state.raw_text)
        
        if document_size <= max_single_request_size:
            # Документ небольшой, обрабатываем целиком
            context = self.doc_processor.get_context_for_llm()
            
            # Формируем полный промпт, который уходит в LLM
            system_prompt = """You are an expert in Russian contract analysis.
        Extract contract information from documents and return it as valid JSON.
        Be precise with INN extraction (10 or 12 digits).
        Use boolean fields is_supplier and is_buyer for roles.
        """
            user_prompt = EXTRACT_CONTRACT_DATA_PROMPT.format(document_text=context)
            full_prompt = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"
            
            # Сохраняем информацию о запросе
            request_info = {
                "request_type": "single",
                "chunk_index": None,
                "total_chunks": 1,
                "request_text": full_prompt,
                "request_size": len(full_prompt),
                "request_tokens_estimate": self.doc_processor.estimate_tokens(full_prompt),
                "timestamp": datetime.now().isoformat(),
            }
            
            try:
                response_data = await self.llm_service.extract_contract_data(context)
                state.extracted_data = response_data
                
                # Сохраняем информацию об ответе
                request_info["response_data"] = response_data
                request_info["response_size"] = len(str(response_data))
                request_info["status"] = "success"
            except Exception as e:
                error_traceback = traceback.format_exc()
                request_info["status"] = "error"
                request_info["error"] = str(e)
                logger.error("Failed to extract contract data (single request)",
                           contract_id=state.contract_id,
                           error=str(e),
                           error_type=type(e).__name__,
                           error_traceback=error_traceback,
                           document_size=document_size,
                           prompt_size=len(full_prompt))
                raise
            finally:
                state.llm_requests.append(request_info)
        else:
            # Документ большой, разбиваем на чанки и обрабатываем ПАРАЛЛЕЛЬНО
            logger.info("Large document detected, splitting into chunks for PARALLEL processing",
                       contract_id=state.contract_id,
                       document_size=document_size)

            chunks = self.doc_processor.get_chunks_for_llm()
            total_chunks = len(chunks)
            logger.info("Document split into chunks",
                       contract_id=state.contract_id,
                       chunks_count=total_chunks)

            await self._update_progress(
                state.contract_id, 'data_extracted', 0,
                f'Извлечение данных: 0/{total_chunks} чанков',
                chunks_total=total_chunks, chunks_processed=0
            )

            # Callback для обновления прогресса при обработке чанков
            async def data_extraction_progress_callback(chunks_processed: int, chunks_total: int):
                progress_percent = (chunks_processed * 100) // chunks_total if chunks_total > 0 else 0
                await self._update_progress(
                    state.contract_id, 'data_extracted', progress_percent,
                    f'Извлечение данных: {chunks_processed}/{chunks_total} чанков',
                    chunks_total=chunks_total, chunks_processed=chunks_processed
                )

            # Обрабатываем все чанки ПАРАЛЛЕЛЬНО через LLM
            parallel_results = await self.llm_service.extract_contract_data_parallel(
                chunks,
                progress_callback=data_extraction_progress_callback
            )

            # Собираем результаты
            chunks_data: List[Dict[str, Any]] = []
            chunks_with_context: List[Dict[str, Any]] = []
            failed_chunks: List[tuple[int, str]] = []

            for chunk_idx, chunk_data, error in parallel_results:
                chunk_text = chunks[chunk_idx - 1] if chunk_idx <= len(chunks) else ""
                chunk_context = chunk_text[:1000] if chunk_text else ""

                # Формируем полный промпт для логирования
                system_prompt = """You are an expert in Russian contract analysis.
        Extract contract information from documents and return it as valid JSON.
        Be precise with INN extraction (10 or 12 digits).
        Use boolean fields is_supplier and is_buyer for roles.
        """
                user_prompt = EXTRACT_CONTRACT_DATA_PROMPT.format(document_text=chunk_text)
                full_prompt = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"

                request_info = {
                    "request_type": "chunk_parallel",
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                    "chunk_context": chunk_context,
                    "request_text": full_prompt,
                    "request_size": len(full_prompt),
                    "request_tokens_estimate": self.doc_processor.estimate_tokens(full_prompt),
                    "timestamp": datetime.now().isoformat(),
                }

                if chunk_data:
                    chunks_data.append(chunk_data)
                    chunks_with_context.append({
                        "chunk_index": chunk_idx,
                        "chunk_context": chunk_context,
                        "accumulated_context": "",  # При параллельной обработке контекст не накапливается
                        "extracted_data": chunk_data
                    })
                    request_info["response_data"] = chunk_data
                    request_info["response_size"] = len(str(chunk_data))
                    request_info["status"] = "success"
                    logger.info("Chunk processed successfully (parallel)",
                               contract_id=state.contract_id,
                               chunk_index=chunk_idx)
                else:
                    request_info["status"] = "error"
                    request_info["error"] = error or "Unknown error"
                    failed_chunks.append((chunk_idx, error or "Unknown error"))
                    
                    # Детальное логирование ошибки чанка
                    chunk_size = len(chunk_text) if chunk_text else 0
                    logger.error("Failed to process chunk (parallel)",
                               contract_id=state.contract_id,
                               chunk_index=chunk_idx,
                               total_chunks=len(chunks),
                               error=error,
                               error_type=type(error).__name__ if error else "Unknown",
                               chunk_size=chunk_size,
                               chunk_preview=chunk_text[:300] if chunk_text else None,
                               chunk_context_preview=chunk_context[:200] if chunk_context else None)

                state.llm_requests.append(request_info)

            # Проверяем результаты обработки
            if not chunks_data:
                failed_chunk_details = [
                    {"chunk_index": idx, "error": err} 
                    for idx, err in failed_chunks
                ]
                error_traceback = traceback.format_exc()
                logger.error("Failed to extract data from any chunk",
                           contract_id=state.contract_id,
                           total_chunks=len(chunks),
                           failed_chunks_count=len(failed_chunks),
                           failed_chunk_details=failed_chunk_details,
                           error_traceback=error_traceback)
                raise Exception(f"Failed to extract data from any chunk. Total chunks: {len(chunks)}, Failed chunks: {len(failed_chunks)}")
            
            # Логируем статистику обработки
            successful_count = len(chunks_data)
            failed_count = len(failed_chunks)
            success_rate = (successful_count / len(chunks)) * 100
            
            logger.info("Parallel chunk processing completed",
                       contract_id=state.contract_id,
                       successful_chunks=successful_count,
                       failed_chunks=failed_count,
                       total_chunks=len(chunks),
                       success_rate=f"{success_rate:.1f}%")
            
            # Предупреждаем, если упало слишком много чанков
            if failed_count > 0:
                failed_chunk_indices = [idx for idx, _ in failed_chunks]
                failed_chunk_errors = [err for _, err in failed_chunks]
                
                logger.warning("Some chunks failed to process, continuing with successful chunks",
                             contract_id=state.contract_id,
                             failed_chunk_indices=failed_chunk_indices,
                             failed_chunk_errors=failed_chunk_errors,
                             failed_count=failed_count,
                             successful_count=successful_count,
                             success_rate=f"{success_rate:.1f}%")
                
                # Если упало больше половины чанков, это критично
                if failed_count > len(chunks) / 2:
                    logger.error("More than half of chunks failed to process",
                               contract_id=state.contract_id,
                               failed_count=failed_count,
                               total_chunks=len(chunks),
                               failed_chunk_indices=failed_chunk_indices,
                               failed_chunk_errors=failed_chunk_errors,
                               success_rate=f"{success_rate:.1f}%",
                               critical=True)

            # Агрегируем результаты из всех чанков через LLM с разрешением конфликтов
            logger.info("Aggregating data from chunks via LLM",
                       contract_id=state.contract_id,
                       chunks_processed=len(chunks_with_context))
            
            # Формируем данные для промпта агрегации (для логирования)
            chunks_data_formatted = []
            for chunk_info in chunks_with_context:
                chunk_data_item = {
                    "chunk_index": chunk_info.get('chunk_index', 0),
                    "chunk_context": chunk_info.get('chunk_context', '')[:1000],
                    "accumulated_context": "",  # При параллельной обработке контекст не накапливается
                    "extracted_data": chunk_info.get('extracted_data', {})
                }
                chunks_data_formatted.append(chunk_data_item)

            # Формируем промпт для агрегации
            chunks_json = json.dumps(chunks_data_formatted, ensure_ascii=False, indent=2)
            user_prompt = MERGE_CHUNKS_DATA_PROMPT.format(
                total_chunks=len(chunks_with_context),
                chunks_data=chunks_json,
                accumulated_context="Параллельная обработка чанков - накопленный контекст отсутствует."
            )
            system_prompt = """You are an expert in Russian contract analysis.
        Merge contract information from multiple document chunks and resolve conflicts.
        Return only valid JSON with all merged fields.
        """
            full_prompt = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"

            # Сохраняем информацию о финальном запросе агрегации
            aggregation_request_info = {
                "request_type": "aggregation_parallel",
                "chunk_index": None,
                "total_chunks": len(chunks_with_context),
                "request_text": full_prompt,
                "request_size": len(full_prompt),
                "request_tokens_estimate": self.doc_processor.estimate_tokens(full_prompt),
                "timestamp": datetime.now().isoformat(),
            }
            
            try:
                # Используем финальную агрегацию через LLM
                state.extracted_data = await self.llm_service.aggregate_chunks_data(chunks_with_context)
                
                aggregation_request_info["status"] = "success"
                aggregation_request_info["response_data"] = state.extracted_data
                aggregation_request_info["response_size"] = len(str(state.extracted_data))
                
                logger.info("Chunks data aggregated successfully via LLM",
                           contract_id=state.contract_id,
                           chunks_count=len(chunks_with_context))
            except Exception as e:
                error_traceback = traceback.format_exc()
                aggregation_request_info["status"] = "error"
                aggregation_request_info["error"] = str(e)
                
                logger.error("Failed to aggregate chunks data via LLM, using fallback",
                           contract_id=state.contract_id,
                           error=str(e),
                           error_type=type(e).__name__,
                           error_traceback=error_traceback,
                           chunks_count=len(chunks_with_context),
                           prompt_size=len(full_prompt))
                
                # Fallback на простое объединение если LLM агрегация не удалась
                state.extracted_data = self.llm_service.merge_extracted_data(chunks_data)
                aggregation_request_info["fallback_used"] = True
            finally:
                state.llm_requests.append(aggregation_request_info)
        
        # Сохраняем информацию о запросах LLM в БД
        if state.llm_requests and self.state_manager.db:
            try:
                # Удаляем старые записи о запросах LLM для этого контракта
                self.state_manager.db.query(ProcessingHistory).filter(
                    ProcessingHistory.contract_id == state.contract_id,
                    ProcessingHistory.event_type == 'llm_request'
                ).delete()
                
                # Сохраняем информацию о каждом запросе
                for req_info in state.llm_requests:
                    history_entry = ProcessingHistory(
                        contract_id=state.contract_id,
                        event_type='llm_request',
                        event_status=EventStatus.SUCCESS if req_info.get('status') == 'success' else EventStatus.FAILED,
                        event_message=f"LLM request {req_info.get('request_type', 'unknown')}",
                        event_details=req_info
                    )
                    self.state_manager.db.add(history_entry)
                
                self.state_manager.db.commit()
                logger.info("LLM requests info saved to DB",
                           contract_id=state.contract_id,
                           requests_count=len(state.llm_requests))
            except Exception as e:
                logger.error("Failed to save LLM requests info to DB",
                           contract_id=state.contract_id,
                           error=str(e))
                self.state_manager.db.rollback()
        
        await self.state_manager.update_status(
            state.contract_id,
            ProcessingState.DATA_EXTRACTED,
            extracted_data=state.extracted_data,
            llm_requests=state.llm_requests
        )

    async def _extract_all_services(self, state: AgentState):
        """Извлечь все услуги отдельным запросом к LLM (ПАРАЛЛЕЛЬНО)"""
        logger.info("Extracting all services separately (parallel)", contract_id=state.contract_id)
        await self._update_progress(state.contract_id, 'services_extracted', 0, 'Начало извлечения услуг...')

        # Инициализируем список запросов LLM если его еще нет
        if state.llm_requests is None:
            state.llm_requests = []

        # Получаем чанки (используем те же что и для основного извлечения)
        if not state.raw_text:
            state.raw_text = self.doc_processor.extract_text()

        max_single_request_size = 64000
        document_size = len(state.raw_text)

        if document_size <= max_single_request_size:
            chunks = [state.raw_text]
        else:
            chunks = self.doc_processor.get_chunks_for_llm()

        total_chunks = len(chunks)

        # Информация о запросе для логирования
        request_info = {
            "request_type": "services_extraction_parallel",
            "chunks_count": total_chunks,
            "timestamp": datetime.now().isoformat(),
        }

        await self._update_progress(
            state.contract_id, 'services_extracted', 0,
            f'Извлечение услуг: 0/{total_chunks} чанков',
            chunks_total=total_chunks, chunks_processed=0
        )

        # Callback для обновления прогресса при извлечении услуг
        async def services_progress_callback(chunks_processed: int, chunks_total: int, _services_found: int):
            progress_percent = (chunks_processed * 100) // chunks_total if chunks_total > 0 else 0
            await self._update_progress(
                state.contract_id, 'services_extracted', progress_percent,
                f'Извлечение услуг: {chunks_processed}/{chunks_total} чанков',
                chunks_total=chunks_total, chunks_processed=chunks_processed
            )

        all_services = []
        try:
            # Извлекаем услуги параллельно из всех чанков
            all_services = await self.llm_service.extract_services_from_chunks(
                chunks,
                progress_callback=services_progress_callback
            )
            state.extracted_data['all_services'] = all_services

            request_info["status"] = "success"
            request_info["services_count"] = len(all_services)

            await self._update_progress(
                state.contract_id, 'services_extracted', 100,
                f'Извлечено {len(all_services)} услуг',
                chunks_total=total_chunks, chunks_processed=total_chunks
            )

            logger.info("Services extracted successfully (parallel)",
                       contract_id=state.contract_id,
                       services_count=len(all_services),
                       chunks_count=total_chunks)
        except Exception as e:
            error_traceback = traceback.format_exc()
            request_info["status"] = "error"
            request_info["error"] = str(e)
            logger.error("Failed to extract services",
                       contract_id=state.contract_id,
                       error=str(e),
                       error_type=type(e).__name__,
                       error_traceback=error_traceback,
                       chunks_count=total_chunks)
            state.extracted_data['all_services'] = []
        finally:
            state.llm_requests.append(request_info)
    async def _validate_data(self, state: AgentState):
        """Валидировать извлеченные данные"""
        logger.info("Validating extracted data", contract_id=state.contract_id)
        await self._update_progress(state.contract_id, 'validation_passed', 0, 'Валидация данных...')

        validation_result = self.validation_service.validate_contract_data(
            state.extracted_data
        )
        
        # Обновляем extracted_data нормализованными данными после auto_correct
        if validation_result.get('validated_data'):
            state.extracted_data = validation_result['validated_data']
        else:
            # Если валидация не прошла, но данные были нормализованы, используем их
            # auto_correct_data уже был применен в validate_contract_data
            normalized_data = self.validation_service.auto_correct_data(state.extracted_data)
            state.extracted_data = normalized_data
        
        if not validation_result['is_valid']:
            state.validation_errors = validation_result['errors']
            logger.warning("Validation failed", 
                          errors=validation_result['errors'],
                          contract_id=state.contract_id)
        
        await self._update_progress(state.contract_id, 'validation_passed', 100, 'Валидация завершена')
        await self.state_manager.update_status(
            state.contract_id,
            ProcessingState.VALIDATION_PASSED
        )

    async def _check_existing_in_1c(self, state: AgentState):
        """Проверить наличие контрагента в справочнике 1С"""
        logger.info("Checking existing counterparty in 1C", contract_id=state.contract_id)
        await self._update_progress(state.contract_id, 'checking_1c', 0, 'Проверка в 1С...')

        if not state.extracted_data:
            raise Exception("Extracted data not found")

        # Подробное логирование для диагностики извлечения ИНН
        extracted_keys = list(state.extracted_data.keys()) if state.extracted_data else []
        root_inn = state.extracted_data.get('inn')
        customer_data = state.extracted_data.get('customer')
        contractor_data = state.extracted_data.get('contractor')

        logger.info("Extracted data structure for INN lookup",
                   contract_id=state.contract_id,
                   extracted_keys=extracted_keys,
                   root_inn=root_inn,
                   root_inn_type=type(root_inn).__name__ if root_inn is not None else 'None',
                   has_customer=customer_data is not None,
                   customer_type=type(customer_data).__name__ if customer_data is not None else 'None',
                   customer_inn=customer_data.get('inn') if isinstance(customer_data, dict) else None,
                   has_contractor=contractor_data is not None,
                   contractor_type=type(contractor_data).__name__ if contractor_data is not None else 'None',
                   contractor_inn=contractor_data.get('inn') if isinstance(contractor_data, dict) else None)

        # Если customer или contractor не dict, логируем их содержимое
        if customer_data is not None and not isinstance(customer_data, dict):
            logger.warning("Customer field is not a dict",
                          contract_id=state.contract_id,
                          customer_value=str(customer_data)[:500],
                          customer_type=type(customer_data).__name__)

        if contractor_data is not None and not isinstance(contractor_data, dict):
            logger.warning("Contractor field is not a dict",
                          contract_id=state.contract_id,
                          contractor_value=str(contractor_data)[:500],
                          contractor_type=type(contractor_data).__name__)

        # Получаем ИНН из корневых полей или из customer/contractor
        # Согласно правилам: из контракта выявить значение ИНН контрагента
        inn = None
        inn_source = None

        if 'inn' in state.extracted_data and state.extracted_data['inn']:
            inn = state.extracted_data['inn']
            inn_source = 'root'
        elif 'customer' in state.extracted_data and isinstance(state.extracted_data['customer'], dict):
            inn = state.extracted_data['customer'].get('inn')
            inn_source = 'customer'
        elif 'contractor' in state.extracted_data and isinstance(state.extracted_data['contractor'], dict):
            inn = state.extracted_data['contractor'].get('inn')
            inn_source = 'contractor'

        if not inn:
            # Подробное логирование ошибки
            logger.error("INN not found in extracted data",
                        contract_id=state.contract_id,
                        extracted_keys=extracted_keys,
                        root_inn=root_inn,
                        customer_data=customer_data if isinstance(customer_data, dict) else str(customer_data)[:500] if customer_data else None,
                        contractor_data=contractor_data if isinstance(contractor_data, dict) else str(contractor_data)[:500] if contractor_data else None)
            raise Exception("INN not found in extracted data (checked root, customer, and contractor fields)")
        
        # Сохраняем источник ИНН для использования при создании контрагента
        state.counterparty_inn_source = inn_source
        
        await self.state_manager.update_status(
            state.contract_id,
            ProcessingState.CHECKING_1C
        )
        
        if self.oneс_service:
            existing = None
            search_error = None
            
            try:
                existing = await self.oneс_service.find_counterparty_by_inn(inn)
                
                # Проверяем, есть ли ошибка в результате
                if existing and isinstance(existing, dict) and existing.get('_error'):
                    search_error = existing.get('_error')
                    existing = None  # Очищаем результат, если есть ошибка
            except Exception as e:
                error_traceback = traceback.format_exc()
                logger.error("Exception during counterparty search", 
                           contract_id=state.contract_id,
                           inn=inn,
                           error=str(e),
                           error_type=type(e).__name__,
                           error_traceback=error_traceback)
                search_error = str(e)
            
            # Сохраняем информацию о поиске в ProcessingHistory
            if self.state_manager.db:
                try:
                    search_result = {
                        'inn': inn,
                        'inn_source': inn_source,  # Источник ИНН: 'root', 'customer', 'contractor'
                        'search_scope': 'all_areas',  # Поиск выполняется по всем областям справочника Контрагенты
                        'found': existing is not None and not (isinstance(existing, dict) and existing.get('_error')),
                        'counterparty_uuid': existing.get('uuid') if existing and isinstance(existing, dict) and not existing.get('_error') else None,
                        'counterparty_data': existing if existing and isinstance(existing, dict) and not existing.get('_error') else None,
                        'error': search_error
                    }
                    
                    # Формируем сообщение с указанием источника ИНН
                    inn_source_text = {
                        'root': 'корневые поля',
                        'customer': 'заказчик (customer)',
                        'contractor': 'исполнитель (contractor)'
                    }.get(inn_source, 'неизвестный источник')
                    
                    history_entry = ProcessingHistory(
                        contract_id=state.contract_id,
                        event_type='1c_check',
                        event_status=EventStatus.ERROR if search_error else EventStatus.SUCCESS,
                        event_message=f"Поиск контрагента по ИНН {inn} (источник: {inn_source_text}, поиск по всем областям справочника)" + (f" - ошибка: {search_error}" if search_error else ""),
                        event_details=search_result
                    )
                    self.state_manager.db.add(history_entry)
                    self.state_manager.db.commit()
                    logger.info("1C search info saved to DB",
                               contract_id=state.contract_id,
                               inn=inn,
                               inn_source=inn_source,
                               search_scope='all_areas',
                               found=search_result['found'],
                               has_error=search_error is not None)
                except Exception as e:
                    logger.error("Failed to save 1C search info to DB",
                               contract_id=state.contract_id,
                               error=str(e))
                    if self.state_manager.db:
                        self.state_manager.db.rollback()
            
            if existing and isinstance(existing, dict) and not existing.get('_error'):
                state.existing_counterparty_id = existing.get('uuid')
                logger.info("Counterparty already exists in 1C",
                           inn=inn,
                           entity_uuid=existing.get('uuid'))

        await self._update_progress(state.contract_id, 'checking_1c', 100, 'Проверка в 1С завершена')

    async def _create_counterparty_in_1c(self, state: AgentState):
        """
        Создать контрагента в 1С.
        
        Согласно правилам:
        - Если по данному ИНН контрагент присутствует в справочнике, то добавлять новый элемент нельзя
        - Если контрагент отсутствует, то создать новый элемент справочника Контрагенты
        """
        # Если контрагент уже существует, добавляем договор и заметку к существующему
        if state.existing_counterparty_id:
            logger.info("Counterparty already exists, adding agreement and note",
                       contract_id=state.contract_id,
                       existing_id=state.existing_counterparty_id)
            await self._add_agreement_to_existing_counterparty(state)
            return

        logger.info("Creating counterparty in 1C", contract_id=state.contract_id)
        await self._update_progress(state.contract_id, 'creating_in_1c', 0, 'Создание в 1С...')

        await self.state_manager.update_status(
            state.contract_id,
            ProcessingState.CREATING_IN_1C
        )
        
        if self.oneс_service:
            created_result = None
            create_error = None
            
            try:
                # Подготавливаем данные контрагента из правильного источника
                # Используем данные из customer или contractor в зависимости от того,
                # откуда был взят ИНН при проверке
                counterparty_data = self._prepare_counterparty_data(state)
                
                # Повторная проверка перед созданием (согласно правилам)
                inn = counterparty_data.get('inn')
                if inn:
                    existing = await self.oneс_service.find_counterparty_by_inn(inn)
                    # Проверяем результат: если есть ошибка или контрагент не найден, продолжаем создание
                    # Если контрагент найден (есть uuid и нет ошибки), пропускаем создание
                    if existing and isinstance(existing, dict):
                        # Проверяем наличие ошибки (ключ _error присутствует)
                        has_error = '_error' in existing
                        # Проверяем наличие uuid (признак найденного контрагента)
                        has_uuid = existing.get('uuid') is not None
                        
                        if has_uuid and not has_error:
                            logger.warning("Counterparty found during final check before creation, skipping",
                                          contract_id=state.contract_id,
                                          inn=inn,
                                          existing_uuid=existing.get('uuid'))
                            state.existing_counterparty_id = existing.get('uuid')
                            return
                        elif has_error:
                            # Если была ошибка при проверке, логируем но продолжаем создание
                            # Ошибка означает, что проверка не удалась, но это не значит, что контрагент существует
                            error_msg = existing.get('_error', 'Unknown error')
                            logger.warning("Error during final check before creation, proceeding with creation",
                                         contract_id=state.contract_id,
                                         inn=inn,
                                         error=error_msg)
                    # Если existing is None или не dict, контрагент не найден - продолжаем создание
                
                created_result = await self.oneс_service.create_counterparty(
                    counterparty_data,
                    state.document_path,
                    raw_text=state.raw_text
                )
            except Exception as e:
                error_traceback = traceback.format_exc()
                create_error = str(e)
                logger.error("Failed to create counterparty in 1C",
                           contract_id=state.contract_id,
                           error=create_error,
                           error_type=type(e).__name__,
                           error_traceback=error_traceback,
                           inn=inn,
                           counterparty_data_keys=list(counterparty_data.keys()) if 'counterparty_data' in locals() else None)
            
            # Извлекаем UUID и данные из результата
            created_id = None
            entity_data = None
            if created_result and isinstance(created_result, dict):
                created_id = created_result.get('uuid')
                entity_data = created_result.get('entity')
            
            # Сохраняем информацию о создании в ProcessingHistory и Counterparty1C
            if self.state_manager.db:
                try:
                    # Используем ИНН из подготовленных данных
                    counterparty_data = self._prepare_counterparty_data(state)
                    create_result_details = {
                        'inn': counterparty_data.get('inn'),
                        'inn_source': state.counterparty_inn_source,
                        'created': created_id is not None,
                        'counterparty_uuid': created_id,
                        'error': create_error
                    }
                    
                    history_entry = ProcessingHistory(
                        contract_id=state.contract_id,
                        event_type='1c_create',
                        event_status=EventStatus.SUCCESS if created_id else EventStatus.ERROR,
                        event_message=f"Создание контрагента в 1С" + (f" - ошибка: {create_error}" if create_error else ""),
                        event_details=create_result_details
                    )
                    self.state_manager.db.add(history_entry)
                    
                    # Сохраняем данные в Counterparty1C
                    if created_id:
                        # Получаем ContractData для связи
                        contract_data = self.state_manager.db.query(ContractData).filter(
                            ContractData.contract_id == state.contract_id
                        ).first()
                        
                        if contract_data:
                            # Извлекаем наименование из entity_data
                            entity_name = None
                            if entity_data:
                                # Пытаемся извлечь наименование из разных возможных полей
                                entity_name = (
                                    entity_data.get('Description') or
                                    entity_data.get('Наименование') or
                                    entity_data.get('НаименованиеПолное') or
                                    counterparty_data.get('full_name') or
                                    counterparty_data.get('short_name')
                                )
                            
                            # Проверяем, существует ли уже запись
                            counterparty_1c = self.state_manager.db.query(Counterparty1C).filter(
                                Counterparty1C.contract_data_id == contract_data.id
                            ).first()
                            
                            if counterparty_1c:
                                # Обновляем существующую запись
                                counterparty_1c.entity_uuid = created_id
                                counterparty_1c.entity_name = entity_name
                                counterparty_1c.status_1c = OneCStatus.CREATED
                                counterparty_1c.created_in_1c_at = datetime.now()
                                counterparty_1c.response_from_1c = entity_data
                                if create_error:
                                    counterparty_1c.error_from_1c = create_error
                            else:
                                # Создаем новую запись
                                counterparty_1c = Counterparty1C(
                                    contract_data_id=contract_data.id,
                                    entity_uuid=created_id,
                                    entity_name=entity_name,
                                    status_1c=OneCStatus.CREATED,
                                    created_in_1c_at=datetime.now(),
                                    response_from_1c=entity_data,
                                    error_from_1c=create_error
                                )
                                self.state_manager.db.add(counterparty_1c)
                    
                    self.state_manager.db.commit()
                    logger.info("1C create info saved to DB",
                               contract_id=state.contract_id,
                               created=created_id is not None)
                except Exception as e:
                    logger.error("Failed to save 1C create info to DB",
                               contract_id=state.contract_id,
                               error=str(e))
                    if self.state_manager.db:
                        self.state_manager.db.rollback()
            
            state.created_counterparty_id = created_id

            if created_id:
                await self._update_progress(state.contract_id, 'creating_in_1c', 100, 'Контрагент создан в 1С')
                logger.info("Counterparty created successfully",
                           contract_id=state.contract_id,
                           counterparty_id=created_id)
            else:
                await self._update_progress(state.contract_id, 'creating_in_1c', 100, 'Создание в 1С завершено')

    async def _add_agreement_to_existing_counterparty(self, state: AgentState):
        """
        Добавить договор и заметку к существующему контрагенту в 1С.

        Используется когда контрагент уже существует в справочнике 1С, но нужно
        добавить новый договор с информацией о контракте и записать в заметку.
        """
        logger.info("Adding agreement and note to existing counterparty",
                   contract_id=state.contract_id,
                   existing_id=state.existing_counterparty_id)

        await self._update_progress(state.contract_id, 'creating_in_1c', 0, 'Добавление договора к существующему контрагенту...')

        await self.state_manager.update_status(
            state.contract_id,
            ProcessingState.CREATING_IN_1C
        )

        if self.oneс_service:
            add_result = None
            add_error = None

            try:
                # Подготавливаем данные контрагента
                counterparty_data = self._prepare_counterparty_data(state)

                add_result = await self.oneс_service.add_agreement_to_existing_counterparty(
                    counterparty_uuid=state.existing_counterparty_id,
                    contract_data=counterparty_data,
                    document_path=state.document_path,
                    raw_text=state.raw_text
                )
            except Exception as e:
                error_traceback = traceback.format_exc()
                add_error = str(e)
                logger.error("Failed to add agreement to existing counterparty",
                           contract_id=state.contract_id,
                           existing_id=state.existing_counterparty_id,
                           error=add_error,
                           error_type=type(e).__name__,
                           traceback=error_traceback)

            agreement_uuid = None
            if add_result:
                agreement_uuid = add_result.get('agreement_uuid')
                logger.info("Agreement added to existing counterparty",
                           contract_id=state.contract_id,
                           existing_id=state.existing_counterparty_id,
                           agreement_uuid=agreement_uuid)

            # Сохраняем информацию в БД
            if self.state_manager.db:
                try:
                    contract = self.state_manager.db.query(Contract).filter(
                        Contract.id == state.contract_id
                    ).first()

                    if contract:
                        contract_data = self.state_manager.db.query(ContractData).filter(
                            ContractData.contract_id == contract.id
                        ).first()

                        if contract_data:
                            # Проверяем, существует ли уже запись
                            counterparty_1c = self.state_manager.db.query(Counterparty1C).filter(
                                Counterparty1C.contract_data_id == contract_data.id
                            ).first()

                            if counterparty_1c:
                                # Обновляем существующую запись
                                counterparty_1c.entity_uuid = state.existing_counterparty_id
                                counterparty_1c.agreement_uuid = agreement_uuid
                                counterparty_1c.status_1c = OneCStatus.CREATED
                                counterparty_1c.created_in_1c_at = datetime.now()
                                if add_result:
                                    counterparty_1c.response_from_1c = add_result.get('entity', {})
                                if add_error:
                                    counterparty_1c.error_from_1c = add_error
                            else:
                                # Создаем новую запись
                                counterparty_1c = Counterparty1C(
                                    contract_data_id=contract_data.id,
                                    entity_uuid=state.existing_counterparty_id,
                                    agreement_uuid=agreement_uuid,
                                    status_1c=OneCStatus.CREATED,
                                    created_in_1c_at=datetime.now(),
                                    response_from_1c=add_result.get('entity', {}) if add_result else None,
                                    error_from_1c=add_error
                                )
                                self.state_manager.db.add(counterparty_1c)

                    self.state_manager.db.commit()
                    logger.info("1C agreement info saved to DB",
                               contract_id=state.contract_id,
                               existing_id=state.existing_counterparty_id,
                               agreement_uuid=agreement_uuid)
                except Exception as e:
                    logger.error("Failed to save 1C agreement info to DB",
                               contract_id=state.contract_id,
                               error=str(e))
                    if self.state_manager.db:
                        self.state_manager.db.rollback()

            # Сохраняем UUID договора в state для возможного дальнейшего использования
            state.created_agreement_id = agreement_uuid

            if agreement_uuid:
                await self._update_progress(state.contract_id, 'creating_in_1c', 100, 'Договор добавлен к контрагенту в 1С')
                logger.info("Agreement added successfully to existing counterparty",
                           contract_id=state.contract_id,
                           existing_id=state.existing_counterparty_id,
                           agreement_uuid=agreement_uuid)
            else:
                await self._update_progress(state.contract_id, 'creating_in_1c', 100, 'Добавление договора завершено')

    def _prepare_counterparty_data(self, state: AgentState) -> Dict[str, Any]:
        """
        Подготовить данные контрагента для создания в 1С согласно правилам 2.1-2.8.
        
        Использует данные из customer или contractor в зависимости от того,
        откуда был взят ИНН при проверке (сохранено в state.counterparty_inn_source).
        """
        extracted_data = state.extracted_data or {}
        counterparty_data = {}
        
        # Определяем источник данных на основе того, откуда был взят ИНН
        inn_source = state.counterparty_inn_source or 'root'
        
        # Базовые данные контрагента
        if inn_source == 'customer' and 'customer' in extracted_data:
            # Используем данные из customer
            customer = extracted_data['customer']
            if isinstance(customer, dict):
                counterparty_data = {
                    'inn': customer.get('inn'),
                    'kpp': customer.get('kpp'),
                    'full_name': customer.get('full_name'),
                    'short_name': customer.get('short_name'),
                    'legal_entity_type': customer.get('legal_entity_type'),
                    'organizational_form': customer.get('organizational_form'),
                    'role': 'Заказчик'  # customer = заказчик
                }
        elif inn_source == 'contractor' and 'contractor' in extracted_data:
            # Используем данные из contractor
            contractor = extracted_data['contractor']
            if isinstance(contractor, dict):
                counterparty_data = {
                    'inn': contractor.get('inn'),
                    'kpp': contractor.get('kpp'),
                    'full_name': contractor.get('full_name'),
                    'short_name': contractor.get('short_name'),
                    'legal_entity_type': contractor.get('legal_entity_type'),
                    'organizational_form': contractor.get('organizational_form'),
                    'role': 'Поставщик'  # contractor = поставщик
                }
        else:
            # Используем корневые поля (legacy формат)
            counterparty_data = {
                'inn': extracted_data.get('inn'),
                'kpp': extracted_data.get('kpp'),
                'full_name': extracted_data.get('full_name'),
                'short_name': extracted_data.get('short_name'),
                'legal_entity_type': extracted_data.get('legal_entity_type'),
                'organizational_form': extracted_data.get('organizational_form'),
                'role': extracted_data.get('role', '')
            }
        
        # Добавляем дополнительные данные из контракта для правил 2.7, 2.8 и 2.9
        counterparty_data.update({
            'locations': extracted_data.get('locations') or extracted_data.get('service_locations'),
            'responsible_persons': extracted_data.get('responsible_persons'),
            'service_start_date': extracted_data.get('service_start_date'),
            'service_end_date': extracted_data.get('service_end_date'),
            'contract_name': extracted_data.get('contract_name'),
            'contract_number': extracted_data.get('contract_number'),
            'contract_date': extracted_data.get('contract_date'),
            'contract_price': extracted_data.get('contract_price'),
            'vat_percent': extracted_data.get('vat_percent'),
            'vat_type': extracted_data.get('vat_type'),
            'service_description': extracted_data.get('service_description'),
            'payment_terms': extracted_data.get('payment_terms'),
            'acceptance_procedure': extracted_data.get('acceptance_procedure'),
            'specification_exists': extracted_data.get('specification_exists'),
            'pricing_method': extracted_data.get('pricing_method'),
            'reporting_forms': extracted_data.get('reporting_forms'),
            'additional_conditions': extracted_data.get('additional_conditions'),
            'technical_info': extracted_data.get('technical_info'),
            'task_execution_term': extracted_data.get('task_execution_term'),
            'customer': extracted_data.get('customer'),  # Для определения организации в заметке
            'contractor': extracted_data.get('contractor'),  # Для определения организации в заметке
            'raw_text': state.raw_text,  # Для поиска фразы "протокол подведения итогов"
            'all_services': extracted_data.get('all_services'),  # Услуги из специализированного извлечения (шаг 3.5)
        })
        
        logger.info("Prepared counterparty data for creation",
                   contract_id=state.contract_id,
                   inn_source=inn_source,
                   has_inn=bool(counterparty_data.get('inn')))
        
        return counterparty_data
