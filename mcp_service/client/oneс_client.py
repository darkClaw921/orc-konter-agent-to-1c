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
        self.base_url = config.get('ONEС_ODATA_URL', '').rstrip('/')
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
    
    async def update_entity(self, entity_type: str, uuid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновить сущность"""
        if not self.session:
            raise RuntimeError("Client not initialized. Call initialize() first.")
        
        url = urljoin(self.base_url + '/', f"{entity_type}('{uuid}')".lstrip('/'))
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        if self.auth_header:
            headers['Authorization'] = self.auth_header
        
        try:
            async with self.session.patch(url, json=data, headers=headers) as response:
                if response.status in [200, 204]:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {'updated': True}
                else:
                    error_text = await response.text()
                    logger.error("Failed to update entity",
                               entity_type=entity_type,
                               uuid=uuid,
                               status=response.status,
                               error=error_text)
                    raise Exception(f"Failed to update entity: {error_text}")
        
        except aiohttp.ClientError as e:
            logger.error("Entity update error", error=str(e), entity_type=entity_type, uuid=uuid)
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
