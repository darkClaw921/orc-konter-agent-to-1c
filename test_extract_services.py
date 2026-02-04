#!/usr/bin/env python3
"""
Тестовая функция для проверки извлечения услуг из документа через LLM
"""
import asyncio
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Добавляем путь к backend в sys.path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from app.services.document_processor import DocumentProcessor
from app.services.llm_service import LLMService
from app.config import settings


async def test_extract_services(file_path: str):
    """
    Тестовая функция для извлечения услуг из документа

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

    # Загружаем и обрабатываем документ
    print(f"\n📖 Загрузка документа...")
    processor = DocumentProcessor()

    if not processor.load_document(file_path):
        print(f"❌ Ошибка: Не удалось загрузить документ")
        return

    print(f"✅ Документ загружен")

    # Извлекаем текст
    print(f"\n📝 Извлечение текста...")
    text = processor.extract_text()
    print(f"✅ Текст извлечен: {len(text)} символов")
    print(f"   Параграфов: {len(processor.paragraphs)}")
    print(f"   Таблиц: {len(processor.tables)}")
    print(f"   Элементов: {len(processor.document_elements)}")

    # Получаем чанки для LLM
    print(f"\n🔪 Разбиение на чанки...")
    chunks = processor.get_chunks_for_llm()
    print(f"✅ Создано чанков: {len(chunks)}")

    for i, chunk in enumerate(chunks, 1):
        tokens_estimate = len(chunk) // 4
        print(f"   Чанк {i}: {len(chunk)} символов (~{tokens_estimate} токенов)")

    # Создаем LLM сервис
    print(f"\n🤖 Инициализация LLM сервиса...")
    try:
        llm_service = LLMService()
        print(f"✅ LLM сервис инициализирован")
    except Exception as e:
        print(f"❌ Ошибка инициализации LLM сервиса: {e}")
        return

    # Извлекаем услуги из чанков
    print(f"\n🔍 Извлечение услуг из {len(chunks)} чанков (параллельно)...")
    try:
        services = await llm_service.extract_services_from_chunks(chunks)
        print(f"✅ Услуги извлечены: {len(services)} шт.")
    except Exception as e:
        print(f"❌ Ошибка извлечения услуг: {e}")
        import traceback
        traceback.print_exc()
        return

    # Выводим найденные услуги
    if services:
        print(f"\n{'='*70}")
        print(f"📋 НАЙДЕННЫЕ УСЛУГИ ({len(services)} шт.)")
        print(f"{'='*70}")

        total_sum = 0
        for i, service in enumerate(services, 1):
            name = service.get('name', 'Без названия')
            quantity = service.get('quantity', '-')
            unit = service.get('unit', '-')
            unit_price = service.get('unit_price', 0)
            total_price = service.get('total_price', 0)
            description = service.get('description', '')

            print(f"\n{i}. {name}")
            print(f"   Количество: {quantity} {unit}")
            print(f"   Цена за единицу: {unit_price}")
            print(f"   Общая стоимость: {total_price}")
            if description:
                print(f"   Описание: {description[:100]}{'...' if len(description) > 100 else ''}")

            if isinstance(total_price, (int, float)):
                total_sum += total_price

        print(f"\n{'='*70}")
        print(f"💰 ИТОГО: {total_sum}")
        print(f"{'='*70}")

        # Сохраняем результат в JSON
        output_file = file_path + ".services.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'file': file_name,
                'chunks_count': len(chunks),
                'services_count': len(services),
                'total_sum': total_sum,
                'services': services
            }, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Результат сохранен в: {output_file}")
    else:
        print(f"\n⚠️  Услуги не найдены в документе")


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
        file_path = "/Users/igorgerasimov/cursorWorkspace/orc-konter-agent-to-1c/storage/contracts/uploaded/00a08716-f1d7-485c-a015-275223d5a828.docx"

    print("=" * 70)
    print("Тест извлечения услуг из документа через LLM")
    print("=" * 70)
    print()

    # Запускаем тест
    asyncio.run(test_extract_services(file_path))

    print("\n" + "=" * 70)
    print("Тест завершен")
    print("=" * 70)


if __name__ == "__main__":
    main()
