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
        
        # Выполнить OData запрос к 1С
        query = f"Catalog_Контрагенты?$filter=ИНН eq '{inn}'"
        result = await self.oneс_client.execute_query(query)
        
        if result and len(result.get('value', [])) > 0:
            counterparty = result['value'][0]
            return {
                'found': True,
                'uuid': counterparty.get('Ref_Key'),
                'data': counterparty
            }
        return {'found': False}
    
    async def _create_counterparty(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Создать нового контрагента"""
        
        if not self.oneс_client:
            raise RuntimeError("1C client not initialized")
        
        # Подготовить данные для 1С
        counterparty_data = {
            'ИНН': params.get('inn'),
            'КПП': params.get('kpp'),
            'Наименование': params.get('short_name') or params.get('full_name'),
            'ПолноеНаименование': params.get('full_name'),
            'ЮрФизЛицо': params.get('legal_entity_type', 'ЮридическоеЛицо'),
            'Поставщик': params.get('is_supplier', False),
            'Покупатель': params.get('is_buyer', False),
        }
        
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
        
        # Прочитать файл
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
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
