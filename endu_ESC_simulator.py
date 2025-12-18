"""
ESC Block Simulator - 30 Second Test Duration
==============================================

Имитирует блок ESC/ABS для эндуранс-стенда.
Все тестовые сценарии выполняются ровно 30 секунд.

Протокол:
- Стенд отправляет на 0x720
- ESC (этот симулятор) отвечает на 0x728

ИСПОЛЬЗОВАНИЕ:
  python esc_simulator_30s.py            # реальный канал 1 (физически канал 2)
  python esc_simulator_30s.py --virtual  # виртуальная шина
  python esc_simulator_30s.py --debug    # с расширенным дебагом
"""

import can
import time
import argparse
import threading
from datetime import datetime

# ANSI Colors
COLOR_RESET = "\033[0m"
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_WHITE = "\033[97m"
COLOR_CYAN = "\033[96m"
COLOR_BLUE = "\033[94m"
COLOR_MAGENTA = "\033[95m"
COLOR_BOLD = "\033[1m"

# ============================================================================
# CONFIGURATION
# ============================================================================
CHANNEL = 1  # Канал 1 (физически канал 2 на Kvaser)
BITRATE = 500000
TEST_DURATION = 30.0  # секунды

STEND_ID = 0x720  # ID команд от стенда
ESC_ID = 0x728    # ID ответов от ESC

DEBUG_MODE = False

# Фильтры вывода
PRINT_ONLY_CMDS = True   # True = показывать только 0x720 и 0x728, False = все CAN сообщения
PRINT_STATS = False      # True = показывать статистику каждые 5 сек, False = не показывать

# ============================================================================
# STATE MACHINE
# ============================================================================
class ESCSimulator:
    def __init__(self):
        self.test_running = False
        self.test_start_time = None
        self.current_scenario = None
        self.lock = threading.Lock()
        self.stats = {
            'total_received': 0,
            'commands_start': 0,
            'commands_poll': 0,
            'commands_reset': 0,
            'commands_init': 0,
            'responses_sent': 0
        }

    def start_test(self, scenario_num):
        """Запуск тестового сценария"""
        with self.lock:
            self.test_running = True
            self.test_start_time = time.time()
            self.current_scenario = scenario_num
            self.stats['commands_start'] += 1
            debug_print(f"Test started: scenario {scenario_num}", "INFO")

    def reset_test(self):
        """Сброс тестового сценария"""
        with self.lock:
            self.test_running = False
            self.test_start_time = None
            self.current_scenario = None
            self.stats['commands_reset'] += 1
            debug_print("Test reset", "INFO")

    def get_test_status(self):
        """Получить статус выполнения теста"""
        with self.lock:
            if not self.test_running or self.test_start_time is None:
                return 0x00  # Не запущен

            elapsed = time.time() - self.test_start_time
            if elapsed >= TEST_DURATION:
                return 0x01  # Завершён
            else:
                return 0x00  # Выполняется

    def get_elapsed_time(self):
        """Получить время выполнения"""
        with self.lock:
            if self.test_start_time is None:
                return 0.0
            return time.time() - self.test_start_time

# ============================================================================
# KVASER HARDWARE CHECK
# ============================================================================
try:
    from canlib import canlib
    CANLIB_AVAILABLE = True
    CANLIB_ERROR = None
except ImportError as e:
    CANLIB_AVAILABLE = False
    CANLIB_ERROR = str(e)
    canlib = None

def check_kvaser_hardware():
    """Проверяет наличие реального Kvaser адаптера через CANlib"""
    if not CANLIB_AVAILABLE:
        return False, f"canlib import failed: {CANLIB_ERROR}"

    try:
        num_channels = canlib.getNumberOfChannels()
        debug_print(f"Kvaser channels found: {num_channels}", "INFO")

        if num_channels == 0:
            return False, "No Kvaser channels found (is driver installed?)"

        print(f"\n{COLOR_CYAN}=== KVASER HARDWARE INFO ==={COLOR_RESET}")
        for ch in range(num_channels):
            try:
                chd = canlib.ChannelData(ch)
                chan_info = f"Channel {ch}: {chd.channel_name}"
                if hasattr(chd, 'card_serial_no'):
                    chan_info += f" (SN: {chd.card_serial_no})"
                if hasattr(chd, 'chan_no_on_card'):
                    chan_info += f" (ch {chd.chan_no_on_card} on card)"
                print(f"{COLOR_WHITE}  {chan_info}{COLOR_RESET}")

                if "Virtual" not in chd.channel_name:
                    debug_print(f"Found physical channel: {chd.channel_name}", "SUCCESS")
            except Exception as e:
                print(f"{COLOR_YELLOW}  Channel {ch}: Error reading info - {e}{COLOR_RESET}")

        print(f"{COLOR_CYAN}{'='*60}{COLOR_RESET}")

        # Проверяем есть ли физические каналы
        has_physical = False
        for ch in range(num_channels):
            try:
                chd = canlib.ChannelData(ch)
                if "Virtual" not in chd.channel_name:
                    has_physical = True
                    break
            except:
                pass

        if not has_physical:
            return False, "Only virtual channels found"

        return True, f"{num_channels} channels found"

    except Exception as e:
        error_type = type(e).__name__
        debug_print(f"Kvaser check error ({error_type}): {e}", "ERROR")
        return False, f"{error_type}: {e}"

# ============================================================================
# DEBUG
# ============================================================================
def debug_print(msg, level="DEBUG"):
    """Печать дебаг-сообщений"""
    if DEBUG_MODE:
        colors = {
            "DEBUG": COLOR_WHITE,
            "INFO": COLOR_CYAN,
            "WARN": COLOR_YELLOW,
            "ERROR": COLOR_RED,
            "SUCCESS": COLOR_GREEN
        }
        color = colors.get(level, COLOR_WHITE)
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"{color}[{timestamp}] [{level}] {msg}{COLOR_RESET}")

def format_hex(data):
    """Форматирование в hex"""
    return ' '.join([f'{b:02X}' for b in data])

# ============================================================================
# PROTOCOL HANDLERS
# ============================================================================
def handle_command_start(data, simulator):
    """
    Обработка команды запуска сценария (CMD=0x01)
    Table 7: CMD=0x01, CTR=scenario, response: PID=0x81, CTR, STATUS
    STATUS: 0x00 - не получен, 0x01 - запущен, 0x02 - давление не соответствует
    """
    if len(data) < 2:
        return None

    scenario = data[1]  # CTR
    simulator.start_test(scenario)

    # Ответ: всегда успешный запуск
    response = [0x81, scenario, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]
    return bytes(response)

def handle_command_poll(data, simulator):
    """
    Обработка команды опроса статуса (CMD=0x02)
    Table 8: CMD=0x02, CTR=scenario, response: PID=0x82, CTR, STATUS
    STATUS: 0x00 - выполняется, 0x01 - завершено
    """
    if len(data) < 2:
        return None

    scenario = data[1]  # CTR
    simulator.stats['commands_poll'] += 1

    # Проверяем, запущен ли этот сценарий
    if simulator.current_scenario != scenario:
        # Negative response: неверный порядок команд
        response = [0x7F, 0x02, scenario, 0x03, 0x00, 0x00, 0x00, 0x00]
        debug_print(f"Poll error: scenario mismatch (current={simulator.current_scenario}, requested={scenario})", "WARN")
        return bytes(response)

    status = simulator.get_test_status()
    elapsed = simulator.get_elapsed_time()

    debug_print(f"Poll scenario {scenario}: STATUS={status:02X}, elapsed={elapsed:.1f}s", "DEBUG")

    response = [0x82, scenario, status, 0x00, 0x00, 0x00, 0x00, 0x00]
    return bytes(response)

def handle_command_reset(data, simulator):
    """
    Обработка команды сброса (CMD=0x03, CTR=0xFF)
    Table 9: CMD=0x03, CTR=0xFF, response: PID=0x83
    """
    simulator.reset_test()
    response = [0x83, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    return bytes(response)

def handle_command_init(data, simulator):
    """
    Обработка команды первичного входа (CMD=0x04, CTR=0x01)
    Table 6: CMD=0x04, response: PID=0x84
    """
    if len(data) < 2:
        return None

    simulator.stats['commands_init'] += 1
    scenario = data[1]  # CTR
    response = [0x84, scenario, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]
    return bytes(response)

def process_message(msg, simulator, bus):
    """Обработка входящего сообщения"""
    simulator.stats['total_received'] += 1

    if len(msg.data) < 2:
        debug_print(f"Ignoring short message: {format_hex(msg.data)}", "WARN")
        return

    cmd = msg.data[0]

    # Определяем обработчик
    handlers = {
        0x01: handle_command_start,
        0x02: handle_command_poll,
        0x03: handle_command_reset,
        0x04: handle_command_init,
    }

    handler = handlers.get(cmd)

    if handler is None:
        debug_print(f"Unknown command: 0x{cmd:02X}", "WARN")
        # Negative response: неверная команда
        response_data = bytes([0x7F, cmd, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00])
    else:
        response_data = handler(msg.data, simulator)

    if response_data is None:
        return

    # Отправляем ответ
    response_msg = can.Message(
        arbitration_id=ESC_ID,
        data=response_data,
        is_extended_id=False
    )

    try:
        bus.send(response_msg)
        simulator.stats['responses_sent'] += 1

        # Логирование
        cmd_names = {
            0x01: "START",
            0x02: "POLL",
            0x03: "RESET",
            0x04: "INIT",
        }
        cmd_name = cmd_names.get(cmd, f"0x{cmd:02X}")

        print(f"{COLOR_WHITE}[RX] 0x{STEND_ID:03X}: {format_hex(msg.data):<24} ({cmd_name}){COLOR_RESET}")

        # Цвет ответа
        if response_data[0] == 0x7F:
            color = COLOR_RED
            resp_name = "ERROR"
        elif response_data[0] == 0x82 and len(response_data) >= 3:
            if response_data[2] == 0x00:
                color = COLOR_YELLOW
                resp_name = "RUNNING"
            else:
                color = COLOR_GREEN
                resp_name = "COMPLETE"
        else:
            color = COLOR_GREEN
            resp_name = "OK"

        print(f"{color}[TX] 0x{ESC_ID:03X}: {format_hex(response_data):<24} ({resp_name}){COLOR_RESET}")
        print()

    except Exception as e:
        print(f"{COLOR_RED}Error sending response: {e}{COLOR_RESET}")

# ============================================================================
# STATUS DISPLAY
# ============================================================================
def display_status(simulator):
    """Отображение текущего статуса"""
    print(f"\n{COLOR_CYAN}{'='*70}{COLOR_RESET}")
    print(f"{COLOR_CYAN}ESC SIMULATOR STATUS{COLOR_RESET}")
    print(f"{COLOR_CYAN}{'='*70}{COLOR_RESET}")

    with simulator.lock:
        if simulator.test_running and simulator.test_start_time:
            elapsed = time.time() - simulator.test_start_time
            remaining = max(0, TEST_DURATION - elapsed)
            progress = min(100, (elapsed / TEST_DURATION) * 100)

            print(f"{COLOR_WHITE}Test running: Scenario {simulator.current_scenario}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}Elapsed: {elapsed:.1f}s / {TEST_DURATION:.1f}s ({progress:.0f}%){COLOR_RESET}")
            print(f"{COLOR_YELLOW}Remaining: {remaining:.1f}s{COLOR_RESET}")
        else:
            print(f"{COLOR_WHITE}Status: IDLE{COLOR_RESET}")

    print(f"\n{COLOR_WHITE}Statistics:{COLOR_RESET}")
    print(f"  Total received: {simulator.stats['total_received']}")
    print(f"  Commands START: {simulator.stats['commands_start']}")
    print(f"  Commands POLL:  {simulator.stats['commands_poll']}")
    print(f"  Commands RESET: {simulator.stats['commands_reset']}")
    print(f"  Commands INIT:  {simulator.stats['commands_init']}")
    print(f"  Responses sent: {simulator.stats['responses_sent']}")
    print(f"{COLOR_CYAN}{'='*70}{COLOR_RESET}\n")

# ============================================================================
# STATUS THREAD
# ============================================================================
def status_display_thread(simulator, running_flag):
    """Поток для периодического отображения статуса"""
    # Проверяем флаг PRINT_STATS
    if not PRINT_STATS:
        return  # Не запускаем поток вообще

    while running_flag['running']:
        time.sleep(5.0)
        if running_flag['running']:
            display_status(simulator)

# ============================================================================
# MAIN
# ============================================================================
def main():
    global DEBUG_MODE

    parser = argparse.ArgumentParser(
        description='ESC Block Simulator - 30 Second Test Duration',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--virtual', '-v', action='store_true',
                        help='Use virtual Kvaser channel')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug output')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Disable auto-debug (only errors)')

    args = parser.parse_args()

    # Включаем дебаг по умолчанию, если не указан --quiet
    if args.debug or not args.quiet:
        DEBUG_MODE = True
    else:
        DEBUG_MODE = False

    print(f"{COLOR_BOLD}{COLOR_CYAN}{'='*70}{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_CYAN}ESC BLOCK SIMULATOR - 30 SECOND TEST DURATION{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_CYAN}{'='*70}{COLOR_RESET}")
    print(f"{COLOR_WHITE}Channel: {CHANNEL} (физически канал 2 на Kvaser){COLOR_RESET}")
    print(f"{COLOR_WHITE}Bitrate: {BITRATE} bps{COLOR_RESET}")
    print(f"{COLOR_WHITE}Test duration: {TEST_DURATION} seconds{COLOR_RESET}")
    print(f"{COLOR_WHITE}Virtual mode: {'YES' if args.virtual else 'NO'}{COLOR_RESET}")
    print(f"{COLOR_WHITE}Debug mode: {'YES' if DEBUG_MODE else 'NO'}{COLOR_RESET}")
    print(f"{COLOR_WHITE}Print only 0x720/0x728: {'YES' if PRINT_ONLY_CMDS else 'NO (all CAN)'}{COLOR_RESET}")
    print(f"{COLOR_WHITE}Auto statistics: {'YES' if PRINT_STATS else 'NO'}{COLOR_RESET}")

    # Проверяем оборудование если не виртуальный режим
    if not args.virtual and CANLIB_AVAILABLE:
        print(f"\n{COLOR_YELLOW}Checking Kvaser hardware...{COLOR_RESET}")
        hw_ok, hw_msg = check_kvaser_hardware()
        if not hw_ok:
            print(f"{COLOR_RED}Hardware check failed: {hw_msg}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}Try --virtual for testing without hardware{COLOR_RESET}")
        else:
            print(f"{COLOR_GREEN}Hardware OK: {hw_msg}{COLOR_RESET}")
    elif not CANLIB_AVAILABLE:
        print(f"{COLOR_YELLOW}canlib not available, skipping hardware check{COLOR_RESET}")

    # Создаём симулятор
    simulator = ESCSimulator()

    # Подключение к CAN
    try:
        print(f"\n{COLOR_CYAN}=== KVASER CONNECTION DEBUG ==={COLOR_RESET}")
        print(f"{COLOR_WHITE}Attempting to connect...{COLOR_RESET}")
        print(f"{COLOR_WHITE}  Interface: kvaser{COLOR_RESET}")
        print(f"{COLOR_WHITE}  Channel: {CHANNEL} (type: {type(CHANNEL)}){COLOR_RESET}")
        print(f"{COLOR_WHITE}  Bitrate: {BITRATE}{COLOR_RESET}")
        print(f"{COLOR_WHITE}  Virtual: {args.virtual}{COLOR_RESET}")

        # ВАЖНО: Kvaser требует строку для канала!
        channel_str = str(CHANNEL)
        print(f"{COLOR_WHITE}  Channel as string: '{channel_str}'{COLOR_RESET}")

        if args.virtual:
            print(f"{COLOR_YELLOW}Opening VIRTUAL channel...{COLOR_RESET}")
            bus = can.Bus(
                interface='kvaser',
                channel=channel_str,
                bitrate=BITRATE,
                accept_virtual=True,
                receive_own_messages=True
            )
            print(f"{COLOR_GREEN}✓ Connected to Kvaser VIRTUAL channel {CHANNEL}{COLOR_RESET}")
        else:
            print(f"{COLOR_YELLOW}Opening PHYSICAL channel...{COLOR_RESET}")
            bus = can.Bus(
                interface='kvaser',
                channel=channel_str,
                bitrate=BITRATE,
                receive_own_messages=True
            )
            print(f"{COLOR_GREEN}✓ Connected to Kvaser channel {CHANNEL}{COLOR_RESET}")
            print(f"{COLOR_GREEN}✓ Светодиод на Kvaser должен загореться!{COLOR_RESET}")

        # Проверяем что канал действительно открыт
        print(f"{COLOR_WHITE}  Bus state: {bus.state if hasattr(bus, 'state') else 'N/A'}{COLOR_RESET}")
        print(f"{COLOR_WHITE}  Bus protocol: {bus.protocol if hasattr(bus, 'protocol') else 'N/A'}{COLOR_RESET}")
        print(f"{COLOR_CYAN}{'='*60}{COLOR_RESET}\n")

        # ТЕСТОВАЯ ОТПРАВКА для проверки что канал работает
        print(f"{COLOR_YELLOW}Sending test message to verify bus...{COLOR_RESET}")
        test_msg = can.Message(
            arbitration_id=ESC_ID,
            data=[0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x00, 0x11],
            is_extended_id=False
        )
        try:
            bus.send(test_msg)
            print(f"{COLOR_GREEN}✓ Test message sent successfully!{COLOR_RESET}")
            print(f"{COLOR_GREEN}✓ Svetodiod на Kvaser должен мигнуть!{COLOR_RESET}")
        except Exception as e:
            print(f"{COLOR_RED}✗ Test message send FAILED: {e}{COLOR_RESET}")
        print()

        print(f"{COLOR_WHITE}Listening on 0x{STEND_ID:03X}, responding on 0x{ESC_ID:03X}{COLOR_RESET}")
        print(f"{COLOR_YELLOW}Press Ctrl+C to stop{COLOR_RESET}")
        print(f"{COLOR_CYAN}{'='*70}{COLOR_RESET}\n")

        # Запускаем поток статуса
        running_flag = {'running': True}
        status_thread = threading.Thread(
            target=status_display_thread,
            args=(simulator, running_flag),
            daemon=True
        )
        status_thread.start()

        # Основной цикл приёма
        with bus:
            msg_count = 0
            last_debug_time = time.time()

            while True:
                try:
                    msg = bus.recv(timeout=0.1)

                    # Дебаг: показываем что вообще что-то приходит
                    if msg is not None:
                        msg_count += 1

                        # Статистика сообщений (если не фильтруем)
                        if not PRINT_ONLY_CMDS and DEBUG_MODE and (time.time() - last_debug_time > 10.0):
                            print(f"{COLOR_MAGENTA}[DEBUG] Total messages received: {msg_count}{COLOR_RESET}")
                            last_debug_time = time.time()

                        # Показываем CAN сообщения в дебаге
                        if DEBUG_MODE:
                            # Если PRINT_ONLY_CMDS=True, показываем только 0x720 и 0x728
                            if PRINT_ONLY_CMDS:
                                if msg.arbitration_id in [STEND_ID, ESC_ID]:
                                    data_hex = ' '.join([f'{b:02X}' for b in msg.data])
                                    print(f"{COLOR_MAGENTA}[DEBUG] CAN RX: 0x{msg.arbitration_id:03X} {data_hex}{COLOR_RESET}")
                            else:
                                # Показываем все сообщения
                                data_hex = ' '.join([f'{b:02X}' for b in msg.data])
                                print(f"{COLOR_MAGENTA}[DEBUG] CAN RX: 0x{msg.arbitration_id:03X} {data_hex}{COLOR_RESET}")

                        # Обрабатываем только сообщения от стенда
                        if msg.arbitration_id == STEND_ID:
                            process_message(msg, simulator, bus)
                        elif DEBUG_MODE and not PRINT_ONLY_CMDS:
                            print(f"{COLOR_YELLOW}[DEBUG] Ignoring non-stend message from 0x{msg.arbitration_id:03X}{COLOR_RESET}")
                    else:
                        # Если долго нет сообщений, показываем что мы живы
                        if DEBUG_MODE and not PRINT_ONLY_CMDS and msg_count == 0 and (time.time() - last_debug_time > 5.0):
                            print(f"{COLOR_YELLOW}[DEBUG] No messages received yet... waiting...{COLOR_RESET}")
                            last_debug_time = time.time()

                except KeyboardInterrupt:
                    print(f"\n{COLOR_YELLOW}Interrupted by user{COLOR_RESET}")
                    break
                except Exception as e:
                    print(f"{COLOR_RED}Error: {e}{COLOR_RESET}")
                    if DEBUG_MODE:
                        import traceback
                        traceback.print_exc()

        # Останавливаем поток статуса
        running_flag['running'] = False
        status_thread.join(timeout=2.0)

        # Финальная статистика
        display_status(simulator)
        print(f"{COLOR_GREEN}Simulator stopped{COLOR_RESET}")

    except Exception as e:
        print(f"{COLOR_RED}Failed to connect to CAN bus: {e}{COLOR_RESET}")
        if DEBUG_MODE:
            import traceback
            traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
