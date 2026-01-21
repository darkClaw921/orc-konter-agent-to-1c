"""
Интеграция с LLM провайдерами
"""
import asyncio
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from openai import AsyncOpenAI

from app.config import settings
from app.services.prompts import EXTRACT_CONTRACT_DATA_PROMPT, VALIDATE_EXTRACTED_DATA_PROMPT, MERGE_CHUNKS_DATA_PROMPT
from app.utils.logging import get_logger

logger = get_logger(__name__)


class BaseLLMProvider(ABC):
    """Абстрактный класс для LLM провайдеров"""
    
    @abstractmethod
    async def extract_contract_data(self, document_text: str) -> Dict[str, Any]:
        """Извлечь данные контракта из текста"""
        pass
    
    @abstractmethod
    async def validate_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидировать извлеченные данные"""
        pass
    
    @abstractmethod
    async def aggregate_chunks_data(self, chunks_with_context: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Агрегировать данные из нескольких чанков с разрешением конфликтов
        
        Args:
            chunks_with_context: Список словарей с ключами:
                - chunk_index: номер чанка
                - chunk_context: контекст чанка (первые символы)
                - extracted_data: извлеченные данные из чанка
                
        Returns:
            Объединенный словарь с данными контракта
        """
        pass


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT провайдер"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
    
    async def extract_contract_data(self, document_text: str) -> Dict[str, Any]:
        """Извлечь данные контракта с помощью GPT"""
        
        system_prompt = """You are an expert in Russian contract analysis.
        Extract contract information from documents and return it as valid JSON.
        Be precise with INN extraction (10 or 12 digits).
        Use boolean fields is_supplier and is_buyer for roles.
        """
        
        user_prompt = EXTRACT_CONTRACT_DATA_PROMPT.format(document_text=document_text)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            if not result_text:
                raise ValueError("Empty response from LLM")
            
            result_json = json.loads(result_text)
            
            logger.info("Contract data extracted", 
                       model=self.model,
                       tokens_used=response.usage.total_tokens if hasattr(response, 'usage') else 0)
            
            return result_json
        
        except Exception as e:
            logger.error("Failed to extract contract data", error=str(e))
            raise
    
    async def validate_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидировать извлеченные данные"""
        
        prompt = VALIDATE_EXTRACTED_DATA_PROMPT.format(extracted_data=json.dumps(data, ensure_ascii=False))
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            if not result_text:
                return {"is_valid": False, "issues": ["Empty validation response"], "suggestions": []}
            
            result_json = json.loads(result_text)
            return result_json
        
        except Exception as e:
            logger.error("Failed to validate data", error=str(e))
            return {"is_valid": False, "issues": [f"Validation error: {str(e)}"], "suggestions": []}
    
    async def aggregate_chunks_data(self, chunks_with_context: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Агрегировать данные из нескольких чанков с разрешением конфликтов через LLM"""
        
        if not chunks_with_context:
            return {}
        
        if len(chunks_with_context) == 1:
            return chunks_with_context[0].get('extracted_data', {})
        
        # Формируем данные для промпта с накопленным контекстом
        chunks_data_formatted = []
        final_accumulated_context = ""
        for chunk_info in chunks_with_context:
            chunk_data = {
                "chunk_index": chunk_info.get('chunk_index', 0),
                "chunk_context": chunk_info.get('chunk_context', '')[:1000],  # Первые 1000 символов текста чанка
                "accumulated_context": chunk_info.get('accumulated_context', ''),  # Накопленный контекст на момент обработки этого чанка
                "extracted_data": chunk_info.get('extracted_data', {})
            }
            chunks_data_formatted.append(chunk_data)
            # Берем финальный накопленный контекст из последнего чанка
            if chunk_info.get('accumulated_context'):
                final_accumulated_context = chunk_info.get('accumulated_context', '')
        
        # Формируем промпт с накопленным контекстом
        chunks_json = json.dumps(chunks_data_formatted, ensure_ascii=False, indent=2)
        prompt = MERGE_CHUNKS_DATA_PROMPT.format(
            total_chunks=len(chunks_with_context),
            chunks_data=chunks_json,
            accumulated_context=final_accumulated_context if final_accumulated_context else "Накопленный контекст отсутствует (это первый чанк или контекст не был сформирован)."
        )
        
        system_prompt = """You are an expert in Russian contract analysis.
        Merge contract information from multiple document chunks and resolve conflicts.
        Return only valid JSON with all merged fields.
        """
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            if not result_text:
                raise ValueError("Empty response from LLM")
            
            result_json = json.loads(result_text)
            
            logger.info("Chunks data aggregated", 
                       model=self.model,
                       chunks_count=len(chunks_with_context),
                       tokens_used=response.usage.total_tokens if hasattr(response, 'usage') else 0)
            
            return result_json
        
        except Exception as e:
            logger.error("Failed to aggregate chunks data", error=str(e))
            raise


class YandexGPTProvider(BaseLLMProvider):
    """Yandex GPT провайдер (для работы в России)"""
    
    def __init__(self, api_key: str, model: str = "yandexgpt"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://llm.api.cloud.yandex.net/foundationModels/v1"
    
    async def extract_contract_data(self, document_text: str) -> Dict[str, Any]:
        """Извлечь данные контракта с помощью Yandex GPT"""
        
        import aiohttp
        
        prompt = EXTRACT_CONTRACT_DATA_PROMPT.format(document_text=document_text)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self.api_key}"
        }
        
        data = {
            "modelUri": f"gpt://{self.model}",
            "completionOptions": {
                "stream": False,
                "temperature": settings.LLM_TEMPERATURE,
                "maxTokens": settings.LLM_MAX_TOKENS
            },
            "messages": [
                {
                    "role": "user",
                    "text": prompt
                }
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/completion",
                    json=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=settings.LLM_REQUEST_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API error {response.status}: {error_text}")
                    
                    result = await response.json()
                    
                    # Парсинг JSON из ответа
                    response_text = result['result']['alternatives'][0]['message']['text']
                    result_json = json.loads(response_text)
                    
                    logger.info("Contract data extracted from Yandex", model=self.model)
                    return result_json
        
        except Exception as e:
            logger.error("Failed to extract contract data from Yandex", error=str(e))
            raise
    
    async def validate_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидировать извлеченные данные"""
        # Реализация аналогична extract_contract_data
        import aiohttp
        
        prompt = VALIDATE_EXTRACTED_DATA_PROMPT.format(extracted_data=json.dumps(data, ensure_ascii=False))
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self.api_key}"
        }
        
        data_payload = {
            "modelUri": f"gpt://{self.model}",
            "completionOptions": {
                "stream": False,
                "temperature": settings.LLM_TEMPERATURE,
                "maxTokens": 1000
            },
            "messages": [
                {
                    "role": "user",
                    "text": prompt
                }
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/completion",
                    json=data_payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=settings.LLM_REQUEST_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        return {"is_valid": False, "issues": ["API error"], "suggestions": []}
                    
                    result = await response.json()
                    response_text = result['result']['alternatives'][0]['message']['text']
                    result_json = json.loads(response_text)
                    return result_json
        
        except Exception as e:
            logger.error("Failed to validate data with Yandex", error=str(e))
            return {"is_valid": False, "issues": [f"Validation error: {str(e)}"], "suggestions": []}
    
    async def aggregate_chunks_data(self, chunks_with_context: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Агрегировать данные из нескольких чанков с разрешением конфликтов через Yandex GPT"""
        
        import aiohttp
        
        if not chunks_with_context:
            return {}
        
        if len(chunks_with_context) == 1:
            return chunks_with_context[0].get('extracted_data', {})
        
        # Формируем данные для промпта с накопленным контекстом
        chunks_data_formatted = []
        final_accumulated_context = ""
        for chunk_info in chunks_with_context:
            chunk_data = {
                "chunk_index": chunk_info.get('chunk_index', 0),
                "chunk_context": chunk_info.get('chunk_context', '')[:1000],  # Первые 1000 символов текста чанка
                "accumulated_context": chunk_info.get('accumulated_context', ''),  # Накопленный контекст на момент обработки этого чанка
                "extracted_data": chunk_info.get('extracted_data', {})
            }
            chunks_data_formatted.append(chunk_data)
            # Берем финальный накопленный контекст из последнего чанка
            if chunk_info.get('accumulated_context'):
                final_accumulated_context = chunk_info.get('accumulated_context', '')
        
        # Формируем промпт с накопленным контекстом
        chunks_json = json.dumps(chunks_data_formatted, ensure_ascii=False, indent=2)
        prompt = MERGE_CHUNKS_DATA_PROMPT.format(
            total_chunks=len(chunks_with_context),
            chunks_data=chunks_json,
            accumulated_context=final_accumulated_context if final_accumulated_context else "Накопленный контекст отсутствует (это первый чанк или контекст не был сформирован)."
        )
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self.api_key}"
        }
        
        data = {
            "modelUri": f"gpt://{self.model}",
            "completionOptions": {
                "stream": False,
                "temperature": settings.LLM_TEMPERATURE,
                "maxTokens": settings.LLM_MAX_TOKENS
            },
            "messages": [
                {
                    "role": "user",
                    "text": prompt
                }
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/completion",
                    json=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=settings.LLM_REQUEST_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API error {response.status}: {error_text}")
                    
                    result = await response.json()
                    
                    # Парсинг JSON из ответа
                    response_text = result['result']['alternatives'][0]['message']['text']
                    result_json = json.loads(response_text)
                    
                    logger.info("Chunks data aggregated from Yandex", 
                               model=self.model,
                               chunks_count=len(chunks_with_context))
                    return result_json
        
        except Exception as e:
            logger.error("Failed to aggregate chunks data with Yandex", error=str(e))
            raise


class LLMService:
    """Сервис для работы с LLM провайдерами"""
    
    def __init__(self):
        if settings.LLM_PROVIDER == "openai":
            if not settings.LLM_API_KEY:
                raise ValueError("LLM_API_KEY is required for OpenAI provider")
            self.provider = OpenAIProvider(
                api_key=settings.LLM_API_KEY,
                model=settings.LLM_MODEL
            )
        elif settings.LLM_PROVIDER == "yandex":
            if not settings.LLM_API_KEY:
                raise ValueError("LLM_API_KEY is required for Yandex provider")
            self.provider = YandexGPTProvider(
                api_key=settings.LLM_API_KEY,
                model=settings.LLM_MODEL
            )
        else:
            raise ValueError(f"Unknown LLM provider: {settings.LLM_PROVIDER}")
    
    async def extract_contract_data(self, document_text: str, retry_count: int = 3) -> Dict[str, Any]:
        """
        Извлечь данные контракта с повторами при ошибке
        """
        for attempt in range(retry_count):
            try:
                return await self.provider.extract_contract_data(document_text)
            except Exception as e:
                logger.warning(f"Extraction attempt {attempt + 1} failed", error=str(e))
                if attempt == retry_count - 1:
                    raise
                # Экспоненциальная задержка перед повтором
                await asyncio.sleep(2 ** attempt)
        
        raise Exception("Failed to extract contract data after retries")
    
    async def validate_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидировать извлеченные данные"""
        return await self.provider.validate_extracted_data(data)
    
    async def aggregate_chunks_data(self, chunks_with_context: List[Dict[str, Any]], retry_count: int = 3) -> Dict[str, Any]:
        """
        Агрегировать данные из нескольких чанков через LLM с разрешением конфликтов
        
        Args:
            chunks_with_context: Список словарей с ключами:
                - chunk_index: номер чанка
                - chunk_context: контекст чанка (первые символы)
                - extracted_data: извлеченные данные из чанка
            retry_count: Количество попыток при ошибке
            
        Returns:
            Объединенный словарь с данными контракта
            
        Raises:
            Exception: Если агрегация не удалась после всех попыток
        """
        if not chunks_with_context:
            return {}
        
        if len(chunks_with_context) == 1:
            return chunks_with_context[0].get('extracted_data', {})
        
        # Пытаемся агрегировать через LLM
        for attempt in range(retry_count):
            try:
                return await self.provider.aggregate_chunks_data(chunks_with_context)
            except Exception as e:
                logger.warning(f"Aggregation attempt {attempt + 1} failed", 
                             error=str(e),
                             chunks_count=len(chunks_with_context))
                if attempt == retry_count - 1:
                    # Если все попытки не удались, используем fallback на простое объединение
                    logger.warning("LLM aggregation failed, using fallback merge",
                                 chunks_count=len(chunks_with_context))
                    # Извлекаем только extracted_data для fallback
                    chunks_data = [chunk.get('extracted_data', {}) for chunk in chunks_with_context]
                    return self.merge_extracted_data(chunks_data)
                # Экспоненциальная задержка перед повтором
                await asyncio.sleep(2 ** attempt)
        
        # Этот код не должен выполниться, но на всякий случай
        chunks_data = [chunk.get('extracted_data', {}) for chunk in chunks_with_context]
        return self.merge_extracted_data(chunks_data)
    
    def merge_extracted_data(self, chunks_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Объединить результаты извлечения данных из разных чанков документа
        
        Args:
            chunks_data: Список словарей с извлеченными данными из каждого чанка
            
        Returns:
            Объединенный словарь с данными контракта
        """
        if not chunks_data:
            return {}
        
        if len(chunks_data) == 1:
            return chunks_data[0]
        
        # Основные поля, которые берутся из первого чанка (обычно там основная информация)
        primary_fields = {
            'inn', 'full_name', 'short_name', 'organizational_form', 'legal_entity_type',
            'kpp', 'contract_name', 'contract_number', 'contract_date', 'contract_price',
            'vat_type', 'vat_percent', 'is_supplier', 'is_buyer'
        }
        
        # Поля-списки, которые объединяются из всех чанков
        list_fields = {
            'service_locations', 'locations', 'responsible_persons'
        }
        
        # Начинаем с первого чанка
        merged = chunks_data[0].copy()
        
        # Обрабатываем остальные чанки
        for chunk_idx, chunk_data in enumerate(chunks_data[1:], start=1):
            if not chunk_data:
                continue
            
            # Объединяем списки из всех чанков
            for field in list_fields:
                if field in chunk_data and chunk_data[field]:
                    chunk_list = chunk_data[field]
                    if not isinstance(chunk_list, list):
                        chunk_list = [chunk_list]
                    
                    if field not in merged or not merged[field]:
                        merged[field] = []
                    
                    # Добавляем элементы из текущего чанка, убирая дубликаты
                    existing_items = merged[field]
                    for item in chunk_list:
                        # Проверяем на дубликаты по ключевым полям
                        is_duplicate = False
                        if isinstance(item, dict):
                            # Для словарей проверяем по основным полям
                            if field == 'service_locations' or field == 'locations':
                                # Проверяем по адресу
                                item_key = item.get('address') or item.get('address_full')
                            elif field == 'responsible_persons':
                                # Проверяем по имени
                                item_key = item.get('name') or item.get('fio')
                            else:
                                item_key = str(item)
                            
                            for existing in existing_items:
                                if isinstance(existing, dict):
                                    if field == 'service_locations' or field == 'locations':
                                        existing_key = existing.get('address') or existing.get('address_full')
                                    elif field == 'responsible_persons':
                                        existing_key = existing.get('name') or existing.get('fio')
                                    else:
                                        existing_key = str(existing)
                                    
                                    if item_key and existing_key and item_key == existing_key:
                                        is_duplicate = True
                                        break
                        else:
                            # Для простых значений
                            if item in existing_items:
                                is_duplicate = True
                        
                        if not is_duplicate:
                            merged[field].append(item)
            
            # Дополняем дополнительные поля из последующих чанков, если они отсутствуют в первом
            for key, value in chunk_data.items():
                if key not in primary_fields and key not in list_fields:
                    if key not in merged or not merged[key]:
                        if value:  # Добавляем только если значение не пустое
                            merged[key] = value
                    elif isinstance(merged[key], str) and isinstance(value, str):
                        # Если оба значения - строки, дополняем если новое длиннее
                        if len(value) > len(merged[key]):
                            merged[key] = value
        
        logger.info("Merged extracted data from chunks",
                   total_chunks=len(chunks_data),
                   merged_fields=len(merged))
        
        return merged
