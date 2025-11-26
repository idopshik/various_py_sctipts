"""
     U N T E S T E D !!!!!!

UNIVERSAL CAN Valve Control Script
==================================
Универсальный скрипт для работы с CAN-шиной клапанов гидроблока ABS/ESC.

РЕЖИМЫ РАБОТЫ:
1. --replay-blf    - Проигрывание CAN-сообщений из BLF/XLSX файла
2. --table-sequence - Запуск табличной последовательности тестирования
3. --blf-output    - Логирование в BLF файл (для любого режима)

ОСОБЕННОСТИ:
- Поддержка BLF и XLSX форматов для воспроизведения
- Табличная последовательность с точными временами T1-T5
- Модификация команд для отключения неактивной диагонали
- Цветовое кодирование сообщений
- Логирование всех операций в BLF
- Исправленная работа с Kvaser адаптерами

проблемы по подмене - не решены! Поэтому и написано проигрываие таблицы! Потому что не вышло починить исправление лога.


# Проигрывание BLF с логированием
python universal_valve_control.py --replay-blf log.blf --blf-output replay.blf

# Табличная последовательность на физическом канале
python universal_valve_control.py --table-sequence --virtual=False

# Проигрывание XLSX без модификации команд
python universal_valve_control.py --replay-blf data.xlsx --no-replace-cmd

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
import os

# ANSI цветовые коды
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_WHITE = "\033[97m"
COLOR_CYAN = "\033[96m"
COLOR_RESET = "\033[0m"

# Флаг для подмены команд - выключение неактивной диагонали
REPLACE_CMD = True

# Временные интервалы для табличной последовательности (в секундах)
T1 = 0.140  # базовый таймаут
T2 = 0.070  # быстрая последовательность (циклы)
T3 = 0.250  # смена диагоналей
T4 = 0.400  # паузы между этапами
T5 = 2.000  # очень длинные паузы (опустошение)

class UniversalValveController:
    def __init__(self, use_virtual=True, channel=0, bitrate=500000, blf_output=None):
        self.use_virtual = use_virtual
        self.channel = channel
        self.bitrate = bitrate
        self.blf_output = blf_output
        self.bus = None
        self.logger = None
        self.current_wheel = "FL"

    def check_kvaser_hardware(self):
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

    def create_can_bus(self, use_virtual=False, channel=0, bitrate=500000):
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

    def connect(self):
        """Подключение к CAN шине с обработкой ошибок"""
        try:
            # Проверка наличия реального адаптера если не используем виртуальный
            if not self.use_virtual:
                hw_present, hw_info = self.check_kvaser_hardware()
                if not hw_present:
                    print(f"{COLOR_RED}Please connect Kvaser adapter!{COLOR_RESET}")
                    print(f"{COLOR_YELLOW}Use --virtual flag to use virtual channel{COLOR_RESET}")
                    return False
                print(f"{COLOR_GREEN}Found Kvaser: {hw_info}{COLOR_RESET}")

            self.bus = self.create_can_bus(
                use_virtual=self.use_virtual,
                channel=self.channel,
                bitrate=self.bitrate
            )

            if self.bus is None:
                print(f"{COLOR_RED}Не удалось инициализировать CAN шину{COLOR_RESET}")
                return False

            print(f"{COLOR_GREEN}Успешно подключено к CAN шине{COLOR_RESET}")

            # Инициализация логгера BLF
            if self.blf_output:
                os.makedirs(os.path.dirname(self.blf_output) if os.path.dirname(self.blf_output) else '.', exist_ok=True)
                self.logger = can.BLFWriter(self.blf_output)
                print(f"{COLOR_GREEN}Логгирование в файл: {self.blf_output}{COLOR_RESET}")

            return True

        except Exception as e:
            print(f"{COLOR_RED}Ошибка подключения: {e}{COLOR_RESET}")
            return False

    def disconnect(self):
        """Отключение от CAN шины"""
        if self.bus:
            self.bus.shutdown()
            self.bus = None
        if self.logger:
            self.logger.stop()
            self.logger = None

    def log_message(self, msg):
        """Записывает сообщение в логгер BLF"""
        if self.logger:
            self.logger.on_message_received(msg)

    def send_message(self, msg, description="", wait_time=0):
        """Отправка CAN сообщения с логированием"""
        if not self.bus:
            print(f"{COLOR_RED}CAN шина не подключена!{COLOR_RESET}")
            return False

        try:
            # Обновляем timestamp перед отправкой
            msg.timestamp = time.time()
            msg.channel = self.channel

            self.bus.send(msg)
            self.log_message(msg)

            # Определяем цвет и форматируем вывод
            msg_type = self.get_message_type(msg.data)
            color = self.get_color_for_message(msg_type, is_response=False)

            data_hex = ' '.join([f'{b:02X}' for b in msg.data])
            direction = "Rx" if msg.is_rx else "Tx"

            print(f"{color}{msg.timestamp:12.6f} {msg.channel}  {msg.arbitration_id:03X}       {direction}   d {len(msg.data)} {data_hex}{COLOR_RESET}")

            if description:
                print(f"{COLOR_CYAN}# {description}{COLOR_RESET}")

            if wait_time > 0:
                time.sleep(wait_time)

            return True

        except Exception as e:
            print(f"{COLOR_RED}Ошибка отправки: {e}{COLOR_RESET}")
            return False

    def wait_for_response(self, expected_id=0x760, timeout=0.1):
        """Ожидание ответа с указанным ID"""
        if not self.bus:
            return None

        start_wait = time.perf_counter()
        while (time.perf_counter() - start_wait) < timeout:
            remaining = timeout - (time.perf_counter() - start_wait)
            if remaining <= 0:
                break

            response = self.bus.recv(timeout=remaining)
            if response is not None and response.arbitration_id == expected_id:
                # Логируем полученный ответ
                response.timestamp = time.time()
                response.channel = self.channel
                self.log_message(response)
                return response

        return None

    def get_message_type(self, data):
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

    def get_color_for_message(self, msg_type, is_response=False):
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

    def modify_valve_command(self, data):
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
        current_wheel = self.current_wheel

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

    def check_outlet_and_switch(self, data):
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
        current = self.current_wheel

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
                self.current_wheel = next_w
                return True
            else:
                print(f"{COLOR_CYAN}>>> Finished sequence at {current}{COLOR_RESET}")
                return True

        return False

    def switch_wheel(self, new_wheel):
        """Переключение на следующее колесо (для табличной последовательности)"""
        if new_wheel != self.current_wheel:
            print(f"{COLOR_CYAN}>>> Switching from {self.current_wheel} to {new_wheel}{COLOR_RESET}")
            self.current_wheel = new_wheel

    def parse_xlsx_file(self, file_path):
        """
        Парсит XLSX файл нового завода и возвращает список CAN сообщений.
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

    def read_can_messages(self, file_path):
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
            return self.parse_xlsx_file(file_path)

        else:
            print(f"{COLOR_RED}Неподдерживаемый формат файла: {file_ext}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}Поддерживаемые форматы: .blf, .xlsx, .xls{COLOR_RESET}")
            return []

    def replay_blf_file(self, blf_file_path, timeout=0.1):
        """Проигрывание только сообщений 0x740 с ожиданием ответов 0x760"""
        if not Path(blf_file_path).exists():
            print(f"{COLOR_RED}Файл {blf_file_path} не найден!{COLOR_RESET}")
            return False

        if not self.connect():
            return False

        try:
            # Чтение и фильтрация сообщений 0x740 из файла
            print(f"{COLOR_WHITE}Чтение файла {Path(blf_file_path).name}...{COLOR_RESET}")
            requests_740 = self.read_can_messages(blf_file_path)

            if not requests_740:
                print(f"{COLOR_RED}Нет сообщений 0x740 в файле{COLOR_RESET}")
                return False

            total_requests = len(requests_740)
            print(f"{COLOR_WHITE}Найдено запросов 0x740: {total_requests}{COLOR_RESET}")

            with self.bus:
                print(f"{COLOR_YELLOW}Проигрывание только 0x740 -> 0x760{COLOR_RESET}")
                if REPLACE_CMD:
                    self.current_wheel = "FL"  # Reset state
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
                        msg_type = self.get_message_type(msg.data)
                        color_req = self.get_color_for_message(msg_type, is_response=False)

                        # Модифицируем данные если включен REPLACE_CMD
                        tx_data = msg.data
                        modified = False
                        if REPLACE_CMD:
                            # Проверяем выпускной и переключаем колесо если нужно
                            self.check_outlet_and_switch(msg.data)
                            # Модифицируем команду
                            new_data = self.modify_valve_command(msg.data)
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
                        self.bus.send(tx_msg)

                        # Создаем сообщение для логирования с текущим временем
                        current_ts = time.perf_counter() - start_time + first_timestamp
                        log_msg = can.Message(
                            arbitration_id=msg.arbitration_id,
                            data=tx_data,
                            timestamp=current_ts,
                            channel=self.channel,
                            is_rx=False
                        )
                        self.log_message(log_msg)

                        # Вывод запроса
                        if modified:
                            # Показываем оригинал и модификацию
                            orig_hex = ' '.join([f'{b:02X}' for b in msg.data])
                            print(f"{COLOR_WHITE}{current_ts:12.6f} {self.channel}  {msg.arbitration_id:03X}       Tx   d {len(msg.data)} {orig_hex} [ORIG]{COLOR_RESET}")
                            data_hex = ' '.join([f'{b:02X}' for b in tx_data])
                            print(f"{COLOR_CYAN}{current_ts:12.6f} {self.channel}  {msg.arbitration_id:03X}       Tx   d {len(tx_data)} {data_hex} [MODIFIED]{COLOR_RESET}")
                        else:
                            data_hex = ' '.join([f'{b:02X}' for b in tx_data])
                            print(f"{color_req}{current_ts:12.6f} {self.channel}  {msg.arbitration_id:03X}       Tx   d {len(tx_data)} {data_hex}{COLOR_RESET}")

                        # Ожидаем ответ 0x760
                        response = self.wait_for_response(expected_id=0x760, timeout=timeout)

                        if response is not None:
                            # Определяем тип ответа
                            resp_type = self.get_message_type(response.data)
                            color_resp = self.get_color_for_message(resp_type, is_response=True)

                            # Обновляем timestamp для вывода
                            response.timestamp = time.perf_counter() - start_time + first_timestamp
                            response.channel = self.channel

                            # Вывод ответа
                            data_hex = ' '.join([f'{b:02X}' for b in response.data])
                            print(f"{color_resp}{response.timestamp:12.6f} {self.channel}  {response.arbitration_id:03X}       Rx   d {len(response.data)} {data_hex}{COLOR_RESET}")

                            if resp_type == "negative_response":
                                error_count += 1
                            else:
                                success_count += 1
                        else:
                            # Таймаут - ответ не получен
                            timeout_ts = time.perf_counter() - start_time + first_timestamp
                            print(f"{COLOR_RED}{timeout_ts:12.6f} {self.channel}  760       Rx   d 0 -- TIMEOUT --{COLOR_RESET}")
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

            return True

        except Exception as e:
            print(f"{COLOR_RED}Критическая ошибка: {e}{COLOR_RESET}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.disconnect()

    def run_table_sequence(self):
        """Запуск полной табличной последовательности тестирования"""
        if not self.connect():
            return False

        try:
            print(f"{COLOR_YELLOW}Начало табличной последовательности тестирования клапанов ESC{COLOR_RESET}")
            print(f"{COLOR_WHITE}Времена: T1={T1}s, T2={T2}s, T3={T3}s, T4={T4}s, T5={T5}s{COLOR_RESET}")
            print(f"{COLOR_WHITE}Ожидаемое время: ~14 секунд{COLOR_RESET}")
            if self.blf_output:
                print(f"{COLOR_WHITE}Логгирование: {self.blf_output}{COLOR_RESET}")
            print()

            total_steps = 82
            pbar = tqdm(total=total_steps, desc="Табличная последовательность", unit="msg", ncols=100)

            start_time = time.time()
            self.current_wheel = "FL"

            # === ШАГ 1-2: Инициализация ===
            self.send_message(can.Message(arbitration_id=0x740, data=[0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00]),
                            "Extended Session", T1)
            pbar.update(1)

            self.send_message(can.Message(arbitration_id=0x740, data=[0x04, 0x14, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00]),
                            "Security Access", T1)
            pbar.update(1)

            # === ШАГ 3-6: Базовые команды ===
            commands = [
                ([0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00], "Повтор Extended Session", T1),
                ([0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "Tester Present", T4),
                ([0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "Tester Present", T4),
                ([0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "Tester Present", T4),
            ]

            for data, desc, stage_time in commands:
                self.send_message(can.Message(arbitration_id=0x740, data=data), desc, stage_time)
                pbar.update(1)

            # === ШАГ 7-13: FL колесо ===
            print(f"{COLOR_CYAN}>>> Начало тестирования FL колеса{COLOR_RESET}")

            fl_commands = [
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x00, 0x00], "Все выкл", T1),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "motor вкл", T1),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x05, 0x40, 0x00], "Впускные передней оси", T1),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x40, 0x00], "Впускные задней оси", T1),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "iso_2 вкл", T1),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "shu_2 вкл", T1),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x54, 0x4A, 0x00], "EVFL выкл", T4),
            ]

            for data, desc, stage_time in fl_commands:
                self.send_message(can.Message(arbitration_id=0x740, data=data), desc, stage_time)
                pbar.update(1)

            # === ЦИКЛ FL: 5 включений/выключений ===
            print(f"{COLOR_CYAN}>>> Цикл FL: 5 включений/выключений{COLOR_RESET}")
            for i in range(5):
                self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00]),
                                f"EVFL вкл ({i+1}/5)", T2)
                pbar.update(1)
                self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x54, 0x4A, 0x00]),
                                f"EVFL выкл ({i+1}/5)", T2)
                pbar.update(1)

            # === Переключение на FR ===
            self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00]),
                            "shu_2 выкл", T1)
            pbar.update(1)
            self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x57, 0x41, 0x00]),
                            "AVFL вкл, iso_1 вкл", T3)
            pbar.update(1)
            self.switch_wheel("FR")

            # === FR этап ===
            print(f"{COLOR_CYAN}>>> Начало тестирования FR колеса{COLOR_RESET}")
            fr_commands = [
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00], "AVFL выкл", T4),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "shu_1 вкл", T1),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x51, 0x45, 0x00], "EVFR выкл", T4),
            ]

            for data, desc, stage_time in fr_commands:
                self.send_message(can.Message(arbitration_id=0x740, data=data), desc, stage_time)
                pbar.update(1)

            # === ЦИКЛ FR: 5 включений/выключений ===
            print(f"{COLOR_CYAN}>>> Цикл FR: 5 включений/выключений{COLOR_RESET}")
            for i in range(5):
                self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00]),
                                f"EVFR вкл ({i+1}/5)", T2)
                pbar.update(1)
                self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x51, 0x45, 0x00]),
                                f"EVFR выкл ({i+1}/5)", T2)
                pbar.update(1)

            # === Переключение на RL ===
            self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00]),
                            "shu_1 выкл", T4)
            pbar.update(1)
            self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x5D, 0x41, 0x00]),
                            "AVFR вкл", T3)
            pbar.update(1)
            self.switch_wheel("RL")

            # === RL этап ===
            print(f"{COLOR_CYAN}>>> Начало тестирования RL колеса{COLOR_RESET}")
            rl_commands = [
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00], "AVFR выкл", T4),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "shu_1 вкл", T1),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x45, 0x45, 0x00], "EVRL выкл", T4),
            ]

            for data, desc, stage_time in rl_commands:
                self.send_message(can.Message(arbitration_id=0x740, data=data), desc, stage_time)
                pbar.update(1)

            # === ЦИКЛ RL: 5 включений/выключений ===
            print(f"{COLOR_CYAN}>>> Цикл RL: 5 включений/выключений{COLOR_RESET}")
            for i in range(5):
                self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00]),
                                f"EVRL вкл ({i+1}/5)", T2)
                pbar.update(1)
                self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x45, 0x45, 0x00]),
                                f"EVRL выкл ({i+1}/5)", T2)
                pbar.update(1)

            # === Переключение на RR ===
            self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00]),
                            "shu_1 выкл", T4)
            pbar.update(1)
            self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x75, 0x42, 0x00]),
                            "AVRL вкл, iso_2 вкл", T3)
            pbar.update(1)
            self.switch_wheel("RR")

            # === RR этап ===
            print(f"{COLOR_CYAN}>>> Начало тестирования RR колеса{COLOR_RESET}")
            rr_commands = [
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "AVRL выкл", T3),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "shu_2 вкл", T4),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x15, 0x4A, 0x00], "EVRR выкл", T1),
            ]

            for data, desc, stage_time in rr_commands:
                self.send_message(can.Message(arbitration_id=0x740, data=data), desc, stage_time)
                pbar.update(1)

            # === ЦИКЛ RR: 5 включений/выключений ===
            print(f"{COLOR_CYAN}>>> Цикл RR: 5 включений/выключений{COLOR_RESET}")
            for i in range(5):
                self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00]),
                                f"EVRR вкл ({i+1}/5)", T2)
                pbar.update(1)
                self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x15, 0x4A, 0x00]),
                                f"EVRR выкл ({i+1}/5)", T2)
                pbar.update(1)

            # === Завершение ===
            self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00]),
                            "shu_2 выкл", T4)
            pbar.update(1)
            self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0xD5, 0x42, 0x00]),
                            "AVRR вкл", T3)
            pbar.update(1)
            self.send_message(can.Message(arbitration_id=0x740, data=[0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00]),
                            "AVRR выкл", T4)
            pbar.update(1)

            # === Финальные команды ===
            final_commands = [
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x40, 0x00], "iso_2 выкл", T1),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x50, 0x40, 0x00], "Впускные передней оси выкл", T1),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "Впускные задней оси выкл", T1),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "Опустошение", T5),
                ([0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x00, 0x00], "motor выкл", T1),
            ]

            for data, desc, stage_time in final_commands:
                self.send_message(can.Message(arbitration_id=0x740, data=data), desc, stage_time)
                pbar.update(1)

            pbar.close()

            total_time = time.time() - start_time
            print(f"{COLOR_GREEN}Табличная последовательность завершена за {total_time:.1f} секунд!{COLOR_RESET}")
            return True

        except KeyboardInterrupt:
            print(f"\n{COLOR_YELLOW}Остановлено пользователем{COLOR_RESET}")
            return False
        except Exception as e:
            print(f"{COLOR_RED}Ошибка выполнения: {e}{COLOR_RESET}")
            return False
        finally:
            self.disconnect()

def generate_blf_filename(prefix="can_log"):
    """Генерирует имя BLF файла на основе текущего времени"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.blf"

def main():
    parser = argparse.ArgumentParser(description='UNIVERSAL CAN Valve Control Script')

    # Режимы работы
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--replay-blf', type=str, metavar='FILE',
                          help='Проигрывание CAN-сообщений из BLF/XLSX файла')
    mode_group.add_argument('--table-sequence', action='store_true',
                          help='Запуск табличной последовательности тестирования')

    # Общие параметры
    parser.add_argument('--virtual', '-v', action='store_true', default=True,
                       help='Use virtual CAN channel (default: True)')
    parser.add_argument('--channel', '-c', type=int, default=0,
                       help='CAN channel number (default: 0)')
    parser.add_argument('--bitrate', '-b', type=int, default=500000,
                       help='CAN bitrate (default: 500000)')
    parser.add_argument('--blf-output', type=str, default=None,
                       help='BLF output file path (default: auto-generated)')
    parser.add_argument('--timeout', '-t', type=float, default=0.1,
                       help='Timeout for response waiting (default: 0.1s)')
    parser.add_argument('--no-replace-cmd', action='store_true',
                       help='Disable command modification (use original commands)')

    args = parser.parse_args()

    # Настройка глобальных параметров
    global REPLACE_CMD
    REPLACE_CMD = not args.no_replace_cmd

    # Генерация имени BLF файла если не указан
    blf_output = args.blf_output
    if blf_output is None:
        prefix = "replay" if args.replay_blf else "table"
        blf_output = generate_blf_filename(prefix)
        print(f"{COLOR_WHITE}BLF файл: {blf_output}{COLOR_RESET}")

    # Создание контроллера
    controller = UniversalValveController(
        use_virtual=args.virtual,
        channel=args.channel,
        bitrate=args.bitrate,
        blf_output=blf_output
    )

    # Запуск выбранного режима
    success = False
    if args.replay_blf:
        success = controller.replay_blf_file(args.replay_blf, timeout=args.timeout)
    elif args.table_sequence:
        success = controller.run_table_sequence()

    if success:
        print(f"{COLOR_GREEN}Операция завершена успешно!{COLOR_RESET}")
        return 0
    else:
        print(f"{COLOR_RED}Операция завершена с ошибками!{COLOR_RESET}")
        return 1

if __name__ == "__main__":
    exit(main())
