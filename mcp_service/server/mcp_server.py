"""
MCP Server для взаимодействия с 1С через SSE
"""
import asyncio
import json
import structlog
from typing import Dict, Any, Optional
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
            return await self._create_agreement(params)
        
        elif command == 'attach_file':
            return await self._attach_file(params)
        
        elif command == 'get_one_counterparty':
            return await self._get_one_counterparty(params)
        
        else:
            raise ValueError(f"Unknown command: {command}")
    
    async def _check_counterparty(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Проверить наличие контрагента по ИНН"""
        inn = params.get('inn')
        if not inn:
            raise ValueError("INN is required")
        
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        # В некоторых конфигурациях 1С фильтрация по ИНН через OData не разрешена
        # Поэтому получаем все контрагенты и фильтруем на стороне клиента
        # Используем $top для ограничения количества (если нужно)
        try:
            # Пробуем сначала с фильтром (может работать в некоторых конфигурациях)
            query = f"Catalog_Контрагенты?$filter=ИНН eq '{inn}'"
            result = await self.oneс_client.execute_query(query)
            
            if result and len(result.get('value', [])) > 0:
                counterparty = result['value'][0]
                return {
                    'found': True,
                    'uuid': counterparty.get('Ref_Key'),
                    'data': counterparty
                }
        except Exception as e:
            # Если фильтрация не работает, получаем все контрагенты и ищем локально
            logger.warning("Filter query failed, trying to fetch all and filter locally", 
                         error=str(e), inn=inn)
            
            try:
                # Получаем все контрагенты (можно ограничить через $top если их много)
                query = "Catalog_Контрагенты?$top=1000"
                result = await self.oneс_client.execute_query(query)
                
                if result and result.get('value'):
                    # Ищем контрагента с нужным ИНН
                    for counterparty in result['value']:
                        counterparty_inn = counterparty.get('ИНН')
                        # Проверяем, что ИНН не пустой и совпадает
                        if counterparty_inn and counterparty_inn.strip() and counterparty_inn == inn:
                            return {
                                'found': True,
                                'uuid': counterparty.get('Ref_Key'),
                                'data': counterparty
                            }
            except Exception as e2:
                logger.error("Failed to check counterparty", error=str(e2), inn=inn)
                raise
        
        return {'found': False}
    
    async def _create_counterparty(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Создать нового контрагента"""
        
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        # Подготовить данные для 1С
        # Маппинг legal_entity_type для поля ЮрФизЛицо в 1С
        # В разных конфигурациях 1С могут использоваться разные значения перечисления
        legal_entity_type_1c = 'ЮрЛицо'  # значение по умолчанию (короткая форма)
        legal_entity_type_param = params.get('legal_entity_type', '')
        if legal_entity_type_param:
            # Нормализуем значение и маппим на значения перечисления в 1С
            legal_entity_type_normalized = legal_entity_type_param.replace(' ', '').lower()
            
            # Проверяем различные варианты значений
            if 'юридическое' in legal_entity_type_normalized or 'юрлицо' in legal_entity_type_normalized:
                # Пробуем разные варианты значений для юридического лица
                # В некоторых конфигурациях используется "ЮрЛицо", в других "ЮридическоеЛицо"
                legal_entity_type_1c = 'ЮрЛицо'  # Короткая форма (чаще используется)
            elif 'физическое' in legal_entity_type_normalized or 'физлицо' in legal_entity_type_normalized:
                legal_entity_type_1c = 'ФизЛицо'  # Короткая форма для физического лица
        
        # Подготовка данных для 1С с правильными названиями полей
        # Согласно структуре ответа 1С:
        # - Description - краткое наименование
        # - НаименованиеПолное - полное наименование
        # - ЮрФизЛицо - перечисление (ЮрЛицо/ФизЛицо)
        counterparty_data = {
            'ИНН': params.get('inn') or '',
            'КПП': params.get('kpp') or '',
            'Description': params.get('short_name') or params.get('full_name') or '',
            'НаименованиеПолное': params.get('full_name') or params.get('short_name') or '',
            'ЮрФизЛицо': legal_entity_type_1c,
            'Поставщик': params.get('is_supplier', False),
            'Покупатель': params.get('is_buyer', False),
        }
        
        # Удаляем пустые значения, чтобы не отправлять их в 1С
        counterparty_data = {k: v for k, v in counterparty_data.items() if v != '' and v is not None}
        
        # Выполнить OData запрос для создания
        result = await self.oneс_client.create_entity(
            'Catalog_Контрагенты',
            counterparty_data
        )
        
        return {
            'created': True,
            'uuid': result.get('Ref_Key'),
            'entity': result
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
    
    async def _create_agreement(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Создать договор"""
        
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        agreement_data = {
            'Контрагент_Key': params.get('counterparty_uuid'),
            'Наименование': params.get('name'),
            'ЦенаДоговора': params.get('price'),
            'СрокДействия': params.get('term'),
            'ВзаиморасчетыВедутся': 'ПоДоговоруВЦелом',
            'ВестиПоДокументамРасчетов': True,
            'КонтролироватьСуммуЗадолженности': True,
            'КонтролироватьЧислоДнейЗадолженности': True,
        }
        
        result = await self.oneс_client.create_entity(
            'Catalog_ДоговорыСКонтрагентами',
            agreement_data
        )
        
        return {
            'created': True,
            'uuid': result.get('Ref_Key'),
            'entity': result
        }
    
    async def _attach_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Прикрепить файл к контрагенту"""
        
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        counterparty_uuid = params.get('counterparty_uuid')
        file_path = params.get('file_path')
        file_name = params.get('file_name')
        
        if not counterparty_uuid or not file_path:
            raise ValueError("counterparty_uuid and file_path are required")
        
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
        
        # Прикрепить к хранилищу дополнительной информации
        result = await self.oneс_client.attach_file(
            'Catalog_Контрагенты',
            counterparty_uuid,
            file_name or file_path.split('/')[-1],
            file_data
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
