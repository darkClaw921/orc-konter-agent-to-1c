"""
Интеграция с 1С через MCP
"""
import aiohttp
from typing import Dict, Any, Optional

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class OneCService:
    """Сервис для работы с 1С через MCP Service"""
    
    def __init__(self):
        self.mcp_service_url = settings.MCP_SERVICE_URL
        self.timeout = 30
    
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
        except Exception as e:
            logger.error("Failed to check counterparty in 1C", error=str(e), inn=inn)
            return {"_error": str(e)}
    
    async def create_counterparty(self, contract_data: Dict[str, Any], document_path: str) -> Optional[str]:
        """
        Создать контрагента в 1С
        
        Args:
            contract_data: Извлеченные данные контракта
            document_path: Путь к файлу контракта
            
        Returns:
            UUID созданного контрагента
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Определяем роль контрагента
                role_value = contract_data.get("role")
                role = str(role_value or "").lower()
                is_supplier = "поставщик" in role or "продавец" in role or "исполнитель" in role
                is_buyer = "покупатель" in role or "заказчик" in role
                
                async with session.post(
                    f"{self.mcp_service_url}/command",
                    json={
                        "command": "create_counterparty",
                        "params": {
                            "inn": contract_data.get("inn"),
                            "kpp": contract_data.get("kpp"),
                            "full_name": contract_data.get("full_name"),
                            "short_name": contract_data.get("short_name"),
                            "legal_entity_type": contract_data.get("legal_entity_type"),
                            "organizational_form": contract_data.get("organizational_form"),
                            "is_supplier": is_supplier,
                            "is_buyer": is_buyer,
                        }
                    },
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("status") == "success":
                            result = response_data.get("result", {})
                            counterparty_uuid = result.get("uuid")
                            
                            # Прикрепить файл контракта
                            if counterparty_uuid and document_path:
                                await self.attach_file(counterparty_uuid, document_path)
                            
                            return counterparty_uuid
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
        except Exception as e:
            logger.error("Failed to create counterparty in 1C", error=str(e))
            return None
    
    async def attach_file(self, entity_uuid: str, file_path: str) -> bool:
        """
        Прикрепить файл к сущности в 1С
        
        Args:
            entity_uuid: UUID сущности в 1С
            file_path: Путь к файлу
            
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
            
            # Отправляем команду через JSON API
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.mcp_service_url}/command",
                    json={
                        "command": "attach_file",
                        "params": {
                            "counterparty_uuid": entity_uuid,
                            "file_path": file_path,
                            "file_name": file_name
                        }
                    },
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get("status") == "success":
                            logger.info("File attached to counterparty", 
                                      entity_uuid=entity_uuid,
                                      file_name=file_name)
                            return True
                        else:
                            logger.error("Failed to attach file", 
                                       error=response_data.get("error"),
                                       entity_uuid=entity_uuid)
                            return False
                    else:
                        error_text = await response.text()
                        logger.error("Failed to attach file", 
                                   status=response.status,
                                   error=error_text,
                                   entity_uuid=entity_uuid)
                        return False
        except Exception as e:
            logger.error("Failed to attach file", error=str(e), entity_uuid=entity_uuid)
            return False
