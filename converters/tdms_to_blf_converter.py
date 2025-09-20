"""
Конвертировать то конвертирует. Но DBC я так и не смог читаемую записать. Да и к blf всегда были вопросы к открытию.
Не факт, что она полная, и в режиме графика в векторе откроется. Поддержки нет полной в open source. Единственный надёжный способ - через
проприетарные конвертые перегонять blf->asc->blf
"""
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


import can
from can.io import BLFWriter
import numpy as np
from tqdm import tqdm

import cantools
from cantools.database import Database, Message, Signal
from cantools.database.conversion import LinearConversion
import hashlib




class TDMS_to_BLF_Converter:
    def __init__(self):
        self.can_db = Database()
        self.signal_info = {}  # Храним метаданные сигналов
        self.consistent_ids = {}  # Для одинаковых ID между файлами
        self.processed_files = []

        self.output_directory = None  # Будем хранить путь к папке с файлами

    def set_output_directory(self, file_path):
        """Устанавливает директорию для сохранения на основе первого файла"""
        if self.output_directory is None:
            self.output_directory = Path(file_path).parent

    def get_consistent_can_id(self, group_name, channel_name):
        """Генерирует одинаковый CAN ID для одинаковых имен"""
        key = f"{group_name}:{channel_name}"
        if key not in self.consistent_ids:
            hash_obj = hashlib.md5(key.encode())
            self.consistent_ids[key] = int(hash_obj.hexdigest()[:3], 16) & 0x7FF
        return self.consistent_ids[key]

    def extract_signal_metadata(self, data, channel):
        if len(data) == 0:
            return {'unit': ''}

        return {
            'min': float(np.min(data)),
            'max': float(np.max(data)),
            'unit': channel.properties.get('unit', '')
        }

    def add_signal_to_dbc(self, group_name, channel_name, can_id, signal_meta):
        signal_key = f"{can_id}_{channel_name}"

        if signal_key not in self.signal_info:
            try:
                # Пробуем разные варианты создания conversion
                from cantools.database.conversion import LinearConversion

                # Вариант 1: Без minimum/maximum
                conversion = LinearConversion(scale=1, offset=0)

                # Пробуем установить атрибуты если они есть
                if hasattr(conversion, 'minimum'):
                    conversion.minimum = signal_meta.get('min')
                if hasattr(conversion, 'maximum'):
                    conversion.maximum = signal_meta.get('max')
                if hasattr(conversion, 'unit'):
                    conversion.unit = signal_meta.get('unit', '')

            except Exception as e:
                print(f"Ошибка создания conversion: {e}")
                conversion = None

            # Создаем сигнал
            signal = Signal(
                name=channel_name,
                start=0,
                length=32,
                byte_order='little_endian',
                is_signed=True,
                conversion=conversion,
                minimum=signal_meta.get('min'),
                maximum=signal_meta.get('max'),
                unit=signal_meta.get('unit', ''),
                comment=f"From group: {group_name}"
            )

            # Создаем сообщение
            message_exists = False
            for msg in self.can_db.messages:
                if msg.frame_id == can_id:
                    msg.signals.append(signal)
                    message_exists = True
                    break

            if not message_exists:
                message = Message(
                    frame_id=can_id,
                    name=f"MSG_{can_id}_{group_name}",
                    length=8,
                    signals=[signal]
                )
                self.can_db.messages.append(message)

            self.signal_info[signal_key] = signal_meta




    def convert_tdms_to_blf(self, filein, DEBUG=False):
        """Конвертирует TDMS в BLF и собирает метаданные для DBC"""
        try:
            file_path = Path(filein)
            base_name = file_path.stem.replace("℃", "C")


            # Устанавливаем директорию для сохранения на основе первого файла
            self.set_output_directory(filein)


            blf_path = str(file_path.with_name(f"{base_name}.blf"))

            if DEBUG:
                print(f"Конвертация: {file_path.name}")

            with TdmsFile.read(filein) as tdms_file, BLFWriter(blf_path) as blf_writer:
                total_messages = 0

                pbar = tqdm(desc=f"Обработка {file_path.name}", unit="msg", disable=not DEBUG)

                for group in tdms_file.groups():
                    # Ищем timestamp канал
                    timestamp_channel = None
                    for channel in group.channels():
                        if channel.name.lower() in ['time', 'timestamp', 't']:
                            timestamp_channel = channel
                            break

                    if not timestamp_channel:
                        continue

                    timestamps = timestamp_channel[:]

                    for channel in group.channels():
                        if channel is timestamp_channel:
                            continue

                        channel_name = channel.name
                        data = channel[:]

                        # Генерируем консистентный CAN ID
                        can_id = self.get_consistent_can_id(group.name, channel_name)

                        # Извлекаем метаданные для DBC
                        signal_meta = self.extract_signal_metadata(data, channel)

                        # Добавляем сигнал в DBC
                        self.add_signal_to_dbc(group.name, channel_name, can_id, signal_meta)

                        # Конвертируем и записываем данные
                        for ts, val in zip(timestamps, data):
                            try:
                                value_bytes = np.float32(val).tobytes()
                            except:
                                value_bytes = b'\x00\x00\x00\x00'

                            msg = can.Message(
                                arbitration_id=can_id,
                                data=value_bytes.ljust(8, b'\x00'),
                                timestamp=float(ts),
                                is_extended_id=False
                            )
                            blf_writer.on_message_received(msg)
                            total_messages += 1
                            pbar.update(1)

                pbar.close()
                self.processed_files.append(file_path.name)

                if DEBUG:
                    print(f"✓ Создан: {Path(blf_path).name}")
                    print(f"  Сообщений: {total_messages}")

                return True, total_messages

        except Exception as e:
            if DEBUG:
                print(f"✗ Ошибка: {e}")
            return False, 0

    def save_dbc_file(self, dbc_name="converted_signals.dbc"):
        """Сохраняет собранный DBC файл в директории с конвертированными файлами"""
        if self.output_directory is None:
            print("✗ Не задана директория для сохранения!")
            return False

        try:
            dbc_path = self.output_directory / dbc_name
            with open(dbc_path, 'w', encoding='utf-8') as f:
                f.write(self.can_db.as_dbc_string())
            print(f"✓ DBC файл сохранен: {dbc_path}")
            print(f"  Обработано файлов: {len(self.processed_files)}")
            print(f"  Сигналов в DBC: {len(self.signal_info)}")
            return True
        except Exception as e:
            print(f"✗ Ошибка сохранения DBC: {e}")
            return False

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

        #  print(self.filderpath)
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

        converter = TDMS_to_BLF_Converter()

        for i, file in enumerate(self.items_to_dealwith):
            #  print(file)
            #  print(file[-5:])
            res = None

            #  print(f"{file = }")
            #  return

            #  res = self.convert_tdms_to_blf_optimized(file)

            success, count = converter.convert_tdms_to_blf(file, DEBUG=True)

            if success:
                successfully_converted += 1

        if successfully_converted == i and i > 0:
            print("ALL OK")
            try:
                converter.save_dbc_file("auto_generated.dbc")
            except Exception:
                print(e)
            else:
                print("dbc successfully saved!")
        else:
            print(f"\nSuccess - {successfully_converted} from {i + 1} files")


        print(f"time taken: {((time.perf_counter_ns())/1000000) - startpoint} ms.")



    def convert_tdms_to_blf_optimized(self, filein, DEBUG=False):
        """
        Оптимизированная версия конвертации TDMS → BLF
        """
        try:
            # Формирование абсолютного пути
            file_path = Path(filein)
            base_name = file_path.stem.replace("℃", "C")
            blf_path = str(file_path.with_name(f"{base_name}.blf"))

            if DEBUG:
                print(f"Начало конвертации: {file_path.name} -> {Path(blf_path).name}")

            with TdmsFile.read(filein) as tdms_file, BLFWriter(blf_path) as blf_writer:
                total_messages = 0

                for group in tdms_file.groups():
                    if DEBUG:
                        print(f"  Обработка группы: {group.name}")

                    # Находим timestamp канал
                    timestamp_channel = None
                    for channel in group.channels():
                        if channel.name.lower() in ['time', 'timestamp', 't']:
                            timestamp_channel = channel
                            break

                    if not timestamp_channel:
                        if DEBUG:
                            print(f"    ⚠ Нет timestamp канала в {group.name}")
                        continue

                    timestamps = timestamp_channel[:]

                    # Обрабатываем данные каналов с прогрессбаром
                    channels_list = [ch for ch in group.channels() if ch is not timestamp_channel]

                    for channel in tqdm(channels_list, desc=f"Группа '{group.name}'", disable=False):
                        if channel is timestamp_channel:
                            continue

                        channel_name = channel.name
                        data = channel[:]

                        # Создаем CAN ID на основе хэша имени канала
                        can_id = hash(f"{group.name}:{channel_name}") & 0x7FF

                        # Создаем сообщения пачками
                        messages = []
                        for i, (ts, val) in enumerate(zip(timestamps, data)):
                            # Конвертируем значение в bytes
                            try:
                                if isinstance(val, float):
                                    data_bytes = np.float32(val).tobytes()
                                elif isinstance(val, int):
                                    data_bytes = val.to_bytes(4, byteorder='little')
                                else:
                                    data_bytes = bytes(str(val)[:8], 'utf-8').ljust(8, b'\x00')
                            except:
                                data_bytes = b'\x00\x00\x00\x00'

                            msg = can.Message(
                                arbitration_id=can_id,
                                data=data_bytes,
                                timestamp=float(ts),
                                is_extended_id=False,
                                channel=0
                            )
                            messages.append(msg)

                        # Пакетная запись
                        for msg in messages:
                            blf_writer.on_message_received(msg)

                        total_messages += len(messages)

                        if DEBUG:
                            print(f"    {channel_name}: {len(messages)} сообщений")

                if DEBUG:
                    print(f"✓ Файл сохранен: {blf_path}")
                    print(f"  Всего сообщений: {total_messages}")

                return True, total_messages

        except Exception as e:
            if DEBUG:
                print(f"✗ Ошибка при конвертации {filein}: {e}")
                import traceback
                traceback.print_exc()
            return False, 0




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
    #  print(fd)

    #  result = [y for x in os.walk(PA) for y in glob(os.path.join(x[0], '*.blf'))]
    # result = [y for x in os.walk(PATH) for y in glob(os.path.join(x[0], '*.blf'))]

    files_written = 0

    fd.convertall()

if __name__ == "__main__":
    main()
