"""
Оркестрация обработки контракта
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List

from app.agent.state_manager import AgentState, StateManager
from app.models.enums import ProcessingState, EventStatus
from app.models.database import ProcessingHistory
from app.services.document_processor import DocumentProcessor
from app.services.llm_service import LLMService
from app.services.prompts import EXTRACT_CONTRACT_DATA_PROMPT, MERGE_CHUNKS_DATA_PROMPT
from app.services.validation_service import ValidationService
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AgentOrchestrator:
    """Главный оркестратор для обработки контрактов"""
    
    def __init__(self, 
                 state_manager: StateManager,
                 doc_processor: DocumentProcessor,
                 llm_service: LLMService,
                 validation_service: ValidationService,
                 oneс_service=None):
        self.state_manager = state_manager
        self.doc_processor = doc_processor
        self.llm_service = llm_service
        self.validation_service = validation_service
        self.oneс_service = oneс_service
    
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
            # Шаг 1: Загрузить документ
            await self._load_document(state)
            
            # Шаг 2: Извлечь текст
            await self._extract_text(state)
            
            # Шаг 3: Извлечь данные контракта с помощью LLM
            await self._extract_contract_data(state)
            
            # Шаг 4: Валидировать извлеченные данные
            await self._validate_data(state)
            
            # Шаг 5: Проверить наличие в 1С (если сервис доступен)
            if self.oneс_service:
                await self._check_existing_in_1c(state)
                
                # Шаг 6: Создать контрагента в 1С
                await self._create_counterparty_in_1c(state)
            
            # Шаг 7: Завершить обработку
            state.status = ProcessingState.COMPLETED
            
        except Exception as e:
            logger.error("Contract processing failed", 
                        contract_id=contract_id,
                        error=str(e),
                        error_type=type(e).__name__)
            state.status = ProcessingState.FAILED
            state.error_message = str(e)
        
        finally:
            await self.state_manager.save_state(state)
        
        return state
    
    async def _load_document(self, state: AgentState):
        """Загрузить DOCX документ"""
        logger.info("Loading document", contract_id=state.contract_id)
        
        if not self.doc_processor.load_document(state.document_path):
            raise Exception(f"Failed to load document: {state.document_path}")
        
        await self.state_manager.update_status(
            state.contract_id,
            ProcessingState.DOCUMENT_LOADED
        )
    
    async def _extract_text(self, state: AgentState):
        """Извлечь текст из документа"""
        logger.info("Extracting text", contract_id=state.contract_id)
        
        state.raw_text = self.doc_processor.extract_text()
        
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
                request_info["status"] = "error"
                request_info["error"] = str(e)
                raise
            finally:
                state.llm_requests.append(request_info)
        else:
            # Документ большой, разбиваем на чанки и обрабатываем постепенно
            logger.info("Large document detected, splitting into chunks",
                       contract_id=state.contract_id,
                       document_size=document_size)
            
            chunks = self.doc_processor.get_chunks_for_llm(max_tokens_per_chunk=8000)
            logger.info("Document split into chunks",
                       contract_id=state.contract_id,
                       chunks_count=len(chunks))
            
            # Обрабатываем каждый чанк через LLM
            chunks_data: List[Dict[str, Any]] = []
            chunks_with_context: List[Dict[str, Any]] = []
            accumulated_data: Dict[str, Any] = {}  # Накопленные данные из предыдущих чанков
            
            for chunk_idx, chunk_text in enumerate(chunks, start=1):
                logger.info("Processing chunk",
                           contract_id=state.contract_id,
                           chunk_index=chunk_idx,
                           total_chunks=len(chunks),
                           chunk_size=len(chunk_text))
                
                # Для чанков после первого добавляем контекст из предыдущих чанков
                enriched_chunk_text = chunk_text
                if chunk_idx > 1 and accumulated_data:
                    context_block = self._build_chunk_context(accumulated_data)
                    enriched_chunk_text = context_block + chunk_text
                    logger.info("Added context to chunk",
                               contract_id=state.contract_id,
                               chunk_index=chunk_idx,
                               context_size=len(context_block))
                
                # Сохраняем контекст чанка (первые 1000 символов для понимания содержимого)
                chunk_context = enriched_chunk_text[:1000] if enriched_chunk_text else ""
                
                # Формируем полный промпт, который уходит в LLM
                system_prompt = """You are an expert in Russian contract analysis.
        Extract contract information from documents and return it as valid JSON.
        Be precise with INN extraction (10 or 12 digits).
        Use boolean fields is_supplier and is_buyer for roles.
        """
                user_prompt = EXTRACT_CONTRACT_DATA_PROMPT.format(document_text=enriched_chunk_text)
                full_prompt = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"
                
                # Сохраняем информацию о запросе для каждого чанка
                request_info = {
                    "request_type": "chunk",
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                    "chunk_context": chunk_context,  # Сохраняем контекст чанка
                    "request_text": full_prompt,
                    "request_size": len(full_prompt),
                    "request_tokens_estimate": self.doc_processor.estimate_tokens(full_prompt),
                    "timestamp": datetime.now().isoformat(),
                }
                
                try:
                    chunk_data = await self.llm_service.extract_contract_data(enriched_chunk_text)
                    chunks_data.append(chunk_data)
                    
                    # Обновляем накопленные данные информацией из текущего чанка
                    # Приоритет отдается более полным данным
                    if chunk_data:
                        try:
                            # Обновляем базовую информацию о контрагенте (если еще не было или если более полная)
                            if not accumulated_data.get('inn') and chunk_data.get('inn'):
                                accumulated_data['inn'] = chunk_data['inn']
                            if not accumulated_data.get('full_name') and chunk_data.get('full_name'):
                                accumulated_data['full_name'] = chunk_data['full_name']
                            elif chunk_data.get('full_name') and len(chunk_data['full_name']) > len(accumulated_data.get('full_name', '')):
                                accumulated_data['full_name'] = chunk_data['full_name']
                            
                            if not accumulated_data.get('short_name') and chunk_data.get('short_name'):
                                accumulated_data['short_name'] = chunk_data['short_name']
                            if not accumulated_data.get('organizational_form') and chunk_data.get('organizational_form'):
                                accumulated_data['organizational_form'] = chunk_data['organizational_form']
                            if not accumulated_data.get('kpp') and chunk_data.get('kpp'):
                                accumulated_data['kpp'] = chunk_data['kpp']
                            
                            # Обновляем роли (объединяем)
                            if chunk_data.get('is_supplier'):
                                accumulated_data['is_supplier'] = True
                            if chunk_data.get('is_buyer'):
                                accumulated_data['is_buyer'] = True
                            
                            # Объединяем ответственных лиц (добавляем уникальных)
                            existing_persons = accumulated_data.get('responsible_persons', [])
                            if not isinstance(existing_persons, list):
                                existing_persons = []
                            
                            new_persons = chunk_data.get('responsible_persons', [])
                            if isinstance(new_persons, list):
                                # Безопасное создание set имен - проверяем что name это строка
                                existing_names = set()
                                for p in existing_persons:
                                    if isinstance(p, dict):
                                        name = p.get('name')
                                        if isinstance(name, str):
                                            existing_names.add(name.lower())
                                        elif isinstance(name, (list, tuple)):
                                            # Если name это список, преобразуем в строку
                                            name_str = ', '.join(str(n) for n in name if n)
                                            if name_str:
                                                existing_names.add(name_str.lower())
                                
                                for person in new_persons:
                                    if isinstance(person, dict):
                                        person_name = person.get('name')
                                        if person_name:
                                            # Преобразуем name в строку если это список
                                            if isinstance(person_name, str):
                                                name_key = person_name.lower()
                                            elif isinstance(person_name, (list, tuple)):
                                                name_key = ', '.join(str(n) for n in person_name if n).lower()
                                            else:
                                                name_key = str(person_name).lower()
                                            
                                            if name_key and name_key not in existing_names:
                                                # Если name был списком, преобразуем в строку
                                                if isinstance(person_name, (list, tuple)):
                                                    person_copy = person.copy()
                                                    person_copy['name'] = ', '.join(str(n) for n in person_name if n)
                                                    existing_persons.append(person_copy)
                                                else:
                                                    existing_persons.append(person)
                                                existing_names.add(name_key)
                                        else:
                                            # Обновляем существующего, если новая информация более полная
                                            for idx, existing_person in enumerate(existing_persons):
                                                if isinstance(existing_person, dict):
                                                    existing_name = existing_person.get('name', '')
                                                    if isinstance(existing_name, str):
                                                        existing_name_key = existing_name.lower()
                                                    elif isinstance(existing_name, (list, tuple)):
                                                        existing_name_key = ', '.join(str(n) for n in existing_name if n).lower()
                                                    else:
                                                        existing_name_key = str(existing_name).lower()
                                                    
                                                    if existing_name_key == name_key:
                                                        # Объединяем контакты
                                                        if person.get('phone') and not existing_person.get('phone'):
                                                            existing_persons[idx]['phone'] = person['phone']
                                                        if person.get('email') and not existing_person.get('email'):
                                                            existing_persons[idx]['email'] = person['email']
                                                        if person.get('position') and not existing_person.get('position'):
                                                            existing_persons[idx]['position'] = person['position']
                                                        break
                            
                            accumulated_data['responsible_persons'] = existing_persons
                            
                            # Объединяем адреса (добавляем уникальные)
                            existing_locations = accumulated_data.get('locations', []) or accumulated_data.get('service_locations', [])
                            if not isinstance(existing_locations, list):
                                existing_locations = []
                            
                            new_locations = chunk_data.get('locations', []) or chunk_data.get('service_locations', [])
                            if isinstance(new_locations, list):
                                # Безопасное создание set адресов - проверяем что address это строка
                                existing_addresses = set()
                                for loc in existing_locations:
                                    if isinstance(loc, dict):
                                        addr = loc.get('address')
                                        if isinstance(addr, str):
                                            existing_addresses.add(addr.lower())
                                
                                for location in new_locations:
                                    if isinstance(location, dict):
                                        addr = location.get('address')
                                        if isinstance(addr, str):
                                            addr_key = addr.lower()
                                            if addr_key and addr_key not in existing_addresses:
                                                existing_locations.append(location)
                                                existing_addresses.add(addr_key)
                                    elif isinstance(addr, (list, tuple)):
                                        # Если address это список, преобразуем в строку
                                        addr_str = ', '.join(str(a) for a in addr if a)
                                        if addr_str:
                                            addr_key = addr_str.lower()
                                            if addr_key not in existing_addresses:
                                                location_copy = location.copy()
                                                location_copy['address'] = addr_str
                                                existing_locations.append(location_copy)
                                                existing_addresses.add(addr_key)
                            
                            accumulated_data['locations'] = existing_locations
                            accumulated_data['service_locations'] = existing_locations
                            
                            # Обновляем информацию о заказчике и исполнителе
                            if chunk_data.get('customer'):
                                customer_data = chunk_data['customer']
                                if isinstance(customer_data, dict):
                                    # Если уже есть customer, обновляем только если новый более полный
                                    if not accumulated_data.get('customer') or isinstance(accumulated_data.get('customer'), dict):
                                        if not accumulated_data.get('customer'):
                                            # Нормализуем данные customer перед сохранением
                                            normalized_customer = {}
                                            for key, value in customer_data.items():
                                                if isinstance(value, (list, tuple)):
                                                    # Преобразуем списки в строки для основных полей
                                                    if key in ['inn', 'kpp', 'full_name', 'short_name', 'organizational_form', 'legal_entity_type']:
                                                        normalized_customer[key] = ', '.join(str(v) for v in value if v) if value else None
                                                    else:
                                                        normalized_customer[key] = value
                                                else:
                                                    normalized_customer[key] = value
                                            accumulated_data['customer'] = normalized_customer
                                    else:
                                        # Объединяем данные, приоритет более полным
                                        existing_customer = accumulated_data['customer']
                                        for key, value in customer_data.items():
                                            if value:
                                                # Нормализуем значение если это список
                                                if isinstance(value, (list, tuple)) and key in ['inn', 'kpp', 'full_name', 'short_name', 'organizational_form', 'legal_entity_type']:
                                                    value = ', '.join(str(v) for v in value if v) if value else None
                                                
                                                if value and (not existing_customer.get(key) or len(str(value)) > len(str(existing_customer.get(key, '')))):
                                                    existing_customer[key] = value
                            
                            if chunk_data.get('contractor'):
                                contractor_data = chunk_data['contractor']
                                if isinstance(contractor_data, dict):
                                    # Если уже есть contractor, обновляем только если новый более полный
                                    if not accumulated_data.get('contractor') or isinstance(accumulated_data.get('contractor'), dict):
                                        if not accumulated_data.get('contractor'):
                                            # Нормализуем данные contractor перед сохранением
                                            normalized_contractor = {}
                                            for key, value in contractor_data.items():
                                                if isinstance(value, (list, tuple)):
                                                    # Преобразуем списки в строки для основных полей
                                                    if key in ['inn', 'kpp', 'full_name', 'short_name', 'organizational_form', 'legal_entity_type']:
                                                        normalized_contractor[key] = ', '.join(str(v) for v in value if v) if value else None
                                                    else:
                                                        normalized_contractor[key] = value
                                                else:
                                                    normalized_contractor[key] = value
                                            accumulated_data['contractor'] = normalized_contractor
                                    else:
                                        # Объединяем данные, приоритет более полным
                                        existing_contractor = accumulated_data['contractor']
                                        for key, value in contractor_data.items():
                                            if value:
                                                # Нормализуем значение если это список
                                                if isinstance(value, (list, tuple)) and key in ['inn', 'kpp', 'full_name', 'short_name', 'organizational_form', 'legal_entity_type']:
                                                    value = ', '.join(str(v) for v in value if v) if value else None
                                                
                                                if value and (not existing_contractor.get(key) or len(str(value)) > len(str(existing_contractor.get(key, '')))):
                                                    existing_contractor[key] = value
                            
                            # Обновляем основную информацию о договоре
                            # Название договора - приоритет первому найденному или более полному
                            if chunk_data.get('contract_name'):
                                if not accumulated_data.get('contract_name'):
                                    accumulated_data['contract_name'] = chunk_data['contract_name']
                                elif len(str(chunk_data['contract_name'])) > len(str(accumulated_data.get('contract_name', ''))):
                                    accumulated_data['contract_name'] = chunk_data['contract_name']
                            
                            # Номер договора - приоритет первому найденному
                            if chunk_data.get('contract_number') and not accumulated_data.get('contract_number'):
                                accumulated_data['contract_number'] = chunk_data['contract_number']
                            
                            # Дата договора - приоритет первой (обычно самая ранняя)
                            if chunk_data.get('contract_date') and not accumulated_data.get('contract_date'):
                                accumulated_data['contract_date'] = chunk_data['contract_date']
                            
                            # Цена договора - приоритет первому найденному или более высокой (если указана)
                            if chunk_data.get('contract_price'):
                                if not accumulated_data.get('contract_price'):
                                    accumulated_data['contract_price'] = chunk_data['contract_price']
                                # Можно также сравнивать числовые значения, но пока берем первое
                            
                            # НДС - приоритет первому найденному
                            if chunk_data.get('vat_type') and not accumulated_data.get('vat_type'):
                                accumulated_data['vat_type'] = chunk_data['vat_type']
                            if chunk_data.get('vat_percent') and not accumulated_data.get('vat_percent'):
                                accumulated_data['vat_percent'] = chunk_data['vat_percent']
                            
                            # Описание услуг/товаров - объединяем или выбираем более полное
                            if chunk_data.get('service_description'):
                                if not accumulated_data.get('service_description'):
                                    accumulated_data['service_description'] = chunk_data['service_description']
                                elif isinstance(chunk_data['service_description'], str) and isinstance(accumulated_data.get('service_description'), str):
                                    # Выбираем более полное описание
                                    if len(chunk_data['service_description']) > len(accumulated_data['service_description']):
                                        accumulated_data['service_description'] = chunk_data['service_description']
                            
                            # Даты оказания услуг - приоритет первому найденному
                            if chunk_data.get('service_start_date') and not accumulated_data.get('service_start_date'):
                                accumulated_data['service_start_date'] = chunk_data['service_start_date']
                            if chunk_data.get('service_end_date') and not accumulated_data.get('service_end_date'):
                                accumulated_data['service_end_date'] = chunk_data['service_end_date']
                            
                            # Условия оплаты - объединяем или выбираем более полное
                            if chunk_data.get('payment_terms'):
                                if not accumulated_data.get('payment_terms'):
                                    accumulated_data['payment_terms'] = chunk_data['payment_terms']
                                elif isinstance(chunk_data['payment_terms'], str) and isinstance(accumulated_data.get('payment_terms'), str):
                                    if len(chunk_data['payment_terms']) > len(accumulated_data['payment_terms']):
                                        accumulated_data['payment_terms'] = chunk_data['payment_terms']
                            
                            # Порядок приема-сдачи - выбираем более полное
                            if chunk_data.get('acceptance_procedure'):
                                if not accumulated_data.get('acceptance_procedure'):
                                    accumulated_data['acceptance_procedure'] = chunk_data['acceptance_procedure']
                                elif isinstance(chunk_data['acceptance_procedure'], str) and isinstance(accumulated_data.get('acceptance_procedure'), str):
                                    if len(chunk_data['acceptance_procedure']) > len(accumulated_data['acceptance_procedure']):
                                        accumulated_data['acceptance_procedure'] = chunk_data['acceptance_procedure']
                            
                            # Наличие спецификации - приоритет true если хотя бы в одном чанке true
                            if chunk_data.get('specification_exists') is not None:
                                if accumulated_data.get('specification_exists') is None:
                                    accumulated_data['specification_exists'] = chunk_data['specification_exists']
                                elif not accumulated_data.get('specification_exists') and chunk_data.get('specification_exists'):
                                    accumulated_data['specification_exists'] = True
                            
                            # Порядок ценообразования - выбираем более полное
                            if chunk_data.get('pricing_method'):
                                if not accumulated_data.get('pricing_method'):
                                    accumulated_data['pricing_method'] = chunk_data['pricing_method']
                                elif isinstance(chunk_data['pricing_method'], str) and isinstance(accumulated_data.get('pricing_method'), str):
                                    if len(chunk_data['pricing_method']) > len(accumulated_data['pricing_method']):
                                        accumulated_data['pricing_method'] = chunk_data['pricing_method']
                            
                            # Формы отчетности - выбираем более полное
                            if chunk_data.get('reporting_forms'):
                                if not accumulated_data.get('reporting_forms'):
                                    accumulated_data['reporting_forms'] = chunk_data['reporting_forms']
                                elif isinstance(chunk_data['reporting_forms'], str) and isinstance(accumulated_data.get('reporting_forms'), str):
                                    if len(chunk_data['reporting_forms']) > len(accumulated_data['reporting_forms']):
                                        accumulated_data['reporting_forms'] = chunk_data['reporting_forms']
                            
                            # Дополнительные условия - выбираем более полное
                            if chunk_data.get('additional_conditions'):
                                if not accumulated_data.get('additional_conditions'):
                                    accumulated_data['additional_conditions'] = chunk_data['additional_conditions']
                                elif isinstance(chunk_data['additional_conditions'], str) and isinstance(accumulated_data.get('additional_conditions'), str):
                                    if len(chunk_data['additional_conditions']) > len(accumulated_data['additional_conditions']):
                                        accumulated_data['additional_conditions'] = chunk_data['additional_conditions']
                            
                            # Техническая информация - выбираем более полное
                            if chunk_data.get('technical_information'):
                                if not accumulated_data.get('technical_information'):
                                    accumulated_data['technical_information'] = chunk_data['technical_information']
                                elif isinstance(chunk_data['technical_information'], str) and isinstance(accumulated_data.get('technical_information'), str):
                                    if len(chunk_data['technical_information']) > len(accumulated_data['technical_information']):
                                        accumulated_data['technical_information'] = chunk_data['technical_information']
                        except Exception as data_update_error:
                            logger.error("Failed to update accumulated data",
                                        contract_id=state.contract_id,
                                        chunk_index=chunk_idx,
                                        error=str(data_update_error),
                                        error_type=type(data_update_error).__name__,
                                        chunk_data_keys=list(chunk_data.keys()) if chunk_data else None)
                            # Продолжаем обработку даже если обновление накопленных данных не удалось
                    
                    # Формируем полный накопленный контекст для этого чанка
                    accumulated_context = self._build_chunk_context(accumulated_data) if accumulated_data else ""
                    
                    # Сохраняем данные для финальной агрегации с контекстом
                    chunks_with_context.append({
                        "chunk_index": chunk_idx,
                        "chunk_context": chunk_context,  # Первые 1000 символов текста чанка для понимания содержимого
                        "accumulated_context": accumulated_context,  # Полный накопленный контекст из предыдущих чанков
                        "extracted_data": chunk_data
                    })
                    
                    # Сохраняем информацию об ответе
                    request_info["response_data"] = chunk_data
                    request_info["response_size"] = len(str(chunk_data))
                    request_info["status"] = "success"
                    
                    logger.info("Chunk processed successfully",
                               contract_id=state.contract_id,
                               chunk_index=chunk_idx)
                except Exception as e:
                    request_info["status"] = "error"
                    request_info["error"] = str(e)
                    
                    logger.error("Failed to process chunk",
                               contract_id=state.contract_id,
                               chunk_index=chunk_idx,
                               error=str(e))
                    # Продолжаем обработку остальных чанков даже если один упал
                finally:
                    state.llm_requests.append(request_info)
            
            if not chunks_data:
                raise Exception("Failed to extract data from any chunk")
            
            # Формируем финальный накопленный контекст из всех чанков
            final_accumulated_context = self._build_chunk_context(accumulated_data) if accumulated_data else ""
            
            # Обновляем последний чанк с финальным накопленным контекстом
            if chunks_with_context and final_accumulated_context:
                chunks_with_context[-1]['accumulated_context'] = final_accumulated_context
            
            # Агрегируем результаты из всех чанков через LLM с разрешением конфликтов
            logger.info("Aggregating data from chunks via LLM",
                       contract_id=state.contract_id,
                       chunks_processed=len(chunks_with_context))
            
            # Формируем данные для промпта агрегации с полным накопленным контекстом (для логирования)
            chunks_data_formatted = []
            for chunk_info in chunks_with_context:
                chunk_data = {
                    "chunk_index": chunk_info.get('chunk_index', 0),
                    "chunk_context": chunk_info.get('chunk_context', '')[:1000],  # Первые 1000 символов текста чанка
                    "accumulated_context": chunk_info.get('accumulated_context', ''),  # Полный накопленный контекст
                    "extracted_data": chunk_info.get('extracted_data', {})
                }
                chunks_data_formatted.append(chunk_data)
            
            # Формируем промпт для агрегации
            chunks_json = json.dumps(chunks_data_formatted, ensure_ascii=False, indent=2)
            user_prompt = MERGE_CHUNKS_DATA_PROMPT.format(
                total_chunks=len(chunks_with_context),
                chunks_data=chunks_json,
                accumulated_context=final_accumulated_context
            )
            system_prompt = """You are an expert in Russian contract analysis.
        Merge contract information from multiple document chunks and resolve conflicts.
        Return only valid JSON with all merged fields.
        """
            full_prompt = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"
            
            # Сохраняем информацию о финальном запросе агрегации
            aggregation_request_info = {
                "request_type": "aggregation",
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
                aggregation_request_info["status"] = "error"
                aggregation_request_info["error"] = str(e)
                
                logger.error("Failed to aggregate chunks data via LLM, using fallback",
                           contract_id=state.contract_id,
                           error=str(e))
                
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
    
    async def _validate_data(self, state: AgentState):
        """Валидировать извлеченные данные"""
        logger.info("Validating extracted data", contract_id=state.contract_id)
        
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
        
        await self.state_manager.update_status(
            state.contract_id,
            ProcessingState.VALIDATION_PASSED
        )
    
    async def _check_existing_in_1c(self, state: AgentState):
        """Проверить наличие контрагента в справочнике 1С"""
        logger.info("Checking existing counterparty in 1C", contract_id=state.contract_id)
        
        if not state.extracted_data:
            raise Exception("Extracted data not found")
        
        # Получаем ИНН из корневых полей или из customer/contractor
        inn = None
        if 'inn' in state.extracted_data and state.extracted_data['inn']:
            inn = state.extracted_data['inn']
        elif 'customer' in state.extracted_data and isinstance(state.extracted_data['customer'], dict):
            inn = state.extracted_data['customer'].get('inn')
        elif 'contractor' in state.extracted_data and isinstance(state.extracted_data['contractor'], dict):
            inn = state.extracted_data['contractor'].get('inn')
        
        if not inn:
            raise Exception("INN not found in extracted data (checked root, customer, and contractor fields)")
        
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
                logger.error("Exception during counterparty search", 
                           contract_id=state.contract_id,
                           inn=inn,
                           error=str(e))
                search_error = str(e)
            
            # Сохраняем информацию о поиске в ProcessingHistory
            if self.state_manager.db:
                try:
                    search_result = {
                        'inn': inn,
                        'found': existing is not None and not (isinstance(existing, dict) and existing.get('_error')),
                        'counterparty_uuid': existing.get('uuid') if existing and isinstance(existing, dict) and not existing.get('_error') else None,
                        'counterparty_data': existing if existing and isinstance(existing, dict) and not existing.get('_error') else None,
                        'error': search_error
                    }
                    
                    history_entry = ProcessingHistory(
                        contract_id=state.contract_id,
                        event_type='1c_check',
                        event_status=EventStatus.ERROR if search_error else EventStatus.SUCCESS,
                        event_message=f"Поиск контрагента по ИНН {inn}" + (f" - ошибка: {search_error}" if search_error else ""),
                        event_details=search_result
                    )
                    self.state_manager.db.add(history_entry)
                    self.state_manager.db.commit()
                    logger.info("1C search info saved to DB",
                               contract_id=state.contract_id,
                               inn=inn,
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
    
    async def _create_counterparty_in_1c(self, state: AgentState):
        """Создать контрагента в 1С"""
        if state.existing_counterparty_id:
            logger.info("Counterparty already exists, skipping creation",
                       contract_id=state.contract_id,
                       existing_id=state.existing_counterparty_id)
            return
        
        logger.info("Creating counterparty in 1C", contract_id=state.contract_id)
        
        await self.state_manager.update_status(
            state.contract_id,
            ProcessingState.CREATING_IN_1C
        )
        
        if self.oneс_service:
            created_id = None
            create_error = None
            
            try:
                created_id = await self.oneс_service.create_counterparty(
                    state.extracted_data,
                    state.document_path
                )
            except Exception as e:
                create_error = str(e)
                logger.error("Failed to create counterparty in 1C",
                           contract_id=state.contract_id,
                           error=create_error)
            
            # Сохраняем информацию о создании в ProcessingHistory
            if self.state_manager.db:
                try:
                    create_result = {
                        'inn': state.extracted_data.get('inn'),
                        'created': created_id is not None,
                        'counterparty_uuid': created_id,
                        'error': create_error
                    }
                    
                    history_entry = ProcessingHistory(
                        contract_id=state.contract_id,
                        event_type='1c_create',
                        event_status=EventStatus.SUCCESS if created_id else EventStatus.ERROR,
                        event_message=f"Создание контрагента в 1С" + (f" - ошибка: {create_error}" if create_error else ""),
                        event_details=create_result
                    )
                    self.state_manager.db.add(history_entry)
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
                logger.info("Counterparty created successfully",
                           contract_id=state.contract_id,
                           counterparty_id=created_id)
