#!/usr/bin/env python3
"""
Тестовая функция для полной обработки документа через весь pipeline
Эмулирует загрузку файла пользователем и его полную обработку
"""
import asyncio
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Добавляем путь к backend в sys.path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from app.agent.orchestrator import AgentOrchestrator
from app.agent.state_manager import StateManager
from app.models.database import SessionLocal, Contract, ContractData, ProcessingHistory, Counterparty1C
from app.models.enums import ProcessingState
from app.services.document_processor import DocumentProcessor
from app.services.document_validator import DocumentValidator
from app.services.llm_service import LLMService
from app.services.oneс_service import OneCService
from app.services.storage_service import StorageService
from app.services.validation_service import ValidationService
from app.config import settings


async def test_full_processing(file_path: str):
    """
    Полная обработка документа через весь pipeline

    Параметры:
        - file_path: Путь к файлу документа (DOCX или PDF)
    """
    # Проверяем существование файла
    if not os.path.exists(file_path):
        print(f"❌ Ошибка: Файл не найден: {file_path}")
        return

    file_name = os.path.basename(file_path)
    file_ext = Path(file_path).suffix.lower()

    print(f"📄 Файл: {file_name}")
    print(f"📁 Путь: {file_path}")
    print(f"📋 Тип файла: {file_ext}")

    # Проверяем настройки LLM
    print(f"\n🤖 LLM Provider: {settings.LLM_PROVIDER}")
    print(f"🤖 LLM Model: {settings.LLM_MODEL}")
    print(f"🤖 Max Chunk Tokens: {settings.MAX_CHUNK_TOKENS}")

    if not settings.LLM_API_KEY:
        print("❌ Ошибка: LLM_API_KEY не задан в переменных окружения")
        return

    # Шаг 1: Валидация файла
    print(f"\n{'='*70}")
    print("ШАГ 1: ВАЛИДАЦИЯ ФАЙЛА")
    print(f"{'='*70}")

    is_valid, error_message = DocumentValidator.validate_file(file_path, file_name)
    if not is_valid:
        print(f"❌ Ошибка валидации: {error_message}")
        return
    print(f"✅ Файл прошел валидацию")

    # Шаг 2: Создание записи в БД
    print(f"\n{'='*70}")
    print("ШАГ 2: СОЗДАНИЕ ЗАПИСИ В БД")
    print(f"{'='*70}")

    db = SessionLocal()
    try:
        # Читаем файл для получения хеша
        storage_service = StorageService()
        with open(file_path, 'rb') as f:
            file_content = f.read()

        file_size = len(file_content)
        file_hash = storage_service._compute_hash(file_content)

        # Создаем запись Contract
        contract = Contract(
            original_filename=file_name,
            file_path=file_path,
            file_size_bytes=file_size,
            file_hash=file_hash,
            status=ProcessingState.UPLOADED,
            created_by="test_script"
        )
        db.add(contract)
        db.commit()
        db.refresh(contract)

        print(f"✅ Создана запись контракта")
        print(f"   ID: {contract.id}")
        print(f"   UUID: {contract.uuid}")
        print(f"   Размер файла: {file_size} байт")
        print(f"   Хеш: {file_hash}")

        contract_id = contract.id

    except Exception as e:
        print(f"❌ Ошибка создания записи в БД: {e}")
        db.rollback()
        db.close()
        return

    # Шаг 3: Инициализация компонентов
    print(f"\n{'='*70}")
    print("ШАГ 3: ИНИЦИАЛИЗАЦИЯ КОМПОНЕНТОВ")
    print(f"{'='*70}")

    try:
        state_manager = StateManager(redis_client=None, db_session=db)
        doc_processor = DocumentProcessor()
        llm_service = LLMService()
        validation_service = ValidationService()
        oneс_service = OneCService()

        print(f"✅ Все компоненты инициализированы")

    except Exception as e:
        print(f"❌ Ошибка инициализации компонентов: {e}")
        db.close()
        return

    # Шаг 4: Создание оркестратора и запуск обработки
    print(f"\n{'='*70}")
    print("ШАГ 4: ОБРАБОТКА ДОКУМЕНТА ЧЕРЕЗ ОРКЕСТРАТОР")
    print(f"{'='*70}")

    try:
        orchestrator = AgentOrchestrator(
            state_manager=state_manager,
            doc_processor=doc_processor,
            llm_service=llm_service,
            validation_service=validation_service,
            oneс_service=oneс_service
        )

        print(f"⏳ Запуск полной обработки контракта...")
        print(f"   Contract ID: {contract_id}")
        print(f"   Document Path: {file_path}")

        # Запускаем полный процесс обработки
        state = await orchestrator.process_contract(contract_id, file_path)

        print(f"\n✅ Обработка завершена")
        print(f"   Статус: {state.status.value}")
        if state.error_message:
            print(f"   Ошибка: {state.error_message}")

    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        db.close()
        return

    # Шаг 5: Вывод результатов
    print(f"\n{'='*70}")
    print("ШАГ 5: РЕЗУЛЬТАТЫ ОБРАБОТКИ")
    print(f"{'='*70}")

    try:
        # Получаем обновленные данные из БД
        contract = db.query(Contract).filter(Contract.id == contract_id).first()
        contract_data = db.query(ContractData).filter(
            ContractData.contract_id == contract_id
        ).first()
        counterparty_1c = None
        if contract_data:
            counterparty_1c = db.query(Counterparty1C).filter(
                Counterparty1C.contract_data_id == contract_data.id
            ).first()

        # Информация о контракте
        print(f"\n📋 КОНТРАКТ:")
        print(f"   Статус: {contract.status.value}")
        print(f"   Создан: {contract.created_at}")
        print(f"   Начало обработки: {contract.processing_started_at}")
        print(f"   Конец обработки: {contract.processing_completed_at}")
        if contract.error_message:
            print(f"   ⚠️  Ошибка: {contract.error_message}")

        # Информация о контрагенте
        if contract_data:
            print(f"\n👤 КОНТРАГЕНТ:")
            print(f"   ИНН: {contract_data.inn}")
            print(f"   КПП: {contract_data.kpp or 'Не указан'}")
            print(f"   Полное наименование: {contract_data.full_name or 'Не указано'}")
            print(f"   Краткое наименование: {contract_data.short_name or 'Не указано'}")
            print(f"   ОПФ: {contract_data.organizational_form or 'Не указана'}")
            if contract_data.legal_entity_type:
                print(f"   Тип: {contract_data.legal_entity_type.value}")

            # Роль контрагента
            roles = []
            if contract_data.is_supplier:
                roles.append("Поставщик")
            if contract_data.is_buyer:
                roles.append("Покупатель")
            if roles:
                print(f"   Роль: {', '.join(roles)}")

        # Информация о договоре
        if contract_data:
            print(f"\n📄 ДОГОВОР:")
            print(f"   Название: {contract_data.contract_name or 'Не указано'}")
            print(f"   Номер: {contract_data.contract_number or 'Не указан'}")
            print(f"   Дата: {contract_data.contract_date or 'Не указана'}")
            if contract_data.contract_price:
                print(f"   Цена: {contract_data.contract_price} руб.")
            if contract_data.vat_type:
                print(f"   НДС: {contract_data.vat_type.value}")
                if contract_data.vat_percent:
                    print(f"   Процент НДС: {contract_data.vat_percent}%")

        # Информация об услугах
        if contract_data and contract_data.services:
            print(f"\n🛠️  УСЛУГИ (краткая спецификация):")
            services = contract_data.services
            if isinstance(services, list):
                for i, service in enumerate(services[:5], 1):  # Показываем первые 5
                    if isinstance(service, dict):
                        name = service.get('name', 'Без названия')
                        print(f"   {i}. {name}")
                if len(services) > 5:
                    print(f"   ... и еще {len(services) - 5} услуг")

        # Информация о всех услугах
        if contract_data and contract_data.all_services:
            all_services = contract_data.all_services
            if isinstance(all_services, list):
                print(f"\n📋 ВСЕ УСЛУГИ: {len(all_services)} шт.")

                # Считаем общую сумму
                total_sum = 0
                for service in all_services:
                    if isinstance(service, dict):
                        total_price = service.get('total_price', 0)
                        if isinstance(total_price, (int, float)):
                            total_sum += total_price

                if total_sum > 0:
                    print(f"   💰 Общая стоимость: {total_sum} руб.")

        # Информация о 1С
        if counterparty_1c:
            print(f"\n🏢 1С:")
            print(f"   UUID: {counterparty_1c.entity_uuid or 'Не создан'}")
            print(f"   Наименование: {counterparty_1c.entity_name or 'Не указано'}")
            if counterparty_1c.status_1c:
                print(f"   Статус: {counterparty_1c.status_1c.value}")
            if counterparty_1c.created_in_1c_at:
                print(f"   Создан: {counterparty_1c.created_in_1c_at}")
            if counterparty_1c.error_from_1c:
                print(f"   ⚠️  Ошибка: {counterparty_1c.error_from_1c}")

        # История обработки
        history = db.query(ProcessingHistory).filter(
            ProcessingHistory.contract_id == contract_id
        ).order_by(ProcessingHistory.created_at.asc()).all()

        if history:
            print(f"\n📜 ИСТОРИЯ ОБРАБОТКИ ({len(history)} событий):")
            for event in history:
                print(f"   - [{event.event_type}] {event.event_message}")
                if event.event_status:
                    print(f"     Статус: {event.event_status.value}")

        # Сохраняем полный результат в JSON
        output_file = file_path + ".full_processing.json"
        result_data = {
            'contract': {
                'id': contract.id,
                'uuid': str(contract.uuid),
                'status': contract.status.value,
                'filename': contract.original_filename,
                'created_at': contract.created_at.isoformat() if contract.created_at else None,
                'processing_started_at': contract.processing_started_at.isoformat() if contract.processing_started_at else None,
                'processing_completed_at': contract.processing_completed_at.isoformat() if contract.processing_completed_at else None,
                'error_message': contract.error_message
            },
            'contract_data': None,
            'counterparty_1c': None,
            'history': []
        }

        if contract_data:
            result_data['contract_data'] = {
                'inn': contract_data.inn,
                'kpp': contract_data.kpp,
                'full_name': contract_data.full_name,
                'short_name': contract_data.short_name,
                'organizational_form': contract_data.organizational_form,
                'legal_entity_type': contract_data.legal_entity_type.value if contract_data.legal_entity_type else None,
                'is_supplier': contract_data.is_supplier,
                'is_buyer': contract_data.is_buyer,
                'contract_name': contract_data.contract_name,
                'contract_number': contract_data.contract_number,
                'contract_date': contract_data.contract_date.isoformat() if contract_data.contract_date else None,
                'contract_price': float(contract_data.contract_price) if contract_data.contract_price else None,
                'vat_percent': float(contract_data.vat_percent) if contract_data.vat_percent else None,
                'vat_type': contract_data.vat_type.value if contract_data.vat_type else None,
                'service_description': contract_data.service_description,
                'services': contract_data.services,
                'all_services': contract_data.all_services,
                'service_start_date': contract_data.service_start_date.isoformat() if contract_data.service_start_date else None,
                'service_end_date': contract_data.service_end_date.isoformat() if contract_data.service_end_date else None,
                'locations': contract_data.locations,
                'responsible_persons': contract_data.responsible_persons,
                'customer': contract_data.customer,
                'contractor': contract_data.contractor
            }

        if counterparty_1c:
            result_data['counterparty_1c'] = {
                'entity_uuid': counterparty_1c.entity_uuid,
                'entity_name': counterparty_1c.entity_name,
                'status_1c': counterparty_1c.status_1c.value if counterparty_1c.status_1c else None,
                'created_in_1c_at': counterparty_1c.created_in_1c_at.isoformat() if counterparty_1c.created_in_1c_at else None,
                'response_from_1c': counterparty_1c.response_from_1c,
                'error_from_1c': counterparty_1c.error_from_1c
            }

        for event in history:
            result_data['history'].append({
                'event_type': event.event_type,
                'event_status': event.event_status.value if event.event_status else None,
                'event_message': event.event_message,
                'event_details': event.event_details,
                'created_at': event.created_at.isoformat() if event.created_at else None
            })

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        print(f"\n💾 Полный результат сохранен в: {output_file}")

    except Exception as e:
        print(f"❌ Ошибка вывода результатов: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


def main():
    """Точка входа"""
    # Загружаем переменные окружения
    load_dotenv()

    # Путь к файлу для тестирования
    # Можно передать как аргумент командной строки или использовать значение по умолчанию
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        # Значение по умолчанию - укажите свой путь
        # file_path = "/Users/igorgerasimov/cursorWorkspace/orc-konter-agent-to-1c/storage/contracts/uploaded/00a08716-f1d7-485c-a015-275223d5a828.docx"
        file_path = "/Users/igorgerasimov/cursorWorkspace/orc-konter-agent-to-1c/storage/contracts/uploaded/90977cde-e531-4ea3-ab9a-6c8483bf339f.docx"

    print("=" * 70)
    print("ТЕСТ ПОЛНОЙ ОБРАБОТКИ ДОКУМЕНТА")
    print("=" * 70)
    print()
    print("Этот скрипт эмулирует полный процесс обработки документа,")
    print("как если бы пользователь загрузил его через веб-интерфейс:")
    print()
    print("1. Валидация файла")
    print("2. Создание записи в БД")
    print("3. Инициализация компонентов")
    print("4. Обработка через оркестратор:")
    print("   - Загрузка документа")
    print("   - Извлечение текста")
    print("   - Извлечение данных контракта (LLM)")
    print("   - Извлечение всех услуг (LLM)")
    print("   - Валидация данных")
    print("   - Проверка в 1С")
    print("   - Создание контрагента в 1С")
    print("5. Сохранение результатов")
    print()
    print("=" * 70)
    print()

    # Запускаем тест
    asyncio.run(test_full_processing(file_path))

    print("\n" + "=" * 70)
    print("ТЕСТ ЗАВЕРШЕН")
    print("=" * 70)


if __name__ == "__main__":
    main()
