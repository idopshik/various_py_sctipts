inregulation_name_xgf = "ABSinRegulation"

VESTA_DBC = "res_files\\MSRS_ESC_ALL_AV3_MESSAGE_LIST_AV3 draft__14_02_2023.dbc"
GRANTA_DBC = "res_files\\ABS_ESP_XGD_XGL_XGM.dbc"

#folder path
PATH = "C:\\Users\\belousov\\Desktop\\tmp"

#time in sec.
TIME_BEFORE_BRAKING = 2
TIME_AFTER_BRAKING = 1
OFF_DELAY = 3

XGD_NO_REGULATION_STRING = "ABS not in regulation"
XGF_NO_REGULATION_STRING = "no ABS regulation"

DID_SPEED_MESSAGE_XGF = 0x5D7
DID_SPEED_MESSAGE_XGD = 0x27C

did_inregulation_xgd = 0x354
did_inregulation_xgf = 0x242   #startbit - 7


DID_BRAKE_CANHS_RNr_03 = 0x29A
DID_BRAKE_CANHS_RNr_04 = 0x29C

#  "WheelSpeed_R_L"
#  "WheelSpeed_R_R"
#  "WheelSpeed_F_L"
#  "WheelSpeed_F_L"
