"""
Интеграция с 1С через MCP
"""
import asyncio
import aiohttp
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any, Optional

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _serialize_for_json(obj: Any) -> Any:
    """
    Сериализовать объект для JSON, преобразуя даты и Decimal в строки.
    
    Args:
        obj: Объект для сериализации
        
    Returns:
        JSON-совместимый объект
    """
    if isinstance(obj, date):
        # Преобразуем date в строку формата YYYY-MM-DD
        return obj.isoformat()
    elif isinstance(obj, datetime):
        # Преобразуем datetime в строку формата YYYY-MM-DD
        return obj.date().isoformat()
    elif isinstance(obj, Decimal):
        # Преобразуем Decimal в float или str
        return float(obj)
    elif isinstance(obj, dict):
        # Рекурсивно обрабатываем словари
        return {key: _serialize_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        # Рекурсивно обрабатываем списки
        return [_serialize_for_json(item) for item in obj]
    else:
        return obj


class OneCService:
    """Сервис для работы с 1С через MCP Service"""

    def __init__(self):
        self.mcp_service_url = settings.MCP_SERVICE_URL
        self.timeout = 60  # Увеличен с 30 до 60 секунд для работы с 1С
    
    async def find_counterparty_by_inn(self, inn: str) -> Optional[Dict[str, Any]]:
        """
        Найти контрагента в 1С по ИНН
        
        Args:
            inn: ИНН контрагента
            
        Returns:
            Dict с данными контрагента (включая uuid) или None если не найден
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.mcp_service_url}/command",
                    json={
                        "command": "check_counterparty",
                        "params": {"inn": inn}
                    },
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("status") == "success":
                            result = response_data.get("result", {})
                            if result.get("found"):
                                # Возвращаем данные контрагента с uuid
                                counterparty_data = result.get("data", {})
                                counterparty_data["uuid"] = result.get("uuid")
                                return counterparty_data
                        elif response_data.get("status") == "error":
                            # Возвращаем специальный объект с ошибкой
                            error_msg = response_data.get("error", "Unknown error")
                            return {"_error": error_msg}
                    else:
                        error_text = await response.text()
                        return {"_error": f"HTTP {response.status}: {error_text}"}
                    return None
        except asyncio.TimeoutError:
            error_msg = f"Timeout after {self.timeout} seconds"
            logger.error("Failed to check counterparty in 1C", error=error_msg, inn=inn, error_type="timeout")
            return {"_error": error_msg}
        except aiohttp.ClientError as e:
            error_msg = f"HTTP client error: {type(e).__name__}: {str(e)}"
            logger.error("Failed to check counterparty in 1C", error=error_msg, inn=inn, error_type="client_error")
            return {"_error": error_msg}
        except Exception as e:
            error_msg = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
            logger.error("Failed to check counterparty in 1C", error=error_msg, inn=inn, error_type=type(e).__name__)
            return {"_error": error_msg}
    
    async def create_counterparty(self, contract_data: Dict[str, Any], document_path: str, raw_text: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Создать контрагента в 1С
        
        Args:
            contract_data: Извлеченные данные контракта
            document_path: Путь к файлу контракта
            raw_text: Полный текст документа (для поиска фразы "протокол подведения итогов")
            
        Returns:
            Dict с данными созданного контрагента: {'uuid': str, 'entity': dict} или None
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Определяем роль контрагента
                role_value = contract_data.get("role")
                role = str(role_value or "").lower()
                is_supplier = "поставщик" in role or "продавец" in role or "исполнитель" in role
                is_buyer = "покупатель" in role or "заказчик" in role
                
                # Извлекаем допустимое число дней задолженности из условий оплаты
                allowed_debt_days = None
                payment_terms = contract_data.get("payment_terms")
                if payment_terms:
                    import re
                    # Ищем число дней отсрочки в тексте условий оплаты
                    days_patterns = [
                        r'(\d+)\s*календарн[ы]?х?\s*дн[ея]й?',
                        r'(\d+)\s*рабоч[иі]х?\s*дн[ея]й?',
                        r'(\d+)\s*дн[ея]й?\s*отсрочк',
                        r'отсрочк[аи]?\s*(\d+)\s*дн',
                        r'(\d+)\s*дн[ея]й?\s*оплат',
                        r'срок\s*не\s*более\s*(\d+)',
                        r'течение\s*(\d+)\s*дн'
                    ]
                    for pattern in days_patterns:
                        match = re.search(pattern, str(payment_terms), re.IGNORECASE)
                        if match:
                            try:
                                allowed_debt_days = int(match.group(1))
                                logger.info("Extracted allowed_debt_days from payment_terms",
                                           days=allowed_debt_days,
                                           pattern=pattern)
                                break
                            except (ValueError, IndexError):
                                continue
                
                # Подготавливаем все данные для создания контрагента согласно правилам 2.1-2.9
                params = {
                    "inn": contract_data.get("inn"),
                    "kpp": contract_data.get("kpp"),
                    "full_name": contract_data.get("full_name"),
                    "short_name": contract_data.get("short_name"),
                    "legal_entity_type": contract_data.get("legal_entity_type"),
                    "organizational_form": contract_data.get("organizational_form"),
                    "role": contract_data.get("role", ""),
                    "is_supplier": is_supplier,
                    "is_buyer": is_buyer,
                    # Дополнительные данные для правил 2.7, 2.8 и 2.9
                    "locations": contract_data.get("locations") or contract_data.get("service_locations"),
                    "responsible_persons": contract_data.get("responsible_persons"),
                    "service_start_date": contract_data.get("service_start_date"),
                    "service_end_date": contract_data.get("service_end_date"),
                    "contract_name": contract_data.get("contract_name"),
                    "contract_number": contract_data.get("contract_number"),
                    "contract_date": contract_data.get("contract_date"),
                    "contract_price": contract_data.get("contract_price"),
                    "vat_percent": contract_data.get("vat_percent"),
                    "vat_type": contract_data.get("vat_type"),
                    "service_description": contract_data.get("service_description"),
                    "services": contract_data.get("services"),
                    "acceptance_procedure": contract_data.get("acceptance_procedure"),
                    "specification_exists": contract_data.get("specification_exists"),
                    "pricing_method": contract_data.get("pricing_method"),
                    "reporting_forms": contract_data.get("reporting_forms"),
                    "additional_conditions": contract_data.get("additional_conditions"),
                    "technical_info": contract_data.get("technical_info"),
                    "task_execution_term": contract_data.get("task_execution_term"),
                    "customer": contract_data.get("customer"),
                    "contractor": contract_data.get("contractor"),
                    "raw_text": raw_text or contract_data.get("raw_text"),  # Для поиска фразы "протокол подведения итогов"
                    # Данные для договора
                    "organization_uuid": contract_data.get("organization_uuid"),  # UUID организации из 1С (если доступно)
                    "allowed_debt_days": allowed_debt_days,  # Допустимое число дней задолженности
                    "payment_terms": payment_terms,  # Условия оплаты для извлечения отсрочки
                }
                
                # Сериализуем данные для JSON (преобразуем date, datetime, Decimal)
                params_serialized = _serialize_for_json(params)
                
                async with session.post(
                    f"{self.mcp_service_url}/command",
                    json={
                        "command": "create_counterparty",
                        "params": params_serialized
                    },
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("status") == "success":
                            result = response_data.get("result", {})
                            counterparty_uuid = result.get("uuid")
                            entity_data = result.get("entity", {})
                            agreement_uuid = result.get("agreement_uuid")
                            
                            # Прикрепить файл контракта к договору (если создан) или к контрагенту
                            if counterparty_uuid and document_path:
                                await self.attach_file(counterparty_uuid, document_path, agreement_uuid=agreement_uuid)
                            
                            return {
                                'uuid': counterparty_uuid,
                                'entity': entity_data,
                                'agreement_uuid': agreement_uuid
                            }
                        else:
                            logger.error("Failed to create counterparty", 
                                       error=response_data.get("error"))
                            return None
                    else:
                        error_text = await response.text()
                        logger.error("Failed to create counterparty", 
                                   status=response.status,
                                   error=error_text)
                        return None
        except asyncio.TimeoutError:
            logger.error("Failed to create counterparty in 1C", error=f"Timeout after {self.timeout} seconds", error_type="timeout")
            return None
        except aiohttp.ClientError as e:
            logger.error("Failed to create counterparty in 1C", error=f"HTTP client error: {type(e).__name__}: {str(e)}", error_type="client_error")
            return None
        except Exception as e:
            logger.error("Failed to create counterparty in 1C", error=str(e) or f"Unknown error: {type(e).__name__}", error_type=type(e).__name__)
            return None
    
    async def attach_file(self, entity_uuid: str, file_path: str, agreement_uuid: Optional[str] = None) -> bool:
        """
        Прикрепить файл к сущности в 1С
        
        Args:
            entity_uuid: UUID контрагента в 1С
            file_path: Путь к файлу
            agreement_uuid: UUID договора (опционально) - если указан, файл прикрепляется к договору,
                           иначе к контрагенту
            
        Returns:
            True если успешно
        """
        try:
            import os
            
            # Проверяем существование файла
            if not os.path.exists(file_path):
                logger.error("File not found", file_path=file_path)
                return False
            
            file_name = os.path.basename(file_path)
            
            # Формируем параметры запроса
            params = {
                "counterparty_uuid": entity_uuid,
                "file_path": file_path,
                "file_name": file_name
            }
            
            # Если указан agreement_uuid, добавляем его для прикрепления к договору
            if agreement_uuid:
                params["agreement_uuid"] = agreement_uuid
                logger.info("Attaching file to agreement",
                           agreement_uuid=agreement_uuid,
                           counterparty_uuid=entity_uuid,
                           file_name=file_name)
            else:
                logger.info("Attaching file to counterparty",
                           counterparty_uuid=entity_uuid,
                           file_name=file_name)
            
            # Отправляем команду через JSON API
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.mcp_service_url}/command",
                    json={
                        "command": "attach_file",
                        "params": params
                    },
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("status") == "success":
                            target = "agreement" if agreement_uuid else "counterparty"
                            logger.info(f"File attached to {target}", 
                                      entity_uuid=entity_uuid,
                                      agreement_uuid=agreement_uuid,
                                      file_name=file_name)
                            return True
                        else:
                            logger.error("Failed to attach file", 
                                       error=response_data.get("error"),
                                       entity_uuid=entity_uuid,
                                       agreement_uuid=agreement_uuid)
                            return False
                    else:
                        error_text = await response.text()
                        logger.error("Failed to attach file", 
                                   status=response.status,
                                   error=error_text,
                                   entity_uuid=entity_uuid,
                                   agreement_uuid=agreement_uuid)
                        return False
        except asyncio.TimeoutError:
            logger.error("Failed to attach file",
                        error=f"Timeout after {self.timeout} seconds",
                        error_type="timeout",
                        entity_uuid=entity_uuid,
                        agreement_uuid=agreement_uuid)
            return False
        except aiohttp.ClientError as e:
            logger.error("Failed to attach file",
                        error=f"HTTP client error: {type(e).__name__}: {str(e)}",
                        error_type="client_error",
                        entity_uuid=entity_uuid,
                        agreement_uuid=agreement_uuid)
            return False
        except Exception as e:
            logger.error("Failed to attach file",
                        error=str(e) or f"Unknown error: {type(e).__name__}",
                        error_type=type(e).__name__,
                        entity_uuid=entity_uuid,
                        agreement_uuid=agreement_uuid)
            return False
    
    async def add_note_to_counterparty(self, counterparty_uuid: str, note_text: str, comment: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Добавить заметку к контрагенту в 1С
        
        Args:
            counterparty_uuid: UUID контрагента
            note_text: Текст заметки для поля "Представление"
            comment: Дополнительный комментарий для поля "Комментарий" (опционально)
            
        Returns:
            Dict с результатом создания заметки: {'created': bool, 'uuid': str, 'entity': dict} или None
        """
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "counterparty_uuid": counterparty_uuid,
                    "note_text": note_text
                }
                
                if comment:
                    params["comment"] = comment
                
                async with session.post(
                    f"{self.mcp_service_url}/command",
                    json={
                        "command": "add_note",
                        "params": params
                    },
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("status") == "success":
                            result = response_data.get("result", {})
                            logger.info("Note added to counterparty successfully",
                                      counterparty_uuid=counterparty_uuid,
                                      note_uuid=result.get("uuid"))
                            return result
                        else:
                            error_msg = response_data.get("error", "Unknown error")
                            logger.error("Failed to add note to counterparty",
                                      error=error_msg,
                                      counterparty_uuid=counterparty_uuid)
                            return None
                    else:
                        error_text = await response.text()
                        logger.error("Failed to add note to counterparty",
                                   status=response.status,
                                   error=error_text,
                                   counterparty_uuid=counterparty_uuid)
                        return None
        except asyncio.TimeoutError:
            logger.error("Failed to add note to counterparty in 1C",
                        error=f"Timeout after {self.timeout} seconds",
                        error_type="timeout",
                        counterparty_uuid=counterparty_uuid)
            return None
        except aiohttp.ClientError as e:
            logger.error("Failed to add note to counterparty in 1C",
                        error=f"HTTP client error: {type(e).__name__}: {str(e)}",
                        error_type="client_error",
                        counterparty_uuid=counterparty_uuid)
            return None
        except Exception as e:
            logger.error("Failed to add note to counterparty in 1C",
                        error=str(e) or f"Unknown error: {type(e).__name__}",
                        error_type=type(e).__name__,
                        counterparty_uuid=counterparty_uuid)
            return None