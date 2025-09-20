import os
from pathlib import Path
import can
from canlib import canlib, kvadblib, Frame
# from icecream import ic

from defs import *


class Blf_dealer():
    def __init__(self) -> None:
        self.f_speedzero = False
        self.dtc_is_on = False
        self.startbraking = None
        self.endbraking = False
        self.braking_active = False
        self.decode_prblm = {}
        self.breakings = []
        self.folder_path = None
        self.filename = None
        self.in_regulation_off_delay = None


        self.FLwss_speed = None
        self.FRwss_speed = None
        self.RLwss_speed = None
        self.RRwss_speed = None

    def forder_creator(self, ttmppath):
        newfolder = Path(ttmppath).stem
        self.filename = newfolder
        # ic(ttmppath)
        # ic(os.path.dirname(ttmppath))

        newpath = os.path.join(os.path.dirname(ttmppath), newfolder)
        self.folder_path = newpath
        if not os.path.exists(newpath):
            try:
                # не знаю, что значит 0o777, но по времени это 40 минут.
                os.mkdir(newpath, mode=0o777)   # 777 - все права.
                print(f"folder {newfolder} created in {newpath}")
                return 0
            except FileExistsError:
                print("exception happened")
                return 1
                # can't happen, because abore if statement.
            except Exception as e:
                print(e)
                return 1
        return 0

    def file_saver(self, ffile):
        # ic(self.breakings)
        file_num = 0
        for listitem in self.breakings:
            file_num += 1
            flag_initial = True
            with open(ffile, "rb") as rr:
                log_in = can.io.BLFReader(rr)
                log_in_iter = log_in.__iter__()
                object_count = log_in.object_count
                try:
                    current_file_name = f"{self.filename}_#0{file_num}.blf"
                    current_file_path = os.path.join(self.folder_path, current_file_name)
                    with open(current_file_path, "wb") as f_out:
                        log_out = can.io.BLFWriter(f_out)
                        i = 1
                        while i < object_count:
                            i += 1
                            aa = log_in_iter.__next__()

                            if aa.timestamp > (listitem[0] - TIME_BEFORE_BRAKING) and flag_initial:
                                log_out.on_message_received(log_in_iter.__next__())
                                #we are writing here
                            if aa.timestamp > (listitem[1] + TIME_AFTER_BRAKING):
                                flag_initial = False
                                log_out.stop()
                                break

                                #we are already stoped writing here
                except StopIteration:
                    pass
                    print("end of file")
        return file_num




    def brakings_report(self):
        print(f" change this ")


    def message_interpreter(self, db, frame):
        """ only one line and Exceptions """

        try:
            bmsg = db.interpret(frame)
        except kvadblib.KvdNoMessage:
            if frame.id in self.decode_prblm:
                self.decode_prblm[frame.id] += 1
            else:
                self.decode_prblm[frame.id] = 1
            return

        if not bmsg._message.dlc == bmsg._frame.dlc:
            if "dlc_mistake" in self.decode_prblm:
                self.decode_prblm["dlc_mistake"] += 1
            else:
                self.decode_prblm["dlc_mistake"] = 1
            return
        return bmsg


    def frameproceed(self, db, frame) -> None:

            if frame.id == DID_BRAKE_CANHS_RNr_03:
                bmsg = self.message_interpreter(db, frame)
                try:
                    for bsig in bmsg:
                        if bsig.name == "WheelSpeed_F_L":
                            self.FLwss_speed = bsig.value
                        if bsig.name == "WheelSpeed_F_R":
                            self.FRwss_speed = bsig.value
                except TypeError as e:
                    print(e)

            if frame.id == DID_BRAKE_CANHS_RNr_04:
                bmsg = self.message_interpreter(db, frame)
                try:
                    for bsig in bmsg:
                        if bsig.name == "WheelSpeed_R_L":
                            self.RLwss_speed = bsig.value
                        if bsig.name == "WheelSpeed_R_R":
                            self.RRwss_speed = bsig.value
                except TypeError as e:
                    print(e)

            if self.RRwss_speed and self.RLwss_speed and self.FRwss_speed and self.FLwss_speed:

                #  print(self.RRwss_speed)
                #  print(self.RLwss_speed)
                #  print(self.FRwss_speed)
                #  print(self.FLwss_speed)

                return True
            else:
                return None

    if __name__ == "__main__":
        Blf_dealer()
