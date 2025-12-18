"""
CAN Valve Control Sequence Player - TABLE SELECTOR VERSION
=========================================================
Проигрывает последовательность тестирования клапанов ESC по таблицам 1 или 2.
Таблицы представлены в максимально читаемом виде с полными описаниями.
"""

import can
import time
import argparse
import os
from datetime import datetime
from tqdm import tqdm

# ANSI цветовые коды
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_WHITE = "\033[97m"
COLOR_CYAN = "\033[96m"
COLOR_BLUE = "\033[94m"
COLOR_MAGENTA = "\033[95m"
COLOR_RESET = "\033[0m"

# Временные интервалы (в секундах)
T1 = 0.140  # базовый таймаут
T2 = 0.070  # быстрая последовательность (циклы)
T3 = 0.250  # смена диагоналей
T4 = 0.400  # паузы между этапами
T5 = 2.000  # очень длинные паузы (опустошение)

# ============================================================================
# TABLE 1 - ПОЛНАЯ ТАБЛИЦА (Одновременная работа обеих диагоналей)
# ============================================================================
TABLE_1 = {
    "name": "TABLE 1 - ОБЕ ДИАГОНАЛИ ОДНОВРЕМЕННО",
    "description": "Тестирование с включением ВСЕХ клапанов каждой диагонали одновременно",
    "sequence": [
        # === ИНИЦИАЛИЗАЦИЯ ===
        {"data": [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T1, "desc": "Extended Session"},
        {"data": [0x04, 0x14, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00], "time": T1, "desc": "Security Access"},
        {"data": [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T1, "desc": "Повтор Extended Session"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},

        # === ОСНОВНАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ TABLE 1 ===
        # Шаг 1-2: Инициализация
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x00, 0x00], "time": T1, "desc": "1. ВСЕ ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T1, "desc": "2. МОТОР НАСОСА ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x05, 0x40, 0x00], "time": T1, "desc": "3. ВПУСКНЫЕ КЛАПАНЫ ПЕРЕДНЕЙ ОСИ ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x40, 0x00], "time": T1, "desc": "4. ВПУСКНЫЕ КЛАПАНЫ ЗАДНЕЙ ОСИ ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T1, "desc": "5. USV1 и USV2 ВКЛ (ISO_1 FR_RL и ISO_2 FL_RR)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "6. HSV1 и HSV2 ВКЛ (SHU_1 FR_RL и SHU_2 FL_RR)"},

        # FL Колесо (Переднее Левое) - диагональ FL_RR
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x54, 0x4F, 0x00], "time": T4, "desc": "7. EVFL ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "8. EVFL ВКЛ"},

        # ЦИКЛ FL: 5 включений/выключений
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x54, 0x4F, 0x00], "time": T2, "desc": "FL цикл"},

        # Переключение на FR
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T1, "desc": "11. HSV1 и HSV2 ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x57, 0x43, 0x00], "time": T3, "desc": "12. AVFL ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "13. AVFL ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "14. HSV1 и HSV2 ВКЛ"},

        # FR Колесо (Переднее Правое) - диагональ FR_RL
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x51, 0x4F, 0x00], "time": T4, "desc": "15. EVFR ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "16. EVFR ВКЛ"},

        # ЦИКЛ FR: 5 включений/выключений
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x51, 0x4F, 0x00], "time": T2, "desc": "FR цикл"},

        # Переключение на RL
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "19. HSV1 и HSV2 ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x5D, 0x43, 0x00], "time": T3, "desc": "20. AVFR ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "21. AVFR ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "22. HSV1 и HSV2 ВКЛ"},

        # RL Колесо (Заднее Левое) - диагональ FR_RL
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x45, 0x4F, 0x00], "time": T4, "desc": "23. EVRL ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "24. EVRL ВКЛ"},

        # ЦИКЛ RL: 5 включений/выключений
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x45, 0x4F, 0x00], "time": T2, "desc": "RL цикл"},

        # Переключение на RR
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "27. HSV1 и HSV2 ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x75, 0x43, 0x00], "time": T3, "desc": "28. AVRL ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T3, "desc": "29. AVRL ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T4, "desc": "30. HSV1 и HSV2 ВКЛ"},

        # RR Колесо (Заднее Правое) - диагональ FL_RR
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x15, 0x4F, 0x00], "time": T1, "desc": "31. EVRR ВЫКЛ (T1)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T4, "desc": "32. EVRR ВКЛ"},

        # ЦИКЛ RR: 5 включений/выключений
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x15, 0x4F, 0x00], "time": T2, "desc": "RR цикл"},

        # Завершение
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "35. HSV1 и HSV2 ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0xD5, 0x43, 0x00], "time": T3, "desc": "36. AVRR ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "37. AVRR ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x40, 0x00], "time": T1, "desc": "38. USV1 и USV2 ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x50, 0x40, 0x00], "time": T1, "desc": "39. ВПУСКНЫЕ КЛАПАНЫ ПЕРЕДНЕЙ ОСИ ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T1, "desc": "40. ВПУСКНЫЕ КЛАПАНЫ ЗАДНЕЙ ОСИ ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T5, "desc": "41. ВСЕ КЛАПАНЫ ВЫКЛ (ОПУСТОШЕНИЕ)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x00, 0x00], "time": 0.1, "desc": "42. МОТОР НАСОСА ВЫКЛ"},
    ]
}

# ============================================================================
# TABLE 2 - РАЗДЕЛЬНАЯ ТАБЛИЦА (Поочередная работа диагоналей)
# ============================================================================
TABLE_2 = {
    "name": "TABLE 2 - РАЗДЕЛЬНО ПО ДИАГОНАЛЯМ",
    "description": "Тестирование с раздельным управлением клапанами диагоналей FR_RL и FL_RR",
    "sequence": [
        # === ИНИЦИАЛИЗАЦИЯ ===
        {"data": [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T1, "desc": "Extended Session"},
        {"data": [0x04, 0x14, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00], "time": T1, "desc": "Security Access"},
        {"data": [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T1, "desc": "Повтор Extended Session"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},

        # === ОСНОВНАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ TABLE 2 ===
        # Шаг 1-2: Инициализация
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x00, 0x00], "time": T1, "desc": "1. ВСЕ ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T1, "desc": "2. МОТОР НАСОСА ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x05, 0x40, 0x00], "time": T1, "desc": "3. ВПУСКНЫЕ КЛАПАНЫ ПЕРЕДНЕЙ ОСИ ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x40, 0x00], "time": T1, "desc": "4. ВПУСКНЫЕ КЛАПАНЫ ЗАДНЕЙ ОСИ ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "time": T1, "desc": "5. USV2 ВКЛ (ISO_2 - ДИАГОНАЛЬ FL_RR)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "time": T1, "desc": "6. HSV2 ВКЛ (SHU_2 - ДИАГОНАЛЬ FL_RR)"},

        # FL Колесо (Переднее Левое) - ДИАГОНАЛЬ FL_RR АКТИВНА
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x54, 0x4A, 0x00], "time": T4, "desc": "7. EVFL ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "time": T1, "desc": "8. EVFL ВКЛ"},

        # ЦИКЛ FL: 5 включений/выключений
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x54, 0x4A, 0x00], "time": T2, "desc": "FL цикл"},

        # Переключение на FR (МЕНЯЕМ ДИАГОНАЛЬ: FL_RR → FR_RL)
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "time": T1, "desc": "11. HSV2 ВЫКЛ (SHU_2)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x57, 0x41, 0x00], "time": T3, "desc": "12. AVFL ВКЛ, USV1 ВКЛ, USV2 ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00], "time": T4, "desc": "13. AVFL ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "time": T1, "desc": "14. HSV1 ВКЛ (SHU_1 - ДИАГОНАЛЬ FR_RL)"},

        # FR Колесо (Переднее Правое) - ДИАГОНАЛЬ FR_RL АКТИВНА
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x51, 0x45, 0x00], "time": T4, "desc": "15. EVFR ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "time": T1, "desc": "16. EVFR ВКЛ"},

        # ЦИКЛ FR: 5 включений/выключений
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x51, 0x45, 0x00], "time": T2, "desc": "FR цикл"},

        # Переключение на RL (ОСТАЕМСЯ НА ДИАГОНАЛИ FR_RL)
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00], "time": T4, "desc": "19. HSV1 ВЫКЛ (SHU_1)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x5D, 0x41, 0x00], "time": T3, "desc": "20. AVFR ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00], "time": T4, "desc": "21. AVFR ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "time": T1, "desc": "22. HSV1 ВКЛ (SHU_1)"},

        # RL Колесо (Заднее Левое) - ДИАГОНАЛЬ FR_RL АКТИВНА
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x45, 0x45, 0x00], "time": T4, "desc": "23. EVRL ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "time": T1, "desc": "24. EVRL ВКЛ"},

        # ЦИКЛ RL: 5 включений/выключений
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x45, 0x45, 0x00], "time": T2, "desc": "RL цикл"},

        # Переключение на RR (МЕНЯЕМ ДИАГОНАЛЬ: FR_RL → FL_RR)
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00], "time": T4, "desc": "27. HSV1 ВЫКЛ (SHU_1)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x75, 0x42, 0x00], "time": T3, "desc": "28. AVRL ВКЛ, USV2 ВКЛ, USV1 ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "time": T3, "desc": "29. AVRL ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "time": T4, "desc": "30. HSV2 ВКЛ (SHU_2 - ДИАГОНАЛЬ FL_RR)"},

        # RR Колесо (Заднее Правое) - ДИАГОНАЛЬ FL_RR АКТИВНА
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x15, 0x4A, 0x00], "time": T1, "desc": "31. EVRR ВЫКЛ (T1)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "time": T4, "desc": "32. EVRR ВКЛ"},

        # ЦИКЛ RR: 5 включений/выключений
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x15, 0x4A, 0x00], "time": T2, "desc": "RR цикл"},

        # Завершение
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "time": T4, "desc": "35. HSV2 ВЫКЛ (SHU_2)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0xD5, 0x42, 0x00], "time": T3, "desc": "36. AVRR ВКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "time": T4, "desc": "37. AVRR ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x40, 0x00], "time": T1, "desc": "38. USV2 ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x50, 0x40, 0x00], "time": T1, "desc": "39. ВПУСКНЫЕ КЛАПАНЫ ПЕРЕДНЕЙ ОСИ ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T1, "desc": "40. ВПУСКНЫЕ КЛАПАНЫ ЗАДНЕЙ ОСИ ВЫКЛ"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T5, "desc": "41. ВСЕ КЛАПАНЫ ВЫКЛ (ОПУСТОШЕНИЕ)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x00, 0x00], "time": 0.1, "desc": "42. МОТОР НАСОСА ВЫКЛ"},
    ]
}

class ValveController:
    def __init__(self, use_virtual=True, channel=0, bitrate=500000, blf_output=None):
        self.use_virtual = use_virtual
        self.channel = channel
        self.bitrate = bitrate
        self.blf_output = blf_output
        self.bus = None
        self.logger = None
        self.current_wheel = "FL"
        self.current_diagonal = "FL_RR"  # Для Table 2

    def connect(self):
        """Подключение к CAN шине и инициализация логгера"""
        try:
            if self.use_virtual:
                print(f"{COLOR_WHITE}Подключение к VIRTUAL каналу {self.channel}...{COLOR_RESET}")
                self.bus = can.Bus(
                    interface='virtual',
                    channel=self.channel,
                    receive_own_messages=True
                )
            else:
                print(f"{COLOR_WHITE}Подключение к Kvaser каналу {self.channel}...{COLOR_RESET}")
                self.bus = can.Bus(
                    interface='kvaser',
                    channel=self.channel,
                    bitrate=self.bitrate,
                    accept_virtual=True
                )

            print(f"{COLOR_GREEN}Успешно подключено к CAN шине{COLOR_RESET}")

            if self.blf_output:
                os.makedirs(os.path.dirname(self.blf_output) if os.path.dirname(self.blf_output) else '.', exist_ok=True)
                self.logger = can.BLFWriter(self.blf_output)
                print(f"{COLOR_GREEN}Логгирование в файл: {self.blf_output}{COLOR_RESET}")

            return True

        except Exception as e:
            print(f"{COLOR_RED}Ошибка подключения: {e}{COLOR_RESET}")
            return False

    def disconnect(self):
        """Отключение от CAN шины и закрытие логгера"""
        if self.bus:
            self.bus.shutdown()
            self.bus = None

        if self.logger:
            self.logger.stop()
            self.logger = None

    def log_message(self, msg):
        """Записывает сообщение в логгер"""
        if self.logger:
            self.logger.on_message_received(msg)

    def send_command(self, data, description="", stage_time=T1):
        """Отправка команды с выдержкой времени этапа"""
        if not self.bus:
            print(f"{COLOR_RED}CAN шина не подключена!{COLOR_RESET}")
            return False

        try:
            stage_start = time.time()

            tx_msg = can.Message(
                arbitration_id=0x740,
                data=data,
                is_extended_id=False,
                timestamp=time.time()
            )

            self.bus.send(tx_msg)
            self.log_message(tx_msg)

            data_hex = ' '.join([f'{b:02X}' for b in data])
            print(f"{COLOR_WHITE}{tx_msg.timestamp:.6f} 0  740       Tx   d {len(data)} {data_hex}{COLOR_RESET}")

            if description:
                print(f"{COLOR_CYAN}# {description}{COLOR_RESET}")

            # Выдерживаем время этапа
            elapsed = time.time() - stage_start
            remaining = stage_time - elapsed
            if remaining > 0:
                time.sleep(remaining)

            return True

        except Exception as e:
            print(f"{COLOR_RED}Ошибка отправки: {e}{COLOR_RESET}")
            return False

    def switch_wheel(self, new_wheel, diagonal=None):
        """Переключение на следующее колесо и/или диагональ"""
        if new_wheel != self.current_wheel:
            diag_info = f" ({diagonal})" if diagonal else ""
            print(f"{COLOR_CYAN}>>> Переключение с {self.current_wheel} на {new_wheel}{diag_info}{COLOR_RESET}")
            self.current_wheel = new_wheel
            if diagonal:
                self.current_diagonal = diagonal

    def run_table_sequence(self, table_data):
        """Запуск последовательности выбранной таблицы"""
        if not self.connect():
            return False

        try:
            print(f"\n{COLOR_YELLOW}{'='*80}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}{table_data['name']}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}{table_data['description']}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}{'='*80}{COLOR_RESET}")

            print(f"{COLOR_WHITE}Временные интервалы: T1={T1}s, T2={T2}s, T3={T3}s, T4={T4}s, T5={T5}s{COLOR_RESET}")
            if self.blf_output:
                print(f"{COLOR_WHITE}Логгирование: {self.blf_output}{COLOR_RESET}")
            print()

            # Подсчет общего количества шагов для прогресс-бара
            total_steps = 0
            for step in table_data["sequence"]:
                if "repeat" in step:
                    total_steps += step["repeat"] * 2  # on + off для каждого повторения
                else:
                    total_steps += 1

            # Прогресс-бар
            pbar = tqdm(total=total_steps, desc="Отправка команд", unit="msg", ncols=100)

            start_time = time.time()

            # Воспроизведение последовательности
            for step in table_data["sequence"]:
                if "repeat" in step:
                    # Циклический шаг
                    # ИСПРАВЛЕНО: безопасное получение времени с fallback
                    default_time = step.get("time", T2)
                    off_time = step.get("off_time", default_time)
                    on_time = step.get("on_time", default_time)

                    for i in range(step["repeat"]):
                        # OFF команда
                        self.send_command(step["off"], f"{step['desc']} - OFF ({i+1}/{step['repeat']})", off_time)
                        pbar.update(1)

                        # ON команда
                        self.send_command(step["on"], f"{step['desc']} - ON ({i+1}/{step['repeat']})", on_time)
                        pbar.update(1)
                else:
                    # Одиночный шаг
                    self.send_command(step["data"], step["desc"], step["time"])
                    pbar.update(1)

            pbar.close()

            total_time = time.time() - start_time
            print(f"\n{COLOR_GREEN}Таблица {table_data['name']} завершена за {total_time:.1f} секунд!{COLOR_RESET}")
            return True

        except KeyboardInterrupt:
            print(f"\n{COLOR_YELLOW}Остановлено пользователем{COLOR_RESET}")
            return False
        except Exception as e:
            print(f"{COLOR_RED}Ошибка выполнения: {e}{COLOR_RESET}")
            return False
        finally:
            self.disconnect()

def print_table_comparison():
    """Печать сравнения таблиц"""
    print(f"\n{COLOR_MAGENTA}{'='*80}{COLOR_RESET}")
    print(f"{COLOR_MAGENTA}СРАВНЕНИЕ ТАБЛИЦ ТЕСТИРОВАНИЯ КЛАПАНОВ ESC{COLOR_RESET}")
    print(f"{COLOR_MAGENTA}{'='*80}{COLOR_RESET}")

    print(f"\n{COLOR_BLUE}ТАБЛИЦА 1:{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Название: {TABLE_1['name']}{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Описание: {TABLE_1['description']}{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Особенности:{COLOR_RESET}")
    print(f"    - Обе диагонали работают одновременно")
    print(f"    - Все USV (изоляционные) и HSV (шатунные) клапаны включены сразу")
    print(f"    - Используются данные: 55 43, 55 4F")

    print(f"\n{COLOR_BLUE}ТАБЛИЦА 2:{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Название: {TABLE_2['name']}{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Описание: {TABLE_2['description']}{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Особенности:{COLOR_RESET}")
    print(f"    - Диагонали работают поочередно")
    print(f"    - USV и HSV включаются только для активной диагонали")
    print(f"    - Используются данные: 55 42, 55 4A (диагональ FL_RR) и 55 41, 55 45 (диагональ FR_RL)")
    print(f"    - Более точное изолированное тестирование")

    print(f"\n{COLOR_MAGENTA}{'='*80}{COLOR_RESET}")

def generate_blf_filename(table_num):
    """Генерирует имя BLF файла на основе текущего времени и номера таблицы"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"valve_table{table_num}_{timestamp}.blf"

def main():
    parser = argparse.ArgumentParser(
        description='Valve Control Sequence Player - Выбор таблицы тестирования',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s --table 1           # Запустить таблицу 1
  %(prog)s --table 2           # Запустить таблицу 2
  %(prog)s --table 1 --no-virtual  # Использовать реальный CAN интерфейс
  %(prog)s --table 2 --channel 1   # Использовать CAN канал 1
        """
    )

    parser.add_argument('--table', '-t', type=int, choices=[1, 2], default=1,
                       help='Номер таблицы для выполнения (1 или 2, по умолчанию: 1)')
    parser.add_argument('--virtual', '-v', action='store_true', default=True,
                       help='Использовать виртуальный CAN канал (по умолчанию: True)')
    parser.add_argument('--no-virtual', action='store_false', dest='virtual',
                       help='Использовать реальный CAN интерфейс (Kvaser)')
    parser.add_argument('--channel', '-c', type=int, default=0,
                       help='Номер CAN канала (по умолчанию: 0)')
    parser.add_argument('--bitrate', '-b', type=int, default=500000,
                       help='Скорость CAN шины (по умолчанию: 500000)')
    parser.add_argument('--blf', action='store_true', default=True,
                       help='Включить логирование в BLF файл (по умолчанию: True)')
    parser.add_argument('--no-blf', action='store_false', dest='blf',
                       help='Отключить логирование в BLF файл')
    parser.add_argument('--blf-file', type=str, default=None,
                       help='Путь к файлу BLF (по умолчанию: авто-генерация)')
    parser.add_argument('--compare', action='store_true',
                       help='Показать сравнение таблиц без выполнения')

    args = parser.parse_args()

    # Показать сравнение таблиц если запрошено
    if args.compare:
        print_table_comparison()
        return

    # Выбор таблицы
    if args.table == 1:
        table_data = TABLE_1
        print(f"\n{COLOR_GREEN}Выбрана ТАБЛИЦА 1{COLOR_RESET}")
    else:
        table_data = TABLE_2
        print(f"\n{COLOR_GREEN}Выбрана ТАБЛИЦА 2{COLOR_RESET}")

    # Настройка логирования
    blf_output = args.blf_file
    if args.blf and blf_output is None:
        blf_output = generate_blf_filename(args.table)
        print(f"{COLOR_WHITE}BLF файл: {blf_output}{COLOR_RESET}")

    # Создание контроллера и запуск
    controller = ValveController(
        use_virtual=args.virtual,
        channel=args.channel,
        bitrate=args.bitrate,
        blf_output=blf_output
    )

    # Показать краткое сравнение перед запуском
    print_table_comparison()

    # Запуск выбранной таблицы
    controller.run_table_sequence(table_data)

if __name__ == "__main__":
    main()
