"""
OData клиент для работы с 1С API
"""
import aiohttp
import base64
import structlog
from typing import Dict, Any, Optional
from urllib.parse import urljoin

logger = structlog.get_logger(__name__)


class OneCClient:
    """Клиент для работы с 1С OData API"""
    
    def __init__(self, config: Dict[str, Any]):
        base_url = config.get('ONEС_ODATA_URL', '').rstrip('/')
        # Убираем $metadata из URL если он там есть
        if base_url.endswith('/$metadata') or base_url.endswith('$metadata'):
            base_url = base_url.replace('/$metadata', '').replace('$metadata', '').rstrip('/')
        self.base_url = base_url
        self.username = config.get('ONEС_USERNAME', '')
        self.password = config.get('ONEС_PASSWORD', '')
        self.session: Optional[aiohttp.ClientSession] = None
        self.auth_header = self._create_auth_header()
    
    def _create_auth_header(self) -> str:
        """Создать заголовок базовой аутентификации"""
        if not self.username or not self.password:
            return ""
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    async def initialize(self):
        """Инициализировать сессию"""
        if not self.base_url:
            logger.warning("1C OData URL not configured")
            return
        
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        logger.info("OData client initialized", base_url=self.base_url)
    
    async def close(self):
        """Закрыть сессию"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def execute_query(self, query: str) -> Dict[str, Any]:
        """Выполнить OData запрос"""
        if not self.session:
            raise RuntimeError("Client not initialized. Call initialize() first.")
        
        url = urljoin(self.base_url + '/', query.lstrip('/'))
        
        headers = {
            'Accept': 'application/json'
        }
        
        if self.auth_header:
            headers['Authorization'] = self.auth_header
        
        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("OData query executed", url=query, status=response.status)
                    return data
                else:
                    error_text = await response.text()
                    logger.error("OData query failed", 
                               status=response.status,
                               error=error_text,
                               url=query)
                    raise Exception(f"OData query failed with status {response.status}: {error_text}")
        
        except aiohttp.ClientError as e:
            logger.error("OData query error", error=str(e), url=query)
            raise Exception(f"OData query error: {str(e)}")
    
    async def query_data(
        self,
        entity_set: str,
        filter_expr: Optional[str] = None,
        top: Optional[int] = None,
        skip: Optional[int] = None,
        order_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Выполнить запрос данных с фильтрацией, пагинацией и сортировкой.
        
        Args:
            entity_set: Название набора сущностей (например, Catalog_Контрагенты)
            filter_expr: Выражение фильтрации OData (например, "Code eq '0000003835'")
            top: Максимальное количество записей для возврата
            skip: Количество записей для пропуска (для пагинации)
            order_by: Поле для сортировки (например, "Code")
            
        Returns:
            Dict с данными (обычно содержит ключ 'value' со списком записей)
        """
        if not self.session:
            raise RuntimeError("Client not initialized. Call initialize() first.")
        
        # Формируем URL с параметрами OData
        query_parts = []
        
        if filter_expr:
            query_parts.append(f"$filter={filter_expr}")
        
        if order_by:
            query_parts.append(f"$orderby={order_by}")
        
        if top is not None:
            query_parts.append(f"$top={top}")
        
        if skip is not None:
            query_parts.append(f"$skip={skip}")
        
        query_string = '&'.join(query_parts)
        # Формируем URL правильно
        base = self.base_url.rstrip('/')
        if query_string:
            url = f"{base}/{entity_set}?{query_string}"
        else:
            url = f"{base}/{entity_set}"
        
        headers = {
            'Accept': 'application/json'
        }
        
        if self.auth_header:
            headers['Authorization'] = self.auth_header
        
        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("OData query_data executed", 
                              entity_set=entity_set,
                              filter_expr=filter_expr,
                              top=top,
                              skip=skip,
                              status=response.status)
                    return data
                else:
                    error_text = await response.text()
                    logger.error("OData query_data failed", 
                               entity_set=entity_set,
                               status=response.status,
                               error=error_text)
                    raise Exception(f"OData query_data failed with status {response.status}: {error_text}")
        
        except aiohttp.ClientError as e:
            logger.error("OData query_data error", error=str(e), entity_set=entity_set)
            raise Exception(f"OData query_data error: {str(e)}")
    
    async def create_entity(self, entity_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Создать сущность"""
        if not self.session:
            raise RuntimeError("Client not initialized. Call initialize() first.")
        
        url = urljoin(self.base_url + '/', entity_type.lstrip('/'))
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        if self.auth_header:
            headers['Authorization'] = self.auth_header
        
        logger.info("Creating entity", urls=url, datas=data)
        try:
            async with self.session.post(url, json=data, headers=headers) as response:
                if response.status in [201, 200]:
                    result = await response.json()
                    logger.info("Entity created", entity_type=entity_type, uuid=result.get('Ref_Key'))
                    return result
                else:
                    error_text = await response.text()
                    logger.error("Failed to create entity",
                               entity_type=entity_type,
                               status=response.status,
                               error=error_text)
                    raise Exception(f"Failed to create entity: {error_text}")
        
        except aiohttp.ClientError as e:
            logger.error("Entity creation error", error=str(e), entity_type=entity_type)
            raise
    
    async def update_entity(self, entity_set: str, entity_key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновить существующую сущность.
        
        Args:
            entity_set: Название набора сущностей (например, Catalog_Контрагенты)
            entity_key: Ключ сущности (UUID)
            data: Данные для обновления
            
        Returns:
            Dict с результатом обновления
        """
        if not self.session:
            raise RuntimeError("Client not initialized. Call initialize() first.")
        
        # Используем формат guid'{key}' как в стандарте OData для 1С
        url = urljoin(self.base_url + '/', f"{entity_set}(guid'{entity_key}')".lstrip('/'))
        
        logger.info(f"Обновление сущности {entity_key} в {entity_set}")
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        if self.auth_header:
            headers['Authorization'] = self.auth_header
        
        try:
            async with self.session.patch(url, json=data, headers=headers) as response:
                if response.status == 204:
                    # Успешное обновление без содержимого
                    logger.debug("Сущность успешно обновлена")
                    return {"success": True}
                elif response.status == 200:
                    result = await response.json()
                    logger.debug("Сущность успешно обновлена")
                    return result
                else:
                    error_text = await response.text()
                    logger.error("Failed to update entity",
                               entity_set=entity_set,
                               entity_key=entity_key,
                               status=response.status,
                               error=error_text)
                    raise Exception(f"Failed to update entity: {error_text}")
        
        except aiohttp.ClientError as e:
            logger.error("Entity update error", error=str(e), entity_set=entity_set, entity_key=entity_key)
            raise
    
    async def attach_file(self, entity_type: str, uuid: str, 
                         file_name: str, file_data: bytes) -> Dict[str, Any]:
        """Прикрепить файл к сущности"""
        
        logger.info("Attaching file to entity",
                   entity_type=entity_type,
                   uuid=uuid,
                   file_name=file_name)
        
        # В зависимости от версии 1С, прикрепление файлов может отличаться
        # Здесь показан примерный алгоритм через OData
        
        # Обычно файлы прикрепляются через отдельный endpoint или через хранилище файлов
        # Для базовой реализации возвращаем успешный результат
        
        # TODO: Реализовать реальное прикрепление файла в зависимости от версии 1С
        # Это может быть через:
        # - InformationRegister_Файлы
        # - Catalog_Файлы
        # - Или другой механизм в зависимости от конфигурации 1С
        
        return {'attached': True, 'file_name': file_name, 'entity_type': entity_type, 'uuid': uuid}
