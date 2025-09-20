import os
import re
from pathlib import Path
from glob import glob

from tkinter import filedialog, Tk
from nptdms import TdmsFile

import time

#  from asammdf.blocks.mdf_v4 import MDF4
from asammdf.signal import Signal
from asammdf.mdf import MDF

class FileDealer():
    def __init__(self, path):
        self.filderpath = path
        self.items_to_dealwith = list()

    def remove_all_items(self):
        self.items_to_dealwith = list()

    def add_item(self, filename):
        #  print(f"{filename = }")
        self.items_to_dealwith.append(filename)

    def add_item_fullpath(self, filename):
        self.items_to_dealwith.append(os.path.join(self.filderpath, filename))

    def __str__(self):
        return (f"{self.items_to_dealwith = }")

    def list_files(self):
        # delete old
        #  for item in tree_view.get_children():
        #  tree_view.delete(item)
        self.remove_all_items()

        try:
            os.listdir(self.filderpath)
        except FileNotFoundError as e:
            self.filderpath = "./"
            print("No such path, using default")

        print(self.filderpath)
        for filename in os.listdir(self.filderpath):
            #  print(f"{filename = }")
            if os.path.isfile(os.path.join(self.filderpath, filename)):
                #  tree_view.insert("", "end", values=(filename,))
                _, ext = os.path.splitext(filename)
                #  print(filename)
                #  print(_)
                #  print(ext)
                #  print(ext)
                if ext.lower() == ".tdms":
                    self.add_item_fullpath(filename)


    def convertall(self):
        startpoint = time.perf_counter_ns()
        successfully_converted = 0
        for i, file in enumerate(self.items_to_dealwith):
            #  print(file)
            #  print(file[-5:])
            res = None
            res = self.convert_tdms_to_md4(file)
            if res:
                successfully_converted += 1

        if successfully_converted == i and i > 0:
            print("ALL OK")
        else:
            print(f"\nSuccess - {successfully_converted} from {i + 1} files")


        print(f"time taken: {((time.perf_counter_ns())/1000000) - startpoint} ms.")


    def convert_tdms_to_md4(self, filein):
        try:
            md4path = filein[:-4].replace("℃", "C") + "md4"
            with TdmsFile.read(filein) as tdms_file:
                #  print(type(tdms_file.groups()))
                for group in tdms_file.groups():

                    group_name = group.name
                    #  print(type(group))

                    #  print(f"{group_name = }")
                    listofsignals = []
                    timestampchannel = group["Time"]
                    for i, channel in enumerate(group.channels()):
                        #  print(f"{type(group.channels()) = }")
                        channel_name = channel.name
                        #  print(f"{channel_name = }")
                        #  Signal(samples=None, timestamps=None, unit='', name='', info=None, comment='')¶
                        listofsignals.append(Signal(samples=channel[:],timestamps=timestampchannel[:], name=channel_name))

                        # Access dictionary of properties:
                        properties = channel.properties
                        # Access numpy array of data for channel:
                        data = channel[:]
                        # Access a subset of data
                        #  if channel_name == 'ECU_Current':
                        if channel_name == 'Time':
                            data_subset = channel[:]
                            #  print(data_subset)
                            #  print(f"{type(data_subset) = }")
                            #  print(dir(channel))

                mdf_file = MDF(version='4.10')
                mdf_file.append(listofsignals, comment='created by asammdf v8.2.9')

                mdf_file.save(md4path)
                mdf_file.close()
                print("*", end="")
        except Exception as e:
            print(e)
            return False
        else:
            return True

def main():
    print("file run")

    #  fd = FileDealer("C:\\Users\\belousov\\Documents\\PyScripts\\test_tdms\\folder_with_files")
    #  fd.list_files()

    #  print(fd)


    #  fd.add_item_fullpath("C:\\Users\\belousov\\Documents\\PyScripts\\test_tdms\\endu_20250516\\20250516_1_23°C-(1)-(1)-Ignition cycle_0_50_0_1-20250516160156-1-23.0℃.tdms")

    files_processed = files_written = files_scipped = wrong_filenames = 0

    root = Tk()
    root.withdraw()
    PA = filedialog.askdirectory()
    fd = FileDealer(PA)
    fd.list_files()
    print(fd)

    #  result = [y for x in os.walk(PA) for y in glob(os.path.join(x[0], '*.blf'))]
    # result = [y for x in os.walk(PATH) for y in glob(os.path.join(x[0], '*.blf'))]

    files_written = 0

    fd.convertall()

if __name__ == "__main__":
    main()
