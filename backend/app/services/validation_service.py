"""
Валидация извлеченных данных контракта
"""
import re
from typing import Dict, Any, List
from decimal import Decimal

from pydantic import ValidationError

from app.config import settings
from app.models.contract_schemas import ContractDataSchema
from app.models.enums import LegalEntityType
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ValidationService:
    """Сервис валидации извлеченных данных"""
    
    def __init__(self, strict_mode: bool = None):
        self.strict_mode = strict_mode if strict_mode is not None else settings.VALIDATION_STRICT_MODE
    
    def validate_contract_data(self, data: Dict[str, Any], auto_correct: bool = True) -> Dict[str, Any]:
        """
        Валидировать данные контракта
        
        Args:
            data: Словарь с извлеченными данными
            auto_correct: Применять ли автоматическую коррекцию перед валидацией
            
        Returns:
            {
                'is_valid': bool,
                'errors': List[str],
                'warnings': List[str],
                'validated_data': Dict or None
            }
        """
        errors: List[str] = []
        warnings: List[str] = []
        validated_data = None
        
        # Автоматическая коррекция данных перед валидацией
        if auto_correct:
            data = self.auto_correct_data(data)
        
        try:
            # Попытаться валидировать по Pydantic схеме
            validated_data = ContractDataSchema(**data)
            
            # Дополнительные проверки после базовой валидации
            additional_checks = self._perform_additional_checks(validated_data)
            
            if additional_checks['has_errors']:
                errors.extend(additional_checks['errors'])
            
            if additional_checks['has_warnings']:
                warnings.extend(additional_checks['warnings'])
            
            logger.info("Data validation completed",
                       has_errors=len(errors) > 0,
                       has_warnings=len(warnings) > 0)
            
        except ValidationError as e:
            logger.error("Validation failed", error=str(e))
            
            for error in e.errors():
                field = '.'.join(str(x) for x in error['loc'])
                message = error['msg']
                errors.append(f"{field}: {message}")
        
        except Exception as e:
            logger.error("Unexpected validation error", error=str(e))
            errors.append(f"Unexpected error: {str(e)}")
        
        is_valid = len(errors) == 0
        
        # В strict mode даже warnings делают результат невалидным
        if self.strict_mode and len(warnings) > 0:
            is_valid = False
        
        return {
            'is_valid': is_valid,
            'errors': errors,
            'warnings': warnings,
            'validated_data': validated_data.model_dump() if validated_data else None
        }
    
    def auto_correct_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Автоматическая коррекция данных перед валидацией
        
        Args:
            data: Словарь с извлеченными данными
            
        Returns:
            Словарь с исправленными данными
        """
        # Нормализация ключей: приведение к snake_case и нижнему регистру
        corrected_data = {}
        key_mapping = {
            'INN': 'inn',
            'KPP': 'kpp',
            'Full Name': 'full_name',
            'FullName': 'full_name',
            'Short Name': 'short_name',
            'ShortName': 'short_name',
            'Organizational Form': 'organizational_form',
            'OrganizationalForm': 'organizational_form',
            'Legal Entity Type': 'legal_entity_type',
            'LegalEntityType': 'legal_entity_type',
            'Contract Name': 'contract_name',
            'ContractName': 'contract_name',
            'Contract Number': 'contract_number',
            'ContractNumber': 'contract_number',
            'Contract Date': 'contract_date',
            'ContractDate': 'contract_date',
            'Contract Price': 'contract_price',
            'ContractPrice': 'contract_price',
            'VAT Percent': 'vat_percent',
            'VATPercent': 'vat_percent',
            'VAT Type': 'vat_type',
            'VATType': 'vat_type',
            'Service Description': 'service_description',
            'ServiceDescription': 'service_description',
            'Service Start Date': 'service_start_date',
            'ServiceStartDate': 'service_start_date',
            'Service End Date': 'service_end_date',
            'ServiceEndDate': 'service_end_date',
            'Role': 'role',
            'Is Supplier': 'is_supplier',
            'IsSupplier': 'is_supplier',
            'Is Buyer': 'is_buyer',
            'IsBuyer': 'is_buyer',
        }
        
        # Нормализация ключей
        for key, value in data.items():
            # Проверяем маппинг
            normalized_key = key_mapping.get(key, key.lower().replace(' ', '_').replace('-', '_'))
            # Убираем множественные подчеркивания
            normalized_key = re.sub(r'_+', '_', normalized_key).strip('_')
            corrected_data[normalized_key] = value
        
        # Приведение ИНН к строке без спецсимволов
        if 'inn' in corrected_data:
            inn_value = str(corrected_data['inn'])
            # Сначала пытаемся найти ИНН с префиксом (ИНН:, ИНН , inn: и т.д.)
            inn_pattern = re.compile(r'(?:ИНН|inn|INN)[\s:=\-]*(\d{10,12})', re.IGNORECASE)
            match = inn_pattern.search(inn_value)
            if match:
                inn_clean = match.group(1)
            else:
                # Если префикс не найден, просто удаляем все нецифровые символы
                inn_clean = re.sub(r'\D', '', inn_value)
            
            if inn_clean:
                corrected_data['inn'] = inn_clean
                logger.debug("Cleaned INN", original=inn_value, cleaned=inn_clean)
        
        # Приведение КПП к строке без спецсимволов
        if 'kpp' in corrected_data and corrected_data['kpp']:
            kpp_value = str(corrected_data['kpp'])
            kpp_clean = re.sub(r'\D', '', kpp_value)
            if kpp_clean:
                corrected_data['kpp'] = kpp_clean
                logger.debug("Cleaned KPP", original=kpp_value, cleaned=kpp_clean)
        
        # Нормализация пробелов в текстовых полях
        text_fields = ['full_name', 'short_name', 'organizational_form', 'contract_name', 
                      'contract_number', 'service_description', 'payment_terms']
        for field in text_fields:
            if field in corrected_data and corrected_data[field]:
                original = corrected_data[field]
                normalized = re.sub(r'\s+', ' ', str(original)).strip()
                if normalized != original:
                    corrected_data[field] = normalized
                    logger.debug("Normalized text field", field=field, original=original, normalized=normalized)
        
        # Установка правильного типа юр.лица по ИНН
        if 'inn' in corrected_data and 'legal_entity_type' in corrected_data:
            inn = corrected_data['inn']
            if isinstance(inn, str) and inn.isdigit():
                inn_len = len(inn)
                if inn_len == 10:
                    # 10 цифр - юридическое лицо
                    if corrected_data.get('legal_entity_type') != LegalEntityType.LEGAL.value:
                        logger.info("Auto-correcting legal_entity_type", 
                                   inn=inn, 
                                   old_type=corrected_data.get('legal_entity_type'),
                                   new_type=LegalEntityType.LEGAL.value)
                        corrected_data['legal_entity_type'] = LegalEntityType.LEGAL.value
                elif inn_len == 12:
                    # 12 цифр - физическое лицо
                    if corrected_data.get('legal_entity_type') != LegalEntityType.INDIVIDUAL.value:
                        logger.info("Auto-correcting legal_entity_type",
                                   inn=inn,
                                   old_type=corrected_data.get('legal_entity_type'),
                                   new_type=LegalEntityType.INDIVIDUAL.value)
                        corrected_data['legal_entity_type'] = LegalEntityType.INDIVIDUAL.value
        
        # Удаление КПП для физических лиц
        if 'inn' in corrected_data and 'kpp' in corrected_data:
            inn = corrected_data['inn']
            if isinstance(inn, str) and len(inn) == 12:
                if corrected_data.get('kpp'):
                    logger.info("Removing KPP for individual", inn=inn)
                    corrected_data['kpp'] = None
        
        # Нормализация responsible_persons - преобразование списков в строки для phone и email
        if 'responsible_persons' in corrected_data and isinstance(corrected_data['responsible_persons'], list):
            normalized_persons = []
            for person in corrected_data['responsible_persons']:
                if isinstance(person, dict):
                    normalized_person = person.copy()
                    # Нормализуем phone - если список, преобразуем в строку
                    if 'phone' in normalized_person:
                        phone = normalized_person['phone']
                        if isinstance(phone, (list, tuple)):
                            normalized_person['phone'] = ', '.join(str(p) for p in phone if p) if phone else None
                        elif phone is None or phone == []:
                            normalized_person['phone'] = None
                    
                    # Нормализуем email - если список, преобразуем в строку
                    if 'email' in normalized_person:
                        email = normalized_person['email']
                        if isinstance(email, (list, tuple)):
                            normalized_person['email'] = ', '.join(str(e) for e in email if e) if email else None
                        elif email is None or email == []:
                            normalized_person['email'] = None
                    
                    # Нормализуем name - если список, преобразуем в строку
                    if 'name' in normalized_person:
                        name = normalized_person['name']
                        if isinstance(name, (list, tuple)):
                            normalized_person['name'] = ', '.join(str(n) for n in name if n) if name else None
                    
                    normalized_persons.append(normalized_person)
                else:
                    normalized_persons.append(person)
            corrected_data['responsible_persons'] = normalized_persons
        
        # Если обязательные поля отсутствуют, но есть customer или contractor, заполняем их из них
        if 'inn' not in corrected_data or not corrected_data.get('inn'):
            # Пробуем взять ИНН из customer или contractor
            if 'customer' in corrected_data and isinstance(corrected_data['customer'], dict):
                customer = corrected_data['customer']
                if customer.get('inn'):
                    corrected_data['inn'] = customer['inn']
                    if 'full_name' not in corrected_data and customer.get('full_name'):
                        corrected_data['full_name'] = customer['full_name']
                    if 'short_name' not in corrected_data and customer.get('short_name'):
                        corrected_data['short_name'] = customer['short_name']
                    if 'organizational_form' not in corrected_data and customer.get('organizational_form'):
                        corrected_data['organizational_form'] = customer['organizational_form']
                    if 'legal_entity_type' not in corrected_data and customer.get('legal_entity_type'):
                        corrected_data['legal_entity_type'] = customer['legal_entity_type']
                    if 'kpp' not in corrected_data and customer.get('kpp'):
                        corrected_data['kpp'] = customer['kpp']
                    if 'is_buyer' not in corrected_data:
                        corrected_data['is_buyer'] = True
            
            elif 'contractor' in corrected_data and isinstance(corrected_data['contractor'], dict):
                contractor = corrected_data['contractor']
                if contractor.get('inn'):
                    corrected_data['inn'] = contractor['inn']
                    if 'full_name' not in corrected_data and contractor.get('full_name'):
                        corrected_data['full_name'] = contractor['full_name']
                    if 'short_name' not in corrected_data and contractor.get('short_name'):
                        corrected_data['short_name'] = contractor['short_name']
                    if 'organizational_form' not in corrected_data and contractor.get('organizational_form'):
                        corrected_data['organizational_form'] = contractor['organizational_form']
                    if 'legal_entity_type' not in corrected_data and contractor.get('legal_entity_type'):
                        corrected_data['legal_entity_type'] = contractor['legal_entity_type']
                    if 'kpp' not in corrected_data and contractor.get('kpp'):
                        corrected_data['kpp'] = contractor['kpp']
                    if 'is_supplier' not in corrected_data:
                        corrected_data['is_supplier'] = True
        
        logger.info("Data auto-correction completed", corrections_applied=True)
        return corrected_data
    
    def _perform_additional_checks(self, data: ContractDataSchema) -> Dict[str, Any]:
        """Выполнить дополнительные проверки"""
        errors: List[str] = []
        warnings: List[str] = []
        
        # Если ИНН отсутствует, пропускаем проверки связанные с ИНН
        if not data.inn:
            return {
                'has_errors': len(errors) > 0,
                'has_warnings': len(warnings) > 0,
                'errors': errors,
                'warnings': warnings
            }
        
        # Проверка на совместимость ИНН и типа юридического лица
        # Эта проверка уже выполняется в валидаторах схемы, но оставляем для дополнительной проверки
        inn_len = len(data.inn)
        if inn_len == 10 and data.legal_entity_type == LegalEntityType.INDIVIDUAL:
            errors.append("ИНН из 10 цифр не соответствует типу 'Физическое лицо' (должно быть 12 цифр)")
        
        if inn_len == 12 and data.legal_entity_type == LegalEntityType.LEGAL:
            errors.append("ИНН из 12 цифр не соответствует типу 'Юридическое лицо' (должно быть 10 цифр)")
        
        # Проверка КПП для юридических лиц
        if data.legal_entity_type == LegalEntityType.LEGAL and inn_len == 10:
            if not data.kpp:
                warnings.append("Для юридического лица рекомендуется указать КПП")
            elif data.kpp and len(data.kpp) != 9:
                errors.append(f"КПП должен содержать 9 цифр, получено {len(data.kpp)}")
        
        if inn_len == 12 and data.kpp:
            errors.append("КПП не должен присутствовать для физического лица (12-значный ИНН)")
        
        # Проверка наименования
        if data.organizational_form and data.full_name:
            if data.organizational_form.lower() not in data.full_name.lower():
                warnings.append(f"ОПФ '{data.organizational_form}' не найдена в полном наименовании")
        
        # Проверка совместимости ИНН и КПП (первые 4 цифры КПП должны совпадать с первыми 4 цифрами ИНН)
        if data.kpp and inn_len == 10:
            if len(data.kpp) == 9 and data.inn[:4] != data.kpp[:4]:
                warnings.append("Первые 4 цифры КПП обычно совпадают с первыми 4 цифрами ИНН")
        
        # Проверка дат (базовая проверка уже в валидаторах схемы)
        if data.contract_date and data.service_start_date:
            if data.service_start_date < data.contract_date:
                errors.append("Дата начала услуг не может быть раньше даты договора")
        
        if data.service_start_date and data.service_end_date:
            if data.service_end_date < data.service_start_date:
                errors.append("Дата окончания услуг не может быть раньше даты начала")
        
        # Проверка цены
        if data.contract_price is not None:
            if data.contract_price <= 0:
                errors.append("Цена договора должна быть положительной")
        
        # Проверка НДС
        if data.vat_type == "Без НДС" and data.vat_percent and data.vat_percent > 0:
            warnings.append("Указан процент НДС при типе 'Без НДС'")
        
        # Проверка уверенности извлечения
        if data.extraction_confidence is not None:
            if data.extraction_confidence < 0.5:
                warnings.append("Низкая уверенность в извлечении данных (< 0.5)")
        
        return {
            'has_errors': len(errors) > 0,
            'has_warnings': len(warnings) > 0,
            'errors': errors,
            'warnings': warnings
        }
