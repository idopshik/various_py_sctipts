import can
from pathlib import Path
import numpy as np

def fix_blf_timestamps(input_path, output_path=None):
    """
    Исправляет временные метки в BLF файле, делая их консистентными.
    Преобразует смешанные/абсолютные метки в относительные от 0.
    """
    input_path = Path(input_path)

    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_fixed_timestamps{input_path.suffix}"

    print(f"Исправление временных меток в файле: {input_path}")
    print(f"Выходной файл: {output_path}")

    try:
        with can.BLFReader(input_path) as reader:
            # Первый проход: анализ временной структуры
            print("Анализ временной структуры...")
            time_info = analyze_time_structure_detailed(reader)
            print_time_analysis(time_info)

            # Второй проход: исправление и запись
            print("Исправление временных меток...")
            return rewrite_with_fixed_timestamps(reader, output_path, time_info)

    except Exception as e:
        print(f"Ошибка при обработке файла: {e}")
        import traceback
        traceback.print_exc()
        return False

def analyze_time_structure_detailed(reader):
    """
    Детальный анализ временной структуры файла
    """
    messages = []
    time_deltas = []
    previous_time = None
    has_relative = False
    has_absolute = False
    absolute_times = []
    relative_times = []

    # Собираем информацию о всех сообщениях
    for i, message in enumerate(reader):
        messages.append(message)

        # Определяем тип времени
        if message.timestamp < 1000000:  # Относительное время
            has_relative = True
            relative_times.append(message.timestamp)
        else:  # Абсолютное время
            has_absolute = True
            absolute_times.append(message.timestamp)

        # Вычисляем дельты между сообщениями
        if previous_time is not None:
            time_deltas.append(message.timestamp - previous_time)
        previous_time = message.timestamp

        # Прогресс для больших файлов
        if (i + 1) % 100000 == 0:
            print(f"Проанализировано {i + 1} сообщений...")

    # Определяем общий тип
    if has_relative and has_absolute:
        time_type = 'mixed'
    elif has_absolute:
        time_type = 'absolute'
    else:
        time_type = 'relative'

    # Находим точку перехода (если есть)
    transition_index = None
    if time_type == 'mixed':
        for i, msg in enumerate(messages):
            if i > 0 and msg.timestamp >= 1000000 and messages[i-1].timestamp < 1000000:
                transition_index = i
                break

    return {
        'type': time_type,
        'messages': messages,
        'time_deltas': time_deltas,
        'transition_index': transition_index,
        'absolute_times': absolute_times,
        'relative_times': relative_times,
        'min_time': min([msg.timestamp for msg in messages]),
        'max_time': max([msg.timestamp for msg in messages]),
        'message_count': len(messages)
    }

def print_time_analysis(time_info):
    """
    Выводит детальную информацию о временной структуре
    """
    print(f"\n=== РЕЗУЛЬТАТЫ АНАЛИЗА ===")
    print(f"Тип времени: {time_info['type']}")
    print(f"Всего сообщений: {time_info['message_count']}")
    print(f"Временной диапазон: {time_info['min_time']} - {time_info['max_time']}")

    if time_info['time_deltas']:
        print(f"Средняя дельта: {np.mean(time_info['time_deltas']):.6f} сек")
        print(f"Максимальная дельта: {np.max(time_info['time_deltas']):.6f} сек")
        print(f"Минимальная дельта: {np.min(time_info['time_deltas']):.6f} сек")

    if time_info['type'] == 'mixed':
        print(f"Точка перехода: сообщение #{time_info['transition_index']}")
        print(f"Время до перехода: относительное")
        print(f"Время после перехода: абсолютное (Unix timestamp)")

        # Анализируем абсолютные времена
        if time_info['absolute_times']:
            abs_times = time_info['absolute_times']
            print(f"Абсолютные времена: {min(abs_times)} - {max(abs_times)}")
            print(f"Это соответствует датам: {unix_time_to_human(min(abs_times))} - {unix_time_to_human(max(abs_times))}")

    elif time_info['type'] == 'absolute':
        print("Все временные метки - абсолютные (Unix timestamp)")
        print(f"Даты: {unix_time_to_human(time_info['min_time'])} - {unix_time_to_human(time_info['max_time'])}")

    print("=" * 50)

def rewrite_with_fixed_timestamps(reader, output_path, time_info):
    """
    Перезаписывает файл с исправленными временными метками
    """
    messages_written = 0
    base_time = None
    last_fixed_time = 0.0

    with can.BLFWriter(output_path) as writer:
        for i, original_message in enumerate(time_info['messages']):
            # Определяем базовое время для абсолютных меток
            if base_time is None and time_info['type'] in ['absolute', 'mixed']:
                if original_message.timestamp >= 1000000:
                    base_time = original_message.timestamp
                else:
                    # Ищем первое абсолютное время
                    for msg in time_info['messages']:
                        if msg.timestamp >= 1000000:
                            base_time = msg.timestamp
                            break
                    if base_time is None:
                        base_time = 0.0

            # Вычисляем исправленное время
            if time_info['type'] == 'relative':
                # Уже относительное время - оставляем как есть
                fixed_timestamp = original_message.timestamp

            elif time_info['type'] == 'absolute':
                # Абсолютное время -> преобразуем в относительное
                fixed_timestamp = original_message.timestamp - base_time

            elif time_info['type'] == 'mixed':
                if original_message.timestamp < 1000000:
                    # Относительное время - оставляем
                    fixed_timestamp = original_message.timestamp
                else:
                    # Абсолютное время -> преобразуем в относительное
                    fixed_timestamp = original_message.timestamp - base_time

            # Создаем исправленное сообщение
            fixed_message = can.Message(
                arbitration_id=original_message.arbitration_id,
                data=original_message.data,
                timestamp=fixed_timestamp,
                is_extended_id=original_message.is_extended_id,
                is_remote_frame=original_message.is_remote_frame,
                is_error_frame=original_message.is_error_frame,
                channel=original_message.channel
            )

            writer.on_message_received(fixed_message)
            messages_written += 1
            last_fixed_time = fixed_timestamp

            # Прогресс
            if (i + 1) % 100000 == 0:
                print(f"Обработано {i + 1}/{time_info['message_count']} сообщений...")

    print(f"Исправлено сообщений: {messages_written}")
    print(f"Финальное время в файле: {last_fixed_time:.3f} сек")
    print(f"Длительность исправленного файла: {last_fixed_time:.3f} сек")

    return True

def unix_time_to_human(timestamp):
    """
    Конвертирует Unix timestamp в читаемый формат
    """
    from datetime import datetime
    try:
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    except (ValueError, OSError):
        return "Некорректное время"

def verify_fixed_file(original_path, fixed_path):
    """
    Проверяет исправленный файл на корректность
    """
    print("\n=== ПРОВЕРКА ИСПРАВЛЕННОГО ФАЙЛА ===")

    try:
        with can.BLFReader(original_path) as orig_reader:
            with can.BLFReader(fixed_path) as fixed_reader:
                orig_times = [msg.timestamp for msg in orig_reader]
                fixed_times = [msg.timestamp for msg in fixed_reader]

                print(f"Оригинальных сообщений: {len(orig_times)}")
                print(f"Исправленных сообщений: {len(fixed_times)}")

                if len(orig_times) != len(fixed_times):
                    print("⚠️  Предупреждение: разное количество сообщений!")

                # Проверяем временные метки
                print(f"Оригинальное время: {min(orig_times):.3f} - {max(orig_times):.3f}")
                print(f"Исправленное время: {min(fixed_times):.3f} - {max(fixed_times):.3f}")

                # Проверяем монотонность
                is_monotonic = all(fixed_times[i] <= fixed_times[i+1] for i in range(len(fixed_times)-1))
                print(f"Время монотонно: {'✅' if is_monotonic else '❌'}")

                return True

    except Exception as e:
        print(f"Ошибка при проверке: {e}")
        return False

# ========== НАСТРОЙКИ ==========
INPUT_BLF_FILE = "C:\\Users\\belousov\\Documents\\PyScripts\\CanBLF\\logs\\bogo_log.blf"
# ===============================

if __name__ == "__main__":
    print("=== ИСПРАВЛЕНИЕ ВРЕМЕННЫХ МЕТОК BLF ФАЙЛА ===")

    # Исправляем временные метки
    success = fix_blf_timestamps(INPUT_BLF_FILE)

    if success:
        print("\n✅ Файл успешно исправлен!")

        # Проверяем результат
        fixed_path = Path(INPUT_BLF_FILE).parent / f"{Path(INPUT_BLF_FILE).stem}_fixed_timestamps{Path(INPUT_BLF_FILE).suffix}"
        verify_fixed_file(INPUT_BLF_FILE, fixed_path)

        print("\nТеперь вы можете использовать исправленный файл для вырезки отрезков!")
    else:
        print("\n❌ Ошибка при исправлении файла!")
