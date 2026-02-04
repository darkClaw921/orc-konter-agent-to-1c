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
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json'
        }
        
        if self.auth_header:
            headers['Authorization'] = self.auth_header
        
        # Логируем данные без base64 для читаемости (первые 100 символов)
        log_data = {k: (v[:100] + '...' if isinstance(v, str) and len(v) > 100 else v) 
                    for k, v in data.items()}
        logger.info("Creating entity", url=url, data_keys=list(data.keys()), 
                   data_preview=log_data,
                   data_size=len(str(data)))
        try:
            # Используем json=data для автоматической сериализации
            
            print(f"data: {data}")
            print(f"url: {url}")
            print(f"headers: {headers}")
            
            
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
                         file_name: str, file_data: bytes,
                         object_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Прикрепить файл к сущности через каталог Catalog_ХранилищеДополнительнойИнформации
        
        Args:
            entity_type: Тип сущности (например, 'Catalog_Контрагенты' или 'Catalog_ДоговорыКонтрагентов')
            uuid: UUID сущности
            file_name: Имя файла
            file_data: Данные файла в байтах
            object_type: Тип объекта для поля Объект_Type (например, 'StandardODATA.Catalog_ДоговорыКонтрагентов')
                        Если не указан, определяется автоматически на основе entity_type
        
        Returns:
            Dict с результатом прикрепления файла
        """
        
        logger.info("Attaching file to entity",
                   entity_type=entity_type,
                   uuid=uuid,
                   file_name=file_name,
                   file_size=len(file_data))
        
        if not self.session:
            raise RuntimeError("Client not initialized. Call initialize() first.")
        
        # Определяем тип объекта для поля Объект_Type
        if not object_type:
            if entity_type == 'Catalog_ДоговорыКонтрагентов':
                object_type = 'StandardODATA.Catalog_ДоговорыКонтрагентов'
            elif entity_type == 'Catalog_Контрагенты':
                object_type = 'StandardODATA.Catalog_Контрагенты'
            else:
                # Пробуем сформировать тип автоматически
                object_type = f'StandardODATA.{entity_type}'
        
        # Определяем расширение файла
        import os
        file_extension = os.path.splitext(file_name)[1].lstrip('.').lower()
        if not file_extension:
            file_extension = 'bin'
        
        
        # Кодируем файл в base64
        import base64
        file_base64 = base64.b64encode(file_data).decode('utf-8')
        
        # Проверяем размер base64 данных (может быть проблемой для больших файлов)
        base64_size = len(file_base64)
        file_size_mb = len(file_data) / (1024 * 1024)
        base64_size_mb = base64_size / (1024 * 1024)
        
        logger.info("File encoding info",
                   original_size=len(file_data),
                   original_size_mb=round(file_size_mb, 2),
                   base64_size=base64_size,
                   base64_size_mb=round(base64_size_mb, 2),
                   file_name=file_name)
        
        # Предупреждение для больших файлов (больше 5MB)
        if file_size_mb > 5:
            logger.warning("Large file detected - may cause issues with OData",
                          file_size_mb=round(file_size_mb, 2),
                          file_name=file_name)
        
        # Формируем описание (Description) из имени файла без расширения
        description = os.path.splitext(file_name)[0]
        if not description:
            description = 'Файл'
        
        # Подготавливаем данные для создания записи в хранилище
        # Структура соответствует формату хранения файлов в 1С
        storage_data = {
            'Description': description,
            'ВидДанных': 'Файл',
            'ИмяФайла': file_name,
            'Объект': uuid,
            'Объект_Type': object_type,
            'Хранилище_Type': 'application/octet-stream',
            # 'Хранилище_Base64Data': file_base64,
            'ТекстФайла_Type': 'application/xml+xdto',
            'ТекстФайла_Base64Data': "",
            'ТипХраненияФайла': 'ВИнформационнойБазе',
            'Том_Key': '00000000-0000-0000-0000-000000000000',
            'Расширение': file_extension,
            'Размер': str(len(file_data))
        }
        
        # Создаем запись в каталоге Catalog_ХранилищеДополнительнойИнформации
        result = await self.create_entity(
            'Catalog_ХранилищеДополнительнойИнформации',
            storage_data
        )
        file_uuid = result.get('Ref_Key')
        logger.info("File attached successfully",
                    entity_type=entity_type,
                    entity_uuid=uuid,
                    file_name=file_name,
                    file_uuid=file_uuid,
                    file_size=len(file_data))
        
        return {
            'attached': True,
            'file_name': file_name,
            'file_uuid': file_uuid,
            'entity_type': entity_type,
            'entity_uuid': uuid,
            'file_size': len(file_data)
        }
            
        