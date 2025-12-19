"""
CAN Valve Control Sequence Player - TABLE SELECTOR VERSION
=========================================================
Plays ESC valve testing sequence according to table 1 or 2.
Tables are presented in a maximally readable format with full descriptions.

CYCLE MODE: Use --cycle to repeat table infinitely with pause between cycles.
"""

import can
import time
import argparse
import os
from datetime import datetime
from tqdm import tqdm

# ANSI color codes
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_WHITE = "\033[97m"
COLOR_CYAN = "\033[96m"
COLOR_BLUE = "\033[94m"
COLOR_MAGENTA = "\033[95m"
COLOR_RESET = "\033[0m"

# Time intervals (in seconds)
T1 = 0.140  # base timeout
T2 = 0.070  # fast sequence (cycles)
T3 = 0.250  # diagonal change
T4 = 0.400  # pauses between stages
T5 = 2.000  # very long pauses (depressurization)

# Default cycle pause
DEFAULT_CYCLE_PAUSE = 15  # seconds

# ============================================================================
# TABLE 1 - FULL TABLE (Both diagonals working simultaneously)
# ============================================================================
TABLE_1 = {
    "name": "Table 1 - Both diagonals simultaneously",
    "description": "Testing with all valves of each diagonal enabled simultaneously",
    "sequence": [
        # === INITIALIZATION ===
        {"data": [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T1, "desc": "Extended Session"},
        {"data": [0x04, 0x14, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00], "time": T1, "desc": "Security Access"},
        {"data": [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T1, "desc": "Repeat Extended Session"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},

        # === MAIN SEQUENCE OF TABLE 1 ===
        # Step 1-2: Initialization
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x00, 0x00], "time": T1, "desc": "1. All off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T1, "desc": "2. Pump motor on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x05, 0x40, 0x00], "time": T1, "desc": "3. Inlet valves front axle on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x40, 0x00], "time": T1, "desc": "4. Inlet valves rear axle on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T1, "desc": "5. USV1 and USV2 on (ISO_1 FR_RL and ISO_2 FL_RR)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "6. HSV1 and HSV2 on (SHU_1 FR_RL and SHU_2 FL_RR)"},

        # FL wheel (Front Left) - diagonal FL_RR
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x54, 0x4F, 0x00], "time": T4, "desc": "7. EVFL off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "8. EVFL on"},

        # CYCLE FL: 5 on/off cycles
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x54, 0x4F, 0x00], "time": T2, "desc": "FL cycle"},

        # Switch to FR
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T1, "desc": "11. HSV1 and HSV2 off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x57, 0x43, 0x00], "time": T3, "desc": "12. AVFL on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "13. AVFL off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "14. HSV1 and HSV2 on"},

        # FR wheel (Front Right) - diagonal FR_RL
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x51, 0x4F, 0x00], "time": T4, "desc": "15. EVFR off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "16. EVFR on"},

        # CYCLE FR: 5 on/off cycles
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x51, 0x4F, 0x00], "time": T2, "desc": "FR cycle"},

        # Switch to RL
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "19. HSV1 and HSV2 off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x5D, 0x43, 0x00], "time": T3, "desc": "20. AVFR on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "21. AVFR off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "22. HSV1 and HSV2 on"},

        # RL wheel (Rear Left) - diagonal FR_RL
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x45, 0x4F, 0x00], "time": T4, "desc": "23. EVRL off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T1, "desc": "24. EVRL on"},

        # CYCLE RL: 5 on/off cycles
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x45, 0x4F, 0x00], "time": T2, "desc": "RL cycle"},

        # Switch to RR
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "27. HSV1 and HSV2 off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x75, 0x43, 0x00], "time": T3, "desc": "28. AVRL on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T3, "desc": "29. AVRL off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T4, "desc": "30. HSV1 and HSV2 on"},

        # RR wheel (Rear Right) - diagonal FL_RR
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x15, 0x4F, 0x00], "time": T1, "desc": "31. EVRR off (T1)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "time": T4, "desc": "32. EVRR on"},

        # CYCLE RR: 5 on/off cycles
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4F, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x15, 0x4F, 0x00], "time": T2, "desc": "RR cycle"},

        # Finalization
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "35. HSV1 and HSV2 off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0xD5, 0x43, 0x00], "time": T3, "desc": "36. AVRR on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x43, 0x00], "time": T4, "desc": "37. AVRR off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x40, 0x00], "time": T1, "desc": "38. USV1 and USV2 off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x50, 0x40, 0x00], "time": T1, "desc": "39. Inlet valves front axle off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T1, "desc": "40. Inlet valves rear axle off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T5, "desc": "41. All valves off (depressurization)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x00, 0x00], "time": 0.1, "desc": "42. Pump motor off"},
    ]
}

# ============================================================================
# TABLE 2 - SEPARATE TABLE (Alternating diagonal work)
# ============================================================================
TABLE_2 = {
    "name": "Table 2 - Separately by diagonals",
    "description": "Testing with separate control of valves on diagonals FR_RL and FL_RR",
    "sequence": [
        # === INITIALIZATION ===
        {"data": [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T1, "desc": "Extended Session"},
        {"data": [0x04, 0x14, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00], "time": T1, "desc": "Security Access"},
        {"data": [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T1, "desc": "Repeat Extended Session"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},
        {"data": [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "time": T4, "desc": "Tester Present"},

        # === MAIN SEQUENCE OF TABLE 2 ===
        # Step 1-2: Initialization
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x00, 0x00], "time": T1, "desc": "1. All off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T1, "desc": "2. Pump motor on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x05, 0x40, 0x00], "time": T1, "desc": "3. Inlet valves front axle on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x40, 0x00], "time": T1, "desc": "4. Inlet valves rear axle on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "time": T1, "desc": "5. USV2 on (ISO_2 - diagonal FL_RR)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "time": T1, "desc": "6. HSV2 on (SHU_2 - diagonal FL_RR)"},

        # FL wheel (Front Left) - diagonal FL_RR active
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x54, 0x4A, 0x00], "time": T4, "desc": "7. EVFL off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "time": T1, "desc": "8. EVFL on"},

        # CYCLE FL: 5 on/off cycles
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x54, 0x4A, 0x00], "time": T2, "desc": "FL cycle"},

        # Switch to FR (CHANGE DIAGONAL: FL_RR → FR_RL)
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "time": T1, "desc": "11. HSV2 off (SHU_2)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x57, 0x41, 0x00], "time": T3, "desc": "12. AVFL on, USV1 on, USV2 off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00], "time": T4, "desc": "13. AVFL off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "time": T1, "desc": "14. HSV1 on (SHU_1 - diagonal FR_RL)"},

        # FR wheel (Front Right) - diagonal FR_RL active
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x51, 0x45, 0x00], "time": T4, "desc": "15. EVFR off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "time": T1, "desc": "16. EVFR on"},

        # CYCLE FR: 5 on/off cycles
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x51, 0x45, 0x00], "time": T2, "desc": "FR cycle"},

        # Switch to RL (STAY ON DIAGONAL FR_RL)
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00], "time": T4, "desc": "19. HSV1 off (SHU_1)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x5D, 0x41, 0x00], "time": T3, "desc": "20. AVFR on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00], "time": T4, "desc": "21. AVFR off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "time": T1, "desc": "22. HSV1 on (SHU_1)"},

        # RL wheel (Rear Left) - diagonal FR_RL active
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x45, 0x45, 0x00], "time": T4, "desc": "23. EVRL off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "time": T1, "desc": "24. EVRL on"},

        # CYCLE RL: 5 on/off cycles
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x45, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x45, 0x45, 0x00], "time": T2, "desc": "RL cycle"},

        # Switch to RR (CHANGE DIAGONAL: FR_RL → FL_RR)
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x41, 0x00], "time": T4, "desc": "27. HSV1 off (SHU_1)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x75, 0x42, 0x00], "time": T3, "desc": "28. AVRL on, USV2 on, USV1 off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "time": T3, "desc": "29. AVRL off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "time": T4, "desc": "30. HSV2 on (SHU_2 - diagonal FL_RR)"},

        # RR wheel (Rear Right) - diagonal FL_RR active
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x15, 0x4A, 0x00], "time": T1, "desc": "31. EVRR off (T1)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "time": T4, "desc": "32. EVRR on"},

        # CYCLE RR: 5 on/off cycles
        {"repeat": 5, "on": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x4A, 0x00], "off": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x15, 0x4A, 0x00], "time": T2, "desc": "RR cycle"},

        # Finalization
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "time": T4, "desc": "35. HSV2 off (SHU_2)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0xD5, 0x42, 0x00], "time": T3, "desc": "36. AVRR on"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x42, 0x00], "time": T4, "desc": "37. AVRR off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x55, 0x40, 0x00], "time": T1, "desc": "38. USV2 off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x50, 0x40, 0x00], "time": T1, "desc": "39. Inlet valves front axle off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T1, "desc": "40. Inlet valves rear axle off"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x40, 0x00], "time": T5, "desc": "41. All valves off (depressurization)"},
        {"data": [0x06, 0x2F, 0x4B, 0x12, 0x03, 0x00, 0x00, 0x00], "time": 0.1, "desc": "42. Pump motor off"},
    ]
}


class ValveController:
    def __init__(self, use_virtual=True, channel=0, bitrate=500000, blf_prefix=None):
        self.use_virtual = use_virtual
        self.channel = channel
        self.bitrate = bitrate
        self.blf_prefix = blf_prefix
        self.bus = None
        self.logger = None
        self.current_wheel = "FL"
        self.current_diagonal = "FL_RR"

    def connect(self):
        """Connect to CAN bus"""
        try:
            if self.use_virtual:
                print(f"{COLOR_WHITE}Connecting to VIRTUAL channel {self.channel}...{COLOR_RESET}")
                self.bus = can.Bus(
                    interface='virtual',
                    channel=self.channel,
                    receive_own_messages=True
                )
            else:
                print(f"{COLOR_WHITE}Connecting to Kvaser channel {self.channel}...{COLOR_RESET}")

                try:
                    from can.interfaces import kvaser
                    available_channels = kvaser.detect_available_configs()
                    print(f"{COLOR_YELLOW}Available Kvaser channels: {available_channels}{COLOR_RESET}")
                except Exception as e:
                    print(f"{COLOR_RED}Error detecting Kvaser: {e}{COLOR_RESET}")

                self.bus = can.Bus(
                    interface='kvaser',
                    channel=self.channel,
                    bitrate=self.bitrate,
                    accept_virtual=True
                )

            print(f"{COLOR_GREEN}Successfully connected to CAN bus{COLOR_RESET}")
            return True

        except Exception as e:
            print(f"{COLOR_RED}Connection error: {e}{COLOR_RESET}")
            return False

    def disconnect(self):
        """Disconnect from CAN bus and close logger"""
        if self.logger:
            self.logger.stop()
            self.logger = None

        if self.bus:
            self.bus.shutdown()
            self.bus = None

    def start_new_log(self, table_num, cycle_num=None):
        """Start new BLF log file"""
        if self.logger:
            self.logger.stop()
            self.logger = None

        if self.blf_prefix:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if cycle_num is not None:
                filename = f"{self.blf_prefix}_table{table_num}_cycle{cycle_num:04d}_{timestamp}.blf"
            else:
                filename = f"{self.blf_prefix}_table{table_num}_{timestamp}.blf"

            os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else '.', exist_ok=True)
            self.logger = can.BLFWriter(filename)
            print(f"{COLOR_GREEN}Logging to: {filename}{COLOR_RESET}")
            return filename
        return None

    def log_message(self, msg):
        """Log message"""
        if self.logger:
            self.logger.on_message_received(msg)

    def send_command(self, data, description="", stage_time=T1):
        """Send command with stage time delay"""
        if not self.bus:
            print(f"{COLOR_RED}CAN bus not connected!{COLOR_RESET}")
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

            elapsed = time.time() - stage_start
            remaining = stage_time - elapsed
            if remaining > 0:
                time.sleep(remaining)

            return True

        except Exception as e:
            print(f"{COLOR_RED}Send error: {e}{COLOR_RESET}")
            return False

    def run_sequence_once(self, table_data, show_header=True):
        """Run table sequence once (without connect/disconnect)"""
        if show_header:
            print(f"\n{COLOR_YELLOW}{'='*80}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}{table_data['name']}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}{table_data['description']}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}{'='*80}{COLOR_RESET}")
            print(f"{COLOR_WHITE}Time intervals: T1={T1}s, T2={T2}s, T3={T3}s, T4={T4}s, T5={T5}s{COLOR_RESET}")
            print()

        # Count total steps
        total_steps = 0
        for step in table_data["sequence"]:
            if "repeat" in step:
                total_steps += step["repeat"] * 2
            else:
                total_steps += 1

        pbar = tqdm(total=total_steps, desc="Sending commands", unit="msg", ncols=100)
        start_time = time.time()

        for step in table_data["sequence"]:
            if "repeat" in step:
                default_time = step.get("time", T2)
                off_time = step.get("off_time", default_time)
                on_time = step.get("on_time", default_time)

                for i in range(step["repeat"]):
                    self.send_command(step["off"], f"{step['desc']} - OFF ({i+1}/{step['repeat']})", off_time)
                    pbar.update(1)
                    self.send_command(step["on"], f"{step['desc']} - ON ({i+1}/{step['repeat']})", on_time)
                    pbar.update(1)
            else:
                self.send_command(step["data"], step["desc"], step["time"])
                pbar.update(1)

        pbar.close()
        total_time = time.time() - start_time
        return total_time

    def run_table_sequence(self, table_data, cycle_pause=None):
        """
        Run table sequence.
        If cycle_pause is set, runs infinitely with pause between cycles.
        """
        if not self.connect():
            return False

        table_num = 1 if "Table 1" in table_data['name'] else 2

        try:
            if cycle_pause is None:
                # Single run mode
                self.start_new_log(table_num)
                total_time = self.run_sequence_once(table_data, show_header=True)
                print(f"\n{COLOR_GREEN}Table {table_data['name']} completed in {total_time:.1f} seconds!{COLOR_RESET}")
            else:
                # Infinite cycle mode
                cycle_num = 1
                total_cycles_time = 0

                print(f"\n{COLOR_MAGENTA}{'='*80}{COLOR_RESET}")
                print(f"{COLOR_MAGENTA}CYCLE MODE: Table {table_num}, pause {cycle_pause}s between cycles{COLOR_RESET}")
                print(f"{COLOR_MAGENTA}Press Ctrl+C to stop{COLOR_RESET}")
                print(f"{COLOR_MAGENTA}{'='*80}{COLOR_RESET}")

                while True:
                    print(f"\n{COLOR_GREEN}{'='*60}{COLOR_RESET}")
                    print(f"{COLOR_GREEN}>>> CYCLE {cycle_num} STARTING{COLOR_RESET}")
                    print(f"{COLOR_GREEN}{'='*60}{COLOR_RESET}")

                    # New log file for each cycle
                    self.start_new_log(table_num, cycle_num)

                    cycle_time = self.run_sequence_once(table_data, show_header=(cycle_num == 1))
                    total_cycles_time += cycle_time

                    print(f"\n{COLOR_GREEN}Cycle {cycle_num} completed in {cycle_time:.1f}s (total: {total_cycles_time:.1f}s){COLOR_RESET}")

                    # Pause before next cycle
                    print(f"{COLOR_YELLOW}>>> Waiting {cycle_pause} seconds before next cycle...{COLOR_RESET}")
                    print(f"{COLOR_YELLOW}    (Press Ctrl+C to stop){COLOR_RESET}")

                    # Countdown with progress
                    for remaining in range(int(cycle_pause), 0, -1):
                        print(f"\r{COLOR_YELLOW}    Next cycle in: {remaining}s   {COLOR_RESET}", end='', flush=True)
                        time.sleep(1)
                    print()

                    cycle_num += 1

        except KeyboardInterrupt:
            print(f"\n\n{COLOR_YELLOW}{'='*60}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}Stopped by user after {cycle_num if cycle_pause else 1} cycle(s){COLOR_RESET}")
            if cycle_pause:
                print(f"{COLOR_YELLOW}Total time: {total_cycles_time:.1f} seconds{COLOR_RESET}")
            print(f"{COLOR_YELLOW}{'='*60}{COLOR_RESET}")
            return False
        except Exception as e:
            print(f"{COLOR_RED}Execution error: {e}{COLOR_RESET}")
            return False
        finally:
            self.disconnect()

        return True


def print_table_comparison():
    """Print table comparison"""
    print(f"\n{COLOR_MAGENTA}{'='*80}{COLOR_RESET}")
    print(f"{COLOR_MAGENTA}ESC VALVE TESTING TABLES COMPARISON{COLOR_RESET}")
    print(f"{COLOR_MAGENTA}{'='*80}{COLOR_RESET}")

    print(f"\n{COLOR_BLUE}TABLE 1:{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Name: {TABLE_1['name']}{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Description: {TABLE_1['description']}{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Features:{COLOR_RESET}")
    print(f"    - Both diagonals work simultaneously")
    print(f"    - All USV (isolation) and HSV (shuttle) valves are enabled at once")
    print(f"    - Uses data: 55 43, 55 4F")

    print(f"\n{COLOR_BLUE}TABLE 2:{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Name: {TABLE_2['name']}{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Description: {TABLE_2['description']}{COLOR_RESET}")
    print(f"  {COLOR_WHITE}• Features:{COLOR_RESET}")
    print(f"    - Diagonals work alternately")
    print(f"    - USV and HSV are enabled only for active diagonal")
    print(f"    - Uses data: 55 42, 55 4A (diagonal FL_RR) and 55 41, 55 45 (diagonal FR_RL)")
    print(f"    - More precise isolated testing")

    print(f"\n{COLOR_MAGENTA}{'='*80}{COLOR_RESET}")


def main():
    parser = argparse.ArgumentParser(
        description='Valve Control Sequence Player - Table selection for testing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  %(prog)s -t 1                     # Run table 1 once
  %(prog)s -t 2                     # Run table 2 once
  %(prog)s -t 1 --cycle             # Run table 1 infinitely (15s pause)
  %(prog)s -t 2 --cycle 30          # Run table 2 infinitely (30s pause)
  %(prog)s -t 1 -p mytest --cycle   # With BLF prefix + infinite cycle
  %(prog)s -t 2 --no-virtual        # Use real CAN interface
        """
    )

    parser.add_argument('--table', '-t', type=int, choices=[1, 2], default=1,
                       help='Table number to execute (1 or 2, default: 1)')
    parser.add_argument('--cycle', nargs='?', type=float, const=DEFAULT_CYCLE_PAUSE, default=None,
                       metavar='SECONDS',
                       help=f'Run infinitely with pause between cycles (default: {DEFAULT_CYCLE_PAUSE}s)')
    parser.add_argument('--prefix', '-p', type=str, default=None,
                       help='BLF output file prefix (e.g., "mytest" -> mytest_table1_cycle0001_*.blf)')
    parser.add_argument('--virtual', '-v', action='store_true', default=False,
                       help='Use virtual CAN channel (default: False)')
    parser.add_argument('--no-virtual', action='store_false', dest='virtual',
                       help='Use real CAN interface (Kvaser)')
    parser.add_argument('--channel', type=int, default=0,
                       help='CAN channel number (default: 0)')
    parser.add_argument('--bitrate', '-b', type=int, default=500000,
                       help='CAN bus speed (default: 500000)')
    parser.add_argument('--compare', action='store_true',
                       help='Show table comparison without execution')

    args = parser.parse_args()

    if args.compare:
        print_table_comparison()
        return

    # Table selection
    if args.table == 1:
        table_data = TABLE_1
        print(f"\n{COLOR_GREEN}Selected TABLE 1{COLOR_RESET}")
    else:
        table_data = TABLE_2
        print(f"\n{COLOR_GREEN}Selected TABLE 2{COLOR_RESET}")

    # Mode info
    if args.cycle is not None:
        print(f"{COLOR_CYAN}Mode: INFINITE CYCLE (pause: {args.cycle}s){COLOR_RESET}")
    else:
        print(f"{COLOR_CYAN}Mode: SINGLE RUN{COLOR_RESET}")

    if args.prefix:
        print(f"{COLOR_WHITE}BLF prefix: {args.prefix}{COLOR_RESET}")

    # Create controller and run
    controller = ValveController(
        use_virtual=args.virtual,
        channel=args.channel,
        bitrate=args.bitrate,
        blf_prefix=args.prefix
    )

    # Brief comparison
    print_table_comparison()

    # Run
    controller.run_table_sequence(table_data, cycle_pause=args.cycle)


if __name__ == "__main__":
    main()
