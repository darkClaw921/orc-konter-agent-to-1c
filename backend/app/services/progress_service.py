"""
Сервис отслеживания прогресса обработки контрактов
"""
import json
from datetime import datetime
from typing import Optional, Dict, Any

import redis.asyncio as redis

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ProgressService:
    """Сервис отслеживания прогресса обработки документов"""

    # Веса стадий обработки (в %)
    STAGE_WEIGHTS = {
        'uploaded': 5,
        'document_loaded': 10,
        'text_extracted': 10,
        'data_extracted': 35,
        'services_extracted': 15,
        'validation_passed': 5,
        'checking_1c': 5,
        'creating_in_1c': 10,
        'completed': 5,
    }

    # Порядок стадий
    STAGE_ORDER = [
        'uploaded',
        'document_loaded',
        'text_extracted',
        'data_extracted',
        'services_extracted',
        'validation_passed',
        'checking_1c',
        'creating_in_1c',
        'completed',
    ]

    # Названия стадий на русском
    STAGE_NAMES = {
        'uploaded': 'Файл загружен',
        'document_loaded': 'Документ открыт',
        'text_extracted': 'Текст извлечён',
        'data_extracted': 'Извлечение данных',
        'services_extracted': 'Извлечение услуг',
        'validation_passed': 'Валидация',
        'checking_1c': 'Проверка в 1С',
        'creating_in_1c': 'Создание в 1С',
        'completed': 'Завершено',
    }

    # TTL для данных прогресса в Redis (в секундах)
    PROGRESS_TTL = 3600  # 1 час

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Инициализация сервиса прогресса

        Args:
            redis_client: Клиент Redis. Если не передан, будет создан новый.
        """
        self._redis_client = redis_client
        self._redis_url = settings.REDIS_URL

    async def _get_redis(self) -> redis.Redis:
        """Получить клиент Redis"""
        if self._redis_client is None:
            self._redis_client = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._redis_client

    def _get_key(self, contract_id: int) -> str:
        """Получить ключ Redis для контракта"""
        return f"progress:contract:{contract_id}"

    def _calculate_overall_progress(
        self,
        stage: str,
        stage_progress: int = 100
    ) -> int:
        """
        Рассчитать общий прогресс на основе стадии и прогресса внутри стадии

        Args:
            stage: Текущая стадия
            stage_progress: Прогресс внутри стадии (0-100)

        Returns:
            Общий прогресс (0-100)
        """
        if stage not in self.STAGE_ORDER:
            return 0

        stage_index = self.STAGE_ORDER.index(stage)

        # Суммируем веса всех завершённых стадий
        completed_weight = sum(
            self.STAGE_WEIGHTS.get(s, 0)
            for s in self.STAGE_ORDER[:stage_index]
        )

        # Добавляем пропорциональный вес текущей стадии
        current_stage_weight = self.STAGE_WEIGHTS.get(stage, 0)
        current_progress = (current_stage_weight * stage_progress) // 100

        return completed_weight + current_progress

    async def update_progress(
        self,
        contract_id: int,
        stage: str,
        stage_progress: int = 0,
        message: Optional[str] = None,
        chunks_total: Optional[int] = None,
        chunks_processed: Optional[int] = None
    ) -> None:
        """
        Обновить прогресс обработки контракта

        Args:
            contract_id: ID контракта
            stage: Текущая стадия обработки
            stage_progress: Прогресс внутри стадии (0-100)
            message: Сообщение о текущем действии
            chunks_total: Общее количество чанков (для стадий с чанками)
            chunks_processed: Количество обработанных чанков
        """
        try:
            redis_client = await self._get_redis()

            stage_index = self.STAGE_ORDER.index(stage) + 1 if stage in self.STAGE_ORDER else 0
            overall_progress = self._calculate_overall_progress(stage, stage_progress)

            # Формируем сообщение по умолчанию
            if message is None:
                if chunks_total and chunks_processed is not None:
                    message = f"Обработка чанков: {chunks_processed}/{chunks_total}"
                else:
                    message = self.STAGE_NAMES.get(stage, stage)

            progress_data = {
                'contract_id': contract_id,
                'stage': stage,
                'stage_name': self.STAGE_NAMES.get(stage, stage),
                'stage_index': stage_index,
                'total_stages': len(self.STAGE_ORDER),
                'stage_progress': stage_progress,
                'stage_message': message,
                'overall_progress': overall_progress,
                'chunks_total': chunks_total,
                'chunks_processed': chunks_processed,
                'updated_at': datetime.utcnow().isoformat(),
            }

            key = self._get_key(contract_id)
            await redis_client.setex(
                key,
                self.PROGRESS_TTL,
                json.dumps(progress_data, ensure_ascii=False)
            )

            logger.debug("Progress updated",
                        contract_id=contract_id,
                        stage=stage,
                        stage_progress=stage_progress,
                        overall_progress=overall_progress,
                        chunks_processed=chunks_processed,
                        chunks_total=chunks_total)

        except Exception as e:
            logger.error("Failed to update progress",
                        contract_id=contract_id,
                        error=str(e))
            # Не пробрасываем исключение, чтобы не прерывать основной процесс

    async def get_progress(self, contract_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить прогресс обработки контракта

        Args:
            contract_id: ID контракта

        Returns:
            Словарь с данными прогресса или None, если данных нет
        """
        try:
            redis_client = await self._get_redis()
            key = self._get_key(contract_id)
            data = await redis_client.get(key)

            if data:
                return json.loads(data)
            return None

        except Exception as e:
            logger.error("Failed to get progress",
                        contract_id=contract_id,
                        error=str(e))
            return None

    async def clear_progress(self, contract_id: int) -> None:
        """
        Очистить прогресс обработки контракта

        Args:
            contract_id: ID контракта
        """
        try:
            redis_client = await self._get_redis()
            key = self._get_key(contract_id)
            await redis_client.delete(key)

            logger.debug("Progress cleared", contract_id=contract_id)

        except Exception as e:
            logger.error("Failed to clear progress",
                        contract_id=contract_id,
                        error=str(e))

    async def close(self) -> None:
        """Закрыть соединение с Redis"""
        if self._redis_client:
            await self._redis_client.close()
            self._redis_client = None
