"""
CAN Bus Valve Control Replay Script - UNIVERSAL PCI FORMAT FIX
===============================================================

КРИТИЧНОЕ ИСПРАВЛЕНИЕ: АВТОДОБАВЛЕНИЕ PCI БАЙТА
- Определяет формат команд автоматически (с PCI или без)
- Добавляет PCI байт (06) для 6-байтных команд без префикса
- Конвертирует в стандартный 8-байтный UDS формат

ФОРМАТЫ:
  БЕЗ PCI:  2F 4B 12 03 00 40          (6 байт) → КОНВЕРТИРУЕТСЯ
  С PCI:    06 2F 4B 12 03 00 40 00    (8 байт) → БЕЗ ИЗМЕНЕНИЙ

ИСПОЛЬЗОВАНИЕ:
  python replay_universal_pci_fix.py                    # авто-PCI + сессия
  python replay_universal_pci_fix.py --no-session      # без авто-сессии
  python replay_universal_pci_fix.py --debug           # дебаг режим
  python replay_universal_pci_fix.py --file log.xlsx   # указать файл
"""

import can
import time
import argparse
import re
import threading
import pandas as pd
from tqdm import tqdm
from pathlib import Path
from datetime import datetime

# ANSI цветовые коды
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_WHITE = "\033[97m"
COLOR_CYAN = "\033[96m"
COLOR_BLUE = "\033[94m"
COLOR_MAGENTA = "\033[95m"
COLOR_RESET = "\033[0m"

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================
DEBUG_MODE = False
CONTROL_ZONE_ONLY = True  # Только команды управления (2F 4B)

# Файл по умолчанию
DEFAULT_FILE = "./log_to_replay/AVA_OK.xlsx"

# Адреса ECU для Tester Present
TESTER_PRESENT_ADDRESSES = [0x740, 0x745, 0x7E0, 0x7E1]

# Интервал Tester Present (секунды)
TESTER_PRESENT_INTERVAL = 2.0

# Таймаут ожидания ответа
RESPONSE_TIMEOUT = 0.5

# Пауза после последней команды (секунды)
POST_CONTROL_DELAY = 5.0

# ============================================================================
# UDS КОМАНДЫ - СТАНДАРТНЫЙ 8-БАЙТНЫЙ ФОРМАТ
# ============================================================================
UDS_EXTENDED_SESSION = bytes([0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])
UDS_TESTER_PRESENT = bytes([0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
UDS_CLEAR_DTC = bytes([0x04, 0x14, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00])

# ============================================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ TESTER PRESENT THREAD
# ============================================================================
tester_present_running = False
tester_present_thread = None
tester_present_bus = None
tester_present_lock = threading.Lock()
tester_present_stats = {"sent": 0, "success": 0, "failed": 0}

# Статистика PCI конверсий
pci_conversion_stats = {
    "converted_6to8": 0,
    "already_8byte": 0,
    "session_commands": 0
}

# Тип источника лога (для имени BLF файла)
log_source_type = "unknown"  # "ava", "piter", "from_blf"


def debug_print(msg, level="DEBUG"):
    """Печать дебаг-сообщений если включен режим отладки"""
    if DEBUG_MODE:
        colors = {
            "DEBUG": COLOR_WHITE,
            "INFO": COLOR_CYAN,
            "WARN": COLOR_YELLOW,
            "ERROR": COLOR_RED,
            "SUCCESS": COLOR_GREEN
        }
        color = colors.get(level, COLOR_WHITE)
        print(f"{color}[{level}] {msg}{COLOR_RESET}")


def generate_blf_filename(source_type, postfix=None):
    """
    Генерирует имя BLF файла на основе типа источника и времени.

    Args:
        source_type: "ava", "piter", или "from_blf"
        postfix: опциональный постфикс

    Returns:
        Путь к BLF файлу в формате: logs/cmd_replay_from_{type}_{timestamp}_{postfix}.blf
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if postfix:
        # Убираем пробелы и заменяем недопустимые символы
        safe_postfix = postfix.replace(" ", "_").replace("/", "-").replace("\\", "-")
        filename = f"cmd_replay_from_{source_type}_{timestamp}_{safe_postfix}.blf"
    else:
        filename = f"cmd_replay_from_{source_type}_{timestamp}.blf"

    # Создаём директорию logs если её нет
    logs_dir = "./logs"
    if not Path(logs_dir).exists():
        Path(logs_dir).mkdir(parents=True, exist_ok=True)
        debug_print(f"Created logs directory: {logs_dir}", "INFO")

    return str(Path(logs_dir) / filename)


# ============================================================================
# PCI FORMAT CONVERSION - КЛЮЧЕВАЯ ФУНКЦИЯ
# ============================================================================
def normalize_to_8byte_uds(data, dlc=None):
    """
    Нормализует данные в стандартный 8-байтный UDS формат с PCI байтом.

    ВХОДНЫЕ ФОРМАТЫ:
      1. 6 байт БЕЗ PCI:  2F 4B 12 03 00 40
      2. 8 байт С PCI:    06 2F 4B 12 03 00 40 00
      3. 8 байт сессия:   02 10 03 00 00 00 00 00

    ВЫХОДНОЙ ФОРМАТ (всегда 8 байт):
      06 2F 4B 12 03 00 40 00
      ^^ ^^               ^^
      │  │                └─ Padding
      │  └─ Данные
      └─ PCI (длина)
    """
    global pci_conversion_stats

    data_len = len(data)

    # СЛУЧАЙ 1: 6 байт БЕЗ PCI (начинается с 2F)
    if data_len == 6 and data[0] == 0x2F:
        # Добавляем PCI байт = 0x06 (длина данных)
        converted = bytes([0x06]) + data + bytes([0x00])
        pci_conversion_stats["converted_6to8"] += 1

        if DEBUG_MODE:
            orig = ' '.join([f'{b:02X}' for b in data])
            new = ' '.join([f'{b:02X}' for b in converted])
            print(f"{COLOR_YELLOW}[PCI ADD] {orig} → {new}{COLOR_RESET}")

        return converted

    # СЛУЧАЙ 2: 8 байт, УЖЕ С PCI (второй байт = 2F или первый = 02/04/06)
    elif data_len == 8:
        pci_byte = data[0]

        # Проверяем валидность PCI
        if pci_byte in [0x02, 0x04, 0x06]:
            # Уже правильный формат
            if data[1] == 0x2F:
                pci_conversion_stats["already_8byte"] += 1
            else:
                pci_conversion_stats["session_commands"] += 1

            return data
        else:
            # Возможно неправильный формат, но оставляем как есть
            debug_print(f"Unexpected 8-byte format, PCI={pci_byte:02X}", "WARN")
            return data

    # СЛУЧАЙ 3: Другая длина - возвращаем как есть с предупреждением
    else:
        debug_print(f"Unexpected data length: {data_len}", "WARN")
        return data


# ============================================================================
# TESTER PRESENT BACKGROUND THREAD
# ============================================================================
def tester_present_worker():
    """Фоновый поток для отправки Tester Present"""
    global tester_present_running, tester_present_bus, tester_present_stats

    debug_print("Tester Present thread started", "INFO")

    while tester_present_running:
        try:
            with tester_present_lock:
                if tester_present_bus is None:
                    break

                for addr in TESTER_PRESENT_ADDRESSES:
                    msg = can.Message(
                        arbitration_id=addr,
                        data=UDS_TESTER_PRESENT,
                        is_extended_id=False
                    )
                    try:
                        tester_present_bus.send(msg)
                        tester_present_stats["sent"] += 1
                        tester_present_stats["success"] += 1
                        debug_print(f"Tester Present sent to 0x{addr:03X}", "DEBUG")
                    except Exception as e:
                        tester_present_stats["failed"] += 1
                        debug_print(f"Tester Present failed for 0x{addr:03X}: {e}", "ERROR")

            time.sleep(TESTER_PRESENT_INTERVAL)

        except Exception as e:
            debug_print(f"Tester Present thread error: {e}", "ERROR")
            break

    debug_print("Tester Present thread stopped", "INFO")


def start_tester_present(bus):
    """Запуск фонового потока Tester Present"""
    global tester_present_running, tester_present_thread, tester_present_bus, tester_present_stats

    tester_present_bus = bus
    tester_present_running = True
    tester_present_stats = {"sent": 0, "success": 0, "failed": 0}

    tester_present_thread = threading.Thread(target=tester_present_worker, daemon=True)
    tester_present_thread.start()

    print(f"{COLOR_GREEN}>>> Tester Present thread started (every {TESTER_PRESENT_INTERVAL}s){COLOR_RESET}")


def stop_tester_present():
    """Остановка фонового потока Tester Present"""
    global tester_present_running, tester_present_thread

    tester_present_running = False
    if tester_present_thread is not None:
        tester_present_thread.join(timeout=3.0)

    print(f"{COLOR_YELLOW}>>> Tester Present thread stopped{COLOR_RESET}")
    print(f"{COLOR_WHITE}    Sent: {tester_present_stats['sent']}, Success: {tester_present_stats['success']}, Failed: {tester_present_stats['failed']}{COLOR_RESET}")


# ============================================================================
# SESSION INITIALIZATION
# ============================================================================
def initialize_diagnostic_session(bus, timeout=0.5):
    """Инициализация диагностической сессии"""
    print(f"\n{COLOR_CYAN}{'='*60}{COLOR_RESET}")
    print(f"{COLOR_CYAN}ИНИЦИАЛИЗАЦИЯ ДИАГНОСТИЧЕСКОЙ СЕССИИ{COLOR_RESET}")
    print(f"{COLOR_CYAN}{'='*60}{COLOR_RESET}")

    success_count = 0

    # Последовательность инициализации
    init_sequence = [
        (UDS_EXTENDED_SESSION, "Extended Session (10 03)"),
        (UDS_TESTER_PRESENT, "Tester Present (3E 00)"),
    ]

    for addr in TESTER_PRESENT_ADDRESSES:
        print(f"\n{COLOR_WHITE}>>> Инициализация ECU 0x{addr:03X}{COLOR_RESET}")

        for cmd_data, cmd_name in init_sequence:
            msg = can.Message(
                arbitration_id=addr,
                data=cmd_data,
                is_extended_id=False
            )

            try:
                bus.send(msg)
                data_hex = ' '.join([f'{b:02X}' for b in cmd_data])
                print(f"{COLOR_WHITE}    TX 0x{addr:03X}: {data_hex} ({cmd_name}){COLOR_RESET}")

                # Ждем ответ
                response_addr = addr + 0x20 if addr == 0x740 else addr + 0x08
                start_wait = time.perf_counter()
                response_received = False

                while (time.perf_counter() - start_wait) < timeout:
                    response = bus.recv(timeout=0.05)
                    if response is not None:
                        if response.arbitration_id in [response_addr, 0x760, 0x7E8]:
                            resp_hex = ' '.join([f'{b:02X}' for b in response.data])

                            if len(response.data) >= 2:
                                if response.data[1] == 0x50:
                                    print(f"{COLOR_GREEN}    RX 0x{response.arbitration_id:03X}: {resp_hex} (OK){COLOR_RESET}")
                                    success_count += 1
                                    response_received = True
                                    break
                                elif response.data[1] == 0x7E:
                                    print(f"{COLOR_GREEN}    RX 0x{response.arbitration_id:03X}: {resp_hex} (OK){COLOR_RESET}")
                                    success_count += 1
                                    response_received = True
                                    break
                                elif response.data[1] == 0x7F:
                                    print(f"{COLOR_RED}    RX 0x{response.arbitration_id:03X}: {resp_hex} (NEGATIVE){COLOR_RESET}")
                                    response_received = True
                                    break

                if not response_received:
                    print(f"{COLOR_YELLOW}    RX 0x{response_addr:03X}: TIMEOUT{COLOR_RESET}")

            except Exception as e:
                print(f"{COLOR_RED}    ERROR: {e}{COLOR_RESET}")

        time.sleep(0.1)

    # Clear DTC
    print(f"\n{COLOR_WHITE}>>> Отправка Clear DTC{COLOR_RESET}")
    msg = can.Message(arbitration_id=0x740, data=UDS_CLEAR_DTC, is_extended_id=False)
    try:
        bus.send(msg)
        data_hex = ' '.join([f'{b:02X}' for b in UDS_CLEAR_DTC])
        print(f"{COLOR_WHITE}    TX 0x740: {data_hex}{COLOR_RESET}")
        time.sleep(0.2)
    except Exception as e:
        print(f"{COLOR_RED}    ERROR: {e}{COLOR_RESET}")

    print(f"\n{COLOR_CYAN}{'='*60}{COLOR_RESET}")
    print(f"{COLOR_GREEN}Сессия инициализирована. Успешно: {success_count}{COLOR_RESET}")
    print(f"{COLOR_CYAN}{'='*60}{COLOR_RESET}\n")

    time.sleep(0.5)
    return success_count > 0


# ============================================================================
# KVASER HARDWARE CHECK
# ============================================================================
try:
    from canlib import canlib
    CANLIB_AVAILABLE = True
except ImportError:
    CANLIB_AVAILABLE = False
    canlib = None

def check_kvaser_hardware():
    """Проверяет наличие реального Kvaser адаптера"""
    if not CANLIB_AVAILABLE:
        return False, "canlib not available"

    try:
        num_channels = canlib.getNumberOfChannels()
        if num_channels == 0:
            return False, "No Kvaser channels found"

        for ch in range(num_channels):
            chd = canlib.ChannelData(ch)
            if "Virtual" not in chd.channel_name:
                return True, f"{chd.channel_name}"

        return False, "Only virtual channels found"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ============================================================================
# FILE PARSING WITH PCI NORMALIZATION
# ============================================================================
def parse_xlsx_file(file_path):
    """Парсит XLSX файл с автоматической нормализацией PCI"""
    global pci_conversion_stats

    try:
        df = pd.read_excel(file_path)
        print(f"{COLOR_WHITE}XLSX файл загружен. Строк: {len(df)}{COLOR_RESET}")

        # Проверяем колонки
        required_columns = ['№ п/п', 'Date', 'Time', 'Type', 'Level', 'Event']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            print(f"{COLOR_RED}ОШИБКА: Отсутствуют колонки: {missing_columns}{COLOR_RESET}")
            return []

        # Фильтруем CAN сообщения
        df_can = df[df['Type'] == 'Can'].copy()
        print(f"{COLOR_WHITE}Найдено CAN сообщений: {len(df_can)}{COLOR_RESET}")

        if len(df_can) == 0:
            print(f"{COLOR_RED}ОШИБКА: Нет CAN сообщений{COLOR_RESET}")
            return []

        messages = []
        base_timestamp = None

        def parse_timestamp(date_str, time_str):
            try:
                datetime_str = f"{date_str} {time_str}"
                dt = datetime.strptime(datetime_str, "%d.%m.%Y %H:%M:%S.%f")
                return dt.timestamp()
            except ValueError:
                try:
                    dt = datetime.strptime(datetime_str, "%d.%m.%Y %H:%M:%S")
                    return dt.timestamp()
                except:
                    return None

        def parse_can_event(event_str):
            pattern = r'\[(0x[0-9a-fA-F]+)\]\s*\((\d+)\)\s*(->|<-)\s*(.+)'
            match = re.search(pattern, event_str)

            if match:
                can_id = match.group(1)
                dlc = int(match.group(2))
                direction = match.group(3)
                data_hex = match.group(4)

                try:
                    arbitration_id = int(can_id, 16)
                    hex_bytes = data_hex.split()
                    data_bytes = bytes(int(byte, 16) for byte in hex_bytes)
                    return arbitration_id, data_bytes, direction, dlc
                except:
                    return None, None, None, None

            return None, None, None, None

        # Статистика
        stats = {
            "total_can": 0,
            "parsed_ok": 0,
            "is_740_tx": 0,
            "extended_filtered": 0,
        }

        for idx, row in df_can.iterrows():
            stats["total_can"] += 1
            try:
                timestamp = parse_timestamp(row['Date'], row['Time'])
                if timestamp is None:
                    continue

                if base_timestamp is None:
                    base_timestamp = timestamp

                arbitration_id, data, direction, dlc = parse_can_event(str(row['Event']))
                if arbitration_id is None:
                    continue

                # Фильтруем extended ID
                if arbitration_id > 0x7FF:
                    stats["extended_filtered"] += 1
                    continue

                # КРИТИЧНО: Нормализуем в 8-байтный формат с PCI
                data_normalized = normalize_to_8byte_uds(data, dlc)

                stats["parsed_ok"] += 1
                relative_timestamp = timestamp - base_timestamp
                is_rx = (direction == '<-')

                msg = can.Message(
                    arbitration_id=arbitration_id,
                    data=data_normalized,  # ИСПОЛЬЗУЕМ НОРМАЛИЗОВАННЫЕ ДАННЫЕ
                    timestamp=relative_timestamp,
                    is_rx=is_rx,
                    is_extended_id=False
                )

                if arbitration_id == 0x740 and not is_rx:
                    stats["is_740_tx"] += 1

                messages.append(msg)

            except Exception as e:
                debug_print(f"Parse error row {idx}: {e}", "ERROR")

        # Статистика PCI конверсий
        print(f"\n{COLOR_CYAN}=== СТАТИСТИКА ПАРСИНГА ==={COLOR_RESET}")
        print(f"{COLOR_WHITE}  Всего CAN строк: {stats['total_can']}{COLOR_RESET}")
        print(f"{COLOR_WHITE}  Успешно распарсено: {stats['parsed_ok']}{COLOR_RESET}")
        print(f"{COLOR_RED}  Extended ID отфильтровано: {stats['extended_filtered']}{COLOR_RESET}")
        print(f"{COLOR_GREEN}  TX 0x740: {stats['is_740_tx']}{COLOR_RESET}")

        print(f"\n{COLOR_CYAN}=== PCI КОНВЕРСИИ ==={COLOR_RESET}")
        print(f"{COLOR_YELLOW}  6→8 байт (добавлен PCI): {pci_conversion_stats['converted_6to8']}{COLOR_RESET}")
        print(f"{COLOR_GREEN}  Уже 8 байт (2F 4B): {pci_conversion_stats['already_8byte']}{COLOR_RESET}")
        print(f"{COLOR_WHITE}  Команды сессии: {pci_conversion_stats['session_commands']}{COLOR_RESET}")

        # Определяем тип источника лога
        global log_source_type
        if pci_conversion_stats['converted_6to8'] > pci_conversion_stats['already_8byte']:
            log_source_type = "ava"  # Завод 2 (без PCI, нужна конверсия)
            print(f"{COLOR_CYAN}  Тип лога: AVA (завод 2, 6→8 конверсия){COLOR_RESET}")
        elif pci_conversion_stats['already_8byte'] > pci_conversion_stats['converted_6to8']:
            log_source_type = "piter"  # Завод 1 (уже с PCI)
            print(f"{COLOR_CYAN}  Тип лога: PITER (завод 1, уже с PCI){COLOR_RESET}")
        else:
            log_source_type = "unknown"
            print(f"{COLOR_YELLOW}  Тип лога: UNKNOWN{COLOR_RESET}")

        # Фильтруем только TX 0x740
        messages_740 = [msg for msg in messages if msg.arbitration_id == 0x740 and not msg.is_rx]
        print(f"\n{COLOR_GREEN}Сообщений 0x740 для проигрывания: {len(messages_740)}{COLOR_RESET}")

        return messages_740

    except Exception as e:
        print(f"{COLOR_RED}Ошибка чтения XLSX: {e}{COLOR_RESET}")
        import traceback
        traceback.print_exc()
        return []


def read_can_messages(file_path):
    """Читает CAN сообщения из BLF или XLSX"""
    global log_source_type

    file_ext = Path(file_path).suffix.lower()

    if file_ext == '.blf':
        log_source_type = "from_blf"  # Из BLF файла

        messages = []
        extended_filtered = 0
        with can.BLFReader(file_path) as log:
            for msg in log:
                if msg.is_extended_id:
                    extended_filtered += 1
                    continue

                if msg.arbitration_id == 0x740:
                    msg.is_extended_id = False
                    # Нормализуем данные
                    msg.data = normalize_to_8byte_uds(msg.data)
                    messages.append(msg)

        print(f"{COLOR_GREEN}BLF: найдено {len(messages)} сообщений 0x740{COLOR_RESET}")
        if extended_filtered > 0:
            print(f"{COLOR_RED}BLF: отфильтровано {extended_filtered} extended ID{COLOR_RESET}")
        print(f"{COLOR_CYAN}Тип лога: FROM_BLF{COLOR_RESET}")
        return messages

    elif file_ext in ['.xlsx', '.xls']:
        return parse_xlsx_file(file_path)

    else:
        print(f"{COLOR_RED}Неподдерживаемый формат: {file_ext}{COLOR_RESET}")
        return []


# ============================================================================
# MESSAGE FILTERING
# ============================================================================
def is_valve_control_command(data):
    """Проверяет, является ли сообщение командой управления клапанами (2F 4B)"""
    # Теперь все данные в 8-байтном формате: 06 2F 4B 12 03 XX YY 00
    if len(data) >= 8 and data[1] == 0x2F and data[2] == 0x4B:
        return True
    return False


def filter_control_zone(messages):
    """Фильтрует сообщения, оставляя только зону управления клапанами"""
    first_idx = None
    last_idx = None

    for i, msg in enumerate(messages):
        if is_valve_control_command(msg.data):
            if first_idx is None:
                first_idx = i
            last_idx = i

    if first_idx is None:
        print(f"{COLOR_RED}ОШИБКА: Не найдено команд управления клапанами (2F 4B)!{COLOR_RESET}")
        return []

    control_messages = messages[first_idx:last_idx + 1]

    print(f"\n{COLOR_CYAN}=== CONTROL_ZONE_ONLY ==={COLOR_RESET}")
    print(f"{COLOR_WHITE}  Всего сообщений: {len(messages)}{COLOR_RESET}")
    print(f"{COLOR_WHITE}  Первая команда 2F 4B: индекс {first_idx}{COLOR_RESET}")
    print(f"{COLOR_WHITE}  Последняя команда 2F 4B: индекс {last_idx}{COLOR_RESET}")
    print(f"{COLOR_GREEN}  Команд в зоне управления: {len(control_messages)}{COLOR_RESET}")

    # Пересчитываем timestamp
    if control_messages:
        base_ts = control_messages[0].timestamp
        for msg in control_messages:
            msg.timestamp = msg.timestamp - base_ts

    return control_messages


# ============================================================================
# MESSAGE FORMATTING
# ============================================================================
def get_message_type(data):
    """Определяет тип сообщения"""
    if len(data) >= 2:
        if data[0] == 0x02 and data[1] == 0x3E:
            return "tester_present"
        if data[0] == 0x02 and data[1] == 0x10:
            return "extended_session"
        if len(data) >= 3 and data[1] == 0x2F and data[2] == 0x4B:
            return "valve_command"
        if data[1] == 0x7F:
            return "negative_response"
    return "other"


def get_color_for_message(msg_type, is_response=False):
    """Возвращает цвет для типа сообщения"""
    colors = {
        "negative_response": COLOR_RED,
        "tester_present": COLOR_YELLOW,
        "extended_session": COLOR_YELLOW,
        "valve_command": COLOR_WHITE,
    }
    if is_response and msg_type not in colors:
        return COLOR_GREEN
    return colors.get(msg_type, COLOR_WHITE)


def format_message(msg, color):
    """Форматирует сообщение для вывода"""
    data_hex = ' '.join([f'{b:02X}' for b in msg.data])
    direction = "Rx" if msg.is_rx else "Tx"
    return f"{color}{msg.timestamp:12.6f} {msg.channel}  {msg.arbitration_id:03X}       {direction}   d {len(msg.data)} {data_hex}{COLOR_RESET}"


# ============================================================================
# MAIN REPLAY FUNCTION
# ============================================================================
def replay_740_760(use_virtual=False, auto_session=True, file_path=None, enable_blf=True, postfix=None, blf_file=None):
    """Проигрывание сообщений 0x740 с ожиданием ответов 0x760"""

    blf_file_path = file_path or DEFAULT_FILE
    channel = 0
    bitrate = 500000
    timeout = RESPONSE_TIMEOUT

    print(f"\n{COLOR_MAGENTA}{'='*70}{COLOR_RESET}")
    print(f"{COLOR_MAGENTA}CAN VALVE CONTROL REPLAY - UNIVERSAL PCI FIX{COLOR_RESET}")
    print(f"{COLOR_MAGENTA}{'='*70}{COLOR_RESET}")
    print(f"{COLOR_WHITE}Файл: {blf_file_path}{COLOR_RESET}")
    print(f"{COLOR_WHITE}Авто-сессия: {'ДА' if auto_session else 'НЕТ'}{COLOR_RESET}")
    print(f"{COLOR_WHITE}CONTROL_ZONE_ONLY: {'ДА' if CONTROL_ZONE_ONLY else 'НЕТ'}{COLOR_RESET}")
    print(f"{COLOR_GREEN}PCI: АВТОМАТИЧЕСКАЯ НОРМАЛИЗАЦИЯ В 8-БАЙТНЫЙ ФОРМАТ{COLOR_RESET}")
    print(f"{COLOR_WHITE}BLF логирование: {'ДА' if enable_blf else 'НЕТ'}{COLOR_RESET}")

    if not Path(blf_file_path).exists():
        print(f"{COLOR_RED}Файл {blf_file_path} не найден!{COLOR_RESET}")
        return

    # Проверка Kvaser
    if not use_virtual:
        hw_present, hw_info = check_kvaser_hardware()
        if not hw_present:
            print(f"{COLOR_RED}Kvaser адаптер не найден: {hw_info}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}Используйте --virtual для виртуального канала{COLOR_RESET}")
            return
        print(f"{COLOR_GREEN}Kvaser: {hw_info}{COLOR_RESET}")

    try:
        # Чтение файла (здесь определяется log_source_type)
        print(f"\n{COLOR_WHITE}Чтение файла...{COLOR_RESET}")
        requests_740 = read_can_messages(blf_file_path)

        if not requests_740:
            print(f"{COLOR_RED}Нет сообщений 0x740{COLOR_RESET}")
            return

        # ТЕПЕРЬ можем генерировать имя BLF файла (тип уже определён)
        blf_output = None
        if enable_blf:
            if blf_file:
                # Пользователь указал своё имя
                blf_output = blf_file
                print(f"{COLOR_GREEN}BLF файл (пользовательский): {blf_output}{COLOR_RESET}")
            else:
                # Автогенерация на основе типа источника
                blf_output = generate_blf_filename(log_source_type, postfix)
                print(f"{COLOR_GREEN}BLF файл (автоген): {blf_output}{COLOR_RESET}")

        total_requests = len(requests_740)
        print(f"{COLOR_GREEN}Найдено запросов 0x740: {total_requests}{COLOR_RESET}")

        # Фильтрация зоны управления
        if CONTROL_ZONE_ONLY:
            requests_740 = filter_control_zone(requests_740)
            if not requests_740:
                print(f"{COLOR_RED}Нет команд для проигрывания{COLOR_RESET}")
                return
            total_requests = len(requests_740)

        # Подключение к CAN
        if use_virtual:
            bus = can.Bus(interface='kvaser', channel=channel, bitrate=bitrate,
                         accept_virtual=True, receive_own_messages=False)
            print(f"{COLOR_WHITE}Подключение к Kvaser VIRTUAL channel {channel}{COLOR_RESET}")
        else:
            bus = can.Bus(interface='kvaser', channel=channel, bitrate=bitrate,
                         receive_own_messages=False)
            print(f"{COLOR_WHITE}Подключение к Kvaser channel {channel}{COLOR_RESET}")

        with bus:
            # Инициализация BLF логгера
            logger = None
            if blf_output:
                try:
                    logger = can.BLFWriter(blf_output)
                    print(f"{COLOR_GREEN}>>> BLF логгер инициализирован: {blf_output}{COLOR_RESET}")
                except Exception as e:
                    print(f"{COLOR_RED}Ошибка инициализации BLF логгера: {e}{COLOR_RESET}")
                    logger = None

            # Инициализация сессии
            if auto_session:
                initialize_diagnostic_session(bus, timeout=0.3)
                start_tester_present(bus)

            print(f"\n{COLOR_YELLOW}Проигрывание 0x740 -> 0x760{COLOR_RESET}")
            print(f"{COLOR_WHITE}Нажмите Ctrl+C для остановки{COLOR_RESET}")
            print()

            pbar = tqdm(total=total_requests, desc="Отправка 0x740", unit="msg", ncols=100)

            start_time = time.perf_counter()
            first_timestamp = requests_740[0].timestamp

            success_count = 0
            timeout_count = 0
            error_count = 0

            for i, msg in enumerate(requests_740):
                try:
                    # Выдерживаем интервалы
                    elapsed = msg.timestamp - first_timestamp
                    while (time.perf_counter() - start_time) < elapsed:
                        time.sleep(0.001)

                    msg_type = get_message_type(msg.data)
                    color_req = get_color_for_message(msg_type)

                    # Вычисляем правильный timestamp
                    current_ts = time.perf_counter() - start_time + first_timestamp

                    # Отправляем (без timestamp для отправки)
                    tx_msg = can.Message(
                        arbitration_id=msg.arbitration_id,
                        data=msg.data,
                        is_extended_id=False
                    )

                    with tester_present_lock:
                        bus.send(tx_msg)

                    # Создаём сообщение для логирования С ПРАВИЛЬНЫМ TIMESTAMP
                    log_msg = can.Message(
                        arbitration_id=msg.arbitration_id,
                        data=msg.data,
                        timestamp=current_ts,
                        channel=channel,
                        is_rx=False,
                        is_extended_id=False
                    )

                    # Логируем сообщение с правильным timestamp
                    if logger:
                        try:
                            logger.on_message_received(log_msg)
                        except Exception as e:
                            debug_print(f"BLF log error (TX): {e}", "ERROR")

                    print(format_message(log_msg, color_req))

                    # Ждем ответ
                    response = None
                    response_received = False
                    start_wait = time.perf_counter()

                    while (time.perf_counter() - start_wait) < timeout:
                        remaining = timeout - (time.perf_counter() - start_wait)
                        if remaining <= 0:
                            break
                        response = bus.recv(timeout=remaining)
                        if response is not None and response.arbitration_id == 0x760:
                            response_received = True
                            break

                    if response_received and response is not None:
                        resp_type = get_message_type(response.data)
                        color_resp = get_color_for_message(resp_type, is_response=True)

                        # Устанавливаем правильный относительный timestamp
                        response.timestamp = time.perf_counter() - start_time + first_timestamp
                        response.channel = channel

                        # Логируем ответ С ПРАВИЛЬНЫМ TIMESTAMP
                        if logger:
                            try:
                                logger.on_message_received(response)
                            except Exception as e:
                                debug_print(f"BLF log error (RX): {e}", "ERROR")

                        print(format_message(response, color_resp))

                        if resp_type == "negative_response":
                            error_count += 1
                        else:
                            success_count += 1
                    else:
                        timeout_ts = time.perf_counter() - start_time + first_timestamp
                        print(f"{COLOR_RED}{timeout_ts:12.6f} {channel}  760       Rx   d 0 TIMEOUT{COLOR_RESET}")
                        timeout_count += 1

                    pbar.update(1)
                    print()

                except KeyboardInterrupt:
                    print(f"\n{COLOR_YELLOW}Остановлено пользователем{COLOR_RESET}")
                    break
                except Exception as e:
                    print(f"{COLOR_RED}Ошибка: {e}{COLOR_RESET}")
                    continue

            pbar.close()

            # Пауза после последней команды
            if CONTROL_ZONE_ONLY:
                print(f"\n{COLOR_CYAN}>>> Ожидание {POST_CONTROL_DELAY} секунд...{COLOR_RESET}")
                time.sleep(POST_CONTROL_DELAY)

            # Останавливаем Tester Present
            if auto_session:
                stop_tester_present()

            # Закрываем BLF логгер
            if logger:
                try:
                    logger.stop()
                    print(f"{COLOR_GREEN}>>> BLF логгер закрыт: {blf_output}{COLOR_RESET}")
                except Exception as e:
                    print(f"{COLOR_RED}Ошибка закрытия BLF логгера: {e}{COLOR_RESET}")

            # Итоги
            print()
            print(f"{COLOR_GREEN}{'='*60}{COLOR_RESET}")
            print(f"{COLOR_WHITE}Воспроизведение завершено{COLOR_RESET}")
            print(f"{COLOR_GREEN}Успешных ответов: {success_count}{COLOR_RESET}")
            print(f"{COLOR_RED}Negative Response: {error_count}{COLOR_RESET}")
            print(f"{COLOR_RED}Таймаутов: {timeout_count}{COLOR_RESET}")
            print(f"{COLOR_GREEN}{'='*60}{COLOR_RESET}")

    except Exception as e:
        print(f"{COLOR_RED}Критическая ошибка: {e}{COLOR_RESET}")
        import traceback
        traceback.print_exc()

        if auto_session:
            stop_tester_present()

        # Закрываем логгер при ошибке
        if 'logger' in locals() and logger:
            try:
                logger.stop()
            except:
                pass


# ============================================================================
# MAIN
# ============================================================================
def main():
    global DEBUG_MODE, CONTROL_ZONE_ONLY

    parser = argparse.ArgumentParser(
        description='CAN Valve Control Replay - Universal PCI Fix',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s                                # Базовое использование с автологом
  %(prog)s --file log.xlsx                # Указать файл
  %(prog)s -p "test1"                     # С постфиксом в имени лога
  %(prog)s --postfix "diag_test"          # С постфиксом (полная форма)
  %(prog)s --no-blf                       # Без логирования
  %(prog)s --blf-file custom.blf          # Своё имя BLF файла
  %(prog)s --no-session                   # Без автосессии
  %(prog)s --virtual                      # Виртуальный канал
  %(prog)s --debug                        # Режим отладки
        """
    )

    parser.add_argument('--virtual', '-v', action='store_true',
                        help='Использовать виртуальный канал')
    parser.add_argument('--no-session', action='store_true',
                        help='Отключить автоматическую сессию')
    parser.add_argument('--no-control-zone', action='store_true',
                        help='Отключить фильтрацию')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Включить дебаг')
    parser.add_argument('--file', '-f', type=str, default=None,
                        help='Путь к файлу')

    # Аргументы для логирования
    parser.add_argument('--postfix', '-p', type=str, default=None,
                        help='Постфикс для имени BLF файла (опционально)')
    parser.add_argument('--no-blf', action='store_true',
                        help='Отключить BLF логирование')
    parser.add_argument('--blf-file', type=str, default=None,
                        help='Путь к BLF файлу (по умолчанию - автогенерация)')

    args = parser.parse_args()

    DEBUG_MODE = args.debug

    if args.no_control_zone:
        CONTROL_ZONE_ONLY = False

    replay_740_760(
        use_virtual=args.virtual,
        auto_session=not args.no_session,
        file_path=args.file,
        enable_blf=not args.no_blf,
        postfix=args.postfix,
        blf_file=args.blf_file
    )


if __name__ == "__main__":
    main()
