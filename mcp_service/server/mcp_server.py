"""
MCP Server для взаимодействия с 1С через SSE
"""
import asyncio
import json
import os
import re
import sys
import structlog
from typing import Dict, Any, Optional
from datetime import datetime, date
from aiohttp import web

logger = structlog.get_logger(__name__)


class MCPServer:
    """MCP Server для взаимодействия с 1С через SSE"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.oneс_client: Optional[Any] = None
        self.active_connections: Dict[str, web.StreamResponse] = {}
    
    async def handle_sse_connect(self, request: web.Request) -> web.StreamResponse:
        """Обработка SSE подключения"""
        client_id = request.match_info.get('client_id', 'default')
        
        logger.info("SSE client connected", client_id=client_id)
        
        response = web.StreamResponse()
        response.content_type = 'text/event-stream'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Accel-Buffering'] = 'no'
        
        await response.prepare(request)
        
        # Отправить welcome message
        welcome_msg = json.dumps({"type": "connected", "client_id": client_id})
        await response.write(f'data: {welcome_msg}\n\n'.encode())
        
        self.active_connections[client_id] = response
        
        try:
            # Держать соединение открытым
            while True:
                await asyncio.sleep(30)  # Heartbeat каждые 30 секунд
                try:
                    await response.write(b': heartbeat\n\n')
                except Exception as e:
                    logger.error("Failed to send heartbeat", error=str(e), client_id=client_id)
                    break
        except asyncio.CancelledError:
            logger.info("SSE client disconnected", client_id=client_id)
        finally:
            if client_id in self.active_connections:
                del self.active_connections[client_id]
            try:
                await response.write_eof()
            except Exception:
                pass
        
        return response
    
    async def execute_command(self, request: web.Request) -> web.Response:
        """Выполнить MCP команду"""
        try:
            data = await request.json()
            command = data.get('command')
            params = data.get('params', {})
            
            logger.info("Executing MCP command", command=command, params=params)
            
            result = await self._execute_command_impl(command, params)
            
            return web.json_response({
                'status': 'success',
                'result': result
            })
        
        except Exception as e:
            logger.error("Command execution failed", error=str(e), exc_info=True)
            return web.json_response({
                'status': 'error',
                'error': str(e)
            }, status=400)
    
    async def _execute_command_impl(self, command: str, params: Dict[str, Any]) -> Any:
        """Реализация команд"""
        
        if command == 'check_counterparty':
            return await self._check_counterparty(params)
        
        elif command == 'create_counterparty':
            return await self._create_counterparty(params)
        
        elif command == 'update_counterparty':
            return await self._update_counterparty(params)
        
        elif command == 'create_agreement':
            logger.info("Create agreemen2", params=params)
            return await self._create_agreement(params)
        
        elif command == 'attach_file':
            return await self._attach_file(params)
        
        elif command == 'get_one_counterparty':
            return await self._get_one_counterparty(params)
        
        elif command == 'add_note':
            return await self._add_note(params)
        
        elif command == 'add_agreement':
            return await self._add_agreement(params)
        
        else:
            raise ValueError(f"Unknown command: {command}")
    
    async def _check_counterparty(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверить наличие контрагента по ИНН по всем областям справочника Контрагенты.
        
        Согласно правилам: проверка должна выполняться по всем областям справочника Контрагенты.
        OData запрос Catalog_Контрагенты возвращает все контрагенты из всех областей (подразделов).
        
        ВАЖНО: 1С не разрешает фильтрацию по ИНН в предложении WHERE, поэтому всегда используем
        локальный поиск по всем контрагентам.
        """
        inn = params.get('inn')
        if not inn:
            raise ValueError("INN is required")
        
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        # ВАЖНО: 1С не разрешает фильтрацию по ИНН в OData запросах (ошибка "Операция не разрешена в предложении ГДЕ")
        # Поэтому всегда получаем все контрагенты и ищем локально
        # OData запрос Catalog_Контрагенты без фильтра возвращает ВСЕ контрагенты из всех областей (подразделов)
        try:
            # Получаем все контрагенты из всех областей справочника
            # Используем пагинацию для получения всех записей, если их больше 1000
            all_counterparties = []
            skip = 0
            top = 1000  # Размер страницы
            
            while True:
                # Запрос с пагинацией для получения всех контрагентов
                query = f"Catalog_Контрагенты?$skip={skip}&$top={top}"
                result = await self.oneс_client.execute_query(query)
                
                if not result or not result.get('value'):
                    break
                
                counterparties_batch = result['value']
                all_counterparties.extend(counterparties_batch)
                
                # Если получили меньше записей, чем запрашивали, значит это последняя страница
                if len(counterparties_batch) < top:
                    break
                
                skip += top
            
            logger.info("Fetched all counterparties for search", 
                      total_count=len(all_counterparties), 
                      inn=inn)
            
            # Ищем контрагента с нужным ИНН по всем областям
            for counterparty in all_counterparties:
                counterparty_inn = counterparty.get('ИНН')
                # Проверяем, что ИНН не пустой и совпадает (точное совпадение)
                if counterparty_inn and counterparty_inn.strip() and counterparty_inn == inn:
                    logger.info("Counterparty found in local search", 
                              inn=inn, 
                              uuid=counterparty.get('Ref_Key'))
                    return {
                        'found': True,
                        'uuid': counterparty.get('Ref_Key'),
                        'data': counterparty
                    }
            
            logger.info("Counterparty not found in any area", inn=inn)
        except Exception as e:
            logger.error("Failed to check counterparty", error=str(e), inn=inn)
            raise
        
        return {'found': False}
    
    def _determine_legal_entity_type_by_inn(self, inn: Optional[str]) -> str:
        """
        Правило 2.2: Определить Юр./физ. лицо на основе количества знаков ИНН.
        Если количество знаков = 12, то это физ. лицо; если = 10, то это юр. лицо.
        """
        if not inn:
            return 'ЮрЛицо'  # По умолчанию
        
        inn_clean = str(inn).strip()
        if len(inn_clean) == 12:
            return 'ФизЛицо'
        elif len(inn_clean) == 10:
            return 'ЮрЛицо'
        else:
            # Если ИНН не соответствует стандарту, пытаемся определить по legal_entity_type
            return 'ЮрЛицо'  # По умолчанию
    
    def _determine_gov_com_type(self, organizational_form: Optional[str]) -> Optional[str]:
        """
        Правило 2.6: Определить Гос./Ком. на основе организационно-правовой формы.
        Для ИП, ООО, АО – значение Ком, для остальных – значение Гос.
        """
        if not organizational_form:
            return 'Ком'
        
        org_form_lower = str(organizational_form).lower()
        
        # Коммерческие организации
        if any(keyword in org_form_lower for keyword in ['индивидуальный предприниматель', 'ип', 'общество с ограниченной ответственностью', 'ооо', 'акционерное общество', 'ао', 'зао', 'оао']):
            return 'Ком'
        
        # Государственные организации (все остальные)
        return 'Гос'
    
    def _prepare_full_name(self, full_name: Optional[str], organizational_form: Optional[str]) -> str:
        """
        Правило 2.5: Заполнить поле Полное наименование с организационно-правовой формой без сокращения.
        """
        if not full_name:
            return ''
        
        # Если в полном наименовании уже есть ОПФ, возвращаем как есть
        # Иначе добавляем ОПФ в начало
        if organizational_form and organizational_form.lower() not in full_name.lower():
            # Проверяем, начинается ли наименование с ОПФ
            org_form_short = organizational_form.replace(' ', '').lower()
            full_name_lower = full_name.lower()
            
            # Если ОПФ не найдено в начале, добавляем
            if not full_name_lower.startswith(org_form_short[:3].lower()):
                return f"{organizational_form} {full_name}"
        
        return full_name
    
    def _prepare_short_name(self, short_name: Optional[str], full_name: Optional[str], 
                           locations: Optional[list], raw_text: Optional[str],
                           service_end_date: Optional[str]) -> str:
        """
        Правило 2.7: Заполнить поле Наименование (без ОПФ) с добавлением СПБ, ЕИС и срока оказания услуг.
        
        - Только наименование без ОПФ
        - Добавить "СПБ" если место оказания услуг - СПБ или ЛО
        - Добавить "ЕИС" если есть фраза "протокол подведения итогов"
        - Добавить срок оказания услуг в формате число.месяц.год
        """
        name = short_name or full_name or ''
        
        # Удаляем ОПФ из начала наименования
        if name:
            # Удаляем распространенные ОПФ из начала
            org_forms = ['ООО', 'АО', 'ЗАО', 'ОАО', 'ИП', 'ОГУП', 'МУП', 'ГУП']
            for org_form in org_forms:
                if name.startswith(org_form + ' '):
                    name = name[len(org_form) + 1:].strip()
                    break
                elif name.startswith(org_form):
                    name = name[len(org_form):].strip()
                    break
        
        # Проверяем наличие СПБ или ЛО в адресах оказания услуг
        if locations:
            for location in locations:
                if isinstance(location, dict):
                    address = str(location.get('address', '') or location.get('full_address', '')).lower()
                    city = str(location.get('city', '')).lower()
                    region = str(location.get('region', '')).lower()
                    
                    if any(keyword in address or keyword in city or keyword in region 
                           for keyword in ['санкт-петербург', 'спб', 'ленинградская область', 'ленинградской области', 'ленинградская обл']):
                        name = f"{name} СПБ" if name else "СПБ"
                        break
        
        # Проверяем наличие фразы "протокол подведения итогов" в тексте
        if raw_text:
            text_lower = raw_text.lower()
            # Ищем фразу в разных падежах
            protocol_patterns = [
                r'протокол\s+подведения\s+итогов',
                r'протокола\s+подведения\s+итогов',
                r'протоколу\s+подведения\s+итогов',
                r'протоколом\s+подведения\s+итогов',
                r'протоколе\s+подведения\s+итогов'
            ]
            
            for pattern in protocol_patterns:
                if re.search(pattern, text_lower):
                    name = f"{name} ЕИС" if name else "ЕИС"
                    break
        
        # Добавляем срок оказания услуг в формате число.месяц.год
        if service_end_date:
            try:
                # Парсим дату (может быть строкой или объектом date)
                if isinstance(service_end_date, str):
                    end_date = datetime.strptime(service_end_date, '%Y-%m-%d').date()
                elif isinstance(service_end_date, date):
                    end_date = service_end_date
                else:
                    end_date = None
                
                if end_date:
                    # Форматируем в формат число.месяц.год
                    date_str = f"{end_date.day}.{end_date.month}.{end_date.year}"
                    name = f"{name} {date_str}" if name else date_str
            except Exception as e:
                logger.warning("Failed to format service end date", error=str(e))
        
        return name
    
    def _prepare_service_address(self, locations: Optional[list], 
                                 responsible_persons: Optional[list]) -> str:
        """
        Правило 2.8: Заполнить поле Адрес для служебного пользования.
        
        - Адреса оказания услуг (каждый с новой строки)
        - Дополнительная информация о местонахождении (directions - как проехать, ориентиры)
        - К каждому адресу: имя, фамилия и контакты ответственного лица
        - Если нет ответственного лица в адресе, использовать первое лицо из общего списка responsible_persons
          (как лицо, уполномоченное на подписание контракта)
        """
        if not locations:
            return ''
        
        address_lines = []
        
        for location in locations:
            if not isinstance(location, dict):
                continue
            
            # Формируем адрес из всех доступных полей
            address_parts = []
            
            # Используем address или full_address (приоритет full_address если есть оба)
            if location.get('full_address'):
                address_parts.append(location.get('full_address'))
            elif location.get('address'):
                address_parts.append(location.get('address'))
            
            if location.get('city'):
                address_parts.append(location.get('city'))
            
            if location.get('region'):
                address_parts.append(location.get('region'))
            
            if location.get('postal_code'):
                address_parts.append(location.get('postal_code'))
            
            address_str = ', '.join(filter(None, address_parts))
            
            # Добавляем дополнительную информацию о местонахождении (directions - как проехать, ориентиры)
            if location.get('directions'):
                address_str += f" ({location.get('directions')})"
            elif location.get('additional_info'):
                # Поддержка старого поля additional_info для обратной совместимости
                address_str += f" ({location.get('additional_info')})"
            
            # Ищем ответственное лицо для этого адреса:
            # 1. Сначала проверяем location.responsible_person (ответственное лицо для конкретного адреса)
            # 2. Если нет, используем первое лицо из общего списка responsible_persons
            #    (как лицо, уполномоченное на подписание контракта)
            responsible_person = None
            
            # Проверяем наличие ответственного лица в самом адресе
            if location.get('responsible_person'):
                responsible_person = location.get('responsible_person')
            # Если нет ответственного лица в адресе, используем первое лицо из общего списка
            elif responsible_persons and len(responsible_persons) > 0:
                responsible_person = responsible_persons[0]
            
            # Формируем контактную информацию ответственного лица
            responsible_info = ''
            if responsible_person:
                if isinstance(responsible_person, dict):
                    person_parts = []
                    
                    # Добавляем ФИО
                    if responsible_person.get('name'):
                        person_parts.append(responsible_person.get('name'))
                    
                    # Добавляем телефон
                    if responsible_person.get('phone'):
                        person_parts.append(f"тел: {responsible_person.get('phone')}")
                    
                    # Добавляем email
                    if responsible_person.get('email'):
                        person_parts.append(f"email: {responsible_person.get('email')}")
                    
                    if person_parts:
                        responsible_info = ', '.join(person_parts)
            
            # Формируем строку адреса с контактами ответственного лица
            if responsible_info:
                address_str = f"{address_str} ({responsible_info})"
            
            if address_str:
                address_lines.append(address_str)
        
        return '\n'.join(address_lines)
    
    def _format_date(self, date_value: Any) -> str:
        """Форматировать дату в читаемый формат"""
        if not date_value:
            return ''
        
        try:
            if isinstance(date_value, str):
                date_obj = datetime.strptime(date_value, '%Y-%m-%d').date()
            elif isinstance(date_value, date):
                date_obj = date_value
            else:
                return str(date_value)
            
            return date_obj.strftime('%d.%m.%Y')
        except Exception:
            return str(date_value)
    
    def _prepare_note(self, params: Dict[str, Any], counterparty_role: str) -> str:
        """
        Правило 2.9: Заполнить поле Заметка со всей информацией о контракте.
        
        В заметке необходимо указать:
        - Наименование и номер контракта, предмет контракта, дату его заключения, цену контракта и сумму единичных расценок
        - Организацию, с которой заключен контракт
        - Процент НДС или "Без НДС"
        - Состав услуг и их особенности
        - Срок оказания услуг
        - Порядок и сроки приема-сдачи услуг или поставки товаров
        - Порядок ценообразования и наличие спецификации
        - Дополнительные сведения для формирования цены
        - Порядок и формы первичных отчетных документов
        - Срок исполнения заявки и сроки плановых работ
        - Дополнительные сведения для исполнения контракта
        """
        note_parts = []
        
        # Наименование и номер контракта, предмет контракта, дата заключения, цена контракта
        contract_info_parts = []
        
        contract_name = params.get('contract_name')
        contract_number = params.get('contract_number')
        if contract_name or contract_number:
            contract_str = ''
            if contract_name:
                contract_str = contract_name
            if contract_number:
                if contract_str:
                    contract_str += f" № {contract_number}"
                else:
                    contract_str = f"Контракт № {contract_number}"
            contract_info_parts.append(contract_str)
        
        # Предмет контракта (описание услуг/товаров)
        service_description = params.get('service_description')
        if service_description:
            contract_info_parts.append(f"Предмет контракта: {service_description}")
        
        # Дата заключения
        contract_date = params.get('contract_date')
        if contract_date:
            date_str = self._format_date(contract_date)
            contract_info_parts.append(f"Дата заключения: {date_str}")
        
        # Цена контракта
        contract_price = params.get('contract_price')
        if contract_price:
            try:
                price_value = float(contract_price)
                price_str = f"{price_value:,.2f}".replace(',', ' ').replace('.', ',')
                contract_info_parts.append(f"Цена контракта: {price_str} руб.")
            except (ValueError, TypeError):
                contract_info_parts.append(f"Цена контракта: {contract_price}")
        
        # Сумма единичных расценок (если есть в данных)
        # Примечание: это поле может быть в спецификации, которое пока не извлекается отдельно
        # Можно добавить в будущем, если потребуется
        
        if contract_info_parts:
            note_parts.append('\n'.join(contract_info_parts))
        
        # Организация, с которой заключен контракт
        # Определяем противоположную сторону договора
        if counterparty_role:
            role_lower = str(counterparty_role).lower()
            if role_lower in ['поставщик', 'исполнитель', 'продавец']:
                # Если текущий контрагент - поставщик, то заказчик - организация, с которой заключен контракт
                customer = params.get('customer')
                if customer and isinstance(customer, dict):
                    customer_name = customer.get('full_name') or customer.get('short_name')
                    if customer_name:
                        note_parts.append(f"Организация, с которой заключен контракт: {customer_name}")
            elif role_lower in ['покупатель', 'заказчик']:
                # Если текущий контрагент - заказчик, то поставщик - организация, с которой заключен контракт
                contractor = params.get('contractor')
                if contractor and isinstance(contractor, dict):
                    contractor_name = contractor.get('full_name') or contractor.get('short_name')
                    if contractor_name:
                        note_parts.append(f"Организация, с которой заключен контракт: {contractor_name}")
        
        # НДС
        vat_percent = params.get('vat_percent')
        vat_type = params.get('vat_type')
        if vat_percent is not None:
            try:
                vat_value = float(vat_percent)
                if vat_value > 0:
                    note_parts.append(f"НДС: {vat_value}%")
                else:
                    note_parts.append("НДС: Без НДС")
            except (ValueError, TypeError):
                if vat_type:
                    vat_type_lower = str(vat_type).lower()
                    if 'без' in vat_type_lower or 'не облагается' in vat_type_lower:
                        note_parts.append("НДС: Без НДС")
                    else:
                        note_parts.append(f"НДС: {vat_type}")
        elif vat_type:
            vat_type_lower = str(vat_type).lower()
            if 'без' in vat_type_lower or 'не облагается' in vat_type_lower:
                note_parts.append("НДС: Без НДС")
            else:
                note_parts.append(f"НДС: {vat_type}")
        else:
            note_parts.append("НДС: Без НДС")
        
        # Состав услуг и их особенности
        if service_description:
            note_parts.append(f"Состав услуг: {service_description}")
        
        # Особенности услуг (могут быть в additional_conditions или technical_info)
        additional_conditions = params.get('additional_conditions')
        if additional_conditions:
            note_parts.append(f"Особенности услуг: {additional_conditions}")
        
        # Срок оказания услуг
        service_start_date = params.get('service_start_date')
        service_end_date = params.get('service_end_date')
        if service_start_date or service_end_date:
            service_period_parts = []
            if service_start_date:
                service_period_parts.append(f"с {self._format_date(service_start_date)}")
            if service_end_date:
                service_period_parts.append(f"по {self._format_date(service_end_date)}")
            if service_period_parts:
                note_parts.append(f"Срок оказания услуг: {' '.join(service_period_parts)}")
        
        # Порядок и сроки приема-сдачи услуг или поставки товаров
        acceptance_procedure = params.get('acceptance_procedure')
        if acceptance_procedure:
            note_parts.append(f"Порядок и сроки приема-сдачи услуг: {acceptance_procedure}")
        
        # Порядок ценообразования и наличие спецификации
        pricing_method = params.get('pricing_method')
        specification_exists = params.get('specification_exists')
        
        pricing_info_parts = []
        if pricing_method:
            pricing_info_parts.append(f"Порядок ценообразования: {pricing_method}")
        if specification_exists:
            pricing_info_parts.append("Спецификация: имеется")
        elif specification_exists is False:
            pricing_info_parts.append("Спецификация: отсутствует")
        
        if pricing_info_parts:
            note_parts.append('\n'.join(pricing_info_parts))
        
        # Дополнительные сведения для формирования цены
        # Могут быть в pricing_method или additional_conditions
        if pricing_method and 'дополнительно' in pricing_method.lower():
            note_parts.append(f"Дополнительные сведения для формирования цены: {pricing_method}")
        
        # Порядок и формы первичных отчетных документов
        reporting_forms = params.get('reporting_forms')
        if reporting_forms:
            reporting_text = f"Формы отчетности: {reporting_forms}"
            # Проверяем наличие нестандартных форм
            reporting_lower = str(reporting_forms).lower()
            if any(keyword in reporting_lower for keyword in ['нестандарт', 'индивидуальн', 'особ', 'специфич']):
                reporting_text += " (нестандартные/индивидуальные формы отчетности)"
            note_parts.append(reporting_text)
        
        # Срок исполнения заявки и сроки плановых работ
        task_execution_term = params.get('task_execution_term')
        if task_execution_term:
            note_parts.append(f"Срок исполнения заявки: {task_execution_term}")
        
        # Дополнительные сведения для исполнения контракта
        # (можно ли забирать технику в сервисный центр, нужно ли возвращать заменные запчасти и пр.)
        if additional_conditions:
            # Проверяем наличие специфических условий
            conditions_lower = str(additional_conditions).lower()
            execution_notes = []
            
            if any(keyword in conditions_lower for keyword in ['забирать', 'забрать', 'сервис', 'центр']):
                execution_notes.append("Можно забирать технику в сервисный центр")
            if any(keyword in conditions_lower for keyword in ['возврат', 'возвращать', 'запчаст']):
                execution_notes.append("Требуется возврат заменных запчастей")
            
            if execution_notes:
                note_parts.append(f"Дополнительные сведения для исполнения: {'; '.join(execution_notes)}")
            else:
                # Если есть дополнительные условия, но они не содержат специфических фраз, добавляем их как есть
                note_parts.append(f"Дополнительные условия исполнения: {additional_conditions}")
        
        # Услуги по договору (из спецификации/таблиц)
        services = params.get('services')
        if services and isinstance(services, list) and len(services) > 0:
            services_parts = ["Услуги по договору:"]
            for idx, service in enumerate(services, start=1):
                if isinstance(service, dict):
                    service_parts = []
                    service_name = service.get('name')
                    if service_name:
                        service_parts.append(f"{idx}. {service_name}")
                    
                    # Добавляем описание, если есть (ставим перед количеством и ценой для лучшей читаемости)
                    description = service.get('description')
                    if description:
                        # Если описание длинное, разбиваем на строки
                        desc_lines = description.split('. ')
                        if len(desc_lines) > 1:
                            service_parts.append(f"   {desc_lines[0]}.")
                            for line in desc_lines[1:]:
                                if line.strip():
                                    service_parts.append(f"   {line.strip()}{'.' if not line.strip().endswith('.') else ''}")
                        else:
                            service_parts.append(f"   {description}")
                    
                    # Добавляем количество и единицу измерения
                    quantity = service.get('quantity')
                    unit = service.get('unit')
                    if quantity is not None and str(quantity).strip() and str(quantity) != 'null':
                        try:
                            quantity_value = float(quantity)
                            if unit and str(unit).strip() and str(unit) != 'null':
                                service_parts.append(f"   Количество: {quantity_value} {unit}")
                            else:
                                service_parts.append(f"   Количество: {quantity_value}")
                        except (ValueError, TypeError):
                            if unit and str(unit).strip() and str(unit) != 'null':
                                service_parts.append(f"   Количество: {quantity} {unit}")
                            else:
                                service_parts.append(f"   Количество: {quantity}")
                    
                    # Добавляем цену за единицу
                    unit_price = service.get('unit_price')
                    if unit_price is not None and str(unit_price).strip() and str(unit_price) != 'null':
                        try:
                            price_value = float(unit_price)
                            price_str = f"{price_value:,.2f}".replace(',', ' ').replace('.', ',')
                            service_parts.append(f"   Цена за единицу: {price_str} руб.")
                        except (ValueError, TypeError):
                            service_parts.append(f"   Цена за единицу: {unit_price} руб.")
                    
                    # Добавляем общую стоимость
                    total_price = service.get('total_price')
                    if total_price is not None and str(total_price).strip() and str(total_price) != 'null':
                        try:
                            total_value = float(total_price)
                            total_str = f"{total_value:,.2f}".replace(',', ' ').replace('.', ',')
                            service_parts.append(f"   Общая стоимость: {total_str} руб.")
                        except (ValueError, TypeError):
                            service_parts.append(f"   Общая стоимость: {total_price} руб.")
                    
                    if service_parts:
                        services_parts.append('\n'.join(service_parts))
            
            if len(services_parts) > 1:  # Если есть хотя бы одна услуга
                note_parts.append('\n\n'.join(services_parts))
        
        # Объединяем все части заметки
        note = '\n\n'.join(note_parts)
        
        return note
    
    async def _create_counterparty(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создать нового контрагента согласно правилам 2.1-2.9.
        
        Правила заполнения полей:
        - 2.1: Определение роли (Поставщик/Покупатель)
        - 2.2: Определение Юр./физ. лица по ИНН
        - 2.3: Заполнение ИНН
        - 2.4: Заполнение КПП (только для ЮЛ)
        - 2.5: Полное наименование с ОПФ
        - 2.6: Определение Гос./Ком.
        - 2.7: Наименование с добавлениями (СПБ, ЕИС, срок)
        - 2.8: Адрес для служебного пользования
        - 2.9: Заметка и Техническая информация
        """
        params.pop('raw_text')
        logger.info("Create counterparty2", params=params)
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        # Логируем входные параметры для диагностики
        logger.info("Creating counterparty - received params",
                   has_inn=bool(params.get('inn')),
                   has_kpp=bool(params.get('kpp')),
                   has_full_name=bool(params.get('full_name')),
                   has_short_name=bool(params.get('short_name')),
                   has_organizational_form=bool(params.get('organizational_form')),
                   has_role=bool(params.get('role')),
                   has_locations=bool(params.get('locations')),
                   has_contract_name=bool(params.get('contract_name')),
                   has_contract_number=bool(params.get('contract_number')))
        
        inn = params.get('inn') or ''
        kpp = params.get('kpp')
        full_name = params.get('full_name') or ''
        short_name = params.get('short_name')
        organizational_form = params.get('organizational_form')
        role = params.get('role', '')
        legal_entity_type_param = params.get('legal_entity_type', '')
        
        # Правило 2.1: Определить роль контрагента (Поставщик/Покупатель)
        # Синонимы: Поставщик = Продавец = Исполнитель; Покупатель = Заказчик
        role_lower = str(role).lower() if role else ''
        is_supplier = any(keyword in role_lower for keyword in ['поставщик', 'продавец', 'исполнитель'])
        is_buyer = any(keyword in role_lower for keyword in ['покупатель', 'заказчик'])
        
        # Если роль не определена из role, используем is_supplier/is_buyer из params
        if not is_supplier and not is_buyer:
            is_supplier = params.get('is_supplier', False)
            is_buyer = params.get('is_buyer', False)
        
        # Если роль все еще не определена, пытаемся определить из данных customer/contractor
        if not is_supplier and not is_buyer:
            # Если есть данные customer и его ИНН совпадает с текущим ИНН, значит это покупатель
            customer = params.get('customer')
            contractor = params.get('contractor')
            
            if customer and isinstance(customer, dict) and customer.get('inn') == inn:
                is_buyer = True
                logger.info("Role determined from customer data: buyer", inn=inn)
            elif contractor and isinstance(contractor, dict) and contractor.get('inn') == inn:
                is_supplier = True
                logger.info("Role determined from contractor data: supplier", inn=inn)
            else:
                # По умолчанию считаем поставщиком
                is_supplier = True
                logger.warning("Role not determined, defaulting to supplier", inn=inn)
        
        # Правило 2.2: Определить Юр./физ. лицо на основе количества знаков ИНН
        legal_entity_type_1c = self._determine_legal_entity_type_by_inn(inn)
        
        # Если есть явное указание типа, используем его (но проверяем по ИНН)
        if legal_entity_type_param:
            legal_entity_type_normalized = legal_entity_type_param.replace(' ', '').lower()
            if 'физическое' in legal_entity_type_normalized or 'физлицо' in legal_entity_type_normalized:
                legal_entity_type_1c = 'ФизЛицо'
            elif 'юридическое' in legal_entity_type_normalized or 'юрлицо' in legal_entity_type_normalized:
                legal_entity_type_1c = 'ЮрЛицо'
        
        # Правило 2.3: Заполнить поле ИНН
        # Правило 2.4: Заполнить поле КПП (только для юридических лиц)
        kpp_value = ''
        if legal_entity_type_1c == 'ЮрЛицо' and kpp:
            kpp_value = kpp
        
        # Правило 2.5: Заполнить поле Полное наименование с ОПФ без сокращения
        full_name_with_opf = self._prepare_full_name(full_name, organizational_form)
        
        # Правило 2.6: Определить Гос./Ком.
        gov_com_type = self._determine_gov_com_type(organizational_form)
        
        # Правило 2.7: Заполнить поле Наименование (без ОПФ) с добавлением СПБ, ЕИС и срока услуг
        locations = params.get('locations')
        raw_text = params.get('raw_text')
        service_end_date = params.get('service_end_date')
        short_name_formatted = self._prepare_short_name(
            short_name, full_name, locations, raw_text, service_end_date
        )
        
        # Правило 2.8: Заполнить поле Адрес для служебного пользования
        responsible_persons = params.get('responsible_persons')
        service_address = self._prepare_service_address(locations, responsible_persons)
        
        # Правило 2.9: Заполнить поле Заметка
        note = self._prepare_note(params, role)
        
        # Правило 2.9: Заполнить поле Техническая информация
        technical_info = params.get('technical_info', '')
        
        # Подготовка данных для 1С с правильными названиями полей
        counterparty_data = {
            'ИНН': inn,
            'КПП': kpp_value,
            'Description': short_name_formatted or full_name_with_opf or '',
            'НаименованиеПолное': full_name_with_opf or short_name_formatted or '',
            'ЮрФизЛицо': legal_entity_type_1c,
            'Поставщик': is_supplier,
            'Покупатель': is_buyer,
            # 'Комментарий':'12345',
            # 'абсГосКом':'Гос'
        }
        
        # Добавляем поле Гос./Ком. если определено
        if gov_com_type:
            counterparty_data['абсГосКом'] = gov_com_type
        logger.info("Counterparty data", counterparty_data=counterparty_data)
        # Удаляем пустые значения, чтобы не отправлять их в 1С
        # Важно: не удаляем булевы False, только None и пустые строки
        counterparty_data = {k: v for k, v in counterparty_data.items() 
                           if not (v is None or (isinstance(v, str) and v == ''))}
        
        logger.info("Creating counterparty with prepared data",
                   inn=inn,
                   legal_entity_type=legal_entity_type_1c,
                   is_supplier=is_supplier,
                   is_buyer=is_buyer,
                   gov_com_type=gov_com_type,
                   has_service_address=bool(service_address),
                   has_note=bool(note),
                   has_technical_info=bool(technical_info),
                   counterparty_data_keys=list(counterparty_data.keys()),
                   description_value=counterparty_data.get('Description'),
                   full_name_value=counterparty_data.get('НаименованиеПолное'))
        
        # Выполнить OData запрос для создания
        result = await self.oneс_client.create_entity(
            'Catalog_Контрагенты',
            counterparty_data
        )
        
        counterparty_uuid = result.get('Ref_Key')
        
        # Создаем записи в информационном регистре для контактной информации
        
        # Правило 2.8: Создать запись "Адрес для служебного пользования"
        if service_address:
            try:
                # Записываем все подготовленные адреса в поле Представление
                # Контакты ответственных лиц уже включены в service_address через метод _prepare_service_address
                logger.info("Creating service address record",
                           counterparty_uuid=counterparty_uuid,
                           service_address=service_address)
                await self._create_contact_info_record(
                    counterparty_uuid=counterparty_uuid,
                    contact_type_uuid='85b3efa7-c818-11e1-9e33-001a4d45222a',  # Адрес для служебного пользования
                    representation=service_address,
                    comment=None,
                    fields=None,
                    contact_type='Адрес'  # Тип контактной информации согласно примеру
                )
            except Exception as e:
                logger.error("Failed to create service address record", 
                           error=str(e), 
                           counterparty_uuid=counterparty_uuid)
        
        # Правило 2.9: Создать запись "Заметка"
        if note:
            try:
                await self._create_contact_info_record(
                    counterparty_uuid=counterparty_uuid,
                    contact_type_uuid='0b03b064-f020-11e1-b31d-00138fb561aa',  # Заметка
                    representation=note,
                    comment=note,
                    note_type='Другое'  # Тип заметки согласно документации
                )
            except Exception as e:
                logger.error("Failed to create note record", 
                           error=str(e), 
                           counterparty_uuid=counterparty_uuid)
        
        # Правило 2.9: Создать запись "Техническая информация"
        if technical_info:
            try:
                await self._create_contact_info_record(
                    counterparty_uuid=counterparty_uuid,
                    contact_type_uuid='47ec1d67-3e72-11e4-82f5-d850e63fbd64',  # Техническая информация
                    representation=technical_info,
                    comment=technical_info
                )
            except Exception as e:
                logger.error("Failed to create technical info record", 
                           error=str(e), 
                           counterparty_uuid=counterparty_uuid)
        
        # Создаем договор после успешного создания контрагента
        # ВАЖНО: Создание договора обернуто в отдельный try-except блок,
        # чтобы ошибки при создании контактной информации не мешали созданию договора
        agreement_uuid = None
        agreement_error = None
        
        logger.info("Checking if should create agreement",
                   has_counterparty_uuid=bool(counterparty_uuid),
                   counterparty_uuid=counterparty_uuid)
        
        if counterparty_uuid:
            logger.info("Starting agreement creation process", counterparty_uuid=counterparty_uuid)
            # Задержка после создания контрагента, чтобы дать 1С время сохранить данные
            # Увеличена до 3 секунд для надежности
            await asyncio.sleep(3.0)
            
            # Проверка существования контрагента пропущена из-за проблем с форматом фильтра в 1C
            # Контрагент только что создан, поэтому продолжаем создание договора
            logger.info("Proceeding with agreement creation", counterparty_uuid=counterparty_uuid)
            try:
                # Подготавливаем данные для договора
                contract_name = params.get('contract_name')
                contract_number = params.get('contract_number')
                contract_date = params.get('contract_date')
                contract_price = params.get('contract_price')
                service_start_date = params.get('service_start_date')
                service_end_date = params.get('service_end_date')
                
                logger.info("Preparing agreement data",
                           has_contract_name=bool(contract_name),
                           has_contract_number=bool(contract_number),
                           has_contract_price=bool(contract_price),
                           has_service_dates=bool(service_start_date and service_end_date),
                           has_contract_date=bool(contract_date))
                
                # Формируем наименование договора в формате "Договор №... от ..."
                # Приоритет: номер + дата > только дата > базовое значение
                date_str = self._format_date(contract_date) if contract_date else ''

                # Всегда начинаем с "Договор"
                agreement_description = "Договор"
                if contract_number:
                    agreement_description = f"{agreement_description} №{contract_number}"
                if date_str:
                    agreement_description = f"{agreement_description} от {date_str}"

                logger.info("Formed agreement description",
                           agreement_description=agreement_description,
                           contract_number=contract_number,
                           contract_date=contract_date)
                
                # Определяем вид договора на основе роли
                agreement_type = 'СПокупателем' if is_buyer else 'СПоставщиком'
                
                # Рассчитываем допустимую сумму задолженности
                # ДопустимаяСуммаЗадолженности = Цена договора / Продолжительность договора в месяцах
                allowed_debt_amount = None
                if contract_price and service_start_date and service_end_date:
                    try:
                        price_value = float(contract_price)
                        if isinstance(service_start_date, str):
                            start_date = datetime.strptime(service_start_date, '%Y-%m-%d').date()
                        else:
                            start_date = service_start_date
                        
                        if isinstance(service_end_date, str):
                            end_date = datetime.strptime(service_end_date, '%Y-%m-%d').date()
                        else:
                            end_date = service_end_date
                        
                        # Вычисляем количество месяцев
                        months_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
                        if months_diff > 0:
                            allowed_debt_amount = price_value / months_diff
                            logger.info("Calculated allowed debt amount",
                                       price=price_value,
                                       months=months_diff,
                                       allowed_debt=allowed_debt_amount)
                    except Exception as e:
                        logger.warning("Failed to calculate allowed debt amount", error=str(e))
                
                # Получаем допустимое число дней задолженности из параметров
                allowed_debt_days = params.get('allowed_debt_days') or params.get('payment_deferral_days')
                
                # Форматируем срок действия
                term_date_iso = None
                if service_end_date:
                    if isinstance(service_end_date, str):
                        term_date = datetime.strptime(service_end_date, '%Y-%m-%d').date()
                    else:
                        term_date = service_end_date
                    # Преобразуем в формат ISO для 1С
                    term_date_iso = term_date.isoformat() + 'T00:00:00'
                elif contract_date:
                    # Если нет даты окончания услуг, используем дату контракта + 1 год
                    if isinstance(contract_date, str):
                        contract_date_obj = datetime.strptime(contract_date, '%Y-%m-%d').date()
                    else:
                        contract_date_obj = contract_date
                    # Добавляем 1 год к дате контракта (используем замену года)
                    term_date = contract_date_obj.replace(year=contract_date_obj.year + 1)
                    term_date_iso = term_date.isoformat() + 'T00:00:00'
                    logger.info("Using contract date + 1 year for agreement term", 
                               contract_date=contract_date_obj,
                               term_date=term_date)
                else:
                    # Если вообще нет дат, используем текущую дату + 1 год
                    from datetime import date as dt_date
                    today = dt_date.today()
                    term_date = today.replace(year=today.year + 1)
                    term_date_iso = term_date.isoformat() + 'T00:00:00'
                    logger.warning("No service or contract dates, using current date + 1 year",
                                  term_date=term_date)
                
                logger.info("Creating agreement for counterparty",
                           counterparty_uuid=counterparty_uuid,
                           description=agreement_description,
                           term=term_date_iso,
                           agreement_type=agreement_type,
                           has_price=bool(contract_price),
                           has_allowed_debt_amount=allowed_debt_amount is not None,
                           has_allowed_debt_days=allowed_debt_days is not None)
                agreement_data = {
                    'counterparty_uuid': counterparty_uuid,
                    'name': agreement_description,
                    'contract_number': contract_number,
                    'contract_date': contract_date,
                    'term': term_date_iso,
                    'price': contract_price,
                    'allowed_debt_amount': allowed_debt_amount,
                    'allowed_debt_days': allowed_debt_days,
                    'organization_uuid': params.get('organization_uuid'),
                    'agreement_type': agreement_type,
                    'is_supplier': is_supplier,
                    'is_buyer': is_buyer
                } 
                logger.info("Agreement data", agreement_data=agreement_data)
                agreement_result = await self._create_agreement(agreement_data)
                
                agreement_uuid = agreement_result.get('uuid')
                if agreement_uuid:
                    logger.info("Agreement created successfully", 
                               agreement_uuid=agreement_uuid,
                               counterparty_uuid=counterparty_uuid)
                else:
                    logger.warning("Agreement creation returned no UUID",
                                  agreement_result=agreement_result,
                                  counterparty_uuid=counterparty_uuid)
                
            except Exception as e:
                agreement_error = str(e)
                logger.error("Failed to create agreement - this is non-critical, counterparty was created successfully", 
                           error=agreement_error,
                           error_type=type(e).__name__,
                           counterparty_uuid=counterparty_uuid,
                           note="Agreement can be created manually later in 1C if needed",
                           exc_info=True)
                # НЕ прерываем выполнение - контрагент уже создан, договор можно создать позже
        else:
            logger.warning("Skipping agreement creation - no counterparty UUID")
        
        return {
            'created': True,
            'uuid': counterparty_uuid,
            'entity': result,
            'agreement_uuid': agreement_uuid,
            'agreement_error': agreement_error if agreement_error else None
        }
    
    async def _update_counterparty(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Обновить данные контрагента"""
        uuid = params.get('uuid')
        data = params.get('data')
        
        if not uuid or not data:
            raise ValueError("UUID and data are required")
        
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        result = await self.oneс_client.update_entity(
            'Catalog_Контрагенты',
            uuid,
            data
        )
        
        return {'updated': True, 'entity': result}
    
    async def _create_contact_info_record(self, counterparty_uuid: str, contact_type_uuid: str, 
                                          representation: str, comment: Optional[str] = None,
                                          fields: Optional[Dict[str, str]] = None,
                                          note_type: Optional[str] = None,
                                          contact_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Создать запись в информационном регистре InformationRegister_КонтактнаяИнформация
        
        Args:
            counterparty_uuid: UUID контрагента
            contact_type_uuid: UUID вида контактной информации
            representation: Текстовое представление
            comment: Комментарий (для заметки и технической информации)
            fields: Словарь с полями Поле1-Поле10 (для адреса)
            note_type: Тип заметки (например, "Другое" для заметки) - устаревший параметр, используйте contact_type
            contact_type: Тип контактной информации (например, "Адрес" для адресов)
            
        Returns:
            Dict с результатом создания записи
        """
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        contact_info_data = {
            'Объект': counterparty_uuid,
            'Объект_Type': 'StandardODATA.Catalog_Контрагенты',
            'Вид': contact_type_uuid,
            'Вид_Type': 'StandardODATA.Catalog_ВидыКонтактнойИнформации',
            'Представление': representation or ''
        }

        logger.info("Contact info data", contact_info_data=contact_info_data)
        
        # Добавляем тип контактной информации (приоритет у contact_type, затем note_type для обратной совместимости)
        if contact_type:
            contact_info_data['Тип'] = contact_type
        elif note_type:
            contact_info_data['Тип'] = note_type
        # Автоматическое определение типа для известных видов контактной информации
        elif contact_type_uuid == '85b3efa7-c818-11e1-9e33-001a4d45222a':  # Адрес для служебного пользования
            contact_info_data['Тип'] = 'Адрес'
        
        # Добавляем поля Поле1-Поле10 если есть
        if fields:
            for i in range(1, 11):
                field_name = f'Поле{i}'
                if field_name in fields:
                    contact_info_data[field_name] = fields[field_name]
        
        # Добавляем комментарий если есть
        if comment:
            contact_info_data['Комментарий'] = comment
        
        # Удаляем пустые значения (но не булевы False)
        contact_info_data = {k: v for k, v in contact_info_data.items() 
                            if not (v is None or (isinstance(v, str) and v == ''))}
        
        logger.info("Creating contact info record",
                   counterparty_uuid=counterparty_uuid,
                   contact_type_uuid=contact_type_uuid,
                   has_fields=bool(fields),
                   has_comment=bool(comment),
                   note_type=note_type,
                   contact_type=contact_type,
                   final_type=contact_info_data.get('Тип'))
        
        result = await self.oneс_client.create_entity(
            'InformationRegister_КонтактнаяИнформация',
            contact_info_data
        )
        
        return {
            'created': True,
            'uuid': result.get('Ref_Key'),
            'entity': result
        }
    
    async def _add_note(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Добавить заметку к контрагенту в информационном регистре InformationRegister_КонтактнаяИнформация
        После успешного создания заметки автоматически создается договор контрагента.
        
        Args:
            params: Параметры команды
                - counterparty_uuid (обязательный): UUID контрагента
                - note_text (обязательный): Текст заметки для поля "Представление"
                - comment (опциональный): Дополнительный комментарий для поля "Комментарий"
                - create_agreement (опциональный): Создавать ли договор после заметки (по умолчанию True)
                - agreement_description (опциональный): Описание договора
                - currency_key (опциональный): UUID валюты взаиморасчетов
                - organization_key (опциональный): UUID организации
                - agreement_type (опциональный): Вид договора (по умолчанию "Прочее")
                - и другие параметры для договора (см. _add_agreement)
                
        Returns:
            Dict с результатом создания записи заметки и договора (если создан)
        """
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")

        counterparty_uuid = params.get('counterparty_uuid')
        note_text = params.get('note_text')

        if not counterparty_uuid:
            raise ValueError("counterparty_uuid is required")

        # Если note_text не передан, но есть параметры контракта - формируем заметку через _prepare_note
        if not note_text:
            # Определяем роль контрагента для формирования заметки
            role = params.get('role', '')
            counterparty_role = role if role else 'Поставщик'  # По умолчанию

            # Формируем заметку из параметров контракта
            note_text = self._prepare_note(params, counterparty_role)

            if not note_text:
                raise ValueError("note_text is required or contract params must be provided to generate note")
        
        # Проверяем существование контрагента
        try:
            # Используем query_data для проверки существования контрагента
            # Формат фильтра: guid'uuid'
            result = await self.oneс_client.query_data(
                entity_set='Catalog_Контрагенты',
                filter_expr=f"Ref_Key eq guid'{counterparty_uuid}'",
                top=1
            )
            
            if not result or not result.get('value') or len(result['value']) == 0:
                raise ValueError(f"Counterparty with UUID {counterparty_uuid} not found")
            
            logger.info("Counterparty found, proceeding with note creation", 
                       counterparty_uuid=counterparty_uuid)
        except Exception as e:
            logger.error("Failed to verify counterparty existence", 
                        error=str(e), 
                        counterparty_uuid=counterparty_uuid)
            raise ValueError(f"Failed to verify counterparty: {str(e)}")
        
        # Создаем запись заметки
        comment = params.get('comment')
        
        try:
            note_result = await self._create_contact_info_record(
                counterparty_uuid=counterparty_uuid,
                contact_type_uuid='0b03b064-f020-11e1-b31d-00138fb561aa',  # UUID вида "Заметка"
                representation=note_text,
                comment=comment,
                note_type='Другое'  # Тип заметки согласно документации
            )
            
            logger.info("Note added successfully to counterparty",
                      counterparty_uuid=counterparty_uuid,
                      note_uuid=note_result.get('uuid'))
            
            # После успешного создания заметки создаем договор
            create_agreement = params.get('create_agreement', True)
            agreement_result = None
            agreement_error = None
            
            if create_agreement:
                try:
                    logger.info("Creating agreement after note creation",
                               counterparty_uuid=counterparty_uuid)
                    
                    # Подготавливаем параметры для создания договора
                    agreement_params = {
                        'counterparty_uuid': counterparty_uuid,
                    }
                    
                    # Копируем параметры договора из params, если они есть
                    agreement_params_to_copy = [
                        'description', 'agreement_description',
                        'currency_key', 'settlement_method', 'contract_conditions_type',
                        'control_debt_amount', 'control_debt_days', 'organization_key',
                        'price_type', 'agreement_type', 'contract_date'
                    ]
                    
                    for param_key in agreement_params_to_copy:
                        if param_key in params:
                            # Если есть agreement_description, используем его как description
                            if param_key == 'agreement_description':
                                agreement_params['description'] = params[param_key]
                            else:
                                agreement_params[param_key] = params[param_key]
                    
                    # Если description не указан, используем note_text как описание договора
                    if not agreement_params.get('description'):
                        agreement_params['description'] = note_text
                    
                    agreement_result = await self._add_agreement(agreement_params)
                    
                    logger.info("Agreement created successfully after note",
                               counterparty_uuid=counterparty_uuid,
                               agreement_uuid=agreement_result.get('uuid'))
                    
                except Exception as e:
                    agreement_error = str(e)
                    logger.error("Failed to create agreement after note - this is non-critical, note was created successfully", 
                               error=agreement_error,
                               error_type=type(e).__name__,
                               counterparty_uuid=counterparty_uuid,
                               note="Agreement can be created manually later in 1C if needed",
                               exc_info=True)
                    # НЕ прерываем выполнение - заметка уже создана
            
            # Формируем результат
            result = {
                'created': True,
                'uuid': note_result.get('uuid'),
                'entity': note_result.get('entity')
            }
            
            # Добавляем информацию о договоре, если он был создан
            if agreement_result:
                result['agreement_uuid'] = agreement_result.get('uuid')
                result['agreement_entity'] = agreement_result.get('entity')
            
            if agreement_error:
                result['agreement_error'] = agreement_error
            
            return result
            
        except Exception as e:
            logger.error("Failed to add note to counterparty",
                        error=str(e),
                        counterparty_uuid=counterparty_uuid,
                        exc_info=True)
            raise
    
    async def _add_agreement(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создать договор контрагента в справочнике Catalog_ДоговорыКонтрагентов
        
        Args:
            params: Параметры команды
                - counterparty_uuid (обязательный): UUID контрагента (используется как Owner_Key)
                - description (опциональный): Описание договора
                - currency_key (опциональный): UUID валюты взаиморасчетов (ВалютаВзаиморасчетов_Key)
                - settlement_method (опциональный): Способ ведения взаиморасчетов (по умолчанию "ПоДоговоруВЦелом")
                - contract_conditions_type (опциональный): Вид условий договора (по умолчанию "БезДополнительныхУсловий")
                - control_debt_amount (опциональный): Контролировать сумму задолженности (по умолчанию True)
                - control_debt_days (опциональный): Контролировать число дней задолженности (по умолчанию False)
                - organization_key (опциональный): UUID организации (если не указано, получается автоматически)
                - price_type (опциональный): UUID типа цен (по умолчанию "00000000-0000-0000-0000-000000000000")
                - agreement_type (опциональный): Вид договора (по умолчанию "Прочее")
                - contract_date (опциональный): Дата договора в формате ISO (по умолчанию "0001-01-01T00:00:00")
                
        Returns:
            Dict с результатом создания договора
        """
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        counterparty_uuid = params.get('counterparty_uuid')
        
        if not counterparty_uuid:
            raise ValueError("counterparty_uuid is required")
        
        # Проверяем существование контрагента
        try:
            result = await self.oneс_client.query_data(
                entity_set='Catalog_Контрагенты',
                filter_expr=f"Ref_Key eq guid'{counterparty_uuid}'",
                top=1
            )
            
            if not result or not result.get('value') or len(result['value']) == 0:
                raise ValueError(f"Counterparty with UUID {counterparty_uuid} not found")
            
            logger.info("Counterparty found, proceeding with agreement creation", 
                       counterparty_uuid=counterparty_uuid)
        except Exception as e:
            logger.error("Failed to verify counterparty existence", 
                        error=str(e), 
                        counterparty_uuid=counterparty_uuid)
            raise ValueError(f"Failed to verify counterparty: {str(e)}")
        
        # Подготавливаем данные договора
        agreement_data = {
            'Owner_Key': counterparty_uuid,
        }
        
        # Описание договора - всегда передается
        description = params.get('description', '')
        agreement_data['Description'] = description if description else 'Договор'
        
        # Валюта взаиморасчетов - всегда передается
        currency_key = params.get('currency_key', 'c45d9bed-280d-11de-a244-000b6ab59421')
        agreement_data['ВалютаВзаиморасчетов_Key'] = currency_key
        
        # Способ ведения взаиморасчетов - всегда передается
        settlement_method = params.get('settlement_method', 'ПоДоговоруВЦелом')
        agreement_data['ВедениеВзаиморасчетов'] = settlement_method
        
        # Вид условий договора - всегда передается
        contract_conditions_type = params.get('contract_conditions_type', 'БезДополнительныхУсловий')
        agreement_data['ВидУсловийДоговора'] = contract_conditions_type
        
        # Контроль суммы задолженности - всегда передается
        control_debt_amount = params.get('control_debt_amount', True)
        agreement_data['КонтролироватьСуммуЗадолженности'] = control_debt_amount
        
        # Контроль числа дней задолженности - всегда передается
        control_debt_days = params.get('control_debt_days', False)
        agreement_data['КонтролироватьЧислоДнейЗадолженности'] = control_debt_days
        
        # Обособленный учет товаров по заказам покупателей - всегда передается
        agreement_data['ОбособленныйУчетТоваровПоЗаказамПокупателей'] = False
        
        # Организация - обязательное поле
        organization_key = params.get('organization_key')
        if not organization_key:
            logger.info("Organization UUID not provided, fetching by code", code='000000006')
            organization_key = await self._get_organization_by_code('000000006')
        
        if organization_key:
            agreement_data['Организация_Key'] = organization_key
            logger.info("Organization UUID added to agreement", organization_uuid=organization_key)
        
        # Тип цен - всегда передается
        price_type = params.get('price_type', '00000000-0000-0000-0000-000000000000')
        agreement_data['ТипЦен'] = price_type
        agreement_data['ТипЦен_Type'] = 'StandardODATA.Catalog_ТипыЦенНоменклатуры'
        
        # Вид договора - всегда передается
        agreement_type = params.get('agreement_type', 'Прочее')
        agreement_data['ВидДоговора'] = agreement_type
        
        # Дата договора - всегда передается
        contract_date = params.get('contract_date', '0001-01-01T00:00:00')
        agreement_data['Дата'] = contract_date
        
        # Удаляем пустые значения (но не булевы False)
        agreement_data = {k: v for k, v in agreement_data.items() 
                         if not (v is None or (isinstance(v, str) and v == ''))}
        
        logger.info("Creating agreement for counterparty",
                   counterparty_uuid=counterparty_uuid,
                   agreement_data_keys=list(agreement_data.keys()),
                   has_organization='Организация_Key' in agreement_data)
        
        try:
            result = await self.oneс_client.create_entity(
                'Catalog_ДоговорыКонтрагентов',
                agreement_data
            )
            
            agreement_uuid = result.get('Ref_Key')
            logger.info("Agreement created successfully",
                       counterparty_uuid=counterparty_uuid,
                       agreement_uuid=agreement_uuid)
            
            return {
                'created': True,
                'uuid': agreement_uuid,
                'entity': result
            }
            
        except Exception as e:
            logger.error("Failed to create agreement for counterparty",
                        error=str(e),
                        counterparty_uuid=counterparty_uuid,
                        agreement_data_keys=list(agreement_data.keys()),
                        exc_info=True)
            raise
    
    async def _get_organization_by_code(self, code: str) -> str:
        """
        Получить UUID организации по коду.
        Если организация не найдена по коду, пытается получить первую организацию из списка.
        Если и это не удалось, возвращает UUID организации по умолчанию.
        
        Args:
            code: Код организации в 1С (например, "000000006")
            
        Returns:
            UUID организации (Ref_Key), всегда возвращает значение (либо найденное, либо по умолчанию)
        """
        # UUID организации по умолчанию
        DEFAULT_ORGANIZATION_UUID = 'fd72d6f7-07d6-11e2-a788-001d60b2ee3b'
        
        if not self.oneс_client:
            logger.error("1C client not initialized, cannot fetch organization, using default")
            return DEFAULT_ORGANIZATION_UUID
        
        try:
            logger.info("Querying organization by code", code=code, entity_set='Catalog_Организации')
            # Получаем организации без фильтра, так как 1С не поддерживает фильтрацию по Code через OData
            # Фильтруем на стороне клиента
            result = await self.oneс_client.query_data(
                entity_set='Catalog_Организации',
                top=100  # Получаем больше записей для поиска по коду
            )
            
            logger.info("Organization query result", 
                       has_result=result is not None,
                       has_value=result.get('value') if result else False,
                       value_count=len(result.get('value', [])) if result and result.get('value') else 0)
            
            # Ищем организацию по коду в полученных результатах
            if result and result.get('value'):
                for organization in result['value']:
                    if organization.get('Code') == code:
                        uuid = organization.get('Ref_Key')
                        logger.info("Organization found by code", code=code, uuid=uuid, organization_data=organization)
                        return uuid
                
                logger.warning("Organization not found by code in fetched results", code=code)
            
            # Если организация не найдена по коду, пробуем получить первую организацию из списка как fallback
            try:
                logger.info("Fetching first organization from list as fallback")
                fallback_result = await self.oneс_client.query_data(
                    entity_set='Catalog_Организации',
                    top=1,
                    order_by='Code'
                )
                
                if fallback_result and fallback_result.get('value') and len(fallback_result['value']) > 0:
                    organization = fallback_result['value'][0]
                    uuid = organization.get('Ref_Key')
                    org_code = organization.get('Code', 'N/A')
                    logger.info("Using first organization as fallback", 
                              uuid=uuid, 
                              code=org_code,
                              organization_data=organization)
                    return uuid
                else:
                    logger.warning("No organizations found in Catalog_Организации, using default UUID")
                    return DEFAULT_ORGANIZATION_UUID
            except Exception as fallback_error:
                logger.warning("Failed to get first organization as fallback, using default UUID", 
                           error=str(fallback_error),
                           error_type=type(fallback_error).__name__)
                return DEFAULT_ORGANIZATION_UUID
        except Exception as e:
            logger.error("Failed to get organization by code", 
                        code=code, 
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True)
            
            # Пробуем fallback даже при ошибке запроса по коду
            try:
                logger.info("Trying fallback after error")
                fallback_result = await self.oneс_client.query_data(
                    entity_set='Catalog_Организации',
                    top=1,
                    order_by='Code'
                )
                
                if fallback_result and fallback_result.get('value') and len(fallback_result['value']) > 0:
                    organization = fallback_result['value'][0]
                    uuid = organization.get('Ref_Key')
                    org_code = organization.get('Code', 'N/A')
                    logger.info("Using first organization as fallback after error", 
                              uuid=uuid, 
                              code=org_code)
                    return uuid
            except Exception as fallback_error:
                logger.warning("Fallback also failed, using default UUID", error=str(fallback_error))
            
            logger.info("Using default organization UUID", default_uuid=DEFAULT_ORGANIZATION_UUID)
            return DEFAULT_ORGANIZATION_UUID
    
    async def _create_agreement(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создать договор контрагента согласно правилам 2.10.
        
        Правила заполнения полей:
        - 2.10.1: Наименование с датой заключения
        - 2.10.3: Срок действия (равен сроку оказания услуг)
        - 2.10.4: Взаиморасчеты ведутся = "ПоДоговоруВЦелом"
        - 2.10.5: Вести по документам расчетов с контрагентом = true
        - 2.10.6: Контролировать сумму задолженности с расчетом допустимой суммы
        - 2.10.7: Контролировать число дней задолженности
        """
        logger.info("Create agreement3", params=params)
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        counterparty_uuid = params.get('counterparty_uuid')
        if not counterparty_uuid:
            raise ValueError("counterparty_uuid is required")
        
        # Получаем данные контракта
        contract_name = params.get('contract_name') or params.get('name') or ''
        contract_number = params.get('contract_number')
        contract_date = params.get('contract_date')
        contract_price = params.get('contract_price') or params.get('price')
        service_start_date = params.get('service_start_date')
        service_end_date = params.get('service_end_date')
        payment_terms = params.get('payment_terms')
        
        # Правило 2.10.1: Наименование договора в формате "Договор №... от ..."
        date_str = self._format_date(contract_date) if contract_date else ''

        # Всегда начинаем с "Договор"
        agreement_description = "Договор"
        if contract_number:
            agreement_description = f"{agreement_description} №{contract_number}"
        if date_str:
            agreement_description = f"{agreement_description} от {date_str}"
        
        # Правило 2.10.3: Срок действия (срок оказания услуг или поставки товаров)
        term_date = params.get('term')
        if not term_date and service_end_date:
            # Если срок действия не указан, но есть дата окончания услуг, используем её
            if isinstance(service_end_date, str):
                term_date_obj = datetime.strptime(service_end_date, '%Y-%m-%d').date()
            else:
                term_date_obj = service_end_date
            term_date = term_date_obj.isoformat() + 'T00:00:00'
        
        # Правило 2.10.4: Взаиморасчеты ведутся
        settlement_method = 'ПоДоговоруВЦелом'
        
        # Правило 2.10.5: Вести по документам расчетов с контрагентом
        track_by_documents = True
        
        # Правило 2.10.6: Контролировать сумму задолженности
        # Рассчитываем допустимую сумму = цена контракта / продолжительность в месяцах
        control_debt_amount = True  # Всегда True
        allowed_debt_amount = params.get('allowed_debt_amount')
        
        # Если допустимая сумма не указана, рассчитываем из цены и продолжительности
        if allowed_debt_amount is None and contract_price and service_start_date and service_end_date:
            try:
                price_value = float(contract_price)
                if isinstance(service_start_date, str):
                    start_date = datetime.strptime(service_start_date, '%Y-%m-%d').date()
                else:
                    start_date = service_start_date
                
                if isinstance(service_end_date, str):
                    end_date = datetime.strptime(service_end_date, '%Y-%m-%d').date()
                else:
                    end_date = service_end_date
                
                # Вычисляем количество месяцев
                months_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
                if months_diff > 0:
                    allowed_debt_amount = price_value / months_diff
                    logger.info("Calculated allowed debt amount from contract price",
                               price=price_value,
                               months=months_diff,
                               allowed_debt=allowed_debt_amount)
            except Exception as e:
                logger.warning("Failed to calculate allowed debt amount", error=str(e))
        
        # Правило 2.10.7: Контролировать число дней задолженности
        # Извлекаем количество дней отсрочки из payment_terms или используем значение из параметров
        allowed_debt_days = params.get('allowed_debt_days') or params.get('payment_deferral_days')
        control_debt_days = False
        
        # Пытаемся извлечь дни отсрочки из payment_terms
        if not allowed_debt_days and payment_terms:
            import re
            # Ищем паттерны типа "отсрочка X дней", "X дней отсрочки", "отсрочка X", "X дней"
            patterns = [
                r'отсрочка\s+(\d+)\s+дн',
                r'(\d+)\s+дн[еяй]?\s+отсроч',
                r'отсрочка\s+(\d+)',
                r'(\d+)\s+дн[еяй]?\s+оплат',
            ]
            payment_terms_str = str(payment_terms) if payment_terms else ''
            for pattern in patterns:
                match = re.search(pattern, payment_terms_str.lower())
                if match:
                    try:
                        allowed_debt_days = int(match.group(1))
                        logger.info("Extracted deferral days from payment_terms",
                                   payment_terms=payment_terms,
                                   days=allowed_debt_days)
                        break
                    except (ValueError, IndexError):
                        continue
        
        # Если найдены дни отсрочки, включаем контроль
        if allowed_debt_days is not None:
            try:
                allowed_debt_days = int(allowed_debt_days)
                if allowed_debt_days > 0:
                    control_debt_days = True
            except (ValueError, TypeError):
                logger.warning("Invalid allowed_debt_days value", value=allowed_debt_days)
                allowed_debt_days = None
        
        # Определяем вид договора на основе роли
        agreement_type = params.get('agreement_type')
        logger.debug("Agreement type", agreement_type=agreement_type)
     
     
        is_supplier = params.get('is_supplier', False)
        is_buyer = params.get('is_buyer', False)
        if is_buyer:
            agreement_type = 'СПокупателем'
        elif is_supplier:
            agreement_type = 'СПоставщиком'
        else:
            agreement_type = 'СПокупателем'  # По умолчанию
        
        # Подготавливаем данные договора
        # Все обязательные поля передаются всегда
        agreement_data = {
            'Owner_Key': counterparty_uuid,
            'ВидДоговора': agreement_type,
        }
        
        # Правило 2.10.1: Наименование (Description) - наименование контракта и дата заключения
        agreement_data['Description'] = agreement_description if agreement_description else "Договор"
        
        # Правило 2.10.2: Цена договора (если поле существует в 1С)
        # Примечание: поле может отсутствовать в OData метаданных, но попробуем добавить
        if contract_price:
            try:
                price_value = float(contract_price)
                # Пробуем разные возможные названия поля
                # Если поле не существует, 1С проигнорирует его
                agreement_data['ЦенаДоговора'] = price_value
            except (ValueError, TypeError):
                logger.warning("Invalid contract_price value", value=contract_price)
        
        # Правило 2.10.3: Срок действия - срок оказания услуг или поставки товаров
        if term_date:
            agreement_data['СрокДействия'] = term_date
        
        # Правило 2.10.4: Взаиморасчеты ведутся - "По договору в целом"
        agreement_data['ВедениеВзаиморасчетов'] = settlement_method
        
        # Правило 2.10.5: Вести по документам расчетов с контрагентами
        agreement_data['ВестиПоДокументамРасчетовСКонтрагентом'] = track_by_documents
        
        # Правило 2.10.6: Контролировать сумму задолженности
        # Значение = среднемесячная ожидаемая выручка (цена контракта / продолжительность в месяцах)
        agreement_data['КонтролироватьСуммуЗадолженности'] = control_debt_amount
        if control_debt_amount and allowed_debt_amount is not None:
            try:
                agreement_data['ДопустимаяСуммаЗадолженности'] = float(allowed_debt_amount)
            except (ValueError, TypeError):
                logger.warning("Invalid allowed_debt_amount value", value=allowed_debt_amount)
        
        # Правило 2.10.7: Контролировать число дней задолженности
        # Значение = количество календарных дней отсрочки из контракта
        agreement_data['КонтролироватьЧислоДнейЗадолженности'] = control_debt_days
        if control_debt_days and allowed_debt_days is not None:
            try:
                agreement_data['ДопустимоеЧислоДнейЗадолженности'] = int(allowed_debt_days)
            except (ValueError, TypeError):
                logger.warning("Invalid allowed_debt_days value", value=allowed_debt_days)
        
        # Валюта взаиморасчетов - всегда передается
        currency_key = params.get('currency_key', 'c45d9bed-280d-11de-a244-000b6ab59421')
        agreement_data['ВалютаВзаиморасчетов_Key'] = currency_key
        
        # Вид условий договора - всегда передается
        agreement_data['ВидУсловийДоговора'] = 'БезДополнительныхУсловий'
        
        # Обособленный учет товаров по заказам покупателей - всегда передается
        agreement_data['ОбособленныйУчетТоваровПоЗаказамПокупателей'] = False
        
        # Тип цен - всегда передается
        price_type = params.get('price_type', '00000000-0000-0000-0000-000000000000')
        agreement_data['ТипЦен'] = price_type
        agreement_data['ТипЦен_Type'] = 'StandardODATA.Catalog_ТипыЦенНоменклатуры'
        
        # Дата договора - всегда передается
        contract_date_iso = '0001-01-01T00:00:00'
        if contract_date:
            if isinstance(contract_date, str):
                try:
                    contract_date_obj = datetime.strptime(contract_date, '%Y-%m-%d').date()
                    contract_date_iso = contract_date_obj.isoformat() + 'T00:00:00'
                except ValueError:
                    pass
            else:
                contract_date_iso = contract_date.isoformat() + 'T00:00:00'
        agreement_data['Дата'] = contract_date_iso
        
        # Добавляем организацию - обязательное поле
        # Сначала проверяем, указана ли организация в параметрах
        organization_uuid = params.get('organization_uuid')
        logger.info("Checking organization UUID", 
                   provided_in_params=organization_uuid is not None,
                   organization_uuid_from_params=organization_uuid)
        
        # Если не указана, получаем организацию с кодом "000000006" (обязательная организация)
        if not organization_uuid:
            logger.info("Organization UUID not provided in params, fetching by code", code='000000006')
            organization_uuid = await self._get_organization_by_code('000000006')
            logger.info("Organization UUID fetched", 
                       found=organization_uuid is not None,
                       organization_uuid=organization_uuid)
        
        if organization_uuid:
            agreement_data['Организация_Key'] = organization_uuid
            logger.info("Organization UUID added to agreement", organization_uuid=organization_uuid)
        
        # Удаляем пустые значения (но не булевы False)
        agreement_data = {k: v for k, v in agreement_data.items() 
                         if not (v is None or (isinstance(v, str) and v == ''))}
        
        # Логируем финальные данные для отладки
        logger.info("Agreement data prepared",
                   agreement_data_keys=list(agreement_data.keys()),
                   has_description='Description' in agreement_data,
                   description_value=agreement_data.get('Description'),
                   term_date=agreement_data.get('СрокДействия'),
                   agreement_type=agreement_data.get('ВидДоговора'),
                   settlement_method=agreement_data.get('ВедениеВзаиморасчетов'),
                   has_organization='Организация_Key' in agreement_data,
                   organization_uuid=agreement_data.get('Организация_Key'),
                   track_by_documents=agreement_data.get('ВестиПоДокументамРасчетовСКонтрагентом'),
                   control_debt_amount=agreement_data.get('КонтролироватьСуммуЗадолженности'),
                   control_debt_days=agreement_data.get('КонтролироватьЧислоДнейЗадолженности'),
                   full_agreement_data=agreement_data)
        
        logger.info("Creating agreement",
                   counterparty_uuid=counterparty_uuid,
                   agreement_type=agreement_type,
                   has_allowed_debt_amount=allowed_debt_amount is not None,
                   has_allowed_debt_days=allowed_debt_days is not None)
        
        try:
            result = await self.oneс_client.create_entity(
                'Catalog_ДоговорыКонтрагентов',
                agreement_data
            )
        except Exception as e:
            # Если не удалось создать с полным набором полей, пробуем минимальный набор
            error_msg = str(e)
            logger.warning("Failed to create agreement with full data, trying minimal set",
                          error=error_msg,
                          full_data_keys=list(agreement_data.keys()))
            
            # Пробуем создать с минимальным набором обязательных полей
            minimal_data = {
                'Owner_Key': counterparty_uuid,
                'ВидДоговора': agreement_type,
                'Description': agreement_description.strip() if agreement_description and agreement_description.strip() else "Договор",
                'ВалютаВзаиморасчетов_Key': params.get('currency_key', 'c45d9bed-280d-11de-a244-000b6ab59421'),
                'ВедениеВзаиморасчетов': settlement_method,
                'ВидУсловийДоговора': 'БезДополнительныхУсловий',
                'КонтролироватьСуммуЗадолженности': control_debt_amount,
                'КонтролироватьЧислоДнейЗадолженности': control_debt_days,
                'ОбособленныйУчетТоваровПоЗаказамПокупателей': False,
                'ТипЦен': params.get('price_type', '00000000-0000-0000-0000-000000000000'),
                'ТипЦен_Type': 'StandardODATA.Catalog_ТипыЦенНоменклатуры',
                'Дата': params.get('contract_date', '0001-01-01T00:00:00'),
            }
            
            # Добавляем обязательное поле Организация_Key если оно было получено
            if organization_uuid:
                minimal_data['Организация_Key'] = organization_uuid
            
            logger.info("Trying to create agreement with minimal data",
                       minimal_data_keys=list(minimal_data.keys()),
                       has_organization='Организация_Key' in minimal_data)
            
            try:
                result = await self.oneс_client.create_entity(
                    'Catalog_ДоговорыКонтрагентов',
                    minimal_data
                )
                logger.info("Successfully created agreement with minimal data")
            except Exception as e2:
                # Если и минимальный набор не сработал, пробуем добавить срок действия
                logger.warning("Failed to create agreement with minimal data, trying with term date",
                              error=str(e2),
                              minimal_data_keys=list(minimal_data.keys()))
                
                # Добавляем срок действия
                if term_date:
                    minimal_data['СрокДействия'] = term_date
                
                logger.info("Trying to create agreement with term date",
                           minimal_data_keys=list(minimal_data.keys()))
                
                try:
                    result = await self.oneс_client.create_entity(
                        'Catalog_ДоговорыКонтрагентов',
                        minimal_data
                    )
                    logger.info("Successfully created agreement with term date")
                except Exception as e3:
                    # Последняя попытка - только Owner_Key и Организация_Key
                    logger.warning("Failed to create agreement with term date, trying absolute minimal",
                                 error=str(e3))
                    
                    absolute_minimal = {
                        'Owner_Key': counterparty_uuid,
                        'Description': agreement_description.strip() if agreement_description and agreement_description.strip() else "Договор",
                        'ВалютаВзаиморасчетов_Key': params.get('currency_key', 'c45d9bed-280d-11de-a244-000b6ab59421'),
                        'ВедениеВзаиморасчетов': settlement_method,
                        'ВидУсловийДоговора': 'БезДополнительныхУсловий',
                        'КонтролироватьСуммуЗадолженности': control_debt_amount,
                        'КонтролироватьЧислоДнейЗадолженности': control_debt_days,
                        'ОбособленныйУчетТоваровПоЗаказамПокупателей': False,
                        'Организация_Key': organization_uuid if organization_uuid else 'fd72d6f7-07d6-11e2-a788-001d60b2ee3b',
                        'ТипЦен': params.get('price_type', '00000000-0000-0000-0000-000000000000'),
                        'ТипЦен_Type': 'StandardODATA.Catalog_ТипыЦенНоменклатуры',
                        'ВидДоговора': agreement_type,
                        'Дата': params.get('contract_date', '0001-01-01T00:00:00'),
                    }
                    
                    logger.info("Trying to create agreement with absolute minimal data",
                               absolute_minimal_keys=list(absolute_minimal.keys()))
                    
                    try:
                        result = await self.oneс_client.create_entity(
                            'Catalog_ДоговорыКонтрагентов',
                            absolute_minimal
                        )
                        logger.info("Successfully created agreement with absolute minimal data")
                    except Exception as e4:
                        # Если все попытки не удались, пробрасываем исходную ошибку
                        logger.error("All attempts to create agreement failed",
                                   original_error=error_msg,
                                   minimal_error=str(e2),
                                   with_term_error=str(e3),
                                   absolute_minimal_error=str(e4),
                                   organization_uuid=organization_uuid,
                                   has_organization_in_all_attempts=True,
                                   note="This may be a 1C business logic issue or missing required fields")
                        raise e
        
        return {
            'created': True,
            'uuid': result.get('Ref_Key'),
            'entity': result
        }
    
    async def _attach_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Прикрепить файл к контрагенту или договору
        
        Параметры:
            - counterparty_uuid (обязательный): UUID контрагента
            - file_path (обязательный): Путь к файлу
            - file_name (опциональный): Имя файла (если не указано, берется из file_path)
            - agreement_uuid (опциональный): UUID договора - если указан, файл прикрепляется к договору,
                                             иначе к контрагенту
        """
        
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        counterparty_uuid = params.get('counterparty_uuid')
        agreement_uuid = params.get('agreement_uuid')
        file_path = params.get('file_path')
        file_name = params.get('file_name')
        
        if not file_path:
            raise ValueError("file_path is required")
        
        # Если указан agreement_uuid, прикрепляем к договору, иначе к контрагенту
        if agreement_uuid:
            entity_uuid = agreement_uuid
            entity_type = 'Catalog_ДоговорыКонтрагентов'
            object_type = 'StandardODATA.Catalog_ДоговорыКонтрагентов'
            logger.info("Attaching file to agreement",
                       agreement_uuid=agreement_uuid,
                       counterparty_uuid=counterparty_uuid)
        elif counterparty_uuid:
            entity_uuid = counterparty_uuid
            entity_type = 'Catalog_Контрагенты'
            object_type = 'StandardODATA.Catalog_Контрагенты'
            logger.info("Attaching file to counterparty",
                       counterparty_uuid=counterparty_uuid)
        else:
            raise ValueError("Either counterparty_uuid or agreement_uuid is required")
        
        # Нормализуем путь к файлу
        import os
        from pathlib import Path
        
        # Если путь относительный, пробуем разные варианты
        if not os.path.isabs(file_path):
            # Пробуем относительно текущей директории
            if os.path.exists(file_path):
                normalized_path = file_path
            # Пробуем относительно /app/storage (в Docker контейнере)
            elif os.path.exists(f"/app/storage/contracts/{file_path.split('storage/contracts/')[-1] if 'storage/contracts/' in file_path else file_path}"):
                normalized_path = f"/app/storage/contracts/{file_path.split('storage/contracts/')[-1] if 'storage/contracts/' in file_path else file_path}"
            # Пробуем извлечь имя файла из пути и найти в storage
            else:
                file_basename = Path(file_path).name
                storage_paths = [
                    f"/app/storage/contracts/uploaded/{file_basename}",
                    f"/app/storage/contracts/processed/{file_basename}",
                    f"./storage/contracts/uploaded/{file_basename}",
                    f"./storage/contracts/processed/{file_basename}",
                ]
                normalized_path = None
                for sp in storage_paths:
                    if os.path.exists(sp):
                        normalized_path = sp
                        break
                
                if not normalized_path:
                    raise ValueError(f"File not found: {file_path}. Tried: {storage_paths}")
        else:
            normalized_path = file_path
        
        # Прочитать файл
        try:
            with open(normalized_path, 'rb') as f:
                file_data = f.read()
            logger.info("File read successfully", 
                       original_path=file_path,
                       normalized_path=normalized_path,
                       file_size=len(file_data))
        except Exception as e:
            raise ValueError(f"Failed to read file: {str(e)}")
        
        # Определяем имя файла
        if not file_name:
            file_name = Path(normalized_path).name
        
        # Прикрепить к хранилищу дополнительной информации
        result = await self.oneс_client.attach_file(
            entity_type,
            entity_uuid,
            file_name,
            file_data,
            object_type=object_type
        )
        
        return {'attached': True, 'result': result}
    
    async def _get_one_counterparty(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Получить одного контрагента из 1С (первого из списка)"""
        
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        # Выполнить OData запрос к 1С для получения первого контрагента
        query = "Catalog_Контрагенты?$top=1"
        result = await self.oneс_client.execute_query(query)
        
        if result and len(result.get('value', [])) > 0:
            counterparty = result['value'][0]
            return {
                'found': True,
                'uuid': counterparty.get('Ref_Key'),
                'data': counterparty
            }
        return {'found': False, 'message': 'No counterparties found in 1C'}


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from client.oneс_client import OneCClient

    from dotenv import load_dotenv
    load_dotenv()

    # Загрузка конфигурации из переменных окружения
    config = {
        'ONEС_ODATA_URL': os.getenv('ONEС_ODATA_URL', ''),
        'ONEС_USERNAME': os.getenv('ONEС_USERNAME', ''),
        'ONEС_PASSWORD': os.getenv('ONEС_PASSWORD', ''),
    }
    # print(config)
    server = MCPServer(config)
    if config.get('ONEС_ODATA_URL'):
        server.oneс_client = OneCClient(config)
        
    else:
        logger.warning("ONEС_ODATA_URL not configured, skipping client initialization")
        
    # async def main():
    #     # Добавляем родительскую директорию в путь для импортов
    #     await server.oneс_client.initialize()
        
    #     # Инициализация клиента 1С только если URL настроен
       
    #     result = await server._get_organization_by_code('000000006')
    #     print(result)
        
    #     # Закрытие клиента при завершении
    #     if server.oneс_client:
    #         await server.oneс_client.close()

    async def main2():
        await server.oneс_client.initialize()
        # params = {
        #     "counterparty_uuid": "c2b6ec5b-fd1d-11f0-9d06-7085c2496eb6",
        #     "name": "Agreement №03453000125240003140001 dated 01.01.2024",
        #     "term": "2026-03-01T00:00:00",
        #     "price": 1500000,
        #     "allowed_debt_amount": None,
        #     "allowed_debt_days": None,
        #     "organization_uuid": None,
        #     "agreement_type": "WithBuyer",
        #     "is_supplier": False,
        #     "is_buyer": True
        # }
        # result = await server._create_agreement(params)
        # print(result)
        params= {
            "inn": "4720016318",
            "kpp": "472501002",
            "full_name": "Государственное бюджетное учреждение здравоохранения Ленинградской области  ЛОМОНОСОВСКАЯ МЕЖРАЙОННАЯ БОЛЬНИЦА ИМ.И.Н.ЮДЧЕНКО",
            "short_name": "ГБУЗ ЛО «Ломоносовская МБ»",
            "legal_entity_type": "Юридическое лицо",
            "organizational_form": "Государственное бюджетное учреждение",
            "role": "Заказчик",
            "is_supplier": False,
            "is_buyer": True,
            "locations": [
            {
                "city": "Ломоносов",
                "region": "Ленинградская область",
                "address": "г. Ломоносов , ул. Еленинская, 13",
                "postal_code": "198412"
            }
            ],
            "responsible_persons": [
            {
                "name": "Усов Сергей Борисович",
                "email": "nach-snab@lmnmed.ru",
                "phone": "8(812)679-47-88",
                "position": "Главный врач"
            },
            {
                "name": "Блинов Константин Михайлович",
                "email": "info@zapravka39.ru",
                "phone": "74012666636",
                "position": "Генеральный директор"
            }
            ],
            "service_start_date": None,
            "service_end_date": None,
            "contract_name": "Контракт",
            "contract_number": "03453000125240003140001",
            "contract_date": "2024-01-01",
            "contract_price": 1500000,
            "vat_percent": None,
            "vat_type": None,
            "service_description": None,
            "services": [
            {
                "name": "Услуга по ремонту и техническому обслуживанию оргтехники",
                "unit": None,
                "quantity": None,
                "unit_price": None,
                "description": "Диагностика предоставленного Заказчиком оборудования, его разборка, профилактические работы по очистке от: пыли, тонера и иных загрязнений, замену вышедших из строя или выработавших свой ресурс деталей, сборку, тестовую проверку.",
                "total_price": None
            },
            {
                "name": "Услуга по заправке картриджей",
                "unit": None,
                "quantity": None,
                "unit_price": None,
                "description": "Разборка, чистка всех его компонентов, заполнение тонерного отделения тонером соответствующей марки, замену вышедших из строя комплектующих и последующую сборку.",
                "total_price": None
            }
            ],
            "acceptance_procedure": "Исполнитель обязан своевременно предоставлять достоверную информацию о ходе исполнения своих обязательств.",
            "specification_exists": False,
            "pricing_method": None,
            "reporting_forms": None,
            "additional_conditions": None,
            "technical_info": None,
            "task_execution_term": None,
            "customer": {
            "inn": "4720016318",
            "kpp": "472501002",
            "full_name": "Государственное бюджетное учреждение здравоохранения Ленинградской области  ЛОМОНОСОВСКАЯ МЕЖРАЙОННАЯ БОЛЬНИЦА ИМ.И.Н.ЮДЧЕНКО",
            "short_name": "ГБУЗ ЛО «Ломоносовская МБ»",
            "legal_entity_type": "Юридическое лицо",
            "organizational_form": "Государственное бюджетное учреждение"
            },
            "contractor": {
            "inn": "3904090275",
            "kpp": "390601001",
            "full_name": "Общество с ограниченной ответственностью «Идеальный магазин»",
            "short_name": "ООО «Идеальный магазин»",
            "legal_entity_type": "Юридическое лицо",
            "organizational_form": "Общество с ограниченной ответственностью"
            },
            "organization_uuid": None,
            "allowed_debt_days": None,
            "payment_terms": "Оплата по настоящему Контракту производится Заказчиком без авансирования за фактически оказанные услуги в срок не более семи рабочих дней с даты подписания.",
            'raw_text': None
        }
  
        result = await server._create_counterparty(params)
    asyncio.run(main2())