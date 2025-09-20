
import re
import os
from pathlib import Path
from glob import glob

from tkinter import filedialog, Tk

import can
from canlib import canlib, kvadblib, Frame
# from icecream import ic
from dealer import Blf_dealer
from defs import *

from icecream import ic

def prepare_message(c_timestamp, list_of_vals):

    arr = []
    for val in list_of_vals:
        val = int(val / 0.02)

        arr.append(val  >> 8 & 0xFF)
        arr.append(val & 0xFF)
        #  arr.append(0xFE)
        #  arr.append(0x02)
    #  print(f"{arr = }")
    msg = can.Message(timestamp=c_timestamp,
                arbitration_id=0x003, is_extended_id=False,
                is_remote_frame=False, channel=0, data=arr)
    return msg


def proceed_file(ttmppath):

    filename = Path(ttmppath).stem   #no extension name
    print(f"{filename = }")
    new_file_name = f"processed_{filename}.blf"

    newpath = os.path.join(os.path.dirname(ttmppath), new_file_name)

    print(f"{newpath = }")
    #  current_file_name = f"_processd.blf"
    #  current_file_path = os.path.join(newfolder, current_file_name)

    #  print(f"{current_file_path = }")

    print("starting proceeding...")

    blf_dealer = Blf_dealer()

    db = kvadblib.Dbc(VESTA_DBC)     # беру dbc файл для весты (define)


    initial = True
    started_timestamp = 0
    with open(ttmppath, "rb") as rr:
        log_in = can.BLFReader(rr)
        log_in_iter = log_in.__iter__()
        object_count = log_in.object_count
        i = 0

        with open(newpath, "wb") as f_out:
            log_out = can.BLFWriter(f_out)
            #  log_out = can.io.generic.MessageWriter(f_out)
            i = 1

            last_timestamp = 0
            lastvalues = [0,0,0,0]

            print("started")
            try:
                for i in range(object_count):
                    aa = log_in_iter.__next__()
                    if initial:
                        started_timestamp = aa.timestamp
                        initial = False

                    frame = Frame(aa.arbitration_id, aa.data, timestamp=aa.timestamp)
                    res = blf_dealer.frameproceed(db, frame)
                    if res:
                        #  print(f"logging byte {i}")


                        arr = []

                        # добавляю хоть тчто-то. Идей нет.
                        coefficient = 48

                        currentvalues = [ blf_dealer.FLwss_speed,
                                         blf_dealer.FRwss_speed,
                                         blf_dealer.RLwss_speed,
                                         blf_dealer.RRwss_speed].copy()
                        ind = 0

                        timestampdiff =   aa.timestamp - last_timestamp
                        #  print(f"{timestampdiff = }")

                        debugval = timestampdiff
                        if timestampdiff < 0.100:
                            if (timestampdiff > 0.002):

                                #  количество неоходимых фреймов
                                qtt = int(timestampdiff // 0.001)
                                #  print("----")
                                #  print(f"{qtt = }")

                                for i in range(qtt):
                                    # подготавливаем новый message

                                    list_of_vals = [0, 0, 0, 0]
                                    timestamp_with_addition = last_timestamp + (i * (timestampdiff/qtt))
                                    for valu in range(4):
                                        list_of_vals[valu] = lastvalues[valu] + ((currentvalues[valu] - lastvalues[valu])/qtt)*i

                                    msg = prepare_message(timestamp_with_addition, list_of_vals)
                                    log_out.on_message_received(msg)
                                    #  print(f".f{i}, {timestamp_with_addition = }")
                        else:
                            print("#### NOT VALID")

                            print(f"{started_timestamp = }  ")
                            print(f"{aa.timestamp = }  ")

                            from_the_beginning = aa.timestamp - started_timestamp
                            print(f"{from_the_beginning = }")

                            print(debugval)
                            last_timestamp = aa.timestamp


                        last_timestamp = aa.timestamp
                        lastvalues = currentvalues.copy()
                        msg = prepare_message(aa.timestamp, currentvalues)

                        arr = []

                        blf_dealer.FLwss_speed = None
                        blf_dealer.FRwss_speed = None
                        blf_dealer.RLwss_speed = None
                        blf_dealer.RRwss_speed = None

                        ### logging here
                        log_out.on_message_received(msg)


                        i += 1
                        #  log_out.
                        pass

            except StopIteration:
                pass
                # print("end of file")
            finally:
                print("FINISHED")
                #  blf_dealer.brakings_report()

                log_out.stop()

                pass

    blf_dealer.forder_creator(ttmppath)
    return blf_dealer.file_saver(ttmppath)


def main():
    root = Tk()
    root.withdraw()

    PA = filedialog.askopenfilename()

    proceed_file(PA)


if __name__ == "__main__":
    main()
