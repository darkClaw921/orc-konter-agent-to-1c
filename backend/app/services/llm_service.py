"""
Интеграция с LLM провайдерами
"""
import asyncio
import json
import random
import traceback
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime

from openai import AsyncOpenAI
from openai import APIConnectionError, APITimeoutError
import httpx

from app.config import settings
from app.services.prompts import EXTRACT_CONTRACT_DATA_PROMPT, VALIDATE_EXTRACTED_DATA_PROMPT, MERGE_CHUNKS_DATA_PROMPT, EXTRACT_SERVICES_ONLY_PROMPT
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

    @abstractmethod
    async def extract_services_only(self, document_text: str) -> Dict[str, Any]:
        """
        Извлечь только услуги из документа

        Args:
            document_text: Текст документа для извлечения услуг

        Returns:
            Словарь с ключом 'services' содержащий список услуг
        """
        pass


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT провайдер"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        # Создаем клиент с детальными таймаутами для обработки больших документов
        # connect: время на установку соединения
        # read: время на чтение ответа (самое важное для длинных запросов)
        # write: время на отправку запроса
        # pool: время на получение соединения из пула
        timeout = httpx.Timeout(
            connect=30.0,  # 30 секунд на подключение
            read=settings.LLM_REQUEST_TIMEOUT,  # Основной таймаут на чтение ответа
            write=60.0,  # 60 секунд на отправку запроса
            pool=10.0  # 10 секунд на получение соединения из пула
        )
        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout
        )
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
        
        except (APIConnectionError, APITimeoutError) as e:
            error_traceback = traceback.format_exc()
            logger.error("Connection error during contract data extraction", 
                        error=str(e),
                        error_type=type(e).__name__,
                        error_traceback=error_traceback,
                        document_size=len(document_text),
                        model=self.model,
                        timeout=settings.LLM_REQUEST_TIMEOUT)
            raise
        except json.JSONDecodeError as e:
            error_traceback = traceback.format_exc()
            logger.error("JSON decode error during contract data extraction",
                        error=str(e),
                        error_type=type(e).__name__,
                        error_traceback=error_traceback,
                        response_text_preview=result_text[:500] if 'result_text' in locals() else None,
                        document_size=len(document_text),
                        model=self.model)
            raise
        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error("Failed to extract contract data",
                        error=str(e),
                        error_type=type(e).__name__,
                        error_traceback=error_traceback,
                        document_size=len(document_text),
                        model=self.model)
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
            error_traceback = traceback.format_exc()
            logger.error("Failed to validate data",
                        error=str(e),
                        error_type=type(e).__name__,
                        error_traceback=error_traceback,
                        data_size=len(str(data)),
                        model=self.model)
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

        except (APIConnectionError, APITimeoutError) as e:
            error_traceback = traceback.format_exc()
            logger.error("Connection error during chunks aggregation",
                        error=str(e),
                        error_type=type(e).__name__,
                        error_traceback=error_traceback,
                        chunks_count=len(chunks_with_context),
                        prompt_size=len(prompt),
                        model=self.model,
                        timeout=settings.LLM_REQUEST_TIMEOUT)
            raise
        except json.JSONDecodeError as e:
            error_traceback = traceback.format_exc()
            logger.error("JSON decode error during chunks aggregation",
                        error=str(e),
                        error_type=type(e).__name__,
                        error_traceback=error_traceback,
                        response_text_preview=result_text[:500] if 'result_text' in locals() else None,
                        chunks_count=len(chunks_with_context),
                        model=self.model)
            raise
        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error("Failed to aggregate chunks data",
                        error=str(e),
                        error_type=type(e).__name__,
                        error_traceback=error_traceback,
                        chunks_count=len(chunks_with_context),
                        prompt_size=len(prompt),
                        model=self.model)
            raise

    async def extract_services_only(self, document_text: str) -> Dict[str, Any]:
        """Извлечь только услуги из документа"""

        system_prompt = """You are an expert at extracting service information from Russian contracts.
        Extract all services with their prices and quantities. Return only valid JSON."""

        user_prompt = EXTRACT_SERVICES_ONLY_PROMPT.format(document_text=document_text)

        try:
            # logger.debug("Extracting services only",
            #            model=self.model,
            #            system_prompt=system_prompt,
            #            user_prompt=user_prompt
            #            )
            # print(system_prompt)
            # print(user_prompt)
            # 1/0
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

            logger.info("Services extracted",
                       model=self.model,
                       services_count=len(result_json.get('services', [])),
                       tokens_used=response.usage.total_tokens if hasattr(response, 'usage') else 0)

            return result_json

        except (APIConnectionError, APITimeoutError) as e:
            error_traceback = traceback.format_exc()
            logger.error("Connection error during services extraction",
                        error=str(e),
                        error_type=type(e).__name__,
                        error_traceback=error_traceback,
                        document_size=len(document_text),
                        model=self.model,
                        timeout=settings.LLM_REQUEST_TIMEOUT)
            raise
        except json.JSONDecodeError as e:
            error_traceback = traceback.format_exc()
            logger.error("JSON decode error during services extraction",
                        error=str(e),
                        error_type=type(e).__name__,
                        error_traceback=error_traceback,
                        response_text_preview=result_text[:500] if 'result_text' in locals() else None,
                        document_size=len(document_text),
                        model=self.model)
            raise
        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error("Failed to extract services",
                        error=str(e),
                        error_type=type(e).__name__,
                        error_traceback=error_traceback,
                        document_size=len(document_text),
                        model=self.model)
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

    async def extract_services_only(self, document_text: str) -> Dict[str, Any]:
        """Извлечь только услуги из документа через Yandex GPT"""

        import aiohttp

        prompt = EXTRACT_SERVICES_ONLY_PROMPT.format(document_text=document_text)

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

                    logger.info("Services extracted from Yandex",
                               model=self.model,
                               services_count=len(result_json.get('services', [])))
                    return result_json

        except Exception as e:
            logger.error("Failed to extract services from Yandex", error=str(e))
            raise


class LLMService:
    """Сервис для работы с LLM провайдерами"""

    # Максимальное количество параллельных запросов к LLM API
    MAX_CONCURRENT_REQUESTS = 3

    # Размер батча для обработки запросов (количество чанков в одном батче)
    BATCH_SIZE = 50

    # Количество попыток для обычных ошибок
    DEFAULT_RETRY_COUNT = 3
    # Количество попыток для connection errors (больше, т.к. они могут быть временными)
    CONNECTION_ERROR_RETRY_COUNT = 5

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

        # Семафор для ограничения параллельных запросов
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_REQUESTS)
    
    def _is_connection_error(self, error: Exception) -> bool:
        """Проверить, является ли ошибка ошибкой соединения"""
        return isinstance(error, (APIConnectionError, APITimeoutError)) or \
               "Connection error" in str(error) or \
               "connection" in str(error).lower()
    
    def _calculate_retry_delay(self, attempt: int, is_connection_error: bool = False) -> float:
        """
        Рассчитать задержку перед повтором с экспоненциальным backoff и jitter
        
        Args:
            attempt: Номер попытки (начинается с 0)
            is_connection_error: Является ли ошибка ошибкой соединения
        
        Returns:
            Задержка в секундах
        """
        # Базовое время задержки (экспоненциальное)
        base_delay = 2 ** attempt
        
        # Для connection errors используем более длительные задержки
        if is_connection_error:
            base_delay = base_delay * 2  # Удваиваем задержку для connection errors
        
        # Добавляем jitter (случайное отклонение до 30% от базовой задержки)
        jitter = random.uniform(0, base_delay * 0.3)
        
        # Максимальная задержка - 60 секунд
        delay = min(base_delay + jitter, 60.0)
        
        return delay
    
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
            'service_locations', 'locations', 'responsible_persons', 'services'
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
                            elif field == 'services':
                                # Проверяем по названию услуги
                                item_key = item.get('name')
                            else:
                                item_key = str(item)
                            
                            for existing in existing_items:
                                if isinstance(existing, dict):
                                    if field == 'service_locations' or field == 'locations':
                                        existing_key = existing.get('address') or existing.get('address_full')
                                    elif field == 'responsible_persons':
                                        existing_key = existing.get('name') or existing.get('fio')
                                    elif field == 'services':
                                        existing_key = existing.get('name')
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

    async def _extract_services_from_chunk_with_retry(
        self,
        chunk_idx: int,
        chunk_text: str,
        retry_count: Optional[int] = None
    ) -> tuple[int, List[Dict[str, Any]]]:
        """
        Извлечь услуги из одного чанка с повторами при ошибке (с семафором)

        Args:
            chunk_idx: Индекс чанка
            chunk_text: Текст чанка
            retry_count: Количество попыток (None = автоматически определяется по типу ошибки)

        Returns:
            Кортеж (индекс чанка, список услуг)
        """
        async with self._semaphore:
            start_time = datetime.now()
            last_error = None
            
            # Определяем количество попыток
            max_retries = retry_count if retry_count is not None else self.DEFAULT_RETRY_COUNT
            
            for attempt in range(max_retries):
                attempt_start_time = datetime.now()
                try:
                    print(chunk_text)
                    # 1/0
                    result = await self.provider.extract_services_only(chunk_text)
                    chunk_services = result.get('services', [])
                    attempt_duration = (datetime.now() - attempt_start_time).total_seconds()
                    total_duration = (datetime.now() - start_time).total_seconds()

                    logger.info("Services extracted from chunk",
                               chunk_index=chunk_idx,
                               services_found=len(chunk_services),
                               attempt=attempt + 1,
                               attempt_duration_seconds=round(attempt_duration, 2),
                               total_duration_seconds=round(total_duration, 2),
                               chunk_size=len(chunk_text))
                    return (chunk_idx, chunk_services)

                except Exception as e:
                    last_error = e
                    is_connection_error = self._is_connection_error(e)
                    attempt_duration = (datetime.now() - attempt_start_time).total_seconds()
                    error_traceback = traceback.format_exc()
                    
                    # Если это connection error и мы еще не использовали увеличенное количество попыток
                    if is_connection_error and retry_count is None and attempt == self.DEFAULT_RETRY_COUNT - 1:
                        # Продолжаем с увеличенным количеством попыток для connection errors
                        max_retries = self.CONNECTION_ERROR_RETRY_COUNT
                        logger.warning("Connection error detected, extending retry count",
                                     chunk_index=chunk_idx,
                                     new_max_retries=max_retries,
                                     error_type=type(e).__name__,
                                     error=str(e))
                    
                    logger.warning(f"Failed to extract services from chunk (attempt {attempt + 1}/{max_retries})",
                                 chunk_index=chunk_idx,
                                 error=str(e),
                                 error_type=type(e).__name__,
                                 error_traceback=error_traceback,
                                 is_connection_error=is_connection_error,
                                 attempt_duration_seconds=round(attempt_duration, 2),
                                 chunk_size=len(chunk_text),
                                 chunk_preview=chunk_text[:200] if chunk_text else None)
                    
                    if attempt == max_retries - 1:
                        total_duration = (datetime.now() - start_time).total_seconds()
                        logger.error("All attempts failed for chunk, skipping",
                                   chunk_index=chunk_idx,
                                   total_attempts=max_retries,
                                   total_duration_seconds=round(total_duration, 2),
                                   final_error=str(e),
                                   final_error_type=type(e).__name__,
                                   final_error_traceback=error_traceback,
                                   chunk_size=len(chunk_text),
                                   is_connection_error=is_connection_error)
                        return (chunk_idx, [])
                    
                    # Рассчитываем задержку с jitter
                    delay = self._calculate_retry_delay(attempt, is_connection_error)
                    logger.info(f"Retrying in {delay:.2f} seconds",
                               chunk_index=chunk_idx,
                               attempt=attempt + 1,
                               next_attempt=attempt + 2,
                               delay_seconds=round(delay, 2),
                               is_connection_error=is_connection_error)
                    await asyncio.sleep(delay)

            total_duration = (datetime.now() - start_time).total_seconds()
            logger.error("Max retries exceeded for services extraction",
                       chunk_index=chunk_idx,
                       total_attempts=max_retries,
                       total_duration_seconds=round(total_duration, 2),
                       final_error=str(last_error) if last_error else "Unknown error")
            return (chunk_idx, [])

    async def extract_services_from_chunks(self, chunks: List[str], retry_count: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Извлечь услуги из всех чанков документа ПАРАЛЛЕЛЬНО с обработкой БАТЧАМИ

        Args:
            chunks: Список текстовых чанков документа
            retry_count: Количество попыток при ошибке (None = автоматически определяется по типу ошибки)

        Returns:
            Список услуг из всех чанков (без дубликатов)
        """
        if not chunks:
            return []

        total_chunks = len(chunks)
        total_batches = (total_chunks + self.BATCH_SIZE - 1) // self.BATCH_SIZE

        logger.info("Starting batched parallel services extraction",
                   total_chunks=total_chunks,
                   batch_size=self.BATCH_SIZE,
                   total_batches=total_batches,
                   max_concurrent=self.MAX_CONCURRENT_REQUESTS)

        all_results = []

        # Обрабатываем чанки батчами
        for batch_num in range(total_batches):
            batch_start = batch_num * self.BATCH_SIZE
            batch_end = min(batch_start + self.BATCH_SIZE, total_chunks)
            batch_chunks = chunks[batch_start:batch_end]

            logger.info("Processing batch",
                       batch_number=batch_num + 1,
                       total_batches=total_batches,
                       batch_start=batch_start + 1,
                       batch_end=batch_end,
                       chunks_in_batch=len(batch_chunks))

            # Запускаем чанки текущего батча параллельно (семафор ограничивает конкурентность)
            tasks = [
                self._extract_services_from_chunk_with_retry(
                    batch_start + chunk_idx + 1,  # Глобальный индекс чанка
                    chunk_text,
                    retry_count
                )
                for chunk_idx, chunk_text in enumerate(batch_chunks)
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=False)
            all_results.extend(batch_results)

            logger.info("Batch completed",
                       batch_number=batch_num + 1,
                       total_batches=total_batches,
                       chunks_processed=len(batch_results))

        # Собираем все услуги, удаляя дубликаты
        all_services = []
        service_names_seen = set()

        # Сортируем по индексу чанка для сохранения порядка
        for chunk_idx, chunk_services in sorted(all_results, key=lambda x: x[0]):
            for service in chunk_services:
                name = service.get('name', '').lower().strip()
                if name and name not in service_names_seen:
                    all_services.append(service)
                    service_names_seen.add(name)
                elif name in service_names_seen:
                    # Обновляем существующую услугу если новая более полная
                    for idx, existing in enumerate(all_services):
                        if existing.get('name', '').lower().strip() == name:
                            existing_fields = sum(1 for v in existing.values() if v is not None)
                            new_fields = sum(1 for v in service.values() if v is not None)
                            if new_fields > existing_fields:
                                all_services[idx] = service
                            break

        logger.info("All services extracted from chunks (batched parallel)",
                   total_chunks=total_chunks,
                   total_batches=total_batches,
                   total_services=len(all_services))

        return all_services

    async def _extract_contract_data_from_chunk_with_retry(
        self,
        chunk_idx: int,
        chunk_text: str,
        retry_count: Optional[int] = None
    ) -> tuple[int, Optional[Dict[str, Any]], Optional[str]]:
        """
        Извлечь данные контракта из одного чанка с повторами (с семафором)

        Args:
            chunk_idx: Индекс чанка
            chunk_text: Текст чанка
            retry_count: Количество попыток (None = автоматически определяется по типу ошибки)

        Returns:
            Кортеж (индекс чанка, извлеченные данные или None, ошибка или None)
        """
        async with self._semaphore:
            last_error = None
            is_connection_error = False
            start_time = datetime.now()
            
            # Определяем количество попыток
            max_retries = retry_count if retry_count is not None else self.DEFAULT_RETRY_COUNT
            
            for attempt in range(max_retries):
                attempt_start_time = datetime.now()
                try:
                    result = await self.provider.extract_contract_data(chunk_text)
                    attempt_duration = (datetime.now() - attempt_start_time).total_seconds()
                    total_duration = (datetime.now() - start_time).total_seconds()
                    
                    logger.info("Contract data extracted from chunk",
                               chunk_index=chunk_idx,
                               attempt=attempt + 1,
                               attempt_duration_seconds=round(attempt_duration, 2),
                               total_duration_seconds=round(total_duration, 2),
                               chunk_size=len(chunk_text))
                    return (chunk_idx, result, None)

                except Exception as e:
                    last_error = e
                    error_msg = str(e)
                    is_connection_error = self._is_connection_error(e)
                    attempt_duration = (datetime.now() - attempt_start_time).total_seconds()
                    error_traceback = traceback.format_exc()
                    
                    # Если это connection error и мы еще не использовали увеличенное количество попыток
                    if is_connection_error and retry_count is None and attempt == self.DEFAULT_RETRY_COUNT - 1:
                        # Продолжаем с увеличенным количеством попыток для connection errors
                        max_retries = self.CONNECTION_ERROR_RETRY_COUNT
                        logger.warning("Connection error detected, extending retry count",
                                     chunk_index=chunk_idx,
                                     new_max_retries=max_retries,
                                     error_type=type(e).__name__,
                                     error=str(e))
                    
                    logger.warning(f"Failed to extract contract data from chunk (attempt {attempt + 1}/{max_retries})",
                                 chunk_index=chunk_idx,
                                 error=error_msg,
                                 error_type=type(e).__name__,
                                 error_traceback=error_traceback,
                                 is_connection_error=is_connection_error,
                                 attempt_duration_seconds=round(attempt_duration, 2),
                                 chunk_size=len(chunk_text),
                                 chunk_preview=chunk_text[:200] if chunk_text else None)
                    
                    if attempt == max_retries - 1:
                        total_duration = (datetime.now() - start_time).total_seconds()
                        logger.error("All attempts failed for chunk",
                                   chunk_index=chunk_idx,
                                   total_attempts=max_retries,
                                   total_duration_seconds=round(total_duration, 2),
                                   final_error=error_msg,
                                   final_error_type=type(e).__name__,
                                   final_error_traceback=error_traceback,
                                   chunk_size=len(chunk_text),
                                   is_connection_error=is_connection_error)
                        return (chunk_idx, None, error_msg)
                    
                    # Рассчитываем задержку с jitter
                    delay = self._calculate_retry_delay(attempt, is_connection_error)
                    logger.info(f"Retrying in {delay:.2f} seconds",
                               chunk_index=chunk_idx,
                               attempt=attempt + 1,
                               next_attempt=attempt + 2,
                               delay_seconds=round(delay, 2),
                               is_connection_error=is_connection_error)
                    await asyncio.sleep(delay)

            total_duration = (datetime.now() - start_time).total_seconds()
            final_error_msg = f"Max retries exceeded: {str(last_error) if last_error else 'Unknown error'}"
            logger.error("Max retries exceeded for chunk",
                       chunk_index=chunk_idx,
                       total_attempts=max_retries,
                       total_duration_seconds=round(total_duration, 2),
                       final_error=final_error_msg)
            return (chunk_idx, None, final_error_msg)

    async def extract_contract_data_parallel(
        self,
        chunks: List[str],
        retry_count: Optional[int] = None
    ) -> List[tuple[int, Optional[Dict[str, Any]], Optional[str]]]:
        """
        Извлечь данные контракта из всех чанков ПАРАЛЛЕЛЬНО с обработкой БАТЧАМИ

        Args:
            chunks: Список текстовых чанков документа
            retry_count: Количество попыток при ошибке (None = автоматически определяется по типу ошибки)

        Returns:
            Список кортежей (индекс чанка, данные или None, ошибка или None)
        """
        if not chunks:
            return []

        total_chunks = len(chunks)
        total_batches = (total_chunks + self.BATCH_SIZE - 1) // self.BATCH_SIZE

        logger.info("Starting batched parallel contract data extraction",
                   total_chunks=total_chunks,
                   batch_size=self.BATCH_SIZE,
                   total_batches=total_batches,
                   max_concurrent=self.MAX_CONCURRENT_REQUESTS)

        all_results = []

        # Обрабатываем чанки батчами
        for batch_num in range(total_batches):
            batch_start = batch_num * self.BATCH_SIZE
            batch_end = min(batch_start + self.BATCH_SIZE, total_chunks)
            batch_chunks = chunks[batch_start:batch_end]

            logger.info("Processing contract data batch",
                       batch_number=batch_num + 1,
                       total_batches=total_batches,
                       batch_start=batch_start + 1,
                       batch_end=batch_end,
                       chunks_in_batch=len(batch_chunks))

            tasks = [
                self._extract_contract_data_from_chunk_with_retry(
                    batch_start + chunk_idx + 1,  # Глобальный индекс чанка
                    chunk_text,
                    retry_count
                )
                for chunk_idx, chunk_text in enumerate(batch_chunks)
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=False)
            all_results.extend(batch_results)

            logger.info("Contract data batch completed",
                       batch_number=batch_num + 1,
                       total_batches=total_batches,
                       chunks_processed=len(batch_results))

        # Сортируем по индексу чанка
        sorted_results = sorted(all_results, key=lambda x: x[0])

        successful = sum(1 for _, data, _ in sorted_results if data is not None)
        failed = total_chunks - successful

        logger.info("Batched parallel contract data extraction completed",
                   total_chunks=total_chunks,
                   total_batches=total_batches,
                   successful=successful,
                   failed=failed)

        if failed > 0:
            failed_chunks = [idx for idx, data, _ in sorted_results if data is None]
            logger.warning("Some chunks failed to process",
                          failed_chunks=failed_chunks,
                          failed_count=failed)

        return sorted_results
