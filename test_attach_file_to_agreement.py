#!/usr/bin/env python3
"""
Тестовая функция для привязки документа к договору в 1С через OData
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Добавляем путь к mcp_service в sys.path
sys.path.insert(0, str(Path(__file__).parent / 'mcp_service'))

from client.oneс_client import OneCClient


async def test_attach_file_to_agreement():
    """
    Тестовая функция для привязки документа к договору в 1С
    
    Параметры:
        - agreement_uuid: UUID договора в 1С
        - file_path: Путь к файлу для прикрепления
    """
    # Загружаем переменные окружения
    load_dotenv()
    
    # Параметры теста
    agreement_uuid = "4275ee2e-0118-11f1-9d06-7085c2496eb6"
    file_path = "/Users/igorgerasimov/cursorWorkspace/orc-konter-agent-to-1c/storage/contracts/uploaded/00a08716-f1d7-485c-a015-275223d5a828.docx"
    
    # Проверяем существование файла
    if not os.path.exists(file_path):
        print(f"❌ Ошибка: Файл не найден: {file_path}")
        return
    
    # Получаем имя файла
    file_name = os.path.basename(file_path)
    print(f"📄 Файл: {file_name}")
    print(f"📋 UUID договора: {agreement_uuid}")
    print(f"📁 Путь к файлу: {file_path}")
    
    # Читаем файл
    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()
        print(f"✅ Файл прочитан успешно. Размер: {len(file_data)} байт")
    except Exception as e:
        print(f"❌ Ошибка при чтении файла: {e}")
        return
    
    # Настраиваем клиент 1С
    config = {
        'ONEС_ODATA_URL': os.getenv('ONEС_ODATA_URL', ''),
        'ONEС_USERNAME': os.getenv('ONEС_USERNAME', ''),
        'ONEС_PASSWORD': os.getenv('ONEС_PASSWORD', ''),
    }
    
    if not config['ONEС_ODATA_URL']:
        print("❌ Ошибка: ONEС_ODATA_URL не задан в переменных окружения")
        return
    
    print(f"\n🔌 Подключение к 1С: {config['ONEС_ODATA_URL']}")
    print(f"👤 Пользователь: {config['ONEС_USERNAME']}")
    
    # Создаем и инициализируем клиент
    client = OneCClient(config)
    
    try:
        # Инициализируем сессию
        await client.initialize()
        print("✅ Клиент 1С инициализирован")
        
        # Проверяем существование договора перед прикреплением файла
        print(f"\n🔍 Проверка существования договора...")
        try:
            agreement_query = f"Catalog_ДоговорыКонтрагентов(guid'{agreement_uuid}')"
            agreement_data = await client.execute_query(agreement_query)
            if agreement_data:
                print(f"✅ Договор найден: {agreement_data.get('Description', 'Без названия')}")
            else:
                print(f"⚠️  Договор не найден, но продолжаем попытку прикрепления файла")
        except Exception as e:
            print(f"⚠️  Не удалось проверить договор: {e}")
            print(f"   Продолжаем попытку прикрепления файла...")
        
        # Прикрепляем файл к договору
        print(f"\n📎 Прикрепление файла к договору...")
        result = await client.attach_file(
            entity_type='Catalog_ДоговорыКонтрагентов',
            uuid=agreement_uuid,
            file_name=file_name,
            file_data=file_data,
            object_type='StandardODATA.Catalog_ДоговорыКонтрагентов'
        )
        
        if result.get('attached'):
            print("\n✅ Файл успешно прикреплен к договору!")
            print(f"   UUID файла в хранилище: {result.get('file_uuid')}")
            print(f"   Имя файла: {result.get('file_name')}")
            print(f"   Размер файла: {result.get('file_size')} байт")
            print(f"   UUID договора: {result.get('entity_uuid')}")
        else:
            print("\n❌ Ошибка: Файл не был прикреплен")
            print(f"   Результат: {result}")
            
    except Exception as e:
        print(f"\n❌ Ошибка при прикреплении файла: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Закрываем сессию
        await client.close()
        print("\n🔌 Сессия закрыта")


if __name__ == "__main__":
    print("=" * 70)
    print("Тест привязки документа к договору в 1С через OData")
    print("=" * 70)
    print()
    
    # Запускаем тест
    asyncio.run(test_attach_file_to_agreement())
    
    print("\n" + "=" * 70)
    print("Тест завершен")
    print("=" * 70)
