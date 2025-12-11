"""
CAN Log Analyzer - Valve Command Processor

ПОДДЕРЖИВАЕМЫЕ ФОРМАТЫ ФАЙЛОВ:
--------------------------------
1. BLF files (*.blf) - Binary CAN logs
2. CSV files (*.csv) - Comma-separated values
3. XLSX files (*.xlsx, *.xls) - Excel files (два типа):
   - xlsx (старый завод): автопоиск колонок Time, Data, ID
   - xlsx_custom (новый завод): фиксированные колонки (№ п/п, Date, Time, Type, Level, Event)
4. ASCII logs (*.txt, *.log, *.asc) - Текстовые CAN логи

ИСПОЛЬЗОВАНИЕ:
--------------
# Автоматическое определение формата (рекомендуется)
python can_analyzer.py

# Явное указание типа файла
python can_analyzer.py -t blf          # BLF файл
python can_analyzer.py -t csv           # CSV файл
python can_analyzer.py -t xlsx          # XLSX старого завода
python can_analyzer.py -t xlsx_custom   # XLSX нового завода
python can_analyzer.py -t ascii         # ASCII лог

# Дополнительные опции
python can_analyzer.py --only-requests  # Только запросы (игнорировать ответы)
python can_analyzer.py --no-graph       # Не создавать графики

# Комбинированные опции
python can_analyzer.py -t xlsx_custom --only-requests --no-graph

ОПИСАНИЕ ВЫХОДНЫХ ДАННЫХ:
-------------------------
Скрипт создает в папке с исходным файлом подпапку с именем файла, содержащую:
1. v_names_<filename>.csv - обработанные данные с идентификацией клапанов
2. valves_analysis_<filename>_<timestamp>.txt - детальный отчет анализа
3. valve_timeline_<filename>_<timestamp>.png - график временной линии (если включено)

АНАЛИЗИРУЕМЫЕ КОМАНДЫ:
---------------------
- 2F commands: WriteDataByIdentifier запросы
- 6F responses: Положительные ответы
- 7F errors: Ошибки
- 3E commands: TesterPresent запросы
- 7E responses: Ответы на TesterPresent
- 10 commands: Session control запросы
- 50 responses: Ответы на session control

ЦИФРОВЫЕ ИДЕНТИФИКАТОРЫ КЛАПАНОВ:
-------------------------------
pump - Насос
sha1 - FL/RR Электрический шаттл-клапан
sha2 - FR/RL Электрический шаттл-клапан
iso1 - FL/RR Изолирующий клапан
iso2 - FR/RL Изолирующий клапан
iFL  - Впускной клапан передний левый
iFR  - Впускной клапан передний правый
iRL  - Впускной клапан задний левый
iRR  - Впускной клапан задний правый
oFL  - Выпускной клапан передний левый
oFR  - Выпускной клапан передний правый
oRL  - Выпускной клапан задний левый
oRR  - Выпускной клапан задний правый

ПРИМЕРЫ ДАННЫХ:
---------------
XLSX нового завода:
№ п/п  Date        Time            Type  Level  Event
1017   19.11.2025  16:03:09.941    Full  Info   [0x740] (6) -> 0x2F 0x4B 0x12 0x03 0x57 0x43

XLSX старого завода:
Time        ID    Data
16:03:09    0x740 2F 4B 12 03 57 43

BLF/CSV/ASCII:
timestamp, arbitration_id, data_bytes...

=============================================================================
КРИТИЧЕСКИ ВАЖНАЯ ИНФОРМАЦИЯ О РАБОТЕ INLET КЛАПАНОВ
=============================================================================

INLET КЛАПАНЫ (iFL, iFR, iRL, iRR) - НОРМАЛЬНО ОТКРЫТЫЕ!

Это означает:
- Клапан НЕ АКТИВИРОВАН в команде (not in valves) → клапан ОТКРЫТ → давление ИДЕТ
- Клапан АКТИВИРОВАН в команде (in valves) → клапан ЗАКРЫТ → давление НЕ ИДЕТ

ЛОГИКА НАКАЧКИ ДАВЛЕНИЯ ДЛЯ КОЛЕСА:
====================================

Для накачки RL (диагональ FR/RL) давление идет когда:
✓ pump активирован (in valves)
✓ sha2 активирован (shuttle для диагонали FR/RL)
✓ iso2 активирован (isolating для диагонали FR/RL)
✓ iFR АКТИВИРОВАН (in valves) ← другой клапан диагонали ЗАКРЫТ
✓ iRL НЕ АКТИВИРОВАН (not in valves) ← наш клапан ОТКРЫТ - давление идет!
✓ oRL НЕ активирован (outlet закрыт)

ПРИМЕР ПО ЛОГУ:
===============

Line 70: `51 45` = pump sha2 iso2 iFL iRL iRR
         ↑ НЕТ iFR в списке = iFR ОТКРЫТ
         ↑ ЕСТЬ iRL в списке = iRL ЗАКРЫТ
         → Давление НЕ идет в RL (наш клапан закрыт)

Line 106: `45 45` = pump sha2 iso2 iFL iFR iRR
          ↑ ЕСТЬ iFR = iFR ЗАКРЫТ (другой закрыт)
          ↑ НЕТ iRL = iRL ОТКРЫТ (наш открыт)
          → Давление ИДЕТ в RL! ✓✓✓

ФОРМУЛА В КОДЕ:
===============

if (isolating_name in valves and           # Isolating закрыт
    shuttle_name in valves and             # Shuttle закрыт
    inlet_name not in valves and           # НАШ inlet ОТКРЫТ ← !!! НЕ ИНВЕРТИРОВАТЬ !!!
    outlet_name not in valves and          # Outlet закрыт
    other_inlet_name in valves and         # ДРУГОЙ inlet ЗАКРЫТ ← !!! НЕ ИНВЕРТИРОВАТЬ !!!
    other_outlet_name not in valves):
    results['build'][wheel] += interval_sec

НЕ ПУТАТЬ С ОБЫЧНЫМИ КЛАПАНАМИ!
Pump, shuttles, isolating - нормально закрытые (работают стандартно)
Inlet - НОРМАЛЬНО ОТКРЫТЫЕ (логика инвертирована)


АВТОР: phoeby
ВЕРСИЯ: 3.1 (ИСПРАВЛЕН баг в расчете времени создания давления)
ОБНОВЛЕНО: 2025.12.11
"""


from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog
import os
import re
import chardet
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from can import BLFReader
import can
import pandas as pd
import argparse

target_ids = [0x740, 0x760]

# Configuration flags
ONLYREQUEST = False
WITHGRAPH = True

# флаг для отображения маркеров начала и конца команд
# Это похоже больше не работает и не нужно!.
SHOW_START_AND_END_COMMAND_MARKERS = True

# флаг для добавления Extended Session и Tester Present
ADD_EXS_AND_TP = True
# строить график только для периода активной работы клапанов
GRAPH_FOR_MOTOR_ONLY = True

IGNORE_RESPONSES_IN_GRAPH = True

# Valve names mapping table - ОБНОВЛЕНО
VALVE_NAMES = {
    "pump": "pump",  # Изменено с "pu"
    "FL RR Electric shuttle EV": "sha1",  # Изменено с "sh1"
    "FR RL Electric shuttle EV": "sha2",  # Изменено с "sh2"
    "FL RR Isolating EV": "iso1",  # Изменено с "is1"
    "FR RL Isolating EV": "iso2",  # Изменено с "is2"
    "inlet EV FL": "iFL",
    "inlet EV FR": "iFR",
    "inlet EV RL": "iRL",
    "inlet EV RR": "iRR",
    "outlet EV FL": "oFL",
    "outlet EV FR": "oFR",
    "outlet EV RL": "oRL",
    "outlet EV RR": "oRR"
}

# ОБНОВЛЕНО
VALVE_ORDER = [
    "pump", "sha1", "sha2", "iso1", "iso2",
    "iFL", "iFR", "iRL", "iRR",
    "oFL", "oFR", "oRL", "oRR"
]

# ОБНОВЛЕНО
VALVE_COLORS = {
    "pump": "#FF0000", "sha1": "#FF8800", "sha2": "#FFBB00", "iso1": "#00AA00",
    "iso2": "#00DDDD", "iFL": "#0088FF", "iFR": "#0044FF", "iRL": "#8800FF",
    "iRR": "#FF00FF", "oFL": "#FF0088", "oFR": "#AA0044", "oRL": "#888800",
    "oRR": "#444444"
}

def find_valve_activity_period(processed_data):
    """
    Находит период активной работы клапанов в processed_data
    Возвращает (start_time_ms, end_time_ms) или None если активность не найдена
    """
    if not processed_data:
        return None

    # Собираем все временные метки, когда есть активные клапаны
    active_times = []
    for entry in processed_data:
        line_num, sequence, bytes_val, timediff, valves, req_type, full_line, timestamp_ms = entry
        if valves and timestamp_ms is not None:  # Если есть активные клапаны и валидное время
            active_times.append(timestamp_ms)

    if not active_times:
        return None

    # Находим начало и конец периода активности
    start_time = min(active_times)
    end_time = max(active_times)

    # Добавляем буфер в 3 секунды до и после для наглядности
    buffer_ms = 3000
    start_time_with_buffer = max(0, start_time - buffer_ms)
    end_time_with_buffer = end_time + buffer_ms

    print(f"[MotorActivity] Found valve activity period: {start_time} - {end_time} ms")
    print(f"[MotorActivity] With buffer: {start_time_with_buffer} - {end_time_with_buffer} ms")
    print(f"[MotorActivity] Activity duration: {(end_time - start_time) / 1000:.2f} seconds")
    print(f"[MotorActivity] Active events: {len(active_times)}")

    return (start_time_with_buffer, end_time_with_buffer)

def filter_data_for_motor_period(processed_data, activity_period):
    """
    Фильтрует processed_data, оставляя только данные в пределах периода активности клапанов
    """
    if not activity_period:
        return processed_data

    start_time, end_time = activity_period
    filtered_data = []

    for entry in processed_data:
        line_num, sequence, bytes_val, timediff, valves, req_type, full_line, timestamp_ms = entry
        if timestamp_ms is not None and start_time <= timestamp_ms <= end_time:
            filtered_data.append(entry)

    print(f"[MotorActivity] Filtered data: {len(filtered_data)} entries (was {len(processed_data)})")
    return filtered_data

def detect_file_format(file_path):
    """Detects file format: csv, blf, xlsx, or ascii log"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.blf':
        return 'blf'
    elif ext == '.csv':
        return 'csv'
    elif ext in ['.xlsx', '.xls']:
        # Проверяем структуру файла для определения подтипа
        try:
            df = pd.read_excel(file_path)
            if all(col in df.columns for col in ['№ п/п', 'Date', 'Time', 'Type', 'Level', 'Event']):
                return 'xlsx_custom'  # Новый формат
            else:
                return 'xlsx'  # Старый формат
        except:
            return 'xlsx'  # По умолчанию старый формат при ошибке
    elif ext in ['.txt', '.log', '.asc']:
        return 'ascii'
    else:
        try:
            with open(file_path, 'rb') as f:
                magic = f.read(100)
                if b'LOGG' in magic or b'TOSUNLOGG' in magic:
                    return 'blf'
                elif b'base hex' in magic or b'date' in magic:
                    return 'ascii'
                elif b'PK' in magic:
                    return 'xlsx'
        except:
            pass
        return 'csv'

def parse_xlsx_file_custom(file_path):
    """
    Parses XLSX file in custom format (№ п/п, Date, Time, Type, Level, Event)
    Returns list of tuples: (timestamp_ms, hex_data_string, original_line)
    """
    messages = []

    try:
        # Читаем Excel файл
        df = pd.read_excel(file_path)
        print(f"Excel file loaded. Shape: {df.shape}")
        print(f"Columns: {df.columns.tolist()}")

        # Фильтруем только CAN сообщения
        df_can = df[df['Type'] == 'Can'].copy()
        print(f"Found {len(df_can)} CAN messages")

        # Функция для парсинга CAN сообщений из колонки Event
        def parse_can_event(event_str):
            pattern = r'\[(0x[0-9a-fA-F]+)\]\s*\((\d+)\)\s*(->|<-)\s*(.+)'
            match = re.search(pattern, event_str)

            if match:
                can_id = match.group(1)
                dlc = int(match.group(2))
                direction = match.group(3)
                data_hex = match.group(4)

                # Конвертируем данные в формат XX XX XX
                hex_bytes = data_hex.split()
                formatted_data = ' '.join([byte.upper().replace('0X', '') for byte in hex_bytes])

                return can_id, dlc, direction, formatted_data
            return None, None, None, None

        # Обрабатываем каждую CAN строку
        for idx, row in df_can.iterrows():
            try:
                # Создаем timestamp (объединяем дату и время)
                timestamp_str = f"{row['Date']} {row['Time']}"

                # Парсим CAN сообщение
                can_id, dlc, direction, data = parse_can_event(str(row['Event']))

                if can_id and data:
                    # Парсим timestamp в миллисекунды
                    timestamp_ms = parse_timestamp_custom(timestamp_str)
                    if timestamp_ms is None:
                        timestamp_ms = idx * 1000  # fallback

                    # Создаем оригинальную строку для совместимости
                    original_line = f"Date: {row['Date']} Time: {row['Time']} Event: {row['Event']}"

                    messages.append((timestamp_ms, data, original_line))

                    if len(messages) <= 5:  # Выводим первые 5 сообщений для отладки
                        print(f"DEBUG: Parsed CAN message - Time: {timestamp_str}, ID: {can_id}, Data: {data}")

            except Exception as e:
                print(f"Error parsing row {idx}: {e}")
                continue

        print(f"Successfully parsed {len(messages)} CAN messages from XLSX")
        return messages

    except Exception as e:
        print(f"Error parsing XLSX file: {e}")
        import traceback
        traceback.print_exc()
        return []

def parse_timestamp_custom(timestamp_str):
    """
    Parse timestamp from custom XLSX format (DD.MM.YYYY HH:MM:SS.mmm)
    Returns time in milliseconds
    """
    try:
        # Remove any arrows or special characters
        cleaned_str = re.sub(r'[⇨⇦]', '', timestamp_str).strip()

        # Handle format DD.MM.YYYY HH:MM:SS.mmm
        if ' ' in cleaned_str:
            date_part, time_part = cleaned_str.split(' ', 1)
        else:
            time_part = cleaned_str

        # Parse time part
        time_parts = time_part.split(':')
        if len(time_parts) >= 3:
            hours = int(time_parts[0])
            minutes = int(time_parts[1])

            # Split seconds and milliseconds
            seconds_parts = time_parts[2].split('.')
            seconds = int(seconds_parts[0])
            milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0

            total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
            return total_ms

        print(f"Warning: Unknown time format: {timestamp_str}")
        return None
    except Exception as e:
        print(f"Error parsing timestamp '{timestamp_str}': {e}")
        return None

def parse_ascii_log(file_path):
    """
    Parses ASCII log file and returns list of tuples:
    (timestamp_ms, hex_data_string, original_line)
    """
    messages = []

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith('//') or line.startswith('date') or line.startswith('base hex'):
                continue

            # Parse ASCII log format
            match = re.match(r'\s*([\d.]+)\s+\d+\s+([0-9A-Fa-f]+)\s+([RT]x)\s+d\s+(\d+)\s+(.*)$', line)
            if match:
                timestamp_str, id_str, direction, data_len, data_str = match.groups()

                # Filter by target IDs
                try:
                    if 'x' in id_str:
                        arbitration_id = int(id_str, 16)
                    else:
                        arbitration_id = int(id_str)

                    if arbitration_id not in target_ids:
                        continue
                except:
                    continue

                # Parse timestamp to milliseconds
                try:
                    timestamp_sec = float(timestamp_str)
                    timestamp_ms = int(timestamp_sec * 1000)
                except:
                    timestamp_ms = line_num * 1000

                # Clean up data string
                hex_data = ' '.join(data_str.split())

                messages.append((timestamp_ms, hex_data, line))

        print(f"Parsed ASCII log: {len(messages)} messages")
        return messages

    except Exception as e:
        print(f"Error parsing ASCII log: {e}")
        import traceback
        traceback.print_exc()
        return []

def parse_blf_file(file_path):
    """Parses BLF file with fallback for invalid timestamps"""
    messages = []

    try:
        with BLFReader(file_path) as log:
            msg_index = 0
            for msg in log:
                if msg.arbitration_id not in target_ids:
                    continue

                # Check if timestamp is valid (not 0 or very small)
                if msg.timestamp < 0.001:  # Less than 1ms - likely invalid
                    # Use message index as fallback (10ms intervals)
                    timestamp_ms = msg_index * 10
                    if msg_index < 5:  # Show first 5 for debugging
                        print(f"Warning: Invalid timestamp {msg.timestamp:.6f} for message {msg_index}, "
                              f"using index-based time: {timestamp_ms} ms")
                else:
                    timestamp_ms = int(msg.timestamp * 1000)

                hex_data = ' '.join(f'{b:02X}' for b in msg.data)
                original_line = f"{msg.timestamp:.6f};ID={msg.arbitration_id:03X};{hex_data}"

                messages.append((timestamp_ms, hex_data, original_line))
                msg_index += 1

        print(f"Parsed BLF file: {len(messages)} relevant CAN messages found")
        return messages

    except Exception as e:
        print(f"Error parsing BLF file: {e}")
        import traceback
        traceback.print_exc()
        return []


def parse_csv_file(file_path):
    """Parses CSV file - возвращаем старый формат с 3 элементами"""
    messages = []

    try:
        encoding = detect_encoding(file_path)
        if not encoding:
            encoding = 'utf-8'

        try:
            with open(file_path, 'r', encoding=encoding) as file:
                lines = file.readlines()
        except UnicodeDecodeError:
            for alt_encoding in ['cp1251', 'latin1', 'iso-8859-1', 'cp1252']:
                try:
                    with open(file_path, 'r', encoding=alt_encoding) as file:
                        lines = file.readlines()
                        encoding = alt_encoding
                        print(f"File read with encoding: {encoding}")
                        break
                except UnicodeDecodeError:
                    continue
            else:
                with open(file_path, 'rb') as file:
                    content = file.read()
                    lines = content.decode('utf-8', errors='replace').splitlines(keepends=True)

        for i, line in enumerate(lines):
            line = line.rstrip('\n\r')
            parts = line.split(';')

            if len(parts) < 11:
                continue

            timestamp_str = parts[1] if len(parts) > 1 else None
            hex_data = parts[-1].strip()

            timestamp_ms = parse_timestamp(timestamp_str)
            if timestamp_ms is None:
                continue

            messages.append((timestamp_ms, hex_data, line))

        print(f"Parsed CSV file: {len(messages)} lines")
        return messages

    except Exception as e:
        print(f"Error parsing CSV file: {e}")
        import traceback
        traceback.print_exc()
        return []

def parse_xlsx_file(file_path):
    """
    Parses XLSX file and returns list of tuples: (timestamp_ms, hex_data_string, original_line)
    Улучшенная версия с лучшей обработкой ID и отладочной информацией
    """
    messages = []

    try:
        # Читаем Excel файл
        df = pd.read_excel(file_path)
        print(f"Excel file loaded. Shape: {df.shape}")
        print(f"Columns: {df.columns.tolist()}")

        # Автоматическое определение колонок
        time_col = None
        data_col = None
        id_col = None

        # Сначала ищем по ключевым словам в названиях колонок
        for col in df.columns:
            col_str = str(col).lower()

            # Поиск колонки времени
            if not time_col and any(keyword in col_str for keyword in
                                  ['time', 'timestamp', 'время', 'date', 'временная']):
                time_col = col
                print(f"Found time column: {col}")

            # Поиск колонки данных
            if not data_col and any(keyword in col_str for keyword in
                                  ['data', 'данные', 'hex', 'message', 'can']):
                data_col = col
                print(f"Found data column: {col}")

            # Поиск колонки ID
            if not id_col and any(keyword in col_str for keyword in
                                ['id', 'идентификатор', 'arbitration']):
                id_col = col
                print(f"Found ID column: {col}")

        # Если не нашли по названиям, используем стандартные имена
        if not time_col:
            for col in ['Time', 'Время', 'Timestamp']:
                if col in df.columns:
                    time_col = col
                    break
            if not time_col and len(df.columns) >= 1:
                time_col = df.columns[0]
                print(f"Using first column as time: {time_col}")

        if not data_col:
            for col in ['Data', 'Данные', 'Message', 'CAN Data']:
                if col in df.columns:
                    data_col = col
                    break
            if not data_col and len(df.columns) >= 2:
                data_col = df.columns[1]
                print(f"Using second column as data: {data_col}")

        if not id_col:
            for col in ['ID', 'Id', 'Arbitration ID']:
                if col in df.columns:
                    id_col = col
                    break
            if not id_col and len(df.columns) >= 3:
                id_col = df.columns[2]
                print(f"Using third column as ID: {id_col}")

        print(f"Final columns - Time: {time_col}, Data: {data_col}, ID: {id_col}")

        if time_col is None or data_col is None:
            raise ValueError(f"Cannot find required columns. Time: {time_col}, Data: {data_col}")

        # Функция для парсинга ID с поддержкой разных форматов
        def parse_id(id_val):
            if pd.isna(id_val):
                return None
            try:
                if isinstance(id_val, str):
                    id_val = id_val.strip()
                    # Убираем префиксы если есть
                    if id_val.startswith('0x'):
                        return int(id_val, 16)
                    elif id_val.startswith('⇨') or id_val.startswith('⇦'):
                        # Убираем стрелки если есть
                        id_val = id_val[1:].strip()
                    # Пробуем как hex (без префикса)
                    try:
                        return int(id_val, 16)
                    except ValueError:
                        # Пробуем как decimal
                        return int(id_val)
                else:
                    # Если это число, считаем что это уже правильный ID
                    return int(id_val)
            except Exception as e:
                print(f"Error parsing ID '{id_val}': {e}")
                return None

        # Собираем статистику по ID для отладки
        id_stats = {}
        processed_count = 0
        target_ids_found = 0

        # Обрабатываем каждую строку
        for index, row in df.iterrows():
            try:
                # Получаем данные
                if data_col not in row:
                    continue

                hex_data = str(row[data_col]).strip()

                # Пропускаем пустые строки
                if not hex_data or hex_data.lower() in ['nan', 'none', '']:
                    continue

                # Очищаем данные - убираем лишние пробелы
                hex_data = ' '.join(hex_data.split())

                # Парсим ID
                arbitration_id = None
                if id_col and id_col in row and not pd.isna(row[id_col]):
                    arbitration_id = parse_id(row[id_col])

                    # Собираем статистику
                    if arbitration_id is not None:
                        id_stats[arbitration_id] = id_stats.get(arbitration_id, 0) + 1

                    # Фильтруем по целевым ID
                    if arbitration_id not in target_ids:
                        continue
                    else:
                        target_ids_found += 1
                else:
                    # Если нет колонки ID, пропускаем фильтрацию
                    print(f"Warning: No ID column or empty ID in row {index}")
                    continue

                # Получаем время
                timestamp_ms = None
                if time_col in row and not pd.isna(row[time_col]):
                    timestamp_str = str(row[time_col])
                    timestamp_ms = parse_timestamp(timestamp_str)

                    # Альтернативные методы парсинга времени
                    if timestamp_ms is None:
                        try:
                            if isinstance(row[time_col], (pd.Timestamp, datetime)):
                                dt = row[time_col]
                                total_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
                                timestamp_ms = int(total_seconds * 1000 + dt.microsecond / 1000)
                                print(f"Parsed timestamp from datetime: {dt} -> {timestamp_ms} ms")
                        except:
                            pass

                # Если время не распарсилось, используем индекс
                if timestamp_ms is None:
                    timestamp_ms = index * 1000
                    print(f"Using index as timestamp for row {index}: {timestamp_ms} ms")

                # Создаем оригинальную строку для совместимости
                original_parts = []
                if time_col in row:
                    original_parts.append(f"Time: {row[time_col]}")
                if id_col and id_col in row:
                    original_parts.append(f"ID: {row[id_col]}")
                original_parts.append(f"Data: {hex_data}")

                original_line = "; ".join(original_parts)

                messages.append((timestamp_ms, hex_data, original_line))
                processed_count += 1

                if processed_count <= 5:  # Выводим первые 5 сообщений для отладки
                    print(f"DEBUG: Successfully parsed row {index}: ID={arbitration_id:03X}, Data={hex_data}")

            except Exception as e:
                print(f"Error parsing row {index}: {e}")
                continue

        # Выводим статистику по ID
        print(f"ID statistics in XLSX file:")
        for id_val, count in sorted(id_stats.items()):
            print(f"  ID 0x{id_val:03X} ({id_val}): {count} occurrences")

        print(f"Target IDs found: {target_ids_found}")
        print(f"Successfully parsed XLSX file: {processed_count} messages processed")
        return messages

    except Exception as e:
        print(f"Error parsing XLSX file: {e}")
        import traceback
        traceback.print_exc()
        return []

def parse_xlsx_file_generic(file_path):
    """
    Parses generic XLSX file and returns list of tuples: (timestamp_ms, hex_data_string, original_line)
    Улучшенная версия с лучшей обработкой ID и отладочной информацией
    """
    messages = []

    try:
        # Читаем Excel файл
        df = pd.read_excel(file_path)
        print(f"Excel file loaded. Shape: {df.shape}")
        print(f"Columns: {df.columns.tolist()}")

        # Автоматическое определение колонок
        time_col = None
        data_col = None
        id_col = None

        # Сначала ищем по ключевым словам в названиях колонок
        for col in df.columns:
            col_str = str(col).lower()

            # Поиск колонки времени
            if not time_col and any(keyword in col_str for keyword in
                                  ['time', 'timestamp', 'время', 'date', 'временная']):
                time_col = col
                print(f"Found time column: {col}")

            # Поиск колонки данных
            if not data_col and any(keyword in col_str for keyword in
                                  ['data', 'данные', 'hex', 'message', 'can']):
                data_col = col
                print(f"Found data column: {col}")

            # Поиск колонки ID
            if not id_col and any(keyword in col_str for keyword in
                                ['id', 'идентификатор', 'arbitration']):
                id_col = col
                print(f"Found ID column: {col}")

        # Если не нашли по названиям, используем стандартные имена
        if not time_col:
            for col in ['Time', 'Время', 'Timestamp']:
                if col in df.columns:
                    time_col = col
                    break
            if not time_col and len(df.columns) >= 1:
                time_col = df.columns[0]
                print(f"Using first column as time: {time_col}")

        if not data_col:
            for col in ['Data', 'Данные', 'Message', 'CAN Data']:
                if col in df.columns:
                    data_col = col
                    break
            if not data_col and len(df.columns) >= 2:
                data_col = df.columns[1]
                print(f"Using second column as data: {data_col}")

        if not id_col:
            for col in ['ID', 'Id', 'Arbitration ID']:
                if col in df.columns:
                    id_col = col
                    break
            if not id_col and len(df.columns) >= 3:
                id_col = df.columns[2]
                print(f"Using third column as ID: {id_col}")

        print(f"Final columns - Time: {time_col}, Data: {data_col}, ID: {id_col}")

        if time_col is None or data_col is None:
            raise ValueError(f"Cannot find required columns. Time: {time_col}, Data: {data_col}")

        # Функция для парсинга ID с поддержкой разных форматов
        def parse_id(id_val):
            if pd.isna(id_val):
                return None
            try:
                if isinstance(id_val, str):
                    id_val = id_val.strip()
                    # Убираем префиксы если есть
                    if id_val.startswith('0x'):
                        return int(id_val, 16)
                    elif id_val.startswith('⇨') or id_val.startswith('⇦'):
                        # Убираем стрелки если есть
                        id_val = id_val[1:].strip()
                    # Пробуем как hex (без префикса)
                    try:
                        return int(id_val, 16)
                    except ValueError:
                        # Пробуем как decimal
                        return int(id_val)
                else:
                    # Если это число, считаем что это уже правильный ID
                    return int(id_val)
            except Exception as e:
                print(f"Error parsing ID '{id_val}': {e}")
                return None

        # Собираем статистику по ID для отладки
        id_stats = {}
        processed_count = 0
        target_ids_found = 0

        # Обрабатываем каждую строку
        for index, row in df.iterrows():
            try:
                # Получаем данные
                if data_col not in row:
                    continue

                hex_data = str(row[data_col]).strip()

                # Пропускаем пустые строки
                if not hex_data or hex_data.lower() in ['nan', 'none', '']:
                    continue

                # Очищаем данные - убираем лишние пробелы
                hex_data = ' '.join(hex_data.split())

                # Парсим ID
                arbitration_id = None
                if id_col and id_col in row and not pd.isna(row[id_col]):
                    arbitration_id = parse_id(row[id_col])

                    # Собираем статистику
                    if arbitration_id is not None:
                        id_stats[arbitration_id] = id_stats.get(arbitration_id, 0) + 1

                    # Фильтруем по целевым ID
                    if arbitration_id not in target_ids:
                        continue
                    else:
                        target_ids_found += 1
                else:
                    # Если нет колонки ID, пропускаем фильтрацию
                    print(f"Warning: No ID column or empty ID in row {index}")
                    continue

                # Получаем время
                timestamp_ms = None
                if time_col in row and not pd.isna(row[time_col]):
                    timestamp_str = str(row[time_col])
                    timestamp_ms = parse_timestamp(timestamp_str)

                    # Альтернативные методы парсинга времени
                    if timestamp_ms is None:
                        try:
                            if isinstance(row[time_col], (pd.Timestamp, datetime)):
                                dt = row[time_col]
                                total_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
                                timestamp_ms = int(total_seconds * 1000 + dt.microsecond / 1000)
                                print(f"Parsed timestamp from datetime: {dt} -> {timestamp_ms} ms")
                        except:
                            pass

                # Если время не распарсилось, используем индекс
                if timestamp_ms is None:
                    timestamp_ms = index * 1000
                    print(f"Using index as timestamp for row {index}: {timestamp_ms} ms")

                # Создаем оригинальную строку для совместимости
                original_parts = []
                if time_col in row:
                    original_parts.append(f"Time: {row[time_col]}")
                if id_col and id_col in row:
                    original_parts.append(f"ID: {row[id_col]}")
                original_parts.append(f"Data: {hex_data}")

                original_line = "; ".join(original_parts)

                messages.append((timestamp_ms, hex_data, original_line))
                processed_count += 1

                if processed_count <= 5:  # Выводим первые 5 сообщений для отладки
                    print(f"DEBUG: Successfully parsed row {index}: ID={arbitration_id:03X}, Data={hex_data}")

            except Exception as e:
                print(f"Error parsing row {index}: {e}")
                continue

        # Выводим статистику по ID
        print(f"ID statistics in XLSX file:")
        for id_val, count in sorted(id_stats.items()):
            print(f"  ID 0x{id_val:03X} ({id_val}): {count} occurrences")

        print(f"Target IDs found: {target_ids_found}")
        print(f"Successfully parsed XLSX file: {processed_count} messages processed")
        return messages

    except Exception as e:
        print(f"Error parsing XLSX file: {e}")
        import traceback
        traceback.print_exc()
        return []

def parse_input_file(file_path, file_type='auto'):
    """Universal parser with explicit XLSX type support"""
    if file_type == 'auto':
        file_type = detect_file_format(file_path)

    print(f"Using file type: {file_type.upper()}")

    if file_type == 'blf':
        return parse_blf_file(file_path)
    elif file_type == 'csv':
        return parse_csv_file(file_path)
    elif file_type == 'xlsx':
        return parse_xlsx_file_generic(file_path)  # Старый формат по умолчанию
    elif file_type == 'xlsx_custom':  # Явное указание нового формата
        return parse_xlsx_file_custom(file_path)
    elif file_type == 'ascii':
        return parse_ascii_log(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_type}")

def analyze_commands(messages, file_format='blf'):
    """
    Analyzes command sequences and their responses
    Улучшенная версия, которая правильно обрабатывает BLF формат с байтом длины
    """
    stats = {
        '2F_commands': [],
        '6F_responses': [],
        '7F_errors': [],
        '3E_commands': [],
        '7E_responses': [],
        '10_commands': [],
        '50_responses': [],
        'command_pairs': [],
        'missing_responses': [],
        'error_commands': []
    }

    # Track pending requests
    pending_2f_requests = {}
    pending_10_requests = {}
    pending_3e_requests = {}

    for idx, (timestamp_ms, hex_data, original_line) in enumerate(messages):
        hex_bytes = hex_data.split()
        if not hex_bytes:
            continue

        # Для BLF файлов данные начинаются с байта длины, поэтому нам нужно пропустить его
        if file_format == 'blf':
            if len(hex_bytes) < 2:
                continue

            # Первый байт - длина данных, второй байт - тип команды
            length_byte = hex_bytes[0]
            first_byte = hex_bytes[1]

            # Для session control (10) и tester present (3E) смотрим на второй байт
            # Для ответов (50, 7E) тоже смотрим на второй байт
        else:
            # Для других форматов используем первый байт как есть
            first_byte = hex_bytes[0]

        # Track 2F commands (requests) - ищем в данных после байта длины
        if file_format == 'blf':
            # В BLF: данные начинаются с длины, затем команда
            if len(hex_bytes) >= 3 and hex_bytes[1] == '2F':
                command_data = ' '.join(hex_bytes[2:4]) if len(hex_bytes) >= 4 else ' '.join(hex_bytes[2:])
                stats['2F_commands'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'command_data': command_data,
                    'original_line': original_line
                })
                pending_2f_requests[idx] = {
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'command_data': command_data
                }
        else:
            # Для других форматов
            if first_byte == '2F':
                command_data = ' '.join(hex_bytes[1:3]) if len(hex_bytes) >= 3 else ' '.join(hex_bytes[1:])
                stats['2F_commands'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'command_data': command_data,
                    'original_line': original_line
                })
                pending_2f_requests[idx] = {
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'command_data': command_data
                }

        # Track 6F responses
        if file_format == 'blf':
            if len(hex_bytes) >= 3 and hex_bytes[1] == '6F':
                response_data = ' '.join(hex_bytes[2:4]) if len(hex_bytes) >= 4 else ' '.join(hex_bytes[2:])
                stats['6F_responses'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'response_data': response_data,
                    'original_line': original_line
                })

                # Try to find matching request
                matched = False
                for req_idx in list(pending_2f_requests.keys()):
                    req = pending_2f_requests[req_idx]
                    if req_idx < idx:  # Request must come before response
                        stats['command_pairs'].append({
                            'request': req,
                            'response': {
                                'timestamp': timestamp_ms,
                                'data': hex_data,
                                'response_data': response_data
                            },
                            'response_time': timestamp_ms - req['timestamp']
                        })
                        del pending_2f_requests[req_idx]
                        matched = True
                        break

                if not matched:
                    stats['missing_responses'].append({
                        'response_index': idx,
                        'response_data': hex_data,
                        'timestamp': timestamp_ms
                    })
        else:
            if first_byte == '6F':
                response_data = ' '.join(hex_bytes[1:3]) if len(hex_bytes) >= 3 else ' '.join(hex_bytes[1:])
                stats['6F_responses'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'response_data': response_data,
                    'original_line': original_line
                })

                # Try to find matching request
                matched = False
                for req_idx in list(pending_2f_requests.keys()):
                    req = pending_2f_requests[req_idx]
                    if req_idx < idx:
                        stats['command_pairs'].append({
                            'request': req,
                            'response': {
                                'timestamp': timestamp_ms,
                                'data': hex_data,
                                'response_data': response_data
                            },
                            'response_time': timestamp_ms - req['timestamp']
                        })
                        del pending_2f_requests[req_idx]
                        matched = True
                        break

                if not matched:
                    stats['missing_responses'].append({
                        'response_index': idx,
                        'response_data': hex_data,
                        'timestamp': timestamp_ms
                    })

        # Track 7F errors
        if file_format == 'blf':
            if len(hex_bytes) >= 2 and hex_bytes[1] == '7F':
                error_data = ' '.join(hex_bytes[1:3]) if len(hex_bytes) >= 3 else ' '.join(hex_bytes[1:])
                stats['7F_errors'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'error_data': error_data,
                    'original_line': original_line
                })
        else:
            if first_byte == '7F':
                error_data = ' '.join(hex_bytes[1:3]) if len(hex_bytes) >= 3 else ' '.join(hex_bytes[1:])
                stats['7F_errors'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'error_data': error_data,
                    'original_line': original_line
                })

        # Track TesterPresent (3E) - для BLF смотрим на второй байт
        if file_format == 'blf':
            if len(hex_bytes) >= 2 and hex_bytes[1] == '3E':
                stats['3E_commands'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'original_line': original_line
                })
                pending_3e_requests[idx] = {
                    'timestamp': timestamp_ms,
                    'data': hex_data
                }
        else:
            if first_byte == '3E':
                stats['3E_commands'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'original_line': original_line
                })
                pending_3e_requests[idx] = {
                    'timestamp': timestamp_ms,
                    'data': hex_data
                }

        # Track TesterPresent responses (7E)
        if file_format == 'blf':
            if len(hex_bytes) >= 2 and hex_bytes[1] == '7E':
                stats['7E_responses'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'original_line': original_line
                })

                # Match with 3E request
                for req_idx in list(pending_3e_requests.keys()):
                    if req_idx < idx:
                        del pending_3e_requests[req_idx]
                        break
        else:
            if first_byte == '7E':
                stats['7E_responses'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'original_line': original_line
                })

                # Match with 3E request
                for req_idx in list(pending_3e_requests.keys()):
                    if req_idx < idx:
                        del pending_3e_requests[req_idx]
                        break

        # Track session commands (10) - особое внимание на Extended Session 10 03
        if file_format == 'blf':
            if len(hex_bytes) >= 3 and hex_bytes[1] == '10':
                session_type = hex_bytes[2] if len(hex_bytes) > 2 else 'unknown'
                stats['10_commands'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'session_type': session_type,
                    'original_line': original_line
                })
                pending_10_requests[idx] = {
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'session_type': session_type
                }
        else:
            if first_byte == '10':
                session_type = hex_bytes[1] if len(hex_bytes) > 1 else 'unknown'
                stats['10_commands'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'session_type': session_type,
                    'original_line': original_line
                })
                pending_10_requests[idx] = {
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'session_type': session_type
                }

        # Track session responses (50)
        if file_format == 'blf':
            if len(hex_bytes) >= 3 and hex_bytes[1] == '50':
                session_type = hex_bytes[2] if len(hex_bytes) > 2 else 'unknown'
                stats['50_responses'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'session_type': session_type,
                    'original_line': original_line
                })

                # Match with 10 request
                for req_idx in list(pending_10_requests.keys()):
                    req = pending_10_requests[req_idx]
                    if req_idx < idx and req.get('session_type') == session_type:
                        del pending_10_requests[req_idx]
                        break
        else:
            if first_byte == '50':
                session_type = hex_bytes[1] if len(hex_bytes) > 1 else 'unknown'
                stats['50_responses'].append({
                    'index': idx,
                    'timestamp': timestamp_ms,
                    'data': hex_data,
                    'session_type': session_type,
                    'original_line': original_line
                })

                # Match with 10 request
                for req_idx in list(pending_10_requests.keys()):
                    req = pending_10_requests[req_idx]
                    if req_idx < idx and req.get('session_type') == session_type:
                        del pending_10_requests[req_idx]
                        break

    # Find missing responses
    for req_idx, req in pending_2f_requests.items():
        stats['missing_responses'].append({
            'request_index': req_idx,
            'request_data': req['data'],
            'timestamp': req['timestamp']
        })

    # Отладочная информация
    print(f"Command analysis results for {file_format.upper()}:")
    print(f"  2F commands: {len(stats['2F_commands'])}")
    print(f"  6F responses: {len(stats['6F_responses'])}")
    print(f"  7F errors: {len(stats['7F_errors'])}")
    print(f"  3E commands: {len(stats['3E_commands'])}")
    print(f"  7E responses: {len(stats['7E_responses'])}")
    print(f"  10 commands: {len(stats['10_commands'])}")
    print(f"  50 responses: {len(stats['50_responses'])}")
    print(f"  Command pairs: {len(stats['command_pairs'])}")
    print(f"  Missing responses: {len(stats['missing_responses'])}")

    # Дополнительная отладочная информация по session types
    if stats['10_commands']:
        session_types = {}
        for cmd in stats['10_commands']:
            session_type = cmd.get('session_type', 'unknown')
            session_types[session_type] = session_types.get(session_type, 0) + 1
        print(f"  10 command session types: {session_types}")

    if stats['50_responses']:
        session_types = {}
        for resp in stats['50_responses']:
            session_type = resp.get('session_type', 'unknown')
            session_types[session_type] = session_types.get(session_type, 0) + 1
        print(f"  50 response session types: {session_types}")

    return stats

def analyze_response_times(command_stats):
    """
    НОВАЯ ФУНКЦИЯ: Анализирует время ответа блока на команды
    Возвращает словарь со статистикой по времени ответа
    """
    response_times = []

    # Собираем все времена ответа из command_pairs
    for pair in command_stats['command_pairs']:
        response_time = pair['response_time']
        if response_time is not None and response_time >= 0:
            response_times.append(response_time)

    if not response_times:
        return None

    # Вычисляем статистику
    stats = {
        'count': len(response_times),
        'average': sum(response_times) / len(response_times),
        'min': min(response_times),
        'max': max(response_times),
        'all_times': response_times
    }

    print(f"[Response Time Analysis]")
    print(f"  Total responses: {stats['count']}")
    print(f"  Average time: {stats['average']:.2f} ms")
    print(f"  Fastest: {stats['min']} ms")
    print(f"  Slowest: {stats['max']} ms")

    return stats

def format_command_analysis_report(command_stats, file_format):
    """Formats command analysis for the report - ОБНОВЛЕНО с анализом времени ответа"""
    report = []

    report.append("COMMAND ANALYSIS REPORT")
    report.append("=" * 80)
    report.append(f"File format: {file_format.upper()}")
    report.append("")

    # 2F/6F command analysis
    total_2f = len(command_stats['2F_commands'])
    total_6f = len(command_stats['6F_responses'])
    total_7f = len(command_stats['7F_errors'])
    total_pairs = len(command_stats['command_pairs'])

    report.append("WRITE DATA BY IDENTIFIER (2F) COMMANDS:")
    report.append("-" * 50)
    report.append(f"Total 2F commands sent: {total_2f}")
    report.append(f"Total 6F responses received: {total_6f}")
    report.append(f"Total 7F error responses: {total_7f}")
    report.append(f"Successfully matched request/response pairs: {total_pairs}")
    report.append(f"Missing responses: {len(command_stats['missing_responses'])}")
    report.append("")

    if total_2f > 0:
        success_rate = (total_6f / total_2f) * 100
        error_rate = (total_7f / total_2f) * 100
        report.append(f"Success rate: {success_rate:.1f}%")
        report.append(f"Error rate: {error_rate:.1f}%")
        report.append("")

    # НОВЫЙ РАЗДЕЛ: Анализ времени ответа блока
    response_time_stats = analyze_response_times(command_stats)
    if response_time_stats:
        report.append("=" * 80)
        report.append("ECU RESPONSE TIME ANALYSIS")
        report.append("=" * 80)
        report.append("")
        report.append("This section analyzes ECU response times to identify")
        report.append("whether the ECU is responding promptly to commands.")
        report.append("")
        report.append("-" * 50)
        report.append(f"Total successful responses analyzed: {response_time_stats['count']}")
        report.append(f"Average response time: {response_time_stats['average']:.2f} ms")
        report.append(f"Fastest response: {response_time_stats['min']} ms")
        report.append(f"Slowest response: {response_time_stats['max']} ms")
        report.append("")

        # Оценка производительности
        avg_time = response_time_stats['average']
        max_time = response_time_stats['max']

        report.append("PERFORMANCE ASSESSMENT:")
        report.append("-" * 50)

        if avg_time < 20:
            report.append("✓ EXCELLENT: Average response time is excellent (< 20ms)")
            report.append("  The ECU is responding very quickly to commands.")
        elif avg_time < 50:
            report.append("✓ GOOD: Average response time is good (< 50ms)")
            report.append("  The ECU is responding appropriately to commands.")
        else:
            report.append("⚠ WARNING: Average response time exceeds 50ms")
            report.append("  The ECU may be experiencing delays.")

        report.append("")

        if max_time < 50:
            report.append("✓ GOOD: Maximum response time is acceptable (< 50ms)")
            report.append("  No significant delays detected in ECU responses.")
        elif max_time < 100:
            report.append("⚠ CAUTION: Maximum response time is elevated (< 100ms)")
            report.append("  Occasional delays may occur.")
        else:
            report.append("⚠ WARNING: Maximum response time exceeds 100ms")
            report.append(f"  Slowest response was {max_time} ms - investigate delays.")

        report.append("")
        report.append("CONCLUSION:")
        report.append("-" * 50)

        if avg_time < 50 and max_time < 100:
            report.append("✓ The ECU is responding within acceptable limits.")
            report.append("✓ Performance delays are likely NOT caused by the ECU.")
            report.append("  → Investigation should focus on:")
            report.append("     - Test bench equipment")
            report.append("     - CAN bus communication")
            report.append("     - External control systems")
        else:
            report.append("⚠ The ECU shows some response delays.")
            report.append("  Further investigation recommended.")

        report.append("")
        report.append("=" * 80)
        report.append("")

    # Show detailed command pairs
    if command_stats['command_pairs']:
        report.append("COMMAND/RESPONSE PAIRS (first 10):")
        report.append("-" * 40)
        for i, pair in enumerate(command_stats['command_pairs'][:10]):
            report.append(f"Pair {i+1}:")
            report.append(f"  Request:  {pair['request']['data']}")
            report.append(f"  Response: {pair['response']['data']}")
            report.append(f"  Response time: {pair['response_time']} ms")
            report.append("")

    # Show 7F errors with details
    if command_stats['7F_errors']:
        report.append("7F ERROR RESPONSES:")
        report.append("-" * 40)
        for error in command_stats['7F_errors']:
            report.append(f"Line {error['index']+1}: {error['data']}")
            report.append(f"  Time: {error['timestamp']} ms")
        report.append("")

    # TesterPresent analysis
    total_3e = len(command_stats['3E_commands'])
    total_7e = len(command_stats['7E_responses'])

    report.append("TESTER PRESENT (3E) COMMANDS:")
    report.append("-" * 50)
    report.append(f"Total 3E commands sent: {total_3e}")
    report.append(f"Total 7E responses received: {total_7e}")

    if total_3e > 0:
        response_rate = (total_7e / total_3e) * 100
        report.append(f"Response rate: {response_rate:.1f}%")

        # Calculate intervals
        if len(command_stats['3E_commands']) > 1:
            intervals = []
            for i in range(1, len(command_stats['3E_commands'])):
                time_diff = command_stats['3E_commands'][i]['timestamp'] - command_stats['3E_commands'][i-1]['timestamp']
                intervals.append(time_diff)

            if intervals:
                avg_interval = sum(intervals) / len(intervals)
                min_interval = min(intervals)
                max_interval = max(intervals)
                report.append(f"Average interval: {avg_interval:.0f} ms ({avg_interval/1000:.1f} s)")
                report.append(f"Min interval: {min_interval} ms ({min_interval/1000:.1f} s)")
                report.append(f"Max interval: {max_interval} ms ({max_interval/1000:.1f} s)")

    report.append("")

    # Session control analysis - ОСОБОЕ ВНИМАНИЕ НА EXTENDED SESSION
    session_commands = {}
    for cmd in command_stats['10_commands']:
        session_type = cmd.get('session_type', 'unknown')
        if session_type not in session_commands:
            session_commands[session_type] = []
        session_commands[session_type].append(cmd)

    session_responses = {}
    for resp in command_stats['50_responses']:
        session_type = resp.get('session_type', 'unknown')
        if session_type not in session_responses:
            session_responses[session_type] = []
        session_responses[session_type].append(resp)

    report.append("SESSION CONTROL COMMANDS:")
    report.append("-" * 40)

    # Собираем все уникальные типы сессий
    all_session_types = set(list(session_commands.keys()) + list(session_responses.keys()))

    # Сначала показываем Extended Session (03), так как она наиболее важна
    important_sessions = ['03', '01', '02']  # Extended, Default, Programming
    other_sessions = [st for st in all_session_types if st not in important_sessions and st != 'unknown']

    for session_type in important_sessions + other_sessions:
        if session_type not in all_session_types:
            continue

        commands_count = len(session_commands.get(session_type, []))
        responses_count = len(session_responses.get(session_type, []))

        session_name = {
            '01': 'Default Session (10 01)',
            '02': 'Programming Session (10 02)',
            '03': 'EXTENDED SESSION (10 03) ★',
            'unknown': 'Unknown Session'
        }.get(session_type, f'Session 10 {session_type}')

        report.append(f"{session_name}:")
        report.append(f"  Commands: {commands_count}")
        report.append(f"  Responses: {responses_count}")
        if commands_count > 0:
            success_rate = (responses_count / commands_count) * 100
            report.append(f"  Success rate: {success_rate:.1f}%")

            # Для Extended Session показываем дополнительную информацию
            if session_type == '03' and commands_count > 0:
                report.append(f"  ★ Extended Session is CRITICAL for valve control")
                if success_rate == 100:
                    report.append(f"  ★ SUCCESS: All Extended Session commands received positive response")
                else:
                    report.append(f"  ★ WARNING: Not all Extended Session commands received response")

    report.append("")
    report.append("=" * 80)

    return '\n'.join(report)


def detect_encoding(file_path):
    """Detects file encoding"""
    with open(file_path, 'rb') as file:
        raw_data = file.read()
        result = chardet.detect(raw_data)
        encoding = result['encoding']
        confidence = result['confidence']
        print(f"Detected encoding: {encoding} with confidence {confidence}")
        return encoding

def select_file(title):
    """Function to select file and return all components"""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    file_path = filedialog.askopenfilename(
        title=title,
        filetypes=[
            ("Log files", "*.csv *.blf *.xlsx *.xls"),
            ("CSV files", "*.csv"),
            ("BLF files", "*.blf"),
            ("Excel files", "*.xlsx *.xls"),
            ("All files", "*.*")
        ]
    )
    root.destroy()
    root.quit()

    if not file_path:
        return None, None, None, None

    directory = os.path.dirname(file_path)
    filename_with_ext = os.path.basename(file_path)
    filename_no_ext = os.path.splitext(filename_with_ext)[0]
    extension = os.path.splitext(filename_with_ext)[1]

    return file_path, directory, filename_no_ext, extension

def parse_valves(hex_string):
    """
    Parses two hex bytes and returns list of active valves according to specification.
    """
    valves_spec = [
        ("outlet EV RR", 1, 0, 1),
        ("inlet EV RR", 1, 1, 1),
        ("outlet EV RL", 1, 2, 1),
        ("inlet EV RL", 1, 3, 1),
        ("outlet EV FR", 1, 4, 1),
        ("inlet EV FR", 1, 5, 1),
        ("outlet EV FL", 1, 6, 1),
        ("inlet EV FL", 1, 7, 1),
        ("Reserved", 2, 0, 1),
        ("pump", 2, 1, 1),
        ("Reserved", 2, 2, 2),
        ("FL RR Electric shuttle EV", 2, 4, 1),
        ("FR RL Electric shuttle EV", 2, 5, 1),
        ("FL RR Isolating EV", 2, 6, 1),
        ("FR RL Isolating EV", 2, 7, 1),
    ]

    hex_bytes = hex_string.split()
    if len(hex_bytes) != 2:
        raise ValueError("Exactly two hex bytes separated by space required")

    byte1 = int(hex_bytes[0], 16)
    byte2 = int(hex_bytes[1], 16)

    active_valves = []

    for name, byte_num, offset, length in valves_spec:
        if name == "Reserved":
            continue

        if byte_num == 1:
            current_byte = byte1
        else:
            current_byte = byte2

        if length == 1:
            if current_byte & (1 << (7 - offset)):
                active_valves.append(VALVE_NAMES[name])

    return active_valves

def parse_timestamp(timestamp_str):
    """
    Parse timestamp from field (format HH:MM:SS.mmm or other Excel formats)
    Returns time in milliseconds
    """
    try:
        # Remove any arrows or special characters
        cleaned_str = re.sub(r'[⇨⇦]', '', timestamp_str).strip()

        # Handle format HH:MM:SS.mmm
        time_parts = cleaned_str.split(':')
        if len(time_parts) == 3:
            hours = int(time_parts[0])
            minutes = int(time_parts[1])

            # Split seconds and milliseconds
            seconds_parts = time_parts[2].split('.')
            seconds = int(seconds_parts[0])
            milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0

            total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
            return total_ms

        # Handle other time formats if needed
        print(f"Warning: Unknown time format: {timestamp_str}")
        return None
    except Exception as e:
        print(f"Error parsing timestamp '{timestamp_str}': {e}")
        return None

def format_timediff(diff_ms):
    """
    Format time difference according to requirements:
    - < 1000 ms: show as "XXX" (3 digits)
    - >= 1000 ms and < 10000 ms: show as "X.Xs"
    - >= 10000 ms and < 99000 ms: show as "XXs"
    - >= 99000 ms: show as "---"
    Always with space on each side
    """
    if diff_ms is None:
        return " --- "

    if diff_ms < 1000:
        return f" {int(diff_ms):3d} "
    elif diff_ms < 10000:
        return f" {diff_ms/1000:.1f}s"
    elif diff_ms < 99000:
        return f" {int(diff_ms/1000):2d}s "
    else:
        return " --- "

def analyze_pressure_modes(processed_data):
    """
    Analyzes pressure build and release times for each wheel.
    Returns dict with times in seconds.

    ВАЖНО: Inlet клапаны - НОРМАЛЬНО ОТКРЫТЫЕ!
    - Клапан НЕ активирован (not in valves) → ОТКРЫТ → давление идет
    - Клапан активирован (in valves) → ЗАКРЫТ → давление НЕ идет
    """
    print(f"[PressureAnalysis] analyze_pressure_modes called with {len(processed_data)} entries")

    # Wheel diagonal mapping
    wheel_diagonals = {
        'FL': 'FL RR',
        'RR': 'FL RR',
        'FR': 'FR RL',
        'RL': 'FR RL'
    }

    results = {
        'build': {'FL': 0.0, 'FR': 0.0, 'RL': 0.0, 'RR': 0.0},
        'release': {'FL': 0.0, 'FR': 0.0, 'RL': 0.0, 'RR': 0.0}
    }

    if not processed_data:
        print("[PressureAnalysis] No processed_data, returning empty results")
        return results

    # ✅ КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Фильтруем ТОЛЬКО команды управления клапанами!
    # Исключаем responses (6F), TesterPresent (3E/7E), ExtendedSession (10/50)
    valve_commands_only = [e for e in processed_data if e[1] == "2F 4B 12 03"]

    print(f"[PressureAnalysis] Filtered to {len(valve_commands_only)} valve commands (from {len(processed_data)} total)")

    # Process consecutive pairs to calculate time intervals
    for i in range(len(valve_commands_only) - 1):
        line_num, sequence, bytes_val, timediff, valves, req_type, full_line, timestamp_ms = valve_commands_only[i]
        next_line = valve_commands_only[i + 1]
        next_timestamp_ms = next_line[7]

        if i == 0:
            print(f"[PressureAnalysis] First entry: line_num={line_num}, timestamp_ms={timestamp_ms}")

        # Calculate time interval to next measurement (in seconds)
        if timestamp_ms is not None and next_timestamp_ms is not None:
            interval_sec = (next_timestamp_ms - timestamp_ms) / 1000.0
        else:
            continue

        # Check pump active
        pump_active = 'pump' in valves

        if not pump_active:
            continue

        # Check each wheel
        for wheel in ['FL', 'FR', 'RL', 'RR']:
            diagonal = wheel_diagonals[wheel]

            # Get short names for diagonal valves
            isolating_name = VALVE_NAMES[f"{diagonal} Isolating EV"]
            shuttle_name = VALVE_NAMES[f"{diagonal} Electric shuttle EV"]

            # Inlet/outlet for this wheel
            inlet_name = VALVE_NAMES[f"inlet EV {wheel}"]
            outlet_name = VALVE_NAMES[f"outlet EV {wheel}"]

            # Get other wheel in same diagonal
            if wheel == 'FL':
                other_wheel = 'RR'
            elif wheel == 'RR':
                other_wheel = 'FL'
            elif wheel == 'FR':
                other_wheel = 'RL'
            else:  # RL
                other_wheel = 'FR'

            other_inlet_name = VALVE_NAMES[f"inlet EV {other_wheel}"]
            other_outlet_name = VALVE_NAMES[f"outlet EV {other_wheel}"]

            # PRESSURE BUILD condition
            if (isolating_name in valves and
                shuttle_name in valves and
                inlet_name not in valves and          # НАШ клапан НЕ активирован = ОТКРЫТ
                outlet_name not in valves and
                other_inlet_name in valves and        # ДРУГОЙ клапан активирован = ЗАКРЫТ
                other_outlet_name not in valves):

                results['build'][wheel] += interval_sec

            # Check PRESSURE RELEASE condition (outlet активирован)
            if outlet_name in valves:
                results['release'][wheel] += interval_sec

    print(f"[PressureAnalysis] Final Results: {results}")
    return results

def show_message(title, message, is_error=False):
    """Shows message without blocking main thread"""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    if is_error:
        messagebox.showerror(title, message)
    else:
        messagebox.showinfo(title, message)

    root.destroy()
    root.quit()


def create_valve_timeline_graph(directory, filename, processed_data, pressure_stats):
    """
    Creates timeline graph showing valve states over time.
    ОБНОВЛЕНО: Убрана легенда, улучшен заголовок и информационная табличка
    """
    if not WITHGRAPH:
        print("[TimestampDebug] WITHGRAPH is False, skipping graph creation")
        return None

    if not processed_data:
        print("[TimestampDebug] No data to plot")
        return None

    print(f"[TimestampDebug] create_valve_timeline_graph called with {len(processed_data)} entries")

    # Для графика используем все записи с командами управления клапанами
    # включая 00 00 (всё выключено), чтобы показать переходы в выключенное состояние
    graph_data = [entry for entry in processed_data
                  if entry[1] in ["2F 4B 12 03", "6F 4B 12 03", "62 4B 12"]]

    if IGNORE_RESPONSES_IN_GRAPH:
       graph_data = [e for e in graph_data if e[5] != "Response"]

    print(f"[GraphDebug] Filtered graph data: {len(graph_data)} valve command entries (from {len(processed_data)} total)")

    if not graph_data:
        print("[GraphDebug] No valve command data to plot")
        return None

    # Определяем период активности клапанов
    activity_period = None
    if GRAPH_FOR_MOTOR_ONLY:
        activity_period = find_valve_activity_period(graph_data)
        if activity_period:
            graph_data = filter_data_for_motor_period(graph_data, activity_period)
            print(f"[MotorActivity] Building graph for motor activity period only: {activity_period}")
        else:
            print(f"[MotorActivity] No valve activity found, building full graph")

    # Собираем маркеры Extended Session и Tester Present
    ext_session_markers = []
    tester_present_markers = []

    if ADD_EXS_AND_TP:
        # Сначала посмотрим, что вообще есть в processed_data
        all_sequences = {}
        for entry in processed_data:
            seq = entry[1]
            all_sequences[seq] = all_sequences.get(seq, 0) + 1

        print(f"[Markers DEBUG] All sequences in processed_data: {all_sequences}")

        # Теперь собираем маркеры
        for entry in processed_data:
            line_num, sequence, bytes_val, timediff, valves, req_type, full_line, timestamp_ms = entry

            # Детальная диагностика для первых нескольких 3E/7E
            if sequence in ["3E", "7E"] and len(tester_present_markers) < 3:
                print(f"[Markers DEBUG] Found {sequence}: timestamp={timestamp_ms}, req_type={req_type}")
                if GRAPH_FOR_MOTOR_ONLY and activity_period:
                    start_time, end_time = activity_period
                    print(f"[Markers DEBUG]   activity_period: {start_time} - {end_time}")
                    print(f"[Markers DEBUG]   in range: {start_time <= timestamp_ms <= end_time}")

            if timestamp_ms is None:
                continue

            # Если GRAPH_FOR_MOTOR_ONLY, фильтруем по периоду активности
            if GRAPH_FOR_MOTOR_ONLY and activity_period:
                start_time, end_time = activity_period
                if timestamp_ms < start_time or timestamp_ms > end_time:
                    continue

            if sequence in ["10 03", "50 03"]:
                ext_session_markers.append((timestamp_ms, sequence, req_type))
            elif sequence in ["3E", "7E"]:
                tester_present_markers.append((timestamp_ms, sequence, req_type))

        print(f"[Markers] Extended Session markers: {len(ext_session_markers)}")
        print(f"[Markers] Tester Present markers: {len(tester_present_markers)}")

    try:
        # Extract time series data for each valve
        valve_timelines = {valve: [] for valve in VALVE_ORDER}

        # Get first timestamp to normalize - используем минимальный из ВСЕХ данных
        first_timestamp = None

        # Сначала находим минимальный timestamp из всех источников
        all_timestamps = []

        # Из graph_data
        for entry in graph_data:
            if entry[7] is not None:  # timestamp_ms
                all_timestamps.append(entry[7])

        # Из маркеров (если ADD_EXS_AND_TP)
        if ADD_EXS_AND_TP:
            for ts, _, _ in ext_session_markers:
                all_timestamps.append(ts)
            for ts, _, _ in tester_present_markers:
                all_timestamps.append(ts)

        if all_timestamps:
            first_timestamp = min(all_timestamps)
            print(f"[GraphDebug] First timestamp set to: {first_timestamp} (from all data)")
        else:
            print("[GraphDebug] Could not find any timestamps")
            return None

        # Теперь строим timeline для клапанов
        for idx, entry in enumerate(graph_data):
            line_num, sequence, bytes_val, timediff, valves, req_type, full_line, timestamp_ms = entry

            if timestamp_ms is not None:
                time_sec = (timestamp_ms - first_timestamp) / 1000.0

                for valve in VALVE_ORDER:
                    is_active = valve in valves
                    valve_timelines[valve].append((time_sec, is_active))

        if first_timestamp is None:
            print("[GraphDebug] Could not parse timestamps - first_timestamp is None")
            return None

        # Create figure
        fig, ax = plt.subplots(figsize=(16, 10), dpi=150)

        # Plot each valve
        for idx, valve in enumerate(VALVE_ORDER):
            timeline = valve_timelines[valve]
            if not timeline:
                continue

            times = []
            values = []

            for time_sec, is_active in timeline:
                times.append(time_sec)
                values.append(len(VALVE_ORDER) - idx if is_active else 0)

            ax.plot(times, values,
                   drawstyle='steps-post',
                   color=VALVE_COLORS[valve],
                   linewidth=3,
                   label=valve,
                   alpha=0.8)

        # Set Y limits
        ax.set_ylim(-0.5, len(VALVE_ORDER) + 0.5)
        y_min, y_max = ax.get_ylim()

        # Draw Extended Session markers
        if ADD_EXS_AND_TP and ext_session_markers:
            for timestamp_ms, sequence, req_type in ext_session_markers:
                time_sec = (timestamp_ms - first_timestamp) / 1000.0

                if "10" in sequence:  # Request
                    color = 'green'
                    linestyle = '--'
                else:  # Response (50)
                    color = 'darkgreen'
                    linestyle = ':'

                ax.axvline(x=time_sec, color=color, linestyle=linestyle,
                          alpha=0.6, linewidth=1.5)

        # Draw Tester Present markers
        if ADD_EXS_AND_TP and tester_present_markers:
            print(f"[TP Draw] Drawing {len(tester_present_markers)} Tester Present markers")
            print(f"[TP Draw] first_timestamp = {first_timestamp}")

            for i, (timestamp_ms, sequence, req_type) in enumerate(tester_present_markers):
                time_sec = (timestamp_ms - first_timestamp) / 1000.0

                if i < 5:  # Показываем первые 5
                    print(f"[TP Draw] Marker {i}: timestamp={timestamp_ms}, time_sec={time_sec:.3f}")

                ax.axvline(x=time_sec, color='gray', linestyle=':', alpha=0.7, linewidth=1)

            # Проверяем границы графика
            x_min, x_max = ax.get_xlim()
            print(f"[TP Draw] Graph X limits: {x_min:.3f} to {x_max:.3f}")

        # Set Y-axis ticks and labels
        y_ticks = [len(VALVE_ORDER) - idx for idx in range(len(VALVE_ORDER))]
        ax.set_yticks(y_ticks)
        ax.set_yticklabels(VALVE_ORDER, fontsize=12, fontweight='bold')

        # Labels and title - ОБНОВЛЕНО (убрали "Motor Activity Period Only")
        ax.set_xlabel('Time (seconds)', fontsize=14, fontweight='bold')
        ax.set_ylabel('Valves', fontsize=14, fontweight='bold')

        # Простой заголовок без упоминания периода активности
        ax.set_title(f'Valve Activity Timeline - {filename}', fontsize=16, fontweight='bold')

        ax.grid(True, alpha=0.3, linestyle='--')

        # УБРАНА ЛЕГЕНДА - закомментирован весь блок
        # legend_handles = []
        # legend_labels = []
        #
        # for valve in VALVE_ORDER:
        #     legend_handles.append(plt.Line2D([0], [0], color=VALVE_COLORS[valve], linewidth=3))
        #     legend_labels.append(valve)
        #
        # # Add Extended Session to legend if present
        # if ADD_EXS_AND_TP and ext_session_markers:
        #     legend_handles.append(plt.Line2D([0], [0], color='green', linestyle='--', linewidth=1.5))
        #     legend_labels.append('Extended Session')
        #
        # if legend_handles:
        #     ax.legend(legend_handles, legend_labels, loc='center left', bbox_to_anchor=(1, 0.5), fontsize=10)

        # Pressure build time table - ОБНОВЛЕНО (убрана информация о Ext Session и Tester Present)
        if pressure_stats and pressure_stats['build']:
            table_text = "Pressure Build Time:\n"
            for wheel in ['FL', 'FR', 'RL', 'RR']:
                time_val = pressure_stats['build'][wheel]
                table_text += f"{wheel}: {time_val:.3f}s\n"

            # УБРАНО - не добавляем информацию о Extended Session и Tester Present
            # if ADD_EXS_AND_TP:
            #     table_text += f"\nExt Session: {len(ext_session_markers)}"
            #     table_text += f"\nTester Present: {len(tester_present_markers)}"

            ax.text(0.98, 0.02, table_text,
                   transform=ax.transAxes,
                   fontsize=11,
                   verticalalignment='bottom',
                   horizontalalignment='right',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8, pad=0.5),
                   family='monospace',
                   fontweight='bold')

        plt.tight_layout()

        # Save figure
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        graph_filename = f"valve_timeline_{filename}_{timestamp}.png"
        graph_path = os.path.join(directory, graph_filename)

        plt.savefig(graph_path, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"[GraphDebug] Created timeline graph: {graph_path}")
        return graph_path

    except Exception as e:
        print(f"[GraphDebug] Error creating graph: {e}")
        import traceback
        traceback.print_exc()
        return None

# Добавляем таблицу команд в отчет
def get_command_reference_table():
    """Returns a formatted table of valve commands for the report"""
    table = """
COMMAND REFERENCE TABLE:
========================

Byte Patterns and Valve States:
-------------------------------

BYTES  | ACTIVE VALVES           | DESCRIPTION
-------|-------------------------|----------------------------------------
"""

    # Создаем таблицу типичных команд
    common_commands = [
        ("00 00", "none", "All valves closed"),
        ("00 02", "pump", "Pump only"),
        ("00 22", "pump, sha1", "Pump + FL/RR Shuttle"),
        ("00 42", "pump, sha2", "Pump + FR/RL Shuttle"),
        ("00 62", "pump, sha1, sha2", "Pump + Both Shuttles"),
        ("40 00", "iFL", "Inlet FL"),
        ("20 00", "iFR", "Inlet FR"),
        ("10 00", "iRL", "Inlet RL"),
        ("08 00", "iRR", "Inlet RR"),
        ("04 00", "oFL", "Outlet FL"),
        ("02 00", "oFR", "Outlet FR"),
        ("01 00", "oRL", "Outlet RL"),
        ("00 80", "oRR", "Outlet RR"),
    ]

    for bytes_val, valves, desc in common_commands:
        table += f"{bytes_val:6} | {valves:23} | {desc}\n"

    table += """
Valve Abbreviations Key:
-----------------------
pump - Pump
sha1 - FL/RR Electric Shuttle Valve
sha2 - FR/RL Electric Shuttle Valve
iso1 - FL/RR Isolating Valve
iso2 - FR/RL Isolating Valve
iFL  - Inlet Front Left
iFR  - Inlet Front Right
iRL  - Inlet Rear Left
iRR  - Inlet Rear Right
oFL  - Outlet Front Left
oFR  - Outlet Front Right
oRL  - Outlet Rear Left
oRR  - Outlet Rear Right

Pressure Modes:
--------------
BUILD   : Pump + Shuttle + Isolating + Inlet (for specific wheel)
RELEASE : Outlet valve active (for specific wheel)
"""
    return table


# Add this to your existing write_analysis_report function:
def write_analysis_report(directory, filename, processed_data, mismatches, pressure_stats, command_stats, file_format):
    """Creates detailed report file with command analysis"""
    VALVE_ORDER_FULL = [
        "pump", "FL RR Electric shuttle EV", "FR RL Electric shuttle EV",
        "FL RR Isolating EV", "FR RL Isolating EV",
        "inlet EV FL", "inlet EV FR", "inlet EV RL", "inlet EV RR",
        "outlet EV FL", "outlet EV FR", "outlet EV RL", "outlet EV RR"
    ]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"valves_analysis_{filename}_{timestamp}.txt"
    report_path = os.path.join(directory, report_filename)

    try:
        with open(report_path, 'w', encoding='utf-8') as report_file:
            report_file.write(f"File analysis: {filename}\n")
            report_file.write(f"Analysis time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            report_file.write(f"File format: {file_format.upper()}\n")
            report_file.write(f"Total combinations found: {len(processed_data)}\n")
            if ONLYREQUEST:
                report_file.write(f"Display mode: ONLY REQUESTS\n")
            else:
                report_file.write(f"Display mode: REQUESTS AND RESPONSES\n")
            report_file.write("=" * 160 + "\n\n")

            # Add command analysis at the beginning
            command_report = format_command_analysis_report(command_stats, file_format)
            report_file.write(command_report)
            report_file.write("\n\n")

            # Existing pressure mode statistics
            if pressure_stats:
                report_file.write("PRESSURE MODE STATISTICS:\n")
                report_file.write("=" * 80 + "\n\n")

                report_file.write("PRESSURE BUILD TIME (накачка):\n")
                report_file.write("-" * 40 + "\n")
                for wheel in ['FL', 'FR', 'RL', 'RR']:
                    time_val = pressure_stats['build'][wheel]
                    report_file.write(f"  {wheel}: {time_val:.3f} seconds\n")
                report_file.write("\n")

                report_file.write("PRESSURE RELEASE TIME (сброс):\n")
                report_file.write("-" * 40 + "\n")
                for wheel in ['FL', 'FR', 'RL', 'RR']:
                    time_val = pressure_stats['release'][wheel]
                    report_file.write(f"  {wheel}: {time_val:.3f} seconds\n")
                report_file.write("\n")
                report_file.write("=" * 80 + "\n\n")

            # Request/Response consistency check
            if mismatches:
                report_file.write("⚠️  REQUEST/RESPONSE MISMATCHES DETECTED:\n")
                report_file.write("-" * 80 + "\n")
                for mismatch in mismatches:
                    report_file.write(f"Line {mismatch['req_line']}: Request bytes: {mismatch['req_bytes']}\n")
                    report_file.write(f"Line {mismatch['resp_line']}: Response bytes: {mismatch['resp_bytes']}\n")
                    report_file.write(f"  Difference in valve states!\n\n")
                report_file.write("\n")

            # Valve statistics
            valve_stats = {}
            for _, _, _, _, valves, _, _, _ in processed_data:
                for valve in valves:
                    valve_stats[valve] = valve_stats.get(valve, 0) + 1

            report_file.write("ACTIVE VALVES STATISTICS:\n")
            report_file.write("-" * 40 + "\n")
            for valve_name in VALVE_ORDER_FULL:
                short_name = VALVE_NAMES[valve_name]
                if short_name in valve_stats:
                    report_file.write(f"  {short_name:<4} : {valve_stats[short_name]:>3} times\n")
            report_file.write("\n")

            # Detailed information for each found combination
            report_file.write("DETAILED COMBINATION INFORMATION:\n")
            report_file.write("=" * 160 + "\n")

            # Column headers
            report_file.write(f"{'Line':<6} | {'Sequence':<15} | {'Bytes':<8} | {'Time':<6} | {'Valve States':<52} | {'Original line (trimmed)'}\n")
            report_file.write("-" * 160 + "\n")

            for line_num, sequence, bytes_val, timediff, valves, req_type, full_line, timestamp_ms in processed_data:
                short_line = full_line[:60] + "..." if len(full_line) > 60 else full_line
                valve_display_parts = []
                for valve_name in VALVE_ORDER_FULL:
                    short_name = VALVE_NAMES[valve_name]
                    if short_name in valves:
                        valve_display_parts.append(f"{short_name:<4}")
                    else:
                        valve_display_parts.append(" " * 4)

                valves_str = "".join(valve_display_parts)
                time_str = format_timediff(timediff)

                report_file.write(f"{line_num:<6} | {sequence:<15} | {bytes_val:<8} | {time_str} | {valves_str} | {short_line}\n")

        return report_path
    except Exception as e:
        print(f"Error creating report: {e}")
        return None


def ensure_output_directory(directory, filename_no_ext):
    """
    Creates output directory named after the source file if it doesn't exist.
    Returns path to the output directory.
    """
    output_dir = os.path.join(directory, filename_no_ext)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}")
    return output_dir

def process_file(file_path, file_type='auto'):
    """
    Processes file - ОСНОВНАЯ ФУНКЦИЯ С ДОБАВЛЕННОЙ ОБРАБОТКОЙ EXS И TP
    """
    # Specific sequences we're looking for
    target_sequences = {
        "2F 4B 12 03": "Request",
        "6F 4B 12 03": "Response",
        "62 4B 12": "Read"
    }

    # For collecting data for report
    processed_data = []
    mismatches = []

    # For tracking request/response pairs
    pending_requests = {}

    # For time diff calculation
    last_timestamp_ms = None

    try:
        # Get file info and create output directory
        directory = os.path.dirname(file_path)
        filename_with_ext = os.path.basename(file_path)
        filename_no_ext = os.path.splitext(filename_with_ext)[0]

        # Use provided file_type or auto-detect
        actual_file_type = file_type if file_type != 'auto' else detect_file_format(file_path)
        print(f"Processing file as: {actual_file_type.upper()}")

        # Create output directory
        output_dir = ensure_output_directory(directory, filename_no_ext)

        # Parse input file with specified type
        messages = parse_input_file(file_path, actual_file_type)

        if not messages:
            show_message("Error", "No valid messages found in file", is_error=True)
            return

        # Analyze commands with file format information
        command_stats = analyze_commands(messages, actual_file_type)
        print("Command analysis completed")

        processed_count = 0
        output_lines = []  # For writing to output file

        # Process each message
        for idx, (timestamp_ms, hex_data, original_line) in enumerate(messages):

            # Calculate time difference
            timediff = None
            if timestamp_ms is not None and last_timestamp_ms is not None:
                timediff = timestamp_ms - last_timestamp_ms

            # Look for each target sequence
            for sequence, seq_type in target_sequences.items():
                if sequence in hex_data:
                    # Find position of sequence
                    pos = hex_data.find(sequence)
                    # Calculate position of two bytes after sequence
                    byte_start = pos + len(sequence) + 1
                    # Extract substring starting from this position
                    remaining = hex_data[byte_start:].strip()
                    # Split into parts by spaces
                    hex_parts = remaining.split()

                    # Check that we have at least 2 bytes
                    if len(hex_parts) >= 2:
                        # Take first two bytes
                        hex1 = hex_parts[0]
                        hex2 = hex_parts[1]

                        # Check if these are valid hex bytes
                        if len(hex1) == 2 and len(hex2) == 2 and all(c in '0123456789ABCDEFabcdef' for c in hex1+hex2):
                            hex_combination = f"{hex1} {hex2}"

                            try:
                                # Get list of active valves
                                active_valves = parse_valves(hex_combination)

                                # Check for request/response consistency
                                if seq_type == "Request":
                                    pending_requests[idx] = (hex_combination, active_valves)
                                elif seq_type == "Response":
                                    # Check if there was a matching request
                                    if (idx-1) in pending_requests:
                                        req_bytes, req_valves = pending_requests[idx-1]
                                        if req_bytes != hex_combination:
                                            mismatches.append({
                                                'req_line': idx,
                                                'resp_line': idx+1,
                                                'req_bytes': req_bytes,
                                                'resp_bytes': hex_combination
                                            })
                                        del pending_requests[idx-1]

                                # Form string with valves
                                if active_valves:
                                    valves_str = f" // valves_names: {', '.join(active_valves)}"
                                else:
                                    valves_str = " // valves_names: none"

                                # Decide whether to show this line based on ONLYREQUEST flag
                                should_show = True
                                if ONLYREQUEST and seq_type == "Response":
                                    should_show = False

                                if should_show:
                                    # Append to output
                                    output_line = original_line + valves_str + '\n'
                                    output_lines.append(output_line)
                                    processed_count += 1

                                    # Output to console
                                    print(f"Line {idx+1}: Found '{sequence}' ({seq_type}), bytes: {hex_combination} -> {active_valves}")

                                # Save for report
                                processed_data.append((idx+1, sequence, hex_combination, timediff, active_valves, seq_type, original_line, timestamp_ms))

                                # Update last timestamp for next iteration
                                if timestamp_ms is not None:
                                    last_timestamp_ms = timestamp_ms

                            except Exception as e:
                                print(f"Error processing combination {hex_combination}: {e}")
                                output_lines.append(original_line + '\n')

                    break  # Break loop after finding first matching sequence

            # ДОБАВЛЯЕМ: Если ADD_EXS_AND_TP = True, ищем Extended Session и Tester Present команды
            if ADD_EXS_AND_TP:
                hex_bytes = hex_data.split()
                if len(hex_bytes) >= 1:
                    # Для разных форматов файлов по-разному определяем команды
                    if actual_file_type == 'blf':
                        # В BLF первый байт - длина данных, поэтому команда на втором байте
                        if len(hex_bytes) >= 2:
                            first_byte = hex_bytes[1]
                            # Extended Session (10 03) - ищем в любом месте данных
                            if '10 03' in hex_data and len(hex_bytes) >= 3:
                                # Проверяем, что это действительно команда 10 с session 03
                                if hex_bytes[1] == '10' and hex_bytes[2] == '03':
                                    sequence = "10 03"
                                    req_type = "Extended Session"
                                    valves = []

                                    # Добавляем в output_lines
                                    output_line = original_line + f" // {req_type}\n"
                                    output_lines.append(output_line)
                                    processed_count += 1

                                    # Добавляем в processed_data
                                    processed_data.append((idx+1, sequence, " ".join(hex_bytes[1:4]), timediff, valves, req_type, original_line, timestamp_ms))

                                    print(f"Line {idx+1}: Found '{sequence}' ({req_type})")

                            # Extended Session Response (50 03)
                            elif '50 03' in hex_data and len(hex_bytes) >= 3:
                                if hex_bytes[1] == '50' and hex_bytes[2] == '03':
                                    sequence = "50 03"
                                    req_type = "Extended Session Response"
                                    valves = []

                                    output_line = original_line + f" // {req_type}\n"
                                    output_lines.append(output_line)
                                    processed_count += 1

                                    processed_data.append((idx+1, sequence, " ".join(hex_bytes[1:4]), timediff, valves, req_type, original_line, timestamp_ms))

                                    print(f"Line {idx+1}: Found '{sequence}' ({req_type})")

                            # Tester Present (3E)
                            elif first_byte == '3E':
                                sequence = "3E"
                                req_type = "Tester Present"
                                valves = []

                                output_line = original_line + f" // {req_type}\n"
                                output_lines.append(output_line)
                                processed_count += 1

                                processed_data.append((idx+1, sequence, " ".join(hex_bytes[1:3]), timediff, valves, req_type, original_line, timestamp_ms))

                                print(f"Line {idx+1}: Found '{sequence}' ({req_type})")

                            # Tester Present Response (7E)
                            elif first_byte == '7E':
                                sequence = "7E"
                                req_type = "Tester Present Response"
                                valves = []

                                output_line = original_line + f" // {req_type}\n"
                                output_lines.append(output_line)
                                processed_count += 1

                                processed_data.append((idx+1, sequence, " ".join(hex_bytes[1:3]), timediff, valves, req_type, original_line, timestamp_ms))

                                print(f"Line {idx+1}: Found '{sequence}' ({req_type})")

                    else:  # XLSX и другие форматы
                        # Для XLSX ищем команды в любом месте данных
                        first_byte = hex_bytes[0]

                        # Extended Session (10 03) - ищем в любом месте данных
                        if '10 03' in hex_data:
                            # Находим позицию команды 10 03 в данных
                            for i in range(len(hex_bytes) - 1):
                                if hex_bytes[i] == '10' and i+1 < len(hex_bytes) and hex_bytes[i+1] == '03':
                                    sequence = "10 03"
                                    req_type = "Extended Session"
                                    valves = []

                                    # Добавляем в output_lines
                                    output_line = original_line + f" // {req_type}\n"
                                    output_lines.append(output_line)
                                    processed_count += 1

                                    # Добавляем в processed_data
                                    command_bytes = " ".join(hex_bytes[i:i+2])
                                    processed_data.append((idx+1, sequence, command_bytes, timediff, valves, req_type, original_line, timestamp_ms))

                                    print(f"Line {idx+1}: Found '{sequence}' ({req_type})")
                                    break

                        # Extended Session Response (50 03)
                        elif '50 03' in hex_data:
                            for i in range(len(hex_bytes) - 1):
                                if hex_bytes[i] == '50' and i+1 < len(hex_bytes) and hex_bytes[i+1] == '03':
                                    sequence = "50 03"
                                    req_type = "Extended Session Response"
                                    valves = []

                                    output_line = original_line + f" // {req_type}\n"
                                    output_lines.append(output_line)
                                    processed_count += 1

                                    command_bytes = " ".join(hex_bytes[i:i+2])
                                    processed_data.append((idx+1, sequence, command_bytes, timediff, valves, req_type, original_line, timestamp_ms))

                                    print(f"Line {idx+1}: Found '{sequence}' ({req_type})")
                                    break

                        # Tester Present (3E) - ищем отдельно
                        elif '3E' in hex_bytes:
                            # Ищем байт 3E в любом месте данных
                            for i, byte in enumerate(hex_bytes):
                                if byte == '3E':
                                    sequence = "3E"
                                    req_type = "Tester Present"
                                    valves = []

                                    output_line = original_line + f" // {req_type}\n"
                                    output_lines.append(output_line)
                                    processed_count += 1

                                    command_bytes = "3E"
                                    processed_data.append((idx+1, sequence, command_bytes, timediff, valves, req_type, original_line, timestamp_ms))

                                    print(f"Line {idx+1}: Found '{sequence}' ({req_type})")
                                    break

                        # Tester Present Response (7E)
                        elif '7E' in hex_bytes:
                            for i, byte in enumerate(hex_bytes):
                                if byte == '7E':
                                    sequence = "7E"
                                    req_type = "Tester Present Response"
                                    valves = []

                                    output_line = original_line + f" // {req_type}\n"
                                    output_lines.append(output_line)
                                    processed_count += 1

                                    command_bytes = "7E"
                                    processed_data.append((idx+1, sequence, command_bytes, timediff, valves, req_type, original_line, timestamp_ms))

                                    print(f"Line {idx+1}: Found '{sequence}' ({req_type})")
                                    break

        # Create path for new file in output directory
        new_filename = "v_names_" + filename_no_ext + ".csv"
        new_file_path = os.path.join(output_dir, new_filename)

        # Write to new file as CSV
        try:
            with open(new_file_path, 'w', encoding='utf-8') as file:
                file.writelines(output_lines)
            print(f"Created output file: {new_file_path}")
        except Exception as write_error:
            print(f"Warning: Could not write output file: {write_error}")

        # Analyze pressure modes
        pressure_stats = analyze_pressure_modes(processed_data)

        # Create graph if enabled
        graph_path = None
        if WITHGRAPH and processed_data:
            graph_path = create_valve_timeline_graph(output_dir, filename_no_ext, processed_data, pressure_stats)

        # Create report if we have processed data
        report_path = None
        if processed_data:
            report_path = write_analysis_report(output_dir, filename_no_ext, processed_data, mismatches, pressure_stats, command_stats, actual_file_type)
            if report_path:
                print(f"\nCreated detailed report file: {report_path}")
            else:
                print("\nFailed to create detailed report file")

        # Show result in messagebox
        output_dir_name = os.path.basename(output_dir)
        mismatch_msg = f"\n⚠️ Found {len(mismatches)} request/response mismatches!" if mismatches else ""
        graph_msg = f"\nCreated timeline graph." if graph_path else ""
        show_message("Processing Complete",
                    f"Created new file: {new_filename}\n"
                    f"Output folder: {output_dir_name}\n"
                    f"Found and processed combinations: {processed_count}\n"
                    f"{'Created detailed report file.' if processed_data else ''}{mismatch_msg}{graph_msg}\n"
                    f"Original file unchanged.")

    except Exception as e:
        show_message("Error", f"Error processing file: {e}", is_error=True)
        import traceback
        traceback.print_exc()


def main():
    """Main function with enhanced XLSX type support"""
    parser = argparse.ArgumentParser(description='Process CAN log files and analyze valve commands')
    parser.add_argument('-t', '--type',
                       choices=['auto', 'blf', 'csv', 'xlsx', 'xlsx_custom', 'ascii'],
                       default='auto',
                       help='Force file type: xlsx (old factory), xlsx_custom (new factory)')
    parser.add_argument('--only-requests', action='store_true',
                       help='Process only requests (skip responses)')
    parser.add_argument('--no-graph', action='store_true',
                       help='Disable graph generation')

    args = parser.parse_args()

    # Update global flags
    global ONLYREQUEST, WITHGRAPH
    ONLYREQUEST = args.only_requests
    WITHGRAPH = not args.no_graph

    print(f"File type: {args.type}")
    print(f"Only requests: {ONLYREQUEST}")
    print(f"With graph: {WITHGRAPH}")

    # Select file
    path_to_file, directory, name_no_ext, extension = select_file("Select log file")

    if path_to_file:
        process_file(path_to_file, args.type)
    else:
        print("No file selected.")

    print("\nScript finished.")


# Main execution
if __name__ == "__main__":
    main()
