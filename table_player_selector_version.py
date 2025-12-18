
"""
CAN Valve Control Sequence Player - TABLE SELECTOR VERSION
=========================================================
Plays ESC valve testing sequence according to table 1 or 2.
Tables are presented in a maximally readable format with full descriptions.
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
    def __init__(self, use_virtual=True, channel=0, bitrate=500000, blf_output=None):
        self.use_virtual = use_virtual
        self.channel = channel
        self.bitrate = bitrate
        self.blf_output = blf_output
        self.bus = None
        self.logger = None
        self.current_wheel = "FL"
        self.current_diagonal = "FL_RR"  # For Table 2

    def connect(self):
        """Connect to CAN bus and initialize logger"""
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

                # Debug
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

            if self.blf_output:
                os.makedirs(os.path.dirname(self.blf_output) if os.path.dirname(self.blf_output) else '.', exist_ok=True)
                self.logger = can.BLFWriter(self.blf_output)
                print(f"{COLOR_GREEN}Logging to file: {self.blf_output}{COLOR_RESET}")

            return True

        except Exception as e:
            print(f"{COLOR_RED}Connection error: {e}{COLOR_RESET}")
            return False

    def disconnect(self):
        """Disconnect from CAN bus and close logger"""
        if self.bus:
            self.bus.shutdown()
            self.bus = None

        if self.logger:
            self.logger.stop()
            self.logger = None

    def log_message(self, msg):
        """Log message to logger"""
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

            # Maintain stage time
            elapsed = time.time() - stage_start
            remaining = stage_time - elapsed
            if remaining > 0:
                time.sleep(remaining)

            return True

        except Exception as e:
            print(f"{COLOR_RED}Send error: {e}{COLOR_RESET}")
            return False

    def switch_wheel(self, new_wheel, diagonal=None):
        """Switch to next wheel and/or diagonal"""
        if new_wheel != self.current_wheel:
            diag_info = f" ({diagonal})" if diagonal else ""
            print(f"{COLOR_CYAN}>>> Switching from {self.current_wheel} to {new_wheel}{diag_info}{COLOR_RESET}")
            self.current_wheel = new_wheel
            if diagonal:
                self.current_diagonal = diagonal

    def run_table_sequence(self, table_data):
        """Run selected table sequence"""
        if not self.connect():
            return False

        try:
            print(f"\n{COLOR_YELLOW}{'='*80}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}{table_data['name']}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}{table_data['description']}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}{'='*80}{COLOR_RESET}")

            print(f"{COLOR_WHITE}Time intervals: T1={T1}s, T2={T2}s, T3={T3}s, T4={T4}s, T5={T5}s{COLOR_RESET}")
            if self.blf_output:
                print(f"{COLOR_WHITE}Logging: {self.blf_output}{COLOR_RESET}")
            print()

            # Count total steps for progress bar
            total_steps = 0
            for step in table_data["sequence"]:
                if "repeat" in step:
                    total_steps += step["repeat"] * 2  # on + off for each repeat
                else:
                    total_steps += 1

            # Progress bar
            pbar = tqdm(total=total_steps, desc="Sending commands", unit="msg", ncols=100)

            start_time = time.time()

            # Play sequence
            for step in table_data["sequence"]:
                if "repeat" in step:
                    # Cyclic step
                    # FIXED: safe time retrieval with fallback
                    default_time = step.get("time", T2)
                    off_time = step.get("off_time", default_time)
                    on_time = step.get("on_time", default_time)

                    for i in range(step["repeat"]):
                        # OFF command
                        self.send_command(step["off"], f"{step['desc']} - OFF ({i+1}/{step['repeat']})", off_time)
                        pbar.update(1)

                        # ON command
                        self.send_command(step["on"], f"{step['desc']} - ON ({i+1}/{step['repeat']})", on_time)
                        pbar.update(1)
                else:
                    # Single step
                    self.send_command(step["data"], step["desc"], step["time"])
                    pbar.update(1)

            pbar.close()

            total_time = time.time() - start_time
            print(f"\n{COLOR_GREEN}Table {table_data['name']} completed in {total_time:.1f} seconds!{COLOR_RESET}")
            return True

        except KeyboardInterrupt:
            print(f"\n{COLOR_YELLOW}Stopped by user{COLOR_RESET}")
            return False
        except Exception as e:
            print(f"{COLOR_RED}Execution error: {e}{COLOR_RESET}")
            return False
        finally:
            self.disconnect()

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

def generate_blf_filename(table_num):
    """Generate BLF filename based on current time and table number"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"valve_table{table_num}_{timestamp}.blf"

def main():
    parser = argparse.ArgumentParser(
        description='Valve Control Sequence Player - Table selection for testing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  %(prog)s --table 1           # Run table 1
  %(prog)s --table 2           # Run table 2
  %(prog)s --table 1 --no-virtual  # Use real CAN interface
  %(prog)s --table 2 --channel 1   # Use CAN channel 1
        """
    )

    parser.add_argument('--table', '-t', type=int, choices=[1, 2], default=1,
                       help='Table number to execute (1 or 2, default: 1)')
    parser.add_argument('--virtual', '-v', action='store_true', default=False,
                       help='Use virtual CAN channel (default: False)')
    parser.add_argument('--no-virtual', action='store_false', dest='virtual',
                       help='Use real CAN interface (Kvaser)')
    parser.add_argument('--channel', '-c', type=int, default=0,
                       help='CAN channel number (default: 0)')
    parser.add_argument('--bitrate', '-b', type=int, default=500000,
                       help='CAN bus speed (default: 500000)')
    parser.add_argument('--blf', action='store_true', default=True,
                       help='Enable BLF logging (default: True)')
    parser.add_argument('--no-blf', action='store_false', dest='blf',
                       help='Disable BLF logging')
    parser.add_argument('--blf-file', type=str, default=None,
                       help='BLF output file path (default: auto-generated)')
    parser.add_argument('--compare', action='store_true',
                       help='Show table comparison without execution')

    args = parser.parse_args()

    # Show table comparison if requested
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

    # Logging setup
    blf_output = args.blf_file
    if args.blf and blf_output is None:
        blf_output = generate_blf_filename(args.table)
        print(f"{COLOR_WHITE}BLF file: {blf_output}{COLOR_RESET}")

    # Create controller and run
    controller = ValveController(
        use_virtual=args.virtual,
        channel=args.channel,
        bitrate=args.bitrate,
        blf_output=blf_output
    )

    # Show brief comparison before execution
    print_table_comparison()

    # Run selected table
    controller.run_table_sequence(table_data)

if __name__ == "__main__":
    main()
