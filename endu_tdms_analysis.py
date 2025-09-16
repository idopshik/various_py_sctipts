import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import configparser
import os
import threading
import time
import pandas as pd
from nptdms import TdmsFile
import numpy as np

import matplotlib
matplotlib.use('TkAgg')  # Явно указываем Tkinter бэкенд
import matplotlib.pyplot as plt

import glob
import tempfile

import webbrowser
import plotly.graph_objects as go


CURRENT_SCALE = 60








class GuiDataChooser:
    def __init__(self, root):
        # Инициализация главного окна
        self.root = root
        self.root.title("TDMS Converter - Выбор данных")
        self.root.geometry("800x600")

        # Установка иконки приложения
        try:
            # Для Windows
            self.root.iconbitmap("endu_tdms_app.ico")
        except:
            try:
                # Для Linux (нужно преобразовать в PNG и использовать iconphoto)
                icon = tk.PhotoImage(file="app.png")
                self.root.iconphoto(False, icon)
            except:
                print("Не удалось загрузить иконку приложения")

        # Создаем объект стиля
        self.style = ttk.Style()
        # Пробуем установить тему (на некоторых системах может не быть 'clam')
        try:
            self.style.theme_use('clam')
        except:
            pass

        # Настраиваем цвета и шрифты через стиль
        self.style.configure('.', font=('Helvetica', 16))
        self.style.configure('TFrame', background='#f0f8f0')  # Слабо-зеленоватый
        self.style.configure('TLabel', background='#f0f8f0')
        self.style.configure('TButton', background='#e0f0e0')
        self.style.configure('TEntry', fieldbackground='#ffffff')

        # Основной фрейм для размещения элементов
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Конфигурация веса строк и колонок для растягивания
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)  # Колонка с Entry будет растягиваться
        main_frame.rowconfigure(1, weight=1)     # Строка со списком файлов будет растягиваться

        # Переменная для хранения пути к папке
        self.folder_path = tk.StringVar()
        self.processor = None
        self.processing_thread = None
        self.stop_processing = False
        self.selected_file = tk.StringVar()  # Для хранения выбранного файла (радио-кнопки)
        self.file_radios = {}  # Словарь для хранения радио-кнопок файлов

        # Метка для пути
        ttk.Label(main_frame, text="Папка с данными:").grid(row=0, column=0, sticky=tk.W, pady=(0, 10))

        # Поле Entry для отображения и ввода пути
        path_entry = ttk.Entry(main_frame, textvariable=self.folder_path, width=50)
        path_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(5, 0), pady=(0, 10))

        # Кнопка "Open Folder"
        self.open_btn = ttk.Button(main_frame, text="Open Folder", command=self.open_folder)
        self.open_btn.grid(row=0, column=2, sticky=tk.W, padx=(5, 0), pady=(0, 10))

        # Фрейм для списка файлов с радио-кнопками
        self.file_frame = ttk.Frame(main_frame)
        self.file_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        # Canvas и Scrollbar для прокрутки списка файлов
        self.canvas = tk.Canvas(self.file_frame, bg='white')
        self.scrollbar = ttk.Scrollbar(self.file_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Фрейм для кнопок Process, Check File, DoInteractive и Cancel
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=3, pady=(10, 5), sticky=(tk.W, tk.E))

        # Кнопка Check File (слева)
        self.check_file_btn = ttk.Button(button_frame, text="Check File",
                                       command=self.check_selected_file,
                                       state=tk.DISABLED)
        self.check_file_btn.pack(side=tk.LEFT, padx=(0, 5))

        # Кнопка DoInteractive (справа от Check File)
        self.do_interactive_btn = ttk.Button(button_frame, text="Interactive",
                                           command=self.do_interactive,
                                           state=tk.DISABLED)
        self.do_interactive_btn.pack(side=tk.LEFT, padx=(5, 0))

        # Кнопка Cancel (справа)
        self.cancel_btn = ttk.Button(button_frame, text="Cancel",
                                   command=self.cancel_processing,
                                   state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))

        # Кнопка Process (справа)
        self.process_btn = ttk.Button(button_frame, text="Process",
                                    command=self.start_processing)
        self.process_btn.pack(side=tk.RIGHT)

        # Прогрессбар
        self.progress_bar = ttk.Progressbar(main_frame, mode='determinate', maximum=100)
        self.progress_bar.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 0))
        self.hide_progress_bar()  # Скрываем прогрессбар initially

        # Загружаем последний использованный путь из .ini файла
        self.load_initial_path()


        self.shutdown_event = threading.Event()

    def open_folder(self):
        """Метод для открытия диалога выбора папки и обработки результата"""
        selected_folder = filedialog.askdirectory(title="Выберите папку с TDMS файлами")
        if selected_folder:  # Если папка выбрана (не нажали 'Cancel')
            self.folder_path.set(selected_folder)
            self.save_path_to_ini(selected_folder)
            self.update_file_list(selected_folder)
            self.hide_progress_bar()  # Скрываем прогрессбар при смене папки

    def update_file_list(self, folder_path):
        """Метод для обновления списка файлов с радио-кнопками"""
        # Очищаем текущий список
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.file_radios.clear()
        self.selected_file.set("")  # Сбрасываем выбор

        try:
            # Получаем список файлов в папке
            files = os.listdir(folder_path)
            # Фильтруем, чтобы показать только файлы (не папки)
            files = [f for f in files if os.path.isfile(os.path.join(folder_path, f))]

            # Сортируем файлы для удобства
            files.sort()

            if not files:
                label = ttk.Label(self.scrollable_frame, text="Папка пуста.")
                label.pack(pady=5)
            else:
                # Создаем радио-кнопки для каждого файла
                for file in files:
                    self.create_file_radio(file)

                # Биндим изменение состояния
                self.update_check_file_button_state()

        except PermissionError:
            label = ttk.Label(self.scrollable_frame, text="Ошибка: Нет доступа к папке.")
            label.pack(pady=5)
        except FileNotFoundError:
            label = ttk.Label(self.scrollable_frame, text="Ошибка: Папка не найдена.")
            label.pack(pady=5)
        except Exception as e:
            label = ttk.Label(self.scrollable_frame, text=f"Произошла ошибка: {e}")
            label.pack(pady=5)

    def create_file_radio(self, filename):
        """Создает радио-кнопку для файла"""
        # Фрейм для радио и метки
        frame = ttk.Frame(self.scrollable_frame)
        frame.pack(fill=tk.X, padx=5, pady=2)

        # Радио-кнопка
        radio = ttk.Radiobutton(frame, variable=self.selected_file, value=filename,
                                command=self.update_check_file_button_state)
        radio.pack(side=tk.LEFT)

        # Метка с именем файла
        label = ttk.Label(frame, text=filename, font=('Courier New', 12))
        label.pack(side=tk.LEFT, padx=(5, 0))

        # Сохраняем в словарь
        self.file_radios[filename] = {
            'radio': radio,
            'label': label,
            'frame': frame
        }

    def update_check_file_button_state(self):
        """Обновляет состояние кнопок Check File и DoInteractive в зависимости от выбора"""
        if self.selected_file.get():
            self.check_file_btn.config(state=tk.NORMAL)
            self.do_interactive_btn.config(state=tk.NORMAL)
        else:
            self.check_file_btn.config(state=tk.DISABLED)
            self.do_interactive_btn.config(state=tk.DISABLED)

    def get_selected_file(self):
        """Возвращает путь к выбранному файлу"""
        selected = self.selected_file.get()
        if selected:
            folder = self.folder_path.get()
            return os.path.join(folder, selected)
        return None

    def check_selected_file(self):
        """Запускает проверку выбранного файла"""
        selected_file = self.get_selected_file()
        if not selected_file:
            return

        # Меняем состояние кнопок
        self.check_file_btn.config(state=tk.DISABLED)
        self.do_interactive_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)

        # Показываем прогрессбар
        self.show_progress_bar()

        # Создаем экземпляр обработчика
        self.processor = Endurance_tdms_logs_dealer(self.folder_path.get())
        self.stop_processing = False

        # Запускаем проверку в отдельном потоке
        self.processing_thread = threading.Thread(
            target=self.check_file_thread,
            args=(selected_file,)
        )
        self.processing_thread.daemon = True
        self.processing_thread.start()

        # Запускаем проверку завершения потока
        self.check_thread_completion()

    def check_file_thread(self, file_path):
        """Метод, который выполняется в отдельном потоке для проверки файла"""
        try:
            self.processor.check_file(file_path, self)
        except Exception as e:
            print(f"Ошибка при проверке файла: {e}")



    def do_interactive(self):
        """Открывает интерактивный график в браузере для выбранного файла"""
        selected_file = self.get_selected_file()
        if not selected_file:
            return

        # Меняем состояние кнопок
        self.do_interactive_btn.config(state=tk.DISABLED)
        self.check_file_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)

        # Показываем прогрессбар
        self.show_progress_bar()

        # Создаем экземпляр обработчика
        self.processor = Endurance_tdms_logs_dealer(self.folder_path.get())
        self.processor.gui_instance = self  # Передаём ссылку на GUI
        self.stop_processing = False

        # Запускаем интерактив в отдельном потоке
        self.processing_thread = threading.Thread(
            target=self.interactive_thread,
            args=(selected_file,)
        )
        self.processing_thread.daemon = True
        self.processing_thread.start()

        # Запускаем проверку завершения потока
        self.check_thread_completion()


    def interactive_thread(self, file_path):
        """Метод для создания интерактивного графика в потоке"""
        try:
            self.processor.create_interactive_plot(file_path)
        except Exception as e:
            print(f"Ошибка при создании интерактивного графика: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Завершаем в главном потоке с проверкой
            try:
                if self.root and self.root.winfo_exists():
                    self.root.after(0, self.processing_finished)
                else:
                    self.processing_finished()
            except:
                self.processing_finished()

    def save_path_to_ini(self, path):
        """Сохраняет путь в файл конфигурации endu_tpms_analysis_settings.ini"""
        config = configparser.ConfigParser()
        config['DEFAULT'] = {'LastFolderPath': path}

        with open('endu_tpms_analysis_settings.ini', 'w') as configfile:
            config.write(configfile)

    def load_initial_path(self):
        """Загружает последний использованный путь из endu_tpms_analysis_settings.ini при запуске"""
        config = configparser.ConfigParser()
        # Значение по умолчанию, если файла нет
        config['DEFAULT'] = {'LastFolderPath': ''}

        try:
            config.read('endu_tpms_analysis_settings.ini')
            last_path = config['DEFAULT'].get('LastFolderPath', '')
            if last_path and os.path.isdir(last_path):
                self.folder_path.set(last_path)
                self.update_file_list(last_path)
        except Exception as e:
            print(f"Ошибка при загрузке конфигурации: {e}")

    def show_progress_bar(self):
        """Показывает прогрессбар и запускает анимацию"""
        self.progress_bar.grid()  # Показываем прогрессбар

    def hide_progress_bar(self):
        """Скрывает прогрессбар и останавливает анимацию"""
        self.progress_bar.grid_remove()  # Скрываем прогрессбар

    def start_processing(self):
        """Запускает процесс обработки в отдельном потоке"""
        folder = self.folder_path.get()
        if not folder or not os.path.isdir(folder):
            return

        # Меняем состояние кнопок
        self.process_btn.config(state=tk.DISABLED)
        self.check_file_btn.config(state=tk.DISABLED)
        self.do_interactive_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)

        # Показываем прогрессбар
        self.show_progress_bar()
        self.progress_bar['value'] = 0

        # Создаем экземпляр обработчика
        self.processor = Endurance_tdms_logs_dealer(folder)
        self.stop_processing = False

        # Запускаем обработку в отдельном потоке
        self.processing_thread = threading.Thread(target=self.process_thread)
        self.processing_thread.daemon = True
        self.processing_thread.start()

        # Запускаем проверку завершения потока
        self.check_thread_completion()

    def process_thread(self):
        """Метод, который выполняется в отдельном потоке"""
        try:
            self.processor.process(self)
        except Exception as e:
            print(f"Ошибка при обработке: {e}")

    def update_progress(self, current, total):
        """Обновляет значение прогрессбара"""
        progress = (current / total) * 100
        self.progress_bar['value'] = progress
        self.root.update_idletasks()

    def check_thread_completion(self):
        """Проверяет завершение потока обработки"""
        if self.processing_thread.is_alive():
            # Если поток еще работает, проверяем снова через 100мс
            self.root.after(100, self.check_thread_completion)
        else:
            # Если поток завершился, обновляем UI
            self.processing_finished()

    def processing_finished(self):
        """Вызывается при завершении обработки"""
        self.hide_progress_bar()
        self.process_btn.config(state=tk.NORMAL)
        self.check_file_btn.config(state=tk.NORMAL)
        self.do_interactive_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.processor = None
        self.update_check_file_button_state()


    def cancel_processing(self):
        """Останавливает процесс обработки"""
        self.stop_processing = True
        self.shutdown_event.set()  # Сигнал всем потокам о завершении
        if self.processor:
            self.processor.cancel()
        self.processing_thread = None
        self.root.after(0, self.processing_finished)








class Endurance_tdms_logs_dealer:
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self._cancel = False

    def __del__(self):
        """Очистка ресурсов при удалении объекта"""
        try:
            plt.close('all')  # Закрываем все фигуры matplotlib
        except:
            pass

    def process(self, gui_instance):
        """Основной метод обработки - обход всех TDMS файлов в папке"""
        print(f"Начата обработка папки: {self.folder_path}")

        # Поиск всех файлов с расширением .tdms в указанной папке
        tdms_files = glob.glob(os.path.join(self.folder_path, "*.tdms"))

        if not tdms_files:
            print("TDMS файлы не найдены в указанной папке")
            return

        total_files = len(tdms_files)
        print(f"Найдено {total_files} TDMS файлов для обработки")

        # Создание временной директории
        temp_dir = tempfile.mkdtemp()
        print(f"Временная директория создана: {temp_dir}")

        # Создание HTML файла
        html_path = os.path.join(temp_dir, 'results.html')
        with open(html_path, 'w', encoding='utf-8') as html_file:
            html_file.write('<html><head><title>TDMS Graphs</title></head><body>\n')

        # Обработка каждого файла
        for i, tdms_file in enumerate(tdms_files, 1):
            if gui_instance.stop_processing or self._cancel:
                print("Обработка прервана пользователем")
                # Закрытие HTML
                with open(html_path, 'a', encoding='utf-8') as html_file:
                    html_file.write('</body></html>')
                return

            print(f"Обработка файла {i}/{total_files}: {os.path.basename(tdms_file)}")

            try:
                # Вызов метода обработки для каждого TDMS файла
                plot_path = self.endu_tdms_log_handler(tdms_file, gui_instance, temp_dir)
                if plot_path:
                    # Добавление в HTML
                    rel_plot_path = os.path.basename(plot_path)
                    filename = os.path.basename(tdms_file)
                    with open(html_path, 'a', encoding='utf-8') as html_file:
                        html_file.write(f'<h2>{filename}</h2>\n')
                        html_file.write(f'<img src="{rel_plot_path}" alt="Graph for {filename}">\n')
                        html_file.write('<br><br><br>\n')
                print(f"Файл {os.path.basename(tdms_file)} успешно обработан")

            except Exception as e:
                print(f"Ошибка при обработке файла {tdms_file}: {e}")

            # Обновляем прогресс
            gui_instance.root.after(0, gui_instance.update_progress, i, total_files)

            time.sleep(0.5)

        # Закрытие HTML
        with open(html_path, 'a', encoding='utf-8') as html_file:
            html_file.write('</body></html>')

        print(f"Обработка всех TDMS файлов завершена успешно")
        print(f"HTML отчет доступен по пути: {html_path}")

        self.open_html_file(html_path)



    def check_file(self, file_path, gui_instance):
        """
        Детальная проверка отдельного TDMS файла с расчетом энергии
        """
        print(f"Детальная проверка файла: {file_path}")

        try:
            # Загрузка файла
            tdms_file = TdmsFile.read(file_path)
            df = tdms_file.as_dataframe()

            # Поиск временной колонки
            time_cols = [col for col in df.columns if 'time' in col.lower()]
            time_col = time_cols[0] if time_cols else None

            if not time_col:
                print("Временная колонка не найдена!")
                return False

            # Поиск колонок с Motor Current и ECU Current
            motor_current_cols = [col for col in df.columns if 'motor current' in col.lower()]
            ecu_current_cols = [col for col in df.columns if 'ecu current' in col.lower()]

            if not motor_current_cols and not ecu_current_cols:
                print("Колонки Motor Current и ECU Current не найдены!")
                return False

            # Поиск колонки с напряжением
            voltage_cols = [col for col in df.columns if 'voltage' in col.lower() and 'current' not in col.lower()]
            if voltage_cols:
                # Берем среднее значение напряжения
                voltage = df[voltage_cols[0]].mean()
                print(f"Напряжение из данных: {voltage:.2f} V")
            else:
                # Напряжение по умолчанию, если не найдено
                voltage = 12.0
                print("Колонка напряжения не найдена, используется 12.0 V по умолчанию")

            # Упрощаем названия колонок для отображения
            energy_results = {}
            plot_data = {}  # Сохраняем данные для графиков

            # Обрабатываем Motor Current
            if motor_current_cols:
                for current_col in motor_current_cols:
                    energy_joules, time_data, current_data, power_data, cumulative_energy = self.calculate_energy_joules(df, time_col, current_col, voltage)
                    # Используем упрощенное имя
                    energy_results["Motor Current"] = energy_joules
                    plot_data[f"Motor_{current_col}"] = (time_data, current_data, power_data, cumulative_energy)
                    print(f"Затраченная энергия для Motor Current: {energy_joules:,.4f} Дж")

            # Обрабатываем ECU Current
            if ecu_current_cols:
                for current_col in ecu_current_cols:
                    energy_joules, time_data, current_data, power_data, cumulative_energy = self.calculate_energy_joules(df, time_col, current_col, voltage)
                    # Используем упрощенное имя
                    energy_results["ECU Current"] = energy_joules
                    plot_data[f"ECU_{current_col}"] = (time_data, current_data, power_data, cumulative_energy)
                    print(f"Затраченная энергия для ECU Current: {energy_joules:,.4f} Дж")

            # Сохраняем данные
            self.plot_data = plot_data
            self.energy_results = energy_results
            self.current_file_name = os.path.basename(file_path)
            self.df = df
            self.time_col = time_col
            self.voltage = voltage  # Сохраняем напряжение для использования в графиках

            # Запускаем построение графиков
            gui_instance.root.after(100, self.create_plots_in_main_thread)

            print(f"Проверка файла завершена")
            return True

        except Exception as e:
            error_msg = f"Ошибка при проверке файла {file_path}: {e}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            return False




    def create_plots_in_main_thread(self):
        """Создает графики в главном потоке"""
        try:
            if not hasattr(self, 'plot_data') or not self.plot_data:
                return

            # Создаем график с новым layout
            fig = plt.figure(figsize=(16, 10))
            gs = fig.add_gridspec(2, 2, width_ratios=[3, 1], height_ratios=[1, 1])

            ax1 = fig.add_subplot(gs[0, 0])  # Токи
            ax2 = fig.add_subplot(gs[1, 0])  # Накопленная энергия
            ax_table = fig.add_subplot(gs[:, 1])  # Таблица на всю высоту справа

            fig.suptitle(f'Energy Analysis: {self.current_file_name}', fontsize=16, fontweight='bold')

            # Строим графики токов с упрощенными названиями
            current_cols = []  # Собираем оригинальные имена колонок токов
            energy_values = {}  # Сохраняем значения энергии для таблички
            current_data_dict = {}  # Сохраняем данные токов для статистики
            time_data_dict = {}  # Сохраняем временные данные

            for key, (time_data, current_data, power_data, cumulative_energy) in self.plot_data.items():
                if key.startswith('Motor_'):
                    col_name = key.replace('Motor_', '')
                    simple_name = 'Motor Current'
                    ax1.plot(time_data, current_data, label=simple_name, linewidth=2, color='red')
                    current_cols.append(col_name)
                    energy_values['Motor'] = self.energy_results.get("Motor Current", 0)
                    current_data_dict['Motor'] = current_data
                    time_data_dict['Motor'] = time_data

                elif key.startswith('ECU_'):
                    col_name = key.replace('ECU_', '')
                    simple_name = 'ECU Current'
                    ax1.plot(time_data, current_data, label=simple_name, linewidth=2, linestyle='--', color='blue')
                    current_cols.append(col_name)
                    energy_values['ECU'] = self.energy_results.get("ECU Current", 0)
                    current_data_dict['ECU'] = current_data
                    time_data_dict['ECU'] = time_data

            # Настройка первого графика (токи)
            ax1.set_xlabel('Time (s)')
            ax1.set_ylabel('Current (A)')
            ax1.set_title('Current Signals')
            ax1.set_ylim(0, CURRENT_SCALE)
            ax1.legend()
            ax1.grid(True, alpha=0.3)

            # Строим графики накопленной энергии
            for key, (time_data, current_data, power_data, cumulative_energy) in self.plot_data.items():
                if key.startswith('Motor_'):
                    ax2.plot(time_data, cumulative_energy, label='Cum. Energy Motor', color='red', linewidth=2)
                elif key.startswith('ECU_'):
                    ax2.plot(time_data, cumulative_energy, label='Cum. Energy ECU', color='blue', linewidth=2, linestyle='--')

            ax2.set_xlabel('Time (s)')
            ax2.set_ylabel('Cumulative Energy (J)')
            ax2.set_title('Cumulative Energy Consumption')
            ax2.legend()
            ax2.grid(True, alpha=0.3)

            # Добавляем информационную табличку справа внизу (поднимем выше)
            if energy_values:
                motor_energy = energy_values.get('Motor', 0)
                ecu_energy = energy_values.get('ECU', 0)

                textstr = f'Motor: {motor_energy:,.4f} J\nECU: {ecu_energy:,.4f} J'

                props = dict(boxstyle='round', facecolor='white', alpha=0.8)
                ax1.text(0.98, 0.10, textstr, transform=ax1.transAxes, fontsize=10,
                        verticalalignment='bottom', horizontalalignment='right',
                        bbox=props, family='monospace')

            # Добавляем вторую табличку слева внизу с анализом активного времени
            if time_data_dict and current_data_dict:
                active_stats = self.calculate_active_stats(time_data_dict, current_data_dict)
                if active_stats:
                    self.add_active_time_table(ax1, active_stats)

            # Полная таблица справа с током и энергией
            self.add_complete_info_table(ax_table, energy_values, current_data_dict)

            plt.tight_layout(rect=[0, 0, 1, 0.96])
            plt.show()

            # Очищаем данные после построения
            delattr(self, 'plot_data')
            delattr(self, 'energy_results')
            delattr(self, 'current_file_name')
            delattr(self, 'df')
            delattr(self, 'time_col')

        except Exception as e:
            print(f"Ошибка при построении графиков: {e}")
            import traceback
            traceback.print_exc()

    def calculate_active_stats(self, time_data_dict, current_data_dict, threshold=0.3):
        """
        Рассчитывает статистику активного времени (ток > 300mA)
        """
        active_stats = {}

        for signal_type in ['Motor', 'ECU']:
            if signal_type in time_data_dict and signal_type in current_data_dict:
                time_data = time_data_dict[signal_type]
                current_data = current_data_dict[signal_type]

                # Находим активные участки (ток > 300mA)
                active_mask = current_data > threshold

                if not np.any(active_mask):
                    # Нет активных участков
                    active_stats[signal_type] = {
                        'has_activity': False,
                        'active_time': 0.0,
                        'avg_current_active': 0.0,
                        'max_current_active': 0.0
                    }
                    continue

                # Находим начало и конец активного периода
                active_indices = np.where(active_mask)[0]
                start_idx = active_indices[0]
                end_idx = active_indices[-1]

                # Время активного периода
                active_time = time_data[end_idx] - time_data[start_idx]

                # Ток только в активном периоде
                active_currents = current_data[start_idx:end_idx+1]

                active_stats[signal_type] = {
                    'has_activity': True,
                    'active_time': active_time,
                    'avg_current_active': np.mean(active_currents),
                    'max_current_active': np.max(active_currents),
                    'start_time': time_data[start_idx],
                    'end_time': time_data[end_idx]
                }

        return active_stats

    def add_active_time_table(self, ax, active_stats):
        """
        Добавляет табличку с анализом активного времени слева внизу
        """
        # Подготовка данных для таблицы
        table_data = []

        for signal_type in ['Motor', 'ECU']:
            if signal_type in active_stats:
                stats = active_stats[signal_type]

                if stats['has_activity']:
                    table_data.append([f'{signal_type} Active', '', ''])
                    table_data.append(['Time', f"{stats['active_time']:.3f}", 's'])
                    table_data.append(['Avg Cur.', f"{stats['avg_current_active']:.3f}", 'A'])
                    table_data.append(['Max Cur.', f"{stats['max_current_active']:.3f}", 'A'])
                    table_data.append(['', '', ''])
                else:
                    table_data.append([f'{signal_type}', 'No activity', ''])
                    table_data.append(['', '', ''])

        if not table_data:
            return

        # Создаем текстовую табличку
        textstr = ''
        for row in table_data:
            if row[1]:  # Если есть значение
                textstr += f"{row[0]:<12} {row[1]:<8} {row[2]}\n"
            else:
                textstr += f"{row[0]}\n"

        # Добавляем полупрозрачную табличку слева внизу
        props = dict(boxstyle='round', facecolor='white', alpha=0.8)
        ax.text(0.02, 0.10, textstr, transform=ax.transAxes, fontsize=9,
                verticalalignment='bottom', horizontalalignment='left',
                bbox=props, family='monospace')







    def add_complete_info_table(self, ax, energy_values, current_data_dict):
        """
        Полная информационная таблица с током и энергией
        """
        ax.axis('off')

        # Подготовка данных для таблицы
        table_data = []

        # Заголовок
        table_data.append(['PARAMETER', 'VALUE', 'UNIT'])

        # Добавляем значения энергии
        motor_energy = energy_values.get('Motor', 0)
        ecu_energy = energy_values.get('ECU', 0)

        table_data.append(['Motor Energy', f'{motor_energy:,.4f}', 'J'])
        table_data.append(['ECU Energy', f'{ecu_energy:,.4f}', 'J'])

        # Добавляем статистику по току
        if 'Motor' in current_data_dict:
            motor_current = current_data_dict['Motor']
            table_data.append(['Motor Current', '', ''])
            table_data.append(['  Avg', f'{np.mean(motor_current):.4f}', 'A'])
            table_data.append(['  Max', f'{np.max(motor_current):.4f}', 'A'])
            table_data.append(['  Min', f'{np.min(motor_current):.4f}', 'A'])

        if 'ECU' in current_data_dict:
            ecu_current = current_data_dict['ECU']
            table_data.append(['ECU Current', '', ''])
            table_data.append(['  Avg', f'{np.mean(ecu_current):.4f}', 'A'])
            table_data.append(['  Max', f'{np.max(ecu_current):.4f}', 'A'])
            table_data.append(['  Min', f'{np.min(ecu_current):.4f}', 'A'])

        # Создаем таблицу
        table = ax.table(
            cellText=table_data,
            cellLoc='center',
            loc='center',
            bbox=[0.1, 0.1, 0.8, 0.8]
        )

        # Настраиваем стиль таблицы
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.3)

        for key, cell in table.get_celld().items():
            cell.set_height(0.08)

        # Выделяем важные строки
        for i, row in enumerate(table_data):
            if any(x in row[0] for x in ['Motor Energy', 'ECU Energy']):
                for j in range(len(row)):
                    table[(i, j)].set_facecolor('#FFE4B5')
                    table[(i, j)].set_text_props(weight='bold')

            elif any(x in row[0] for x in ['Motor Current', 'ECU Current']):
                for j in range(len(row)):
                    table[(i, j)].set_facecolor('#E6E6FA')
                    table[(i, j)].set_text_props(weight='bold')

        ax.set_title('Energy & Current Analysis', fontsize=12, fontweight='bold', pad=20)




    def add_simple_info_table(self, ax, energy_values):
        """
        Упрощенная информационная таблица только с основными данными
        """
        ax.axis('off')

        # Подготовка данных для таблицы
        table_data = []

        # Заголовок
        table_data.append(['ENERGY SUMMARY', 'JOULE'])
        table_data.append(['='*20, '='*15])

        # Добавляем значения энергии
        motor_energy = energy_values.get('Motor', 0)
        ecu_energy = energy_values.get('ECU', 0)

        table_data.append(['Motor Current', f'{motor_energy:,.4f}'])
        table_data.append(['ECU Current', f'{ecu_energy:,.4f}'])

        # Создаем таблицу
        table = ax.table(
            cellText=table_data,
            cellLoc='center',
            loc='center',
            bbox=[0.1, 0.1, 0.8, 0.8]
        )

        # Настраиваем стиль таблицы
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        table.scale(1, 1.5)

        for key, cell in table.get_celld().items():
            cell.set_height(0.1)

        # Выделяем важные строки
        for i, row in enumerate(table_data):
            if any(x in row[0] for x in ['Motor', 'ECU']):
                for j in range(len(row)):
                    table[(i, j)].set_facecolor('#E6E6FA')
                    table[(i, j)].set_text_props(weight='bold')

        ax.set_title('Energy Summary', fontsize=12, fontweight='bold', pad=20)








    def add_info_table(self, ax, energy_results, df, time_col, current_cols):
        """
        Добавляет информационную таблицу с анализом серий управления
        """
        ax.axis('off')

        # Находим напряжение в данных
        voltage = 12.0
        voltage_cols = [col for col in df.columns if 'voltage' in col.lower()]
        if voltage_cols:
            try:
                voltage = df[voltage_cols[0]].mean()
            except:
                pass

        # Подготовка данных для таблицы
        table_data = []

        # Заголовок
        table_data.append(['ENERGY ANALYSIS', 'VALUE', 'UNIT'])
        table_data.append(['='*25, '='*18, '='*10])

        # Результаты по энергии с высокой точностью (4 знака после запятой)
        total_energy = 0.0
        for signal_name, energy in energy_results.items():
            short_name = signal_name.replace('Motor Current', 'MOTOR').replace('ECU Current', 'ECU')
            short_name = short_name.split('(')[0].strip()

            # Округляем до 4 знаков после запятой
            energy_j = energy
            table_data.append([short_name, f'{energy_j:,.4f}', 'J'])
            total_energy += energy

        # Округляем общую энергию до 4 знаков
        total_energy_j = total_energy
        table_data.append(['TOTAL ENERGY', f'{total_energy_j:,.4f}', 'J'])
        table_data.append(['─'*25, '─'*18, '─'*10])

        # Простой анализ
        for signal_name, energy in energy_results.items():
            current_col = signal_name.split('(')[1].rstrip(')') if '(' in signal_name else ''
            if current_col and current_col in df.columns:
                try:
                    # Простой анализ - среднее значение тока с высокой точностью
                    avg_current = df[current_col].mean()
                    max_current = df[current_col].max()

                    table_data.append([f"{current_col.split('/')[-1]}", '', ''])
                    table_data.append(['  Avg Cur.', f"{avg_current:.4f}", 'A'])
                    table_data.append(['  Max Cur.', f"{max_current:.4f}", 'A'])

                    # Попробуем найти активации
                    analysis = self.analyze_consumption(df, time_col, current_col)
                    if analysis['has_activation']:
                        table_data.append(['  Activ.', 'YES', ''])
                        table_data.append(['  Dur.', f"{analysis['series_duration']:.4f}", 's'])
                        table_data.append(['  Avg Cur.*', f"{analysis['avg_current_series']:.4f}", 'A'])
                    else:
                        table_data.append(['  Activ.', 'NO', ''])

                    table_data.append(['', '', ''])

                except Exception as e:
                    table_data.append([f"{current_col.split('/')[-1]}", 'ERROR', ''])
                    table_data.append(['', '', ''])

        table_data.append(['VOLTAGE', f'{voltage:.4f}', 'V'])

        # Создаем таблицу
        table = ax.table(
            cellText=table_data,
            cellLoc='left',
            loc='center',
            bbox=[0.05, 0.05, 0.9, 0.9],
            colWidths=[0.6, 0.3, 0.1]  # Сужаем третий столбец, расширяем первый
        )

        # Настраиваем стиль таблицы
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.2)

        for key, cell in table.get_celld().items():
            cell.set_height(0.05)

        # Выделяем важные строки
        for i, row in enumerate(table_data):
            if 'TOTAL ENERGY' in row[0]:
                for j in range(len(row)):
                    table[(i, j)].set_facecolor('#FFE4B5')
                    table[(i, j)].set_text_props(weight='bold')

            elif any(x in row[0] for x in ['MOTOR', 'ECU']):
                for j in range(len(row)):
                    table[(i, j)].set_facecolor('#E6E6FA')

            elif 'Activ.' in row[0] and 'YES' in row[1]:
                for j in range(len(row)):
                    table[(i, j)].set_facecolor('#F0FFF0')

        ax.set_title('Energy Analysis (High Precision)', fontsize=11, fontweight='bold', pad=15)


    def analyze_consumption(self, df, time_col, current_col, base_threshold=0.2, activation_threshold=0.2):
        """
        Анализирует серии управления оборудованием, игнорируя холостой ток ~200 мА
        """
        try:
            # Убедимся, что данные отсортированы по времени
            df_sorted = df.sort_values(by=time_col).dropna(subset=[time_col, current_col])

            time_data = df_sorted[time_col].values
            current_data = df_sorted[current_col].values

            if len(time_data) < 2:
                return {'has_activation': False}

            # Определяем базовое потребление (простой)
            base_mask = current_data < activation_threshold
            if np.any(base_mask):
                base_current = np.median(current_data[base_mask])
            else:
                base_current = 0.0

            # Находим активации (ток выше порога активации)
            activation_mask = current_data > activation_threshold

            # Если нет активаций выше порога
            if not np.any(activation_mask):
                return {
                    'has_activation': False,
                    'base_current': base_current,
                    'total_activation_time': 0.0
                }

            # Находим индексы активаций
            activation_indices = np.where(activation_mask)[0]

            # Группируем смежные индексы активаций
            activation_segments = []
            current_segment = []

            for i in range(len(activation_indices)):
                if not current_segment:
                    current_segment.append(activation_indices[i])
                elif activation_indices[i] == current_segment[-1] + 1:
                    current_segment.append(activation_indices[i])
                else:
                    if len(current_segment) > 5:  # Минимум 5 точек для сегмента
                        activation_segments.append((current_segment[0], current_segment[-1]))
                    current_segment = [activation_indices[i]]

            # Добавляем последний сегмент
            if len(current_segment) > 5:
                activation_segments.append((current_segment[0], current_segment[-1]))

            if not activation_segments:
                return {
                    'has_activation': False,
                    'base_current': base_current,
                    'total_activation_time': 0.0
                }

            # Группируем сегменты в серии
            activation_series = self.find_activation_series(activation_segments, time_data)

            if not activation_series:
                return {
                    'has_activation': False,
                    'base_current': base_current,
                    'total_activation_time': 0.0
                }

            # Анализируем первую найденную серию
            series = activation_series[0]  # Берем первую серию

            # Получаем все индексы активаций в серии
            series_indices = []
            for start_idx, end_idx in series:
                series_indices.extend(range(start_idx, end_idx + 1))

            series_indices = np.array(series_indices)

            # Параметры серии
            series_time_start = time_data[series_indices[0]]
            series_time_end = time_data[series_indices[-1]]
            series_duration = series_time_end - series_time_start

            # Ток во время серии
            series_currents = current_data[series_indices]
            avg_current_series = np.mean(series_currents)
            avg_power_series = avg_current_series * 12.0

            # Анализ отдельных импульсов в серии
            impulse_durations = []
            impulse_currents = []

            for start_idx, end_idx in series:
                impulse_duration = time_data[end_idx] - time_data[start_idx]
                impulse_avg_current = np.mean(current_data[start_idx:end_idx+1])
                impulse_durations.append(impulse_duration)
                impulse_currents.append(impulse_avg_current)

            return {
                'has_activation': True,
                'base_current': base_current,
                'series_duration': series_duration,
                'series_start': series_time_start,
                'series_end': series_time_end,
                'avg_current_series': avg_current_series,
                'avg_power_series': avg_power_series,
                'impulse_count': len(series),
                'avg_impulse_duration': np.mean(impulse_durations) if impulse_durations else 0.0,
                'avg_impulse_current': np.mean(impulse_currents) if impulse_currents else 0.0,
                'max_impulse_current': np.max(impulse_currents) if impulse_currents else 0.0,
                'total_activation_time': sum(impulse_durations),
                'activation_segments': activation_segments
            }

        except Exception as e:
            print(f"Ошибка при анализе активаций для {current_col}: {e}")
            import traceback
            traceback.print_exc()
            return {'has_activation': False}

    def find_activation_series(self, activation_segments, time_data, max_gap=5.0):
        """
        Группирует отдельные активации в серии
        """
        if not activation_segments:
            return []

        # Сортируем сегменты по времени начала
        activation_segments.sort(key=lambda x: time_data[x[0]])

        series = []
        current_series = [activation_segments[0]]

        for i in range(1, len(activation_segments)):
            current_end_time = time_data[current_series[-1][1]]
            next_start_time = time_data[activation_segments[i][0]]

            # Если промежуток меньше max_gap, добавляем в текущую серию
            if (next_start_time - current_end_time) <= max_gap:
                current_series.append(activation_segments[i])
            else:
                # Начинаем новую серию
                if len(current_series) >= 2:  # Серия должна содержать минимум 2 импульса
                    series.append(current_series)
                current_series = [activation_segments[i]]

        # Добавляем последнюю серию
        if len(current_series) >= 2:
            series.append(current_series)

        return series







    def calculate_energy_joules(self, df, time_col, current_col, voltage):
        """
        Расчет затраченной энергии в джоулях и возврат данных для графиков, включая накопленную энергию
        """
        try:
            # Убедимся, что данные отсортированы по времени
            df_sorted = df.sort_values(by=time_col).dropna(subset=[time_col, current_col])

            # Получаем данные
            time_data = df_sorted[time_col].values
            current_data = df_sorted[current_col].values

            # Проверяем, что достаточно точек данных
            if len(time_data) < 2:
                return 0.0, time_data, current_data, np.zeros_like(time_data), np.zeros_like(time_data)

            # Рассчитываем мощность (Вт)
            power_data = current_data * voltage

            # Интегрируем мощность по времени для получения энергии в джоулях
            total_energy_joules = 0.0
            cumulative_energy = np.zeros_like(time_data)
            cumulative_energy[0] = 0.0

            for i in range(len(time_data) - 1):
                # Средняя мощность в интервале
                avg_power = (power_data[i] + power_data[i + 1]) / 2.0

                # Время в секундах
                time_interval = time_data[i + 1] - time_data[i]

                # Энергия в джоулях за интервал
                energy_interval = avg_power * time_interval

                total_energy_joules += energy_interval
                cumulative_energy[i + 1] = total_energy_joules

            return total_energy_joules, time_data, current_data, power_data, cumulative_energy

        except Exception as e:
            print(f"Ошибка при расчете энергии для {current_col}: {e}")
            return 0.0, np.array([]), np.array([]), np.array([]), np.array([])








    def endu_tdms_log_handler(self, tdms_file_path, gui_instance, temp_dir):
        """
        Метод для обработки отдельного TDMS файла
        """
        print(f"Обработчик вызван для файла: {tdms_file_path}")

        # Загрузка TDMS файла
        tdms_file = TdmsFile.read(tdms_file_path)
        df = tdms_file.as_dataframe()

        # Фильтрация колонок: оставить только 'time' или содержащие 'Station' (регистронезависимо)
        columns_to_keep = [col for col in df.columns if 'time' in col.lower() or 'station' in col.lower()]
        if not columns_to_keep:
            print("Нет подходящих колонок для обработки")
            return None
        df = df[columns_to_keep]

        # Удалить столбец с 'voltage' (регистронезависимо)
        voltage_cols = [col for col in df.columns if 'voltage' in col.lower()]
        df = df.drop(columns=voltage_cols, errors='ignore')

        # Идентификация колонок
        time_col = next((col for col in df.columns if 'time' in col.lower()), None)
        if time_col is None:
            print("Столбец 'time' не найден")
            return None

        motor_current_cols = [col for col in df.columns if 'motor current' in col.lower()]
        ecu_current_cols = [col for col in df.columns if 'ecu current' in col.lower()]
        pressure_cols = [col for col in df.columns if any(wheel in col.lower() for wheel in ['rl', 'fr', 'fl', 'rr', 'mc'])]

        # Расчет энергии
        voltage = 12.0
        motor_energy = 0.0
        valves_energy = 0.0

        if motor_current_cols:
            for col in motor_current_cols:
                energy, _, _, _, _ = self.calculate_energy_joules(df, time_col, col, voltage)
                motor_energy += energy

        if ecu_current_cols:
            for col in ecu_current_cols:
                energy, _, _, _, _ = self.calculate_energy_joules(df, time_col, col, voltage)
                valves_energy += energy

        # Построение графика
        fig, ax1 = plt.subplots(figsize=(12, 6))

        # Плот для current (левая ось, лимит до CURRENT_SCALE)
        ax1.set_xlabel(time_col)
        ax1.set_ylabel('Current (A)', color='tab:blue')
        for col in motor_current_cols:
            ax1.plot(df[time_col], df[col], label=col, color='red')
        for col in ecu_current_cols:
            ax1.plot(df[time_col], df[col], label=col, color='tab:blue')
        ax1.set_ylim(0, CURRENT_SCALE)
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.legend(loc='upper left')

        # Плот для pressure (правая ось, лимит до 200 бар), если есть
        if pressure_cols:
            ax2 = ax1.twinx()
            ax2.set_ylabel('Pressure (bar)', color='tab:orange')
            for col in pressure_cols:
                color = 'purple' if 'mc' in col.lower() else 'tab:orange'
                ax2.plot(df[time_col], df[col], label=col.split('(')[-1].rstrip(')'), color=color, linestyle='--')
            ax2.set_ylim(0, 200)
            ax2.tick_params(axis='y', labelcolor='tab:orange')
            ax2.legend(loc='upper right')

        plt.title(f"Graph for {os.path.basename(tdms_file_path)}")
        plt.tight_layout()

        # Добавление полупрозрачной таблички 2x2 справа внизу
        props = dict(boxstyle='round', facecolor='white', alpha=0.7)
        textstr = f'Motor Energy: {motor_energy:.0f} J\nValves Energy: {valves_energy:.0f} J'
        plt.text(0.95, 0.05, textstr, transform=ax1.transAxes, fontsize=10,
                 verticalalignment='bottom', horizontalalignment='right', bbox=props)

        # Сохранение графика в PNG
        plot_filename = f"plot_{os.path.basename(tdms_file_path)}.png"
        plot_path = os.path.join(temp_dir, plot_filename)
        plt.savefig(plot_path)
        plt.close()

        # Проверка флага отмены
        if gui_instance.stop_processing or self._cancel:
            print("Обработка файла прервана")
            return None

        return plot_path




    def create_interactive_plot(self, file_path):
        """
        Создает интерактивный график только для активного участка и открывает в браузере
        """

        print(f"Создание интерактивного графика для: {file_path}")

        # Проверяем, не завершена ли работа GUI
        if (hasattr(self, 'gui_instance') and self.gui_instance and
            hasattr(self.gui_instance, 'root') and self.gui_instance.root):
            if not self.gui_instance.root.winfo_exists():
                print("Главное окно закрыто, прерываем обработку")
                return



        try:
            # Проверка флага отмены
            if self._cancel:
                print("Обработка прервана перед началом (флаг отмены активен)")
                return

            # Загрузка TDMS файла
            tdms_file = TdmsFile.read(file_path)
            df = tdms_file.as_dataframe()
            print(f"Колонки в DataFrame: {df.columns.tolist()}")  # Отладка

            # Проверка флага отмены
            if self._cancel:
                print("Обработка прервана после загрузки файла")
                return

            # Фильтрация колонок: time или 'station' и не '_bsw'
            columns_to_keep = [col for col in df.columns if 'time' in col.lower() or ('station' in col.lower() and not col.lower().endswith('_bsw'))]
            if not columns_to_keep:
                print("Нет подходящих колонок для обработки (включая время)")
                return

            df = df[columns_to_keep]
            print(f"Отфильтрованные колонки: {df.columns.tolist()}")  # Отладка

            # Идентификация временной колонки
            time_cols = [col for col in df.columns if 'time' in col.lower()]
            time_col = time_cols[0] if time_cols else None
            if not time_col:
                print("Временная колонка не найдена!")
                return

            # Идентификация колонок токов и давления
            motor_current_cols = [col for col in df.columns if 'motor current' in col.lower()]
            ecu_current_cols = [col for col in df.columns if 'ecu current' in col.lower()]
            pressure_cols = [col for col in df.columns if any(wheel in col.lower() for wheel in ['rl', 'fr', 'fl', 'rr', 'mc']) and 'current' not in col.lower()]
            print(f"Motor Current: {motor_current_cols}, ECU Current: {ecu_current_cols}, Pressure: {pressure_cols}")  # Отладка

            # Проверка наличия данных
            if not motor_current_cols and not ecu_current_cols and not pressure_cols:
                print("Нет данных для построения графика (Motor Current, ECU Current или Pressure)")
                return

            # Проверка данных на NaN или пустоту
            if df[time_col].isna().all():
                print("Временная колонка содержит только NaN")
                return
            for col in motor_current_cols + ecu_current_cols + pressure_cols:
                if df[col].isna().all():
                    print(f"Колонка {col} содержит только NaN")
                    return

            # Проверка флага отмены
            if self._cancel:
                print("Обработка прервана перед поиском активного участка")
                return

            # Находим активный участок
            active_start, active_end = self.find_active_section(df, time_col, motor_current_cols + ecu_current_cols)
            print(f"Активный участок: start={active_start}, end={active_end}")  # Отладка

            if active_start is None or active_end is None:
                print("Активный участок не найден!")
                return

            # Фильтруем DataFrame на активный участок
            mask = (df[time_col] >= active_start) & (df[time_col] <= active_end)
            df_active = df.loc[mask]
            if df_active.empty:
                print("Активный участок пустой!")
                return

            # Проверка флага отмены
            if self._cancel:
                print("Обработка прервана перед созданием графика")
                return

            # Создаем интерактивный график с Plotly
            fig = go.Figure()

            # Добавляем токи (левая ось)
            for col in motor_current_cols:
                short_name = col.split('/')[-1]
                short_name = short_name.split('Station one')[-1].strip() if 'Station one' in short_name else short_name
                fig.add_trace(go.Scatter(x=df_active[time_col], y=df_active[col], mode='lines', name=short_name, line=dict(color='red')))

            for col in ecu_current_cols:
                short_name = col.split('/')[-1]
                short_name = short_name.split('Station one')[-1].strip() if 'Station one' in short_name else short_name
                fig.add_trace(go.Scatter(x=df_active[time_col], y=df_active[col], mode='lines', name=short_name, line=dict(color='blue')))

            # Добавляем давления (правая ось)
            for col in pressure_cols:
                short_name = col.split('/')[-1]
                short_name = short_name.split('Station one')[-1].strip() if 'Station one' in short_name else short_name
                color = 'purple' if 'mc' in col.lower() else 'orange'
                fig.add_trace(go.Scatter(x=df_active[time_col], y=df_active[col], mode='lines', name=short_name, yaxis='y2', line=dict(color=color, dash='dash')))

            # Определяем общее начало для таблички
            station_prefix = "Station one" if any('Station one' in col for col in df.columns) else "Unknown Station"

            # Проверка флага отмены
            if self._cancel:
                print("Обработка прервана перед сохранением HTML")
                return

            # Настройка layout
            fig.update_layout(
                title=f"Interactive Graph for {os.path.basename(file_path)} (Active Section) - {station_prefix}",
                xaxis_title='Time (s)',
                yaxis_title='Current (A)',
                yaxis2=dict(
                    title='Pressure (bar)',
                    overlaying='y',
                    side='right',
                    range=[0, 250]
                ),
                legend=dict(orientation='h', yanchor='bottom', y=1.0, xanchor='right', x=1),
                margin=dict(t=100),
                hovermode='x unified'
            )

            # Сохраняем в временный HTML файл
            with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as tmp_file:
                fig.write_html(tmp_file.name)
                html_path = tmp_file.name

            # Проверка флага отмены
            if self._cancel:
                print("Обработка прервана перед открытием браузера")
                return

            # Открываем в браузере (в главном потоке через after)
            def open_browser():
                webbrowser.open('file://' + os.path.abspath(html_path))
                print(f"Интерактивный график открыт: {html_path}")

            # Планируем открытие браузера в главном потоке
            if hasattr(self, 'gui_instance') and self.gui_instance and self.gui_instance.root:
                try:
                    self.gui_instance.root.after(0, open_browser)
                except RuntimeError:
                    # Если главный поток уже завершен, открываем напрямую
                    open_browser()
            else:
                open_browser()

        except Exception as e:
            print(f"Ошибка при создании интерактивного графика: {e}")
            import traceback
            traceback.print_exc()







    def find_active_section(self, df, time_col, current_cols, threshold=0.2):
        """
        Находит активный участок, где хотя бы один ток > threshold
        """
        if not current_cols:
            return None, None

        df_sorted = df.sort_values(by=time_col)

        active_mask = np.zeros(len(df_sorted), dtype=bool)
        for col in current_cols:
            if col in df_sorted.columns:
                active_mask |= df_sorted[col] > threshold

        if not np.any(active_mask):
            return None, None

        active_indices = np.where(active_mask)[0]
        start_idx = active_indices[0]
        end_idx = active_indices[-1]

        # Добавляем небольшой буфер (например, 0.5 с до и после)
        buffer = 0.5
        time_data = df_sorted[time_col].values
        start_time = max(time_data[start_idx] - buffer, time_data[0])
        end_time = min(time_data[end_idx] + buffer, time_data[-1])

        return start_time, end_time

    def cancel(self):
        """Метод для отмены обработки"""
        self._cancel = True
        print("Команда отмены получена")

    def open_html_file(self, file_path):
        """
        Открывает HTML файл в браузере по умолчанию
        """
        # Проверяем существование файла
        if not os.path.exists(file_path):
            print(f"Файл {file_path} не найден!")
            return False

        # Преобразуем путь в абсолютный и правильный формат
        absolute_path = os.path.abspath(file_path)

        # Открываем файл в браузере
        webbrowser.open('file://' + absolute_path)
        return True

# Запуск приложения
if __name__ == "__main__":
    root = tk.Tk()
    app = GuiDataChooser(root)
    root.mainloop()
