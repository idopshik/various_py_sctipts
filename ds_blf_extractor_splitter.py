"""
Укажите параметры в шапке программы:

INPUT_BLF_FILE - путь к вашему BLF файлу

START_TIME и END_TIME - диапазон в секундах

Выберите режим вырезки (раскомментируйте нужную функцию)

Запустите программу - она создаст новый файл с префиксом part_of_
"""


import can
from pathlib import Path
import sys

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog
import os

# ========== НАСТРОЙКИ ==========
# Укажите здесь параметры для вырезки
INPUT_BLF_FILE = "C:\\Users\\belousov\\Documents\\PyScripts\\CanBLF\\logs\\bogo_log_fixed_timestamps.blf"
START_TIME = 1410.0  # начальное время в секундах
END_TIME = 1500.0    # конечное время в секундах
# ===============================




def get_time_interval():
    """
    Открывает модальное окно для ввода начального и конечного времени.
    Возвращает кортеж (start, end) при успешном вводе или None при отмене.
    """
    result = []  # Будет использоваться для передачи результата из внутренней функции

    def validate_and_return():
        nonlocal result

        # Получаем значения из полей ввода
        start_val = start_entry.get().strip()
        end_val = end_entry.get().strip()

        # Валидация: проверяем, что оба значения являются целыми числами
        try:
            start_int = int(start_val)
            end_int = int(end_val)
        except ValueError:
            messagebox.showerror("Ошибка ввода", "Пожалуйста, введите целые числа в оба поля.")
            return

        # Дополнительные проверки
        if end_int == 0:
            messagebox.showerror("Ошибка ввода", "Конечное время не может быть нулевым.")
            return

        if start_int == end_int:
            messagebox.showerror("Ошибка ввода", "Начальное и конечное время не могут быть равны.")
            return

        # Если все проверки пройдены, сохраняем результат и закрываем окно
        result.append((start_int, end_int))
        root.destroy()

    def on_cancel():
        nonlocal result
        result.append(None)
        root.destroy()

    def validate_numeric_input(action, value_if_allowed):
        # Функция для валидации ввода - разрешаем только цифры
        if action == '1':  # Вставка
            if value_if_allowed:
                return value_if_allowed.isdigit() or (value_if_allowed.startswith('-') and value_if_allowed[1:].isdigit())
            return False
        return True

    # Создаем модальное окно
    root = tk.Tk()
    root.title("Input start and end time [s]")
    root.resizable(False, False)

    # Устанавливаем большой шрифт
    big_font = ('Arial', 16)
    medium_font = ('Arial', 14)

    # Увеличиваем размер окна в 4 раза
    window_width = 600
    window_height = 300
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    # Делаем окно поверх всех остальных
    root.attributes('-topmost', True)
    root.focus_force()

    # Регистрируем функцию валидации
    vcmd = (root.register(validate_numeric_input), '%d', '%P')

    # Создаем и размещаем элементы интерфейса
    main_frame = ttk.Frame(root, padding="20")
    main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    # Поле для начального времени
    start_label = ttk.Label(main_frame, text="Start time [s]:", font=big_font)
    start_label.grid(row=0, column=0, sticky=tk.W, pady=15)

    start_entry = ttk.Entry(main_frame, validate="key", validatecommand=vcmd, font=big_font, width=15)
    start_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=15, padx=15)

    # Поле для конечного времени
    end_label = ttk.Label(main_frame, text="End time [s]:", font=big_font)
    end_label.grid(row=1, column=0, sticky=tk.W, pady=15)

    end_entry = ttk.Entry(main_frame, validate="key", validatecommand=vcmd, font=big_font, width=15)
    end_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=15, padx=15)

    # Кнопки
    button_frame = ttk.Frame(main_frame)
    button_frame.grid(row=2, column=0, columnspan=2, pady=30)

    ok_button = ttk.Button(button_frame, text="OK", command=validate_and_return, style="Big.TButton")
    ok_button.pack(side=tk.LEFT, padx=20)

    cancel_button = ttk.Button(button_frame, text="Cancel", command=on_cancel, style="Big.TButton")
    cancel_button.pack(side=tk.LEFT, padx=20)

    # Стиль для больших кнопок
    style = ttk.Style()
    style.configure("Big.TButton", font=medium_font, padding=(20, 10))

    # Настраиваем изменение размеров
    root.columnconfigure(0, weight=1)
    main_frame.columnconfigure(1, weight=1)

    # Устанавливаем фокус на первое поле ввода
    start_entry.focus()

    # Обработка закрытия окна через крестик
    root.protocol("WM_DELETE_WINDOW", on_cancel)

    # Запускаем обработчик событий
    root.mainloop()

    # Возвращаем результат
    return result[0] if result else None




def select_file(title):
    """Функция для выбора файла и возврата всех компонентов"""
    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(title=title)
    root.destroy()

    if not file_path:
        return None, None, None, None

    directory = os.path.dirname(file_path)
    filename_with_ext = os.path.basename(file_path)
    filename_no_ext = os.path.splitext(filename_with_ext)[0]
    extension = os.path.splitext(filename_with_ext)[1]

    return file_path, directory, filename_no_ext, extension

def extract_blf_segment_relative(input_path, start_time_rel, end_time_rel):
    """
    Вырезает отрезок по относительному времени (от начала файла)
    """
    input_path = Path(input_path)
    output_path = input_path.parent / f"part_of_{input_path.stem}_{start_time_rel}s_to_{end_time_rel}s.blf"

    print(f"Обрабатываем файл: {input_path}")
    print(f"Вырезаем отрезок: {start_time_rel} - {end_time_rel} секунд от начала файла")
    print(f"Выходной файл: {output_path}")

    try:
        with can.BLFReader(input_path) as reader:
            # Находим первое сообщение чтобы определить базовое время
            first_message = None
            for message in reader:
                first_message = message
                break

            if first_message is None:
                print("Файл пустой!")
                return False

            base_time = first_message.timestamp
            abs_start_time = base_time + start_time_rel
            abs_end_time = base_time + end_time_rel

            print(f"Базовое время файла: {base_time}")
            print(f"Абсолютное время начала: {abs_start_time}")
            print(f"Абсолютное время окончания: {abs_end_time}")
            print(f"len of interval: {abs_end_time - abs_start_time}")

            first_message_timestamp = -1

            # Переоткрываем reader для обработки
            messages_written = 0
            with can.BLFWriter(output_path) as writer:
                with can.BLFReader(input_path) as reader2:
                    for message in reader2:


                        # первоначально сохнаняем метку первого сообщения
                        if first_message_timestamp == -1:
                            first_message_timestamp = message.timestamp
                            #  print(f"type: {type(first_message_timestamp)}")
                            #  print(f"first_message_timestamp: {first_message_timestamp}")

                            #  abs_start_time = START_TIME + first_message_timestamp
                            #  abs_end_time = END_TIME + first_message_timestamp


                        if abs_start_time <= message.timestamp <= abs_end_time:
                            writer.on_message_received(message)
                            messages_written += 1
                        elif message.timestamp > abs_end_time:
                            break

                print(f"Сохранено сообщений: {messages_written}")

                if messages_written == 0:
                    print("ВНИМАНИЕ: Не найдено сообщений в указанном диапазоне!")
                    print("Возможные причины:")
                    print("1. Неправильный временной диапазон")
                    print("2. Файл использует абсолютное время (Unix timestamp)")
                    print("3. Указанное время выходит за пределы файла")

                    # Покажем реальный диапазон времени файла
                    show_file_time_range(input_path)

                return messages_written > 0

    except Exception as e:
        print(f"Ошибка при обработке файла: {e}")
        return False

def show_file_time_range(input_path):
    """
    Показывает реальный временной диапазон файла
    """
    print("\n=== АНАЛИЗ ФАЙЛА ===")

    try:
        with can.BLFReader(input_path) as reader:
            first_message = None
            last_message = None
            min_time = float('inf')
            max_time = float('-inf')
            message_count = 0

            for message in reader:
                if first_message is None:
                    first_message = message
                last_message = message
                min_time = min(min_time, message.timestamp)
                max_time = max(max_time, message.timestamp)
                message_count += 1

            if first_message is None:
                print("Файл пустой!")
                return

            duration = max_time - min_time

            print(f"Сообщений: {message_count}")
            print(f"Абсолютное время первого сообщения: {first_message.timestamp}")
            print(f"Абсолютное время последнего сообщения: {last_message.timestamp}")
            print(f"Минимальное время: {min_time}")
            print(f"Максимальное время: {max_time}")
            print(f"Длительность файла: {duration:.3f} секунд")

            # Определяем тип времени
            if first_message.timestamp > 1000000000:  # Unix timestamp (после 2001 года)
                print("Тип времени: АБСОЛЮТНОЕ (Unix timestamp)")
                print(f"Дата начала: {unix_time_to_human(first_message.timestamp)}")
                print(f"Дата окончания: {unix_time_to_human(last_message.timestamp)}")
            else:
                print("Тип времени: ОТНОСИТЕЛЬНОЕ")

            print(f"\nРекомендуемый диапазон для вырезки: 0 - {duration:.1f} секунд")

    except Exception as e:
        print(f"Ошибка при анализе файла: {e}")

def unix_time_to_human(timestamp):
    """
    Конвертирует Unix timestamp в читаемый формат
    """
    from datetime import datetime
    try:
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    except:
        return "Некорректное время"

def extract_with_absolute_time(input_path, abs_start_time, abs_end_time):
    """
    Вырезает отрезок по абсолютному времени
    """
    input_path = Path(input_path)
    output_path = input_path.parent / f"part_of_{input_path.stem}_abs_{abs_start_time}s_to_{abs_end_time}s.blf"

    print(f"Вырезаем по абсолютному времени: {abs_start_time} - {abs_end_time}")

    try:
        with can.BLFReader(input_path) as reader:
            messages_written = 0
            with can.BLFWriter(output_path) as writer:
                for message in reader:
                    if abs_start_time <= message.timestamp <= abs_end_time:
                        writer.on_message_received(message)
                        messages_written += 1
                    elif message.timestamp > abs_end_time:
                        break

                print(f"Сохранено сообщений: {messages_written}")
                return messages_written > 0

    except Exception as e:
        print(f"Ошибка: {e}")
        return False

# ========== АВТОМАТИЧЕСКИЙ РЕЖИМ ==========
def auto_extract(input_path, start_time_rel=10.0, end_time_rel=30.0):
    """
    Автоматически определяет тип времени и вырезает отрезок
    """
    print("=== АВТОМАТИЧЕСКАЯ ВЫРЕЗКА ===")

    # Сначала анализируем файл
    try:
        with can.BLFReader(input_path) as reader:
            first_message = None
            for message in reader:
                first_message = message
                break

            if first_message is None:
                print("Файл пустой!")
                return False

            # Определяем тип времени
            if first_message.timestamp > 1000000000:  # Вероятно Unix timestamp
                print("Обнаружено абсолютное время (Unix timestamp)")
                print(f"Первое сообщение: {first_message.timestamp}")
                print(f"Дата: {unix_time_to_human(first_message.timestamp)}")

                # Показываем диапазон и предлагаем ввести абсолютное время
                show_file_time_range(input_path)

                abs_start = float(input("Введите абсолютное время начала: "))
                abs_end = float(input("Введите абсолютное время окончания: "))

                return extract_with_absolute_time(input_path, abs_start, abs_end)
            else:
                print("Обнаружено относительное время")
                return extract_blf_segment_relative(input_path, start_time_rel, end_time_rel)

    except Exception as e:
        print(f"Ошибка: {e}")
        return False

def main():
    print("=== ВЫРЕЗКА ОТРЕЗКА BLF ФАЙЛА ===")


    path_to_blf, directory, name_no_ext, extension = select_file(" select BLF file")
    print(f"{path_to_blf = }")
    print("end of script")


    print("going to choose time")
    interval = get_time_interval()
    if not interval:
        print("canceled")
        return
    else:
        start_time, end_time = interval
        print(f"Результат: {interval}")


    # Вариант 1: Относительное время (по умолчанию)
    #  success = extract_blf_segment_relative(INPUT_BLF_FILE, START_TIME, END_TIME)
    #  show_file_time_range(path_to_blf)
    success = extract_blf_segment_relative(path_to_blf, start_time, end_time)


    # Вариант 2: Автоматическое определение
    # success = auto_extract(INPUT_BLF_FILE, START_TIME, END_TIME)
    #  success = auto_extract(path_to_blf, start_time, end_time)

    # Вариант 3: Абсолютное время (раскомментировать и указать значения)
    # ABS_START = 1337354164.123  # пример абсолютного времени
    # ABS_END = 1337354194.123
    # success = extract_with_absolute_time(INPUT_BLF_FILE, ABS_START, ABS_END)

    #  print("=== АНАЛИЗ ФАЙЛА ===")
    #  show_file_time_range(INPUT_BLF_FILE)

    if success:
        print("Операция завершена успешно!")
    else:
        print("Операция завершена с ошибками!")



if __name__ == "__main__":
    main()
