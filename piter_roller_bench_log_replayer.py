"""
CAN Bus Valve Control Replay Script
====================================

НАЗНАЧЕНИЕ:
Скрипт воспроизводит CAN-сообщения из BLF-файла для управления клапанами
гидроблока ABS/ESC. Отправляет только сообщения 0x740 и ожидает ответы 0x760.

КЛЮЧЕВАЯ ФУНКЦИЯ - REPLACE_CMD:
При REPLACE_CMD = True скрипт модифицирует команды управления клапанами (4B12),
отключая изолирующие и питающие клапаны НЕАКТИВНОЙ диагонали.

Диагонали тормозной системы:
  - FL-RR (Front Left - Rear Right): изоляция 0xA (биты 1,3)
  - FR-RL (Front Right - Rear Left): изоляция 0x5 (биты 0,2)

Последовательность колёс: FL → FR → RL → RR
Переключение на следующее колесо происходит при обнаружении команды
на выпускной клапан текущего колеса.

Выпускные клапаны (в valve byte, data[5]):
  - FL: бит 1 (0x02)
  - FR: бит 3 (0x08)
  - RL: бит 5 (0x20)
  - RR: бит 7 (0x80)

ФОРМАТ КОМАНДЫ 4B12:
06 2F 4B 12 03 XX YY 00
  - XX (data[5]): управление клапанами (впускные/выпускные)
  - YY (data[6]): изоляция/питание, младший ниббл модифицируется

ЦВЕТОВОЕ КОДИРОВАНИЕ:
  - Белый: обычные команды
  - Жёлтый: Tester Present (3E/7E) и Extended Session (10 03)
  - Зелёный: положительные ответы
  - Красный: Negative Response и таймауты
  - Cyan: модифицированные команды и переключение колёс

ИСПОЛЬЗОВАНИЕ:
  python replay_740_760.py              # реальный Kvaser адаптер
  python replay_740_760.py --virtual    # виртуальный канал (для теста)
  python replay_740_760.py -v           # короткий флаг

КОНФИГУРАЦИЯ:
  - blf_file_path: путь к BLF файлу
  - channel: номер канала Kvaser (0 = первый)
  - bitrate: скорость CAN (по умолчанию 500000)
  - timeout: таймаут ожидания ответа
  - REPLACE_CMD: True для модификации команд, False для оригинальных

ТРЕБОВАНИЯ:
  - python-can
  - canlib (Kvaser CANlib SDK)
  - tqdm (прогресс-бар)
  - pandas (для XLSX файлов)

ИЗВЕСТНЫЕ БАГИ:
    Так и не проигрывает логи из автоваза. Так и не нашёл я баг. Но это и не потребовалось.
    Понятия не имею, почему. вроде смотрел логи, вроде там норм. И симулятор вроде отвечал успешно. А реальный лог не отвечает
"""

import can
import time
import argparse
import re
import pandas as pd
from tqdm import tqdm
from pathlib import Path
from datetime import datetime
from canlib import canlib

# ANSI цветовые коды
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_WHITE = "\033[97m"
COLOR_CYAN = "\033[96m"
COLOR_RESET = "\033[0m"

# Флаг для подмены команд - выключение неактивной диагонали
REPLACE_CMD = True

#  BLF_FILE_PATH = "./log_to_replay/XTAGA0000T0014007.xlsx"
BLF_FILE_PATH = "/home/st/tmptmp/Roller_bench_12025_11_18_13_25_30_xjo_dynamic_OK.blf"




def check_kvaser_hardware():
    """Проверяет наличие реального Kvaser адаптера через CANlib"""
    try:
        num_channels = canlib.getNumberOfChannels()

        for ch in range(num_channels):
            chd = canlib.ChannelData(ch)
            if "Virtual" not in chd.channel_name:
                return True, f"{chd.channel_name} (SN: {chd.card_serial_no}, ch {chd.chan_no_on_card})"

        return False, "Only virtual channels found"
    except canlib.exceptions.CanGeneralError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def parse_xlsx_file(file_path):
    """
    Парсит XLSX файл нового завода и возвращает список CAN сообщений.

    Формат XLSX нового завода:
    № п/п | Date       | Time         | Type | Level | Event
    """
    try:
        # Читаем Excel файл
        df = pd.read_excel(file_path)
        print(f"{COLOR_WHITE}XLSX файл загружен. Строк: {len(df)}{COLOR_RESET}")
        print(f"{COLOR_WHITE}Колонки: {df.columns.tolist()}{COLOR_RESET}")

        # Проверяем наличие обязательных колонок
        required_columns = ['№ п/п', 'Date', 'Time', 'Type', 'Level', 'Event']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            print(f"{COLOR_RED}ОШИБКА: В файле отсутствуют обязательные колонки: {missing_columns}{COLOR_RESET}")
            return []

        # Фильтруем только CAN сообщения
        df_can = df[df['Type'] == 'Can'].copy()
        print(f"{COLOR_WHITE}Найдено CAN сообщений: {len(df_can)}{COLOR_RESET}")

        if len(df_can) == 0:
            print(f"{COLOR_RED}ОШИБКА: В файле нет CAN сообщений (Type='Can'){COLOR_RESET}")
            return []

        messages = []
        base_timestamp = None

        # Функция для парсинга времени
        def parse_timestamp(date_str, time_str):
            try:
                # Объединяем дату и время
                datetime_str = f"{date_str} {time_str}"
                # Парсим в datetime объект
                dt = datetime.strptime(datetime_str, "%d.%m.%Y %H:%M:%S.%f")
                return dt.timestamp()
            except ValueError:
                try:
                    dt = datetime.strptime(datetime_str, "%d.%m.%Y %H:%M:%S")
                    return dt.timestamp()
                except Exception as e:
                    print(f"{COLOR_RED}Ошибка парсинга времени '{datetime_str}': {e}{COLOR_RESET}")
                    return None

        # Функция для парсинга CAN события
        def parse_can_event(event_str):
            pattern = r'\[(0x[0-9a-fA-F]+)\]\s*\((\d+)\)\s*(->|<-)\s*(.+)'
            match = re.search(pattern, event_str)

            if match:
                can_id = match.group(1)  # 0x740 или 0x760
                dlc = int(match.group(2))
                direction = match.group(3)  # -> или <-
                data_hex = match.group(4)   # HEX данные

                # Конвертируем CAN ID
                try:
                    arbitration_id = int(can_id, 16)
                except:
                    print(f"{COLOR_RED}Ошибка парсинга CAN ID: {can_id}{COLOR_RESET}")
                    return None, None, None

                # Конвертируем HEX данные в байты
                try:
                    hex_bytes = data_hex.split()
                    data_bytes = bytes(int(byte, 16) for byte in hex_bytes)

                    if len(data_bytes) != dlc:
                        print(f"{COLOR_YELLOW}Предупреждение: DLC ({dlc}) не соответствует длине данных ({len(data_bytes)}){COLOR_RESET}")

                    return arbitration_id, data_bytes, direction
                except Exception as e:
                    print(f"{COLOR_RED}Ошибка парсинга данных: {data_hex} - {e}{COLOR_RESET}")
                    return None, None, None

            return None, None, None

        # Обрабатываем каждую CAN строку
        valid_messages = 0
        for idx, row in df_can.iterrows():
            try:
                # Парсим время
                timestamp = parse_timestamp(row['Date'], row['Time'])
                if timestamp is None:
                    continue

                # Устанавливаем базовое время
                if base_timestamp is None:
                    base_timestamp = timestamp

                # Парсим CAN событие
                arbitration_id, data, direction = parse_can_event(str(row['Event']))
                if arbitration_id is None:
                    continue

                # Создаем CAN сообщение
                # Временная метка относительно начала файла
                relative_timestamp = timestamp - base_timestamp

                msg = can.Message(
                    arbitration_id=arbitration_id,
                    data=data,
                    timestamp=relative_timestamp,
                    is_rx=(direction == '<-')
                )

                messages.append(msg)
                valid_messages += 1

                # Выводим первые несколько сообщений для отладки
                if valid_messages <= 3:
                    data_hex = ' '.join([f'{b:02X}' for b in data])
                    print(f"{COLOR_WHITE}DEBUG: CAN ID: 0x{arbitration_id:03X}, Data: {data_hex}, Time: {relative_timestamp:.3f}s{COLOR_RESET}")

            except Exception as e:
                print(f"{COLOR_RED}Ошибка обработки строки {idx}: {e}{COLOR_RESET}")
                continue

        print(f"{COLOR_GREEN}Успешно обработано CAN сообщений: {valid_messages}{COLOR_RESET}")

        # Фильтруем только сообщения 0x740 для проигрывания
        messages_740 = [msg for msg in messages if msg.arbitration_id == 0x740 and not msg.is_rx]
        print(f"{COLOR_GREEN}Сообщений 0x740 для проигрывания: {len(messages_740)}{COLOR_RESET}")

        if len(messages_740) == 0:
            print(f"{COLOR_RED}ОШИБКА: В файле нет исходящих сообщений 0x740{COLOR_RESET}")
            return []

        return messages_740

    except Exception as e:
        print(f"{COLOR_RED}Ошибка чтения XLSX файла: {e}{COLOR_RESET}")
        return []

def modify_valve_command(data):
    """
    Модифицирует команду управления клапанами 4B12.
    Поддерживает оба формата: 8-байтный (BLF) и 6-байтный (XLSX).
    """
    # Проверяем что это команда 4B12 для обоих форматов
    is_8byte_format = len(data) >= 7 and data[1] == 0x2F and data[2] == 0x4B and data[3] == 0x12
    is_6byte_format = len(data) >= 6 and data[0] == 0x2F and data[1] == 0x4B and data[2] == 0x12

    if not (is_8byte_format or is_6byte_format):
        return data

    # Определяем индексы в зависимости от формата
    if is_8byte_format:
        # 8-байтный формат: 06 2F 4B 12 03 XX YY 00
        valve_index = 5  # XX - управление клапанами
        iso_index = 6    # YY - изоляция
    else:
        # 6-байтный формат: 2F 4B 12 03 XX YY
        valve_index = 4  # XX - управление клапанами
        iso_index = 5    # YY - изоляция

    iso_byte = data[iso_index]
    current_wheel = modify_valve_command.current_wheel

    # Модифицируем только младший ниббл байта изоляции
    iso_low_nibble = iso_byte & 0x0F
    iso_high_nibble = iso_byte & 0xF0

    # Определяем диагональ по текущему колесу
    if current_wheel in ["FL", "RR"]:
        # Диагональ FL-RR (0xA), выключаем FR-RL (0x5)
        iso_low_nibble &= ~0x05  # clear bits 0 and 2
    else:  # FR, RL
        # Диагональ FR-RL (0x5), выключаем FL-RR (0xA)
        iso_low_nibble &= ~0x0A  # clear bits 1 and 3

    new_iso_byte = iso_high_nibble | iso_low_nibble

    # Создаём новый массив данных
    new_data = bytearray(data)
    new_data[iso_index] = new_iso_byte

    return bytes(new_data)

# Инициализация state machine
modify_valve_command.current_wheel = "FL"

def check_outlet_and_switch(data):
    """
    Проверяет выпускной клапан и переключает на следующее колесо.
    Поддерживает оба формата: 8-байтный (BLF) и 6-байтный (XLSX).
    """
    # Проверяем что это команда 4B12 для обоих форматов
    is_8byte_format = len(data) >= 7 and data[1] == 0x2F and data[2] == 0x4B and data[3] == 0x12
    is_6byte_format = len(data) >= 6 and data[0] == 0x2F and data[1] == 0x4B and data[2] == 0x12

    if not (is_8byte_format or is_6byte_format):
        return False

    # Определяем индекс байта клапанов в зависимости от формата
    if is_8byte_format:
        # 8-байтный формат: 06 2F 4B 12 03 XX YY 00
        valve_index = 5  # XX - управление клапанами
    else:
        # 6-байтный формат: 2F 4B 12 03 XX YY
        valve_index = 4  # XX - управление клапанами

    valve_byte = data[valve_index]
    current = modify_valve_command.current_wheel

    # Маски выпускных клапанов
    outlet_masks = {
        "FL": 0x02,  # бит 1
        "FR": 0x08,  # бит 3
        "RL": 0x20,  # бит 5
        "RR": 0x80   # бит 7
    }

    # Последовательность переключения
    next_wheel = {
        "FL": "FR",
        "FR": "RL",
        "RL": "RR",
        "RR": None  # конец
    }

    # Проверяем выпускной текущего колеса
    if valve_byte & outlet_masks[current]:
        next_w = next_wheel[current]
        if next_w:
            print(f"{COLOR_CYAN}>>> Switching from {current} to {next_w}{COLOR_RESET}")
            modify_valve_command.current_wheel = next_w
            return True
        else:
            print(f"{COLOR_CYAN}>>> Finished sequence at {current}{COLOR_RESET}")
            return True

    return False

def get_message_type(data):
    """Определяет тип сообщения по данным"""
    if len(data) >= 2:
        # Tester Present
        if data[0] == 0x02 and data[1] == 0x3E:
            return "tester_present"
        # Tester Present Response
        if data[0] == 0x02 and data[1] == 0x7E:
            return "tester_present_response"
        # Extended Session Request (проверяем оба формата)
        if (len(data) >= 3 and data[1] == 0x10 and data[2] == 0x03) or \
           (len(data) >= 2 and data[0] == 0x10 and data[1] == 0x03):
            return "extended_session"
        # Extended Session Response
        if len(data) >= 3 and data[1] == 0x50 and data[2] == 0x03:
            return "extended_session_response"
        # Negative Response
        if data[0] >= 0x03 and data[1] == 0x7F:
            return "negative_response"
    return "other"

def get_color_for_message(msg_type, is_response=False):
    """Возвращает цвет для сообщения"""
    if msg_type == "negative_response":
        return COLOR_RED
    elif msg_type in ["tester_present", "tester_present_response",
                      "extended_session", "extended_session_response"]:
        return COLOR_YELLOW
    elif is_response:
        return COLOR_GREEN
    else:
        return COLOR_WHITE

def format_message(msg, color):
    """Форматирует сообщение для вывода"""
    data_hex = ' '.join([f'{b:02X}' for b in msg.data])
    direction = "Rx" if msg.is_rx else "Tx"
    return f"{color}{msg.timestamp:12.6f} {msg.channel}  {msg.arbitration_id:03X}       {direction}   d {len(msg.data)} {data_hex}{COLOR_RESET}"

def read_can_messages(file_path):
    """
    Читает CAN сообщения из файла.
    Поддерживает BLF и XLSX форматы.
    """
    file_ext = Path(file_path).suffix.lower()

    if file_ext in ['.blf']:
        # Старый функционал для BLF файлов
        messages = []
        with can.BLFReader(file_path) as log:
            for msg in log:
                if msg.arbitration_id == 0x740:
                    messages.append(msg)
        return messages

    elif file_ext in ['.xlsx', '.xls']:
        # Новый функционал для XLSX файлов нового завода
        return parse_xlsx_file(file_path)

    else:
        print(f"{COLOR_RED}Неподдерживаемый формат файла: {file_ext}{COLOR_RESET}")
        print(f"{COLOR_YELLOW}Поддерживаемые форматы: .blf, .xlsx, .xls{COLOR_RESET}")
        return []

def create_can_bus(use_virtual=False, channel=0, bitrate=500000):
    """Create CAN bus with comprehensive error handling"""
    bus = None

    try:
        if use_virtual:
            print(f"{COLOR_WHITE}Попытка подключения к VIRTUAL каналу {channel}...{COLOR_RESET}")
            bus = can.Bus(
                interface='kvaser',
                channel=channel,
                bitrate=bitrate,
                accept_virtual=True,
                receive_own_messages=False,
                fd=False,  # Disable CAN-FD
                data_bitrate=bitrate,
                sjw=1
            )
        else:
            print(f"{COLOR_WHITE}Попытка подключения к физическому каналу {channel}...{COLOR_RESET}")
            bus = can.Bus(
                interface='kvaser',
                channel=channel,
                bitrate=bitrate,
                receive_own_messages=False,
                fd=False,  # Disable CAN-FD
                data_bitrate=bitrate
            )

    except Exception as e:
        print(f"{COLOR_RED}Ошибка Kvaser инициализации: {e}{COLOR_RESET}")

        # Fallback to virtual if hardware fails
        if not use_virtual:
            print(f"{COLOR_YELLOW}Попытка использовать виртуальный канал...{COLOR_RESET}")
            try:
                bus = can.Bus(
                    interface='kvaser',
                    channel=channel,
                    bitrate=bitrate,
                    accept_virtual=True,
                    receive_own_messages=False
                )
                print(f"{COLOR_GREEN}Успешно подключен к виртуальному каналу{COLOR_RESET}")
            except Exception as e2:
                print(f"{COLOR_RED}Виртуальный канал также не доступен: {e2}{COLOR_RESET}")

    return bus

def replay_740_760(use_virtual=False):
    """Проигрывание только сообщений 0x740 с ожиданием ответов 0x760"""

    # Конфигурация
    blf_file_path = BLF_FILE_PATH
    channel = 0  # Kvaser channel 0 (первый канал)
    bitrate = 500000
    timeout = 0.1

    if not Path(blf_file_path).exists():
        print(f"{COLOR_RED}Файл {blf_file_path} не найден!{COLOR_RESET}")
        return

    # Проверка наличия реального адаптера если не используем виртуальный
    if not use_virtual:
        hw_present, hw_info = check_kvaser_hardware()
        if not hw_present:
            print(f"{COLOR_RED}Please connect Kvaser adapter!{COLOR_RESET}")
            print(f"{COLOR_YELLOW}Use --virtual flag to use virtual channel{COLOR_RESET}")
            return
        print(f"{COLOR_GREEN}Found Kvaser: {hw_info}{COLOR_RESET}")

    try:
        # Чтение и фильтрация сообщений 0x740 из файла
        print(f"{COLOR_WHITE}Чтение файла {Path(blf_file_path).name}...{COLOR_RESET}")
        requests_740 = read_can_messages(blf_file_path)

        if not requests_740:
            print(f"{COLOR_RED}Нет сообщений 0x740 в файле{COLOR_RESET}")
            return

        total_requests = len(requests_740)
        print(f"{COLOR_WHITE}Найдено запросов 0x740: {total_requests}{COLOR_RESET}")

        # Подключение к CAN-шине

        bus = create_can_bus(use_virtual=use_virtual, channel=channel, bitrate=bitrate)

        if bus is None:
            print(f"{COLOR_RED}Не удалось инициализировать CAN шину{COLOR_RESET}")
            return

        with bus:
            print(f"{COLOR_YELLOW}Проигрывание только 0x740 -> 0x760{COLOR_RESET}")
            if REPLACE_CMD:
                modify_valve_command.current_wheel = "FL"  # Reset state
                print(f"{COLOR_CYAN}>>> Starting with wheel: FL (sequence: FL -> FR -> RL -> RR){COLOR_RESET}")
            print(f"{COLOR_WHITE}Нажмите Ctrl+C для остановки{COLOR_RESET}")
            print()

            # Прогресс-бар
            pbar = tqdm(total=total_requests, desc="Отправка 0x740", unit="msg", ncols=100)

            start_time = time.perf_counter()
            first_timestamp = requests_740[0].timestamp

            success_count = 0
            timeout_count = 0
            error_count = 0

            for i, msg in enumerate(requests_740):
                try:
                    # Выдерживаем временные интервалы из лога
                    elapsed = msg.timestamp - first_timestamp
                    while (time.perf_counter() - start_time) < elapsed:
                        time.sleep(0.001)

                    # Определяем тип сообщения для цветового кодирования
                    msg_type = get_message_type(msg.data)
                    color_req = get_color_for_message(msg_type, is_response=False)

                    # Модифицируем данные если включен REPLACE_CMD
                    tx_data = msg.data
                    modified = False
                    if REPLACE_CMD:
                        # Проверяем выпускной и переключаем колесо если нужно
                        check_outlet_and_switch(msg.data)
                        # Модифицируем команду
                        new_data = modify_valve_command(msg.data)
                        if new_data != msg.data:
                            tx_data = new_data
                            modified = True

                    # Создаем новое сообщение для отправки (без timestamp)
                    tx_msg = can.Message(
                        arbitration_id=msg.arbitration_id,
                        data=tx_data,
                        is_extended_id=msg.is_extended_id
                    )

                    # Отправляем сообщение
                    bus.send(tx_msg)

                    # Создаем сообщение для логирования с текущим временем
                    current_ts = time.perf_counter() - start_time + first_timestamp
                    log_msg = can.Message(
                        arbitration_id=msg.arbitration_id,
                        data=tx_data,
                        timestamp=current_ts,
                        channel=channel,
                        is_rx=False
                    )

                    # Вывод запроса
                    if modified:
                        # Показываем оригинал и модификацию
                        orig_hex = ' '.join([f'{b:02X}' for b in msg.data])
                        print(f"{COLOR_WHITE}{current_ts:12.6f} {channel}  {msg.arbitration_id:03X}       Tx   d {len(msg.data)} {orig_hex} [ORIG]{COLOR_RESET}")
                        print(format_message(log_msg, COLOR_CYAN) + f" {COLOR_CYAN}[MODIFIED]{COLOR_RESET}")
                    else:
                        print(format_message(log_msg, color_req))

                    # Ожидаем ответ 0x760
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
                        # Определяем тип ответа
                        resp_type = get_message_type(response.data)
                        color_resp = get_color_for_message(resp_type, is_response=True)

                        # Обновляем timestamp для вывода
                        response.timestamp = time.perf_counter() - start_time + first_timestamp
                        response.channel = channel

                        # Вывод ответа
                        print(format_message(response, color_resp))

                        if resp_type == "negative_response":
                            error_count += 1
                        else:
                            success_count += 1
                    else:
                        # Таймаут - ответ не получен
                        timeout_ts = time.perf_counter() - start_time + first_timestamp
                        print(f"{COLOR_RED}{timeout_ts:12.6f} {channel}  760       Rx   d 0 -- TIMEOUT --{COLOR_RESET}")
                        timeout_count += 1

                    pbar.update(1)
                    print()  # пустая строка между парами запрос-ответ

                except KeyboardInterrupt:
                    print(f"\n{COLOR_YELLOW}Остановлено пользователем{COLOR_RESET}")
                    break
                except Exception as e:
                    print(f"{COLOR_RED}Ошибка при обработке сообщения: {e}{COLOR_RESET}")
                    continue

            pbar.close()
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Replay CAN messages 0x740 -> 0x760')
    parser.add_argument('--virtual', '-v', action='store_true',
                        help='Use Kvaser virtual channel')
    args = parser.parse_args()

    replay_740_760(use_virtual=args.virtual)
