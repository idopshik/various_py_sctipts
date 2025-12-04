


import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QRadioButton, QScrollArea,
                               QProgressBar, QFileDialog, QFrame)
from PySide6.QtCore import Qt, QEvent,QTimer, QThread, Signal, QObject


from PySide6.QtGui import QIcon, QPixmap
import configparser
import os
import threading
import time
import pandas as pd
from nptdms import TdmsFile
import numpy as np
import matplotlib
matplotlib.use('Qt5Agg')  # Используем Qt5 бэкенд для matplotlib
import matplotlib.pyplot as plt
import glob
import tempfile
import webbrowser
import plotly.graph_objects as go
import subprocess  # Добавьте этот импорт
import time        # Убедитесь, что time импортирован

CURRENT_SCALE = 60




class FileCheckWorker(QObject):
    finished = Signal()

    def __init__(self, processor, file_path, gui_instance):
        super().__init__()
        self.processor = processor
        self.file_path = file_path
        self.gui_instance = gui_instance

    def run(self):
        try:
            self.processor.check_file(self.file_path, self.gui_instance)
        except Exception as e:
            print(f"Ошибка при проверке файла: {e}")
        finally:
            self.finished.emit()

class InteractiveWorker(QObject):
    finished = Signal()

    def __init__(self, processor, file_path):
        super().__init__()
        self.processor = processor
        self.file_path = file_path

    def run(self):
        try:
            self.processor.create_interactive_plot(self.file_path)
        except Exception as e:
            print(f"Ошибка при создании интерактивного графика: {e}")
        finally:
            self.finished.emit()


class ProcessingThread(QThread):
    finished_signal = Signal()
    progress_signal = Signal(int, int)

    def __init__(self, target, args=()):
        super().__init__()
        self.target = target
        self.args = args

    def run(self):
        self.target(*self.args)
        self.finished_signal.emit()


class GuiDataChooser(QMainWindow):
    create_plots_requested = Signal()
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TDMS Converter - Выбор данных")
        self.setGeometry(100, 100, 800, 600)

        # Определяем тему системы
        theme = self.detect_system_theme()

        # Установка иконки приложения
        try:
            self.setWindowIcon(QIcon("endu_tdms_app.ico"))
        except:
            try:
                self.setWindowIcon(QIcon("app.png"))
            except:
                print("Не удалось загрузить иконку приложения")

        # Основной виджет и макет
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Путь к папке
        self.folder_path = ""
        self.processor = None
        self.processing_thread = None
        self.stop_processing = False
        self.selected_file = None
        self.file_radios = {}

        # Верхний фрейм: метка, поле ввода и кнопка
        top_frame = QWidget()
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(10, 10, 10, 10)

        self.path_label = QLabel("Папка с данными:")
        top_layout.addWidget(self.path_label)

        self.path_entry = QLineEdit()
        self.path_entry.setFixedWidth(400)
        top_layout.addWidget(self.path_entry)

        self.open_btn = QPushButton("Open Folder")
        self.open_btn.clicked.connect(self.open_folder)
        top_layout.addWidget(self.open_btn)
        top_layout.addStretch()

        self.main_layout.addWidget(top_frame)

        # Область для списка файлов
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.file_widget = QWidget()
        self.file_layout = QVBoxLayout(self.file_widget)
        self.file_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.file_widget)
        self.main_layout.addWidget(self.scroll_area)

        # Фрейм для кнопок
        button_frame = QWidget()
        button_layout = QHBoxLayout(button_frame)

        self.check_file_btn = QPushButton("Check File")
        self.check_file_btn.setEnabled(False)
        self.check_file_btn.clicked.connect(self.check_selected_file)
        button_layout.addWidget(self.check_file_btn)

        self.do_interactive_btn = QPushButton("Interactive")
        self.do_interactive_btn.setEnabled(False)
        self.do_interactive_btn.clicked.connect(self.do_interactive)
        button_layout.addWidget(self.do_interactive_btn)

        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_processing)
        button_layout.addWidget(self.cancel_btn)

        self.process_btn = QPushButton("Process")
        self.process_btn.clicked.connect(self.start_processing)
        button_layout.addWidget(self.process_btn)


        self.debug_btn = QPushButton("Debug File")
        self.debug_btn.setEnabled(False)
        self.debug_btn.clicked.connect(self.debug_selected_file)
        button_layout.addWidget(self.debug_btn)


        self.main_layout.addWidget(button_frame)

        # Прогрессбар
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setVisible(False)
        self.main_layout.addWidget(self.progress_bar)
        # Применяем стили в зависимости от темы
        self.apply_theme(theme)

        # Стилизация
        self.setStyleSheet("""
            QWidget {
                font-size: 16px;
                background-color: #f0f8f0;
                color: #000000;  /* ЧЕРНЫЙ текст */
            }
            QPushButton {
                background-color: #e0f0e0;
                padding: 5px;
                color: #000000;  /* ЧЕРНЫЙ текст на кнопках */
            }
            QLineEdit {
                background-color: #ffffff;
                color: #000000;  /* ЧЕРНЫЙ текст в полях ввода */
                border: 1px solid #cccccc;
            }
            QLabel {
                color: #000000;  /* ЧЕРНЫЙ текст в метках */
            }
            QRadioButton {
                color: #000000;  /* ЧЕРНЫЙ текст радиокнопок */
            }
            QScrollArea {
                background-color: #f0f8f0;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #f0f8f0;
            }
            QProgressBar {
                color: #000000;  /* ЧЕРНЫЙ текст прогрессбара */
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
        """)

        # Загружаем последний путь
        self.load_initial_path()

        self._processing = False

        self.create_plots_requested.connect(self.on_create_plots_requested)


    def debug_selected_file(self):
        """Отладочный анализ файла"""
        selected_file = self.get_selected_file()
        if not selected_file:
            return

        print(f"\n{'='*60}")
        print(f"НАЧИНАЕМ ОТЛАДОЧНЫЙ АНАЛИЗ ФАЙЛА")
        print(f"{'='*60}")

        # Создаем процессор
        processor = Endurance_tdms_logs_dealer(self.folder_path)

        # Выполняем анализ
        processor.debug_tdms_structure(selected_file)

    def apply_theme(self, theme='light'):
        """Применение стилей в зависимости от темы"""
        if theme == 'dark':
            # Стили для темной темы
            dark_stylesheet = """
                QWidget {
                    font-size: 16px;
                    background-color: #2b2b2b;
                    color: #ffffff;  /* БЕЛЫЙ текст */
                }
                QPushButton {
                    background-color: #3c3c3c;
                    padding: 5px;
                    color: #ffffff;
                    border: 1px solid #555555;
                }
                QPushButton:hover {
                    background-color: #4c4c4c;
                }
                QPushButton:pressed {
                    background-color: #2c2c2c;
                }
                QLineEdit {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555555;
                    selection-background-color: #555555;
                }
                QLabel {
                    color: #ffffff;
                }
                QRadioButton {
                    color: #ffffff;
                }
                QRadioButton::indicator {
                    width: 13px;
                    height: 13px;
                }
                QRadioButton::indicator::unchecked {
                    border: 2px solid #888888;
                    border-radius: 6px;
                    background-color: #2b2b2b;
                }
                QRadioButton::indicator::checked {
                    border: 2px solid #4CAF50;
                    border-radius: 6px;
                    background-color: #4CAF50;
                }
                QScrollArea {
                    background-color: #2b2b2b;
                    border: none;
                }
                QScrollArea > QWidget > QWidget {
                    background-color: #2b2b2b;
                }
                QScrollBar:vertical {
                    background: #2b2b2b;
                    width: 12px;
                }
                QScrollBar::handle:vertical {
                    background: #555555;
                    border-radius: 6px;
                    min-height: 20px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #666666;
                }
                QProgressBar {
                    color: #ffffff;
                    text-align: center;
                    border: 1px solid #555555;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                    border-radius: 3px;
                }
                QFrame {
                    background-color: #2b2b2b;
                    border: none;
                }
            """
            self.setStyleSheet(dark_stylesheet)
        else:
            # Стили для светлой темы (оригинальные)
            light_stylesheet = """
                QWidget {
                    font-size: 16px;
                    background-color: #f0f8f0;
                    color: #000000;
                }
                QPushButton {
                    background-color: #e0f0e0;
                    padding: 5px;
                    color: #000000;
                    border: 1px solid #cccccc;
                }
                QPushButton:hover {
                    background-color: #d0e0d0;
                }
                QPushButton:pressed {
                    background-color: #c0d0c0;
                }
                QLineEdit {
                    background-color: #ffffff;
                    color: #000000;
                    border: 1px solid #cccccc;
                }
                QLabel {
                    color: #000000;
                }
                QRadioButton {
                    color: #000000;
                }
                QRadioButton::indicator {
                    width: 13px;
                    height: 13px;
                }
                QRadioButton::indicator::unchecked {
                    border: 2px solid #888888;
                    border-radius: 6px;
                    background-color: #ffffff;
                }
                QRadioButton::indicator::checked {
                    border: 2px solid #4CAF50;
                    border-radius: 6px;
                    background-color: #4CAF50;
                }
                QScrollArea {
                    background-color: #f0f8f0;
                    border: none;
                }
                QScrollArea > QWidget > QWidget {
                    background-color: #f0f8f0;
                }
                QProgressBar {
                    color: #000000;
                    text-align: center;
                    border: 1px solid #cccccc;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                    border-radius: 3px;
                }
            """
            self.setStyleSheet(light_stylesheet)

    def detect_system_theme(self):
        """Определение темы системы (светлая/темная)"""
        try:
            # Проверка переменных окружения
            desktop_session = os.environ.get('DESKTOP_SESSION', '').lower()
            current_theme = os.environ.get('GTK_THEME', '').lower()

            # Ключевые слова для темной темы
            dark_keywords = ['dark', 'black', 'midnight', 'dracula', 'solarized']

            # Проверяем наличие ключевых слов
            for keyword in dark_keywords:
                if keyword in desktop_session or keyword in current_theme:
                    return 'dark'

            # Дополнительная проверка для GNOME
            try:
                import subprocess
                result = subprocess.run(
                    ['gsettings', 'get', 'org.gnome.desktop.interface', 'gtk-theme'],
                    capture_output=True,
                    text=True
                )
                theme_name = result.stdout.strip().lower().strip("'")
                for keyword in dark_keywords:
                    if keyword in theme_name:
                        return 'dark'
            except:
                pass

        except Exception as e:
            print(f"Не удалось определить тему системы: {e}")

        return 'light'  # По умолчанию светлая тема

    def on_create_plots_requested(self):
        """Обработчик запроса на создание графиков из другого потока"""
        if hasattr(self, 'processor') and self.processor:
            self.processor.create_plots_in_main_thread()

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку с TDMS файлами")
        if folder:
            self.folder_path = folder
            self.path_entry.setText(folder)
            self.save_path_to_ini(folder)
            self.update_file_list(folder)
            self.progress_bar.setVisible(False)

    def update_file_list(self, folder_path):
        # Очищаем текущий список
        for radio in self.file_radios.values():
            radio.deleteLater()
        self.file_radios.clear()
        self.selected_file = None
        self.check_file_btn.setEnabled(False)
        self.do_interactive_btn.setEnabled(False)

        try:
            files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
            files.sort()

            if not files:
                label = QLabel("Папка пуста.")
                self.file_layout.addWidget(label)
            else:
                button_group = []
                for file in files:
                    radio = QRadioButton(file)
                    radio.toggled.connect(lambda checked, f=file: self.on_radio_toggled(checked, f))
                    self.file_layout.addWidget(radio)
                    self.file_radios[file] = radio
                    button_group.append(radio)
                self.file_layout.addStretch()

        except Exception as e:
            label = QLabel(f"Ошибка: {str(e)}")
            self.file_layout.addWidget(label)

    def on_radio_toggled(self, checked, filename):
        """Обработчик переключения радиокнопок"""

        """Обработчик переключения радиокнопок"""
        print(f"Radio toggled: {filename}, checked: {checked}")

        if checked:
            self.selected_file = filename
        else:
            # Если текущая кнопка отключена, но есть другие выбранные
            if self.selected_file == filename:
                # Проверяем, есть ли другие выбранные радиокнопки
                any_checked = any(radio.isChecked() for radio in self.file_radios.values())
                if not any_checked:
                    self.selected_file = None
                else:
                    # Находим первую выбранную радиокнопку
                    for file, radio in self.file_radios.items():
                        if radio.isChecked():
                            self.selected_file = file
                            break

        # Обновляем состояние кнопок
        self.update_check_file_button_state()

    def update_check_file_button_state(self):
        """Обновление состояния всех кнопок"""
        print(f"Updating button state. Selected file: {self.selected_file}, Processing: {self._processing}")

        if self.selected_file and not self._processing:
            self.check_file_btn.setEnabled(True)
            self.do_interactive_btn.setEnabled(True)
            self.debug_btn.setEnabled(True)  # Новая кнопка
            print("Buttons enabled")
        else:
            self.check_file_btn.setEnabled(False)
            self.do_interactive_btn.setEnabled(False)
            self.debug_btn.setEnabled(False)  # Новая кнопка
            print("Buttons disabled")


    def get_selected_file(self):
        return os.path.join(self.folder_path, self.selected_file) if self.selected_file else None

    def check_selected_file(self):
        selected_file = self.get_selected_file()
        if not selected_file:
            return

        self._processing = True
        self.check_file_btn.setEnabled(False)
        self.do_interactive_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.processor = Endurance_tdms_logs_dealer(self.folder_path)
        self.stop_processing = False

        # ЗАМЕНИТЕ на QThread
        self.processing_thread = QThread()
        self.worker = FileCheckWorker(self.processor, selected_file, self)
        self.worker.moveToThread(self.processing_thread)
        self.processing_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.processing_finished)
        self.worker.finished.connect(self.processing_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.processing_thread.finished.connect(self.processing_thread.deleteLater)
        self.processing_thread.start()

    def do_interactive(self):
        selected_file = self.get_selected_file()
        if not selected_file:
            return

        self._processing = True
        self.do_interactive_btn.setEnabled(False)
        self.check_file_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.processor = Endurance_tdms_logs_dealer(self.folder_path)
        self.processor.gui_instance = self
        self.stop_processing = False

        # ЗАМЕНИТЕ на QThread
        self.processing_thread = QThread()
        self.worker = InteractiveWorker(self.processor, selected_file)
        self.worker.moveToThread(self.processing_thread)
        self.processing_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.processing_finished)
        self.worker.finished.connect(self.processing_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.processing_thread.finished.connect(self.processing_thread.deleteLater)
        self.processing_thread.start()

    def processing_finished(self):
        self._processing = False
        self.progress_bar.setVisible(False)
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        # Если был процессор и он сохранил HTML
        if hasattr(self, 'processor') and self.processor:
            # Можно добавить вывод информации о сохраненном файле
            print("\n" + "="*60)
            print("ОБРАБОТКА ЗАВЕРШЕНА")
            print("="*60)

        # Обновляем состояние кнопок
        self.update_check_file_button_state()
        print("Processing finished - buttons should be updated")


    def save_path_to_ini(self, path):
        config = configparser.ConfigParser()
        config['DEFAULT'] = {'LastFolderPath': path}
        with open('endu_tpms_analysis_settings.ini', 'w') as configfile:
            config.write(configfile)

    def load_initial_path(self):
        config = configparser.ConfigParser()
        config['DEFAULT'] = {'LastFolderPath': ''}
        try:
            config.read('endu_tpms_analysis_settings.ini')
            last_path = config['DEFAULT'].get('LastFolderPath', '')
            if last_path and os.path.isdir(last_path):
                self.folder_path = last_path
                self.path_entry.setText(last_path)
                self.update_file_list(last_path)
        except Exception as e:
            print(f"Ошибка при загрузке конфигурации: {e}")

    def start_processing(self):
        folder = self.folder_path
        if not folder or not os.path.isdir(folder):
            return

        self.process_btn.setEnabled(False)
        self.check_file_btn.setEnabled(False)
        self.do_interactive_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.processor = Endurance_tdms_logs_dealer(folder)
        self.stop_processing = False

        self.processing_thread = ProcessingThread(self.process_thread)
        self.processing_thread.finished_signal.connect(self.processing_finished)
        self.processing_thread.progress_signal.connect(self.update_progress)
        self.processing_thread.start()

    def process_thread(self):
        try:
            self.processor.process(self)
        except Exception as e:
            print(f"Ошибка при обработке: {e}")

    def update_progress(self, current, total):
        progress = (current / total) * 100
        self.progress_bar.setValue(int(progress))



    def cancel_processing(self):
        self.stop_processing = True
        self._processing = False  # ← ДОБАВЬТЕ ЭТУ СТРОКУ
        if self.processor:
            self.processor.cancel()

        # Завершаем поток если он существует
        if hasattr(self, 'processing_thread') and self.processing_thread.isRunning():
            self.processing_thread.quit()
            self.processing_thread.wait()

        self.processing_finished()

    def after(self, ms, func):
        QTimer.singleShot(ms, func)




class Endurance_tdms_logs_dealer:
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self._cancel = False
        self.signal_manager = SignalManager()  # Добавляем менеджер сигналов

    def __del__(self):
        """Очистка ресурсов при удалении объекта"""
        try:
            plt.close('all')  # Закрываем все фигуры matplotlib
        except:
            pass

    def debug_tdms_structure(self, file_path):
        """
        Детальный анализ структуры TDMS файла
        """
        print(f"\n{'='*60}")
        print(f"АНАЛИЗ СТРУКТУРЫ TDMS ФАЙЛА:")
        print(f"Файл: {os.path.basename(file_path)}")
        print(f"{'='*60}")

        try:
            # Чтение файла
            tdms_file = TdmsFile.read(file_path)

            # Получаем все группы
            print(f"\nГРУППЫ в файле:")
            groups = list(tdms_file.groups())
            print(f"Всего групп: {len(groups)}")

            for i, group in enumerate(groups):
                print(f"\n  Группа #{i+1}: '{group.name}'")
                print(f"  Путь: {group.path}")

                # Получаем каналы в группе
                channels = list(group.channels())
                print(f"  Каналов в группе: {len(channels)}")

                # Анализ каждого канала
                for j, channel in enumerate(channels[:10]):  # Показываем первые 10
                    print(f"    Канал #{j+1}: '{channel.name}'")
                    print(f"      Путь: {channel.path}")
                    print(f"      Тип данных: {channel.data_type}")
                    if hasattr(channel, 'length'):
                        print(f"      Количество точек: {channel.length}")

                    # Показываем пример данных
                    try:
                        data_sample = channel[:min(5, len(channel))]
                        print(f"      Пример данных (первые 5): {data_sample}")
                    except:
                        print(f"      Не удалось получить данные")

                if len(channels) > 10:
                    print(f"    ... и еще {len(channels) - 10} каналов")

            # Преобразуем в DataFrame для дополнительного анализа
            df = tdms_file.as_dataframe()

            print(f"\nДАННЫЕ В DATAFRAME:")
            print(f"Форма: {df.shape}")
            print(f"Колонки: {len(df.columns)}")

            # Группируем колонки по паттернам
            print(f"\nКАТЕГОРИЗАЦИЯ КОЛОНОК:")

            categories = {
                'time': [],
                'current': [],
                'pressure': [],
                'temperature': [],
                'voltage': [],
                'speed': [],
                'position': [],
                'status': [],
                'other': []
            }

            keywords = {
                'time': ['time', 'timestamp', 't_'],
                'current': ['current', 'curr', 'i_', 'ampere'],
                'pressure': ['pressure', 'press', 'bar', 'psi', 'pa'],
                'temperature': ['temp', 'temperature', '°c', 'deg'],
                'voltage': ['voltage', 'volt', 'v_', 'u_'],
                'speed': ['speed', 'rpm', 'velocity'],
                'position': ['position', 'pos', 'angle', 'deg'],
                'status': ['status', 'state', 'flag', 'error', 'alarm']
            }

            for col in df.columns:
                col_lower = col.lower()
                categorized = False

                for category, key_list in keywords.items():
                    for keyword in key_list:
                        if keyword in col_lower:
                            categories[category].append(col)
                            categorized = True
                            break
                    if categorized:
                        break

                if not categorized:
                    categories['other'].append(col)

            # Выводим категории
            for category, cols in categories.items():
                if cols:
                    print(f"\n  {category.upper()} ({len(cols)}):")
                    for col in cols[:10]:  # Показываем первые 10
                        print(f"    - {col}")
                    if len(cols) > 10:
                        print(f"    ... и еще {len(cols) - 10}")

            # Статистика по данным
            print(f"\nСТАТИСТИКА ПО ДАННЫМ:")
            print(f"Общее количество строк: {len(df)}")

            if not df.empty:
                time_cols = [col for col in df.columns if 'time' in col.lower()]
                if time_cols:
                    time_col = time_cols[0]
                    print(f"Временная колонка: {time_col}")
                    print(f"  Минимальное время: {df[time_col].min():.2f}")
                    print(f"  Максимальное время: {df[time_col].max():.2f}")
                    print(f"  Длительность: {df[time_col].max() - df[time_col].min():.2f} сек")

            print(f"\n{'='*60}")
            print("АНАЛИЗ ЗАВЕРШЕН")
            print(f"{'='*60}\n")

            return tdms_file, df

        except Exception as e:
            print(f"Ошибка при анализе файла: {e}")
            import traceback
            traceback.print_exc()
            return None, None


    def check_browser_available(self):
        """Проверяет доступность различных браузеров в системе"""
        import shutil
        import subprocess

        browsers = {
            'firefox': 'firefox',
            'chrome': 'google-chrome',
            'chromium': 'chromium',
            'brave': 'brave-browser',
            'edge': 'microsoft-edge',
            'xdg-open': 'xdg-open'
        }

        available = []

        for name, command in browsers.items():
            if shutil.which(command):
                available.append((name, command))
                print(f"✓ {name} доступен ({command})")
            else:
                print(f"✗ {name} не найден")

        return available



    def open_html_file_with_fallback(self, html_path):
        """
        Универсальный метод открытия HTML файлов с несколькими попытками
        """
        import platform
        import subprocess

        print(f"\nПопытка открыть HTML файл: {html_path}")

        # Проверяем существование файла
        if not os.path.exists(html_path):
            print(f"ОШИБКА: Файл {html_path} не найден!")
            return False

        # Получаем абсолютный путь
        abs_path = os.path.abspath(html_path)
        print(f"Абсолютный путь: {abs_path}")

        # Определяем ОС
        system = platform.system().lower()

        if system == 'linux':
            print("Обнаружена система: Linux")

            # Пробуем разные способы для Linux
            attempts = [
                # Способ 1: Через xdg-open (наиболее стандартный)
                lambda: subprocess.Popen(['xdg-open', abs_path]),

                # Способ 2: Через firefox напрямую
                lambda: subprocess.Popen(['firefox', abs_path]),

                # Способ 3: Через google-chrome
                lambda: subprocess.Popen(['google-chrome', abs_path]),

                # Способ 4: Через chromium
                lambda: subprocess.Popen(['chromium', abs_path]),

                # Способ 5: Через webbrowser (стандартная библиотека)
                lambda: webbrowser.open(f'file://{abs_path}'),
            ]

            browser_names = ['xdg-open', 'firefox', 'chrome', 'chromium', 'default browser']

            for i, (attempt_func, browser_name) in enumerate(zip(attempts, browser_names)):
                print(f"Попытка {i+1}: открыть через {browser_name}...")
                try:
                    # Проверяем, доступен ли браузер
                    if i < 4:  # Для xdg-open, firefox, chrome, chromium
                        import shutil
                        if browser_name == 'xdg-open':
                            # xdg-open должен быть всегда
                            pass
                        elif not shutil.which(browser_name):
                            print(f"  {browser_name} не найден, пропускаем...")
                            continue

                    # Пробуем открыть
                    attempt_func()

                    # Ждем немного
                    import time
                    time.sleep(2)

                    # Проверяем, открылся ли
                    print(f"  Успешно отправлена команда для {browser_name}")
                    return True

                except Exception as e:
                    print(f"  Ошибка при открытии через {browser_name}: {e}")
                    continue

            # Если все попытки не удались, показываем путь пользователю
            print(f"\n{'='*60}")
            print("НЕ УДАЛОСЬ ОТКРЫТЬ АВТОМАТИЧЕСКИ")
            print(f"HTML файл сохранен по пути:")
            print(f"{abs_path}")
            print(f"\nОткройте его вручную:")
            print(f"1. Откройте браузер (Firefox, Chrome и т.д.)")
            print(f"2. Нажмите Ctrl+O или выберите 'Open File'")
            print(f"3. Выберите файл: {abs_path}")
            print(f"{'='*60}\n")

            return False

        elif system == 'windows':
            # Для Windows используем стандартный способ
            print("Обнаружена система: Windows")
            try:
                webbrowser.open(f'file://{abs_path}')
                return True
            except Exception as e:
                print(f"Ошибка при открытии в Windows: {e}")
                return False

        else:
            # Для других ОС
            print(f"Обнаружена система: {system}")
            try:
                webbrowser.open(f'file://{abs_path}')
                return True
            except Exception as e:
                print(f"Ошибка при открытии: {e}")
                return False

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

        # СОЗДАЕМ ВРЕМЕННУЮ ДИРЕКТОРИЮ В ДОМАШНЕЙ ПАПКЕ, А НЕ В /tmp
        home_dir = os.path.expanduser("~")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        temp_dir = os.path.join(home_dir, f"tdms_analysis_{timestamp}")

        try:
            os.makedirs(temp_dir, exist_ok=True)
            print(f"Временная директория создана: {temp_dir}")
        except Exception as e:
            print(f"Ошибка при создании директории {temp_dir}: {e}")
            # Фолбэк на текущую директорию
            temp_dir = f"tdms_analysis_{timestamp}"
            os.makedirs(temp_dir, exist_ok=True)
            print(f"Создана директория в текущей папке: {temp_dir}")

        # Создание HTML файла - УПРОЩЕННЫЙ ШАБЛОН
        html_path = os.path.join(temp_dir, 'results.html')

        try:
            # Создаем базовый HTML без форматирования через .format()
            html_content = f'''<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TDMS Analysis Results</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f5f5f5;
            }}
            h1 {{
                color: #333;
                text-align: center;
            }}
            h2 {{
                color: #444;
                border-bottom: 2px solid #4CAF50;
                padding-bottom: 5px;
                margin-top: 30px;
            }}
            .image-container {{
                text-align: center;
                margin: 20px 0;
                padding: 10px;
                background-color: white;
                border-radius: 5px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            img {{
                max-width: 90%;
                height: auto;
                border: 1px solid #ddd;
                border-radius: 4px;
            }}
            .file-list {{
                background-color: white;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
            }}
            .file-list ul {{
                list-style-type: none;
                padding: 0;
            }}
            .file-list li {{
                padding: 5px;
                border-bottom: 1px solid #eee;
            }}
            .footer {{
                text-align: center;
                margin-top: 30px;
                color: #777;
                font-size: 0.9em;
            }}
        </style>
    </head>
    <body>
        <h1>TDMS Analysis Results</h1>
        <div class="file-list">
            <h3>Processed Files ({total_files} total):</h3>
            <ul>
    '''

            with open(html_path, 'w', encoding='utf-8') as html_file:
                html_file.write(html_content)

        except Exception as e:
            print(f"Ошибка при создании HTML файла: {e}")
            print(f"Детали ошибки: {type(e).__name__}: {e}")
            return

        # Список файлов
        try:
            with open(html_path, 'a', encoding='utf-8') as html_file:
                for i, tdms_file in enumerate(tdms_files, 1):
                    filename = os.path.basename(tdms_file)
                    html_file.write(f'            <li>{i}. {filename}</li>\n')

                html_file.write('''        </ul>
        </div>
        <hr>
    ''')
        except Exception as e:
            print(f"Ошибка при записи списка файлов: {e}")
            return

        # Обработка каждого файла
        successful_files = 0
        for i, tdms_file in enumerate(tdms_files, 1):
            if gui_instance.stop_processing or self._cancel:
                print("Обработка прервана пользователем")
                break

            print(f"Обработка файла {i}/{total_files}: {os.path.basename(tdms_file)}")

            try:
                plot_path = self.endu_tdms_log_handler(tdms_file, gui_instance, temp_dir)
                if plot_path:
                    try:
                        with open(html_path, 'a', encoding='utf-8') as html_file:
                            html_file.write(f'    <h2>{os.path.basename(tdms_file)}</h2>\n')
                            html_file.write(f'    <div class="image-container">\n')
                            html_file.write(f'        <img src="{os.path.basename(plot_path)}" alt="Graph">\n')
                            html_file.write(f'    </div>\n')
                            html_file.write(f'    <br>\n')

                        successful_files += 1
                        print(f"Файл успешно обработан")

                    except Exception as e:
                        print(f"Ошибка при записи в HTML: {e}")

            except Exception as e:
                print(f"Ошибка при обработке файла: {e}")
                import traceback
                traceback.print_exc()

            # Обновляем прогресс
            gui_instance.update_progress(i, total_files)
            time.sleep(0.1)

        # Завершение HTML
        try:
            with open(html_path, 'a', encoding='utf-8') as html_file:
                html_file.write(f'''
        <div class="footer">
            <hr>
            <p>Processing completed: {successful_files}/{total_files} files processed successfully</p>
            <p>Generated on: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p>Directory: {temp_dir}</p>
        </div>
    </body>
    </html>''')
        except Exception as e:
            print(f"Ошибка при завершении HTML: {e}")

        print(f"Обработка завершена. Успешно: {successful_files}/{total_files}")
        print(f"HTML отчет: {html_path}")

        # Открываем в браузере
        self.open_html_file_with_fallback(html_path)


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
            gui_instance.create_plots_requested.emit()  # Нужно создать сигнал

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

            # Добавляем между графиками больше чуть-чуть пространства, чтобы не
            # налезали буквы друг на друга.
            plt.subplots_adjust(hspace=0.270)

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

        table_data.append(['M. Energy', f'{motor_energy:,.4f}', 'J'])
        table_data.append(['ECU Energy', f'{ecu_energy:,.4f}', 'J'])

        # Добавляем статистику по току
        if 'Motor' in current_data_dict:
            motor_current = current_data_dict['Motor']
            table_data.append(['M. Current', '', ''])
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
        Упрощенный метод обработки файла с разноцветными графиками
        """
        print(f"Обработка файла: {os.path.basename(tdms_file_path)}")

        try:
            # Загрузка файла
            tdms_file = TdmsFile.read(tdms_file_path)
            df = tdms_file.as_dataframe()

            # Простой анализ сигналов
            print("\nАнализ сигналов...")
            signal_info = self.signal_manager.analyze_signals(df.columns.tolist())
            self.signal_manager.print_summary()

            # Временная колонка
            time_col = next((col for col in df.columns if 'time' in col.lower()), None)
            if not time_col:
                print("Временная колонка не найдена!")
                return None

            # Получаем сигналы для построения
            plot_signals = []
            for col, info in signal_info.items():
                if info['detected_type'] != 'other':
                    plot_signals.append((col, info))

            if not plot_signals:
                print("Нет интересных сигналов для графика")
                return None

            print(f"\nБудем строить {len(plot_signals)} сигналов")

            # Создаем график с двумя осями Y
            fig, ax1 = plt.subplots(figsize=(14, 8))

            # Разделяем сигналы по типам для разных осей
            current_signals = [(col, info) for col, info in plot_signals if info['is_current']]
            pressure_signals = [(col, info) for col, info in plot_signals if info['is_pressure']]
            voltage_signals = [(col, info) for col, info in plot_signals if info['detected_type'] == 'voltage']

            # Рисуем токи на основной оси (левая)
            for col, info in current_signals:
                ax1.plot(df[time_col], df[col],
                        label=info['display_name'],
                        color=info['color'],
                        linewidth=2)

            ax1.set_xlabel('Time (s)', fontsize=12)
            ax1.set_ylabel('Current (A)', color='black', fontsize=12)
            ax1.tick_params(axis='y', labelcolor='black')
            ax1.set_ylim(0, CURRENT_SCALE)

            # Создаем вторую ось для давления
            if pressure_signals:
                ax2 = ax1.twinx()
                ax2.set_ylabel('Pressure (bar)', color='black', fontsize=12)

                for col, info in pressure_signals:
                    ax2.plot(df[time_col], df[col],
                            label=info['display_name'],
                            color=info['color'],
                            linewidth=2,
                            linestyle='--')

                ax2.set_ylim(-5, 250)
                ax2.tick_params(axis='y', labelcolor='black')

            # Создаем третью ось для напряжения (если нужно)
            if voltage_signals and not pressure_signals:
                ax3 = ax1.twinx()
                ax3.set_ylabel('Voltage (V)', color='black', fontsize=12)

                for col, info in voltage_signals:
                    ax3.plot(df[time_col], df[col],
                            label=info['display_name'],
                            color=info['color'],
                            linewidth=1.5,
                            linestyle=':')

                ax3.set_ylim(0, 20)
                ax3.tick_params(axis='y', labelcolor='black')

            # Заголовок
            plt.title(f"TDMS Analysis: {os.path.basename(tdms_file_path)}", fontsize=14, fontweight='bold')

            # Легенда
            handles1, labels1 = ax1.get_legend_handles_labels()
            all_handles = handles1
            all_labels = labels1

            if pressure_signals:
                handles2, labels2 = ax2.get_legend_handles_labels()
                all_handles.extend(handles2)
                all_labels.extend(labels2)

            if voltage_signals and not pressure_signals:
                handles3, labels3 = ax3.get_legend_handles_labels()
                all_handles.extend(handles3)
                all_labels.extend(labels3)

            if all_handles:
                fig.legend(all_handles, all_labels, loc='upper center',
                          bbox_to_anchor=(0.5, -0.05), ncol=4, fontsize=10)

            # Сетка
            ax1.grid(True, alpha=0.2, linestyle='--')

            # Расчет и отображение энергии
            voltage = 12.0  # Предполагаемое напряжение
            energy_text = "Energy (J):\n"
            total_energy = 0.0

            for col, info in current_signals:
                try:
                    energy, _, _, _, _ = self.calculate_energy_joules(df, time_col, col, voltage)
                    energy_text += f"{info['display_name']}: {energy:.1f}\n"
                    total_energy += energy
                except:
                    pass

            if total_energy > 0:
                energy_text += f"Total: {total_energy:.1f}"
                props = dict(boxstyle='round', facecolor='white', alpha=0.9)
                plt.text(0.95, 0.95, energy_text, transform=ax1.transAxes, fontsize=9,
                        verticalalignment='top', horizontalalignment='right',
                        bbox=props, family='monospace')

            # Оптимизируем layout
            plt.tight_layout(rect=[0, 0.1, 1, 0.95])

            # Сохраняем
            plot_filename = f"plot_{os.path.basename(tdms_file_path).replace('.tdms', '')}.png"
            plot_path = os.path.join(temp_dir, plot_filename)
            plt.savefig(plot_path, dpi=150, bbox_inches='tight')
            plt.close()

            print(f"График сохранен: {plot_path}")
            return plot_path

        except Exception as e:
            print(f"Ошибка: {e}")
            import traceback
            traceback.print_exc()
            return None

    def open_html_file_in_browser(self, file_path):
        """
        Открывает HTML файл в браузере (специально для Linux)
        """
        try:
            # Получаем абсолютный путь
            abs_path = os.path.abspath(file_path)

            # Проверяем существование файла
            if not os.path.exists(abs_path):
                print(f"Файл {abs_path} не найден!")
                return False

            print(f"Пытаемся открыть: file://{abs_path}")

            # Пробуем разные способы открытия
            try:
                # Способ 1: Стандартный (для большинства браузеров)
                webbrowser.open(f'file://{abs_path}')

                # Ждем немного
                import time
                time.sleep(1)

                # Проверяем, открылся ли файл
                if not self.check_browser_opened(abs_path):
                    print("Стандартный способ не сработал, пробуем альтернативный...")

                    # Способ 2: Через xdg-open (Linux специфичный)
                    subprocess.Popen(['xdg-open', abs_path])

                    # Способ 3: Через firefox напрямую
                    time.sleep(2)
                    if not self.check_browser_opened(abs_path):
                        subprocess.Popen(['firefox', abs_path])

                return True

            except Exception as e:
                print(f"Ошибка при открытии в браузере: {e}")

                # Фолбэк: просто сообщаем пользователю путь
                print(f"\n\n{'='*60}")
                print(f"Файл сохранен по пути:")
                print(f"{abs_path}")
                print(f"\nОткройте его вручную в браузере.")
                print(f"{'='*60}\n")

                return False

        except Exception as e:
            print(f"Общая ошибка: {e}")
            return False

    def check_browser_opened(self, file_path):
        """Проверяет, открылся ли файл в браузере"""
        # Простая проверка - файл должен быть доступен
        return os.path.exists(file_path)



    def create_interactive_plot(self, file_path):
        """
        Создает интерактивный график только для активного участка и открывает в браузере
        """
        print(f"Создание интерактивного графика для: {file_path}")

        try:
            # Проверка флага отмены
            if self._cancel:
                print("Обработка прервана перед началом (флаг отмены активен)")
                return

            # Загрузка TDMS файла
            tdms_file = TdmsFile.read(file_path)
            df = tdms_file.as_dataframe()
            print(f"Колонки в DataFrame: {df.columns.tolist()}")

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

            # Находим активный участок
            active_start, active_end = self.find_active_section(df, time_col, motor_current_cols + ecu_current_cols)
            print(f"Активный участок: start={active_start}, end={active_end}")

            if active_start is None or active_end is None:
                print("Активный участок не найден!")
                return

            # Фильтруем DataFrame на активный участок
            mask = (df[time_col] >= active_start) & (df[time_col] <= active_end)
            df_active = df.loc[mask]
            if df_active.empty:
                print("Активный участок пустой!")
                return

            # Создаем интерактивный график с Plotly
            # Анализируем сигналы
            print(f"\nАнализ сигналов для интерактивного графика...")
            signal_info = self.signal_manager.analyze_signals(df.columns.tolist())

            # Создаем интерактивный график с Plotly
            fig = go.Figure()

            # Добавляем токи с их цветами
            current_signals = self.signal_manager.get_current_signals()
            for signal_name, info in current_signals.items():
                display_name = info['display_name']
                color = info['color']

                fig.add_trace(go.Scatter(
                    x=df_active[time_col],
                    y=df_active[signal_name],
                    mode='lines',
                    name=display_name,
                    line=dict(color=color, width=2),
                    opacity=0.8
                ))

            # Добавляем давления с их цветами
            pressure_signals = self.signal_manager.get_pressure_signals()
            if pressure_signals:
                for signal_name, info in pressure_signals.items():
                    display_name = info['display_name']
                    color = info['color']

                    fig.add_trace(go.Scatter(
                        x=df_active[time_col],
                        y=df_active[signal_name],
                        mode='lines',
                        name=display_name,
                        yaxis='y2',
                        line=dict(color=color, width=2, dash='dash'),
                        opacity=0.8
                    ))

            # Добавляем токи (левая ось)
            for col in motor_current_cols:
                short_name = col.split('/')[-1]
                short_name = short_name.split('Station one')[-1].strip() if 'Station one' in short_name else short_name
                fig.add_trace(go.Scatter(
                    x=df_active[time_col],
                    y=df_active[col],
                    mode='lines',
                    name=short_name,
                    line=dict(color='red')
                ))

            for col in ecu_current_cols:
                short_name = col.split('/')[-1]
                short_name = short_name.split('Station one')[-1].strip() if 'Station one' in short_name else short_name
                fig.add_trace(go.Scatter(
                    x=df_active[time_col],
                    y=df_active[col],
                    mode='lines',
                    name=short_name,
                    line=dict(color='blue')
                ))

            # Добавляем давления (правая ось)
            for col in pressure_cols:
                short_name = col.split('/')[-1]
                short_name = short_name.split('Station one')[-1].strip() if 'Station one' in short_name else short_name
                color = 'purple' if 'mc' in col.lower() else 'orange'
                fig.add_trace(go.Scatter(
                    x=df_active[time_col],
                    y=df_active[col],
                    mode='lines',
                    name=short_name,
                    yaxis='y2',
                    line=dict(color=color, dash='dash')
                ))

            # Настройка layout
            fig.update_layout(
                title=f"Interactive Graph for {os.path.basename(file_path)} (Active Section)",
                xaxis_title='Time (s)',
                yaxis_title='Current (A)',
                yaxis2=dict(
                    title='Pressure (bar)',
                    overlaying='y',
                    side='right',
                    range=[0, 250]
                ),
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
                margin=dict(t=100),
                hovermode='x unified'
            )

            # СОХРАНЯЕМ В ДОМАШНЮЮ ДИРЕКТОРИЮ ВМЕСТО /tmp
            home_dir = os.path.expanduser("~")
            html_filename = f"plotly_interactive_{os.path.basename(file_path).replace('.tdms', '')}_{int(time.time())}.html"
            html_path = os.path.join(home_dir, html_filename)

            # Сохраняем HTML файл
            fig.write_html(html_path)
            print(f"HTML файл сохранен: {html_path}")

            # Открываем в браузере - КОРРЕКТНЫЙ СПОСОБ ДЛЯ LINUX
            self.open_html_file_in_browser(html_path)

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
        Универсальный метод открытия HTML файлов
        """
        try:
            # Преобразуем путь в абсолютный
            abs_path = os.path.abspath(file_path)

            # Проверяем существование файла
            if not os.path.exists(abs_path):
                print(f"Файл {abs_path} не найден!")
                return False

            # Определяем ОС
            import platform
            system = platform.system().lower()

            if system == 'linux':
                # Для Linux используем специальный метод
                return self.open_html_file_in_browser(abs_path)
            else:
                # Для Windows и других ОС - стандартный способ
                webbrowser.open(f'file://{abs_path}')
                return True

        except Exception as e:
            print(f"Ошибка при открытии HTML файла: {e}")
            return False



class SignalManager:
    """Класс для управления названиями и цветами сигналов"""

    # Стандартные цвета для разных типов сигналов
    DEFAULT_COLORS = {
        'motor_current': '#FF0000',  # Красный
        'ecu_current': '#0000FF',    # Синий
        'pressure_mc': '#FF4500',    # Красно-оранжевый
        'pressure_rl': '#32CD32',    # Лаймовый
        'pressure_fr': '#1E90FF',    # Синий доджер
        'pressure_fl': '#FF1493',    # Глубокий розовый
        'pressure_rr': '#FFD700',    # Золотой
        'voltage': '#9370DB',        # Фиолетовый
        'default': '#A9A9A9'         # Серый
    }

    def __init__(self):
        self.signal_info = {}

    def analyze_signals(self, df_columns):
        """Простой анализ сигналов"""
        self.signal_info = {}

        for col in df_columns:
            col_lower = col.lower()
            signal_type = 'other'
            color = self.DEFAULT_COLORS['default']

            # Определяем тип сигнала и цвет
            if 'motor current' in col_lower:
                signal_type = 'motor_current'
                color = self.DEFAULT_COLORS['motor_current']
            elif 'ecu current' in col_lower:
                signal_type = 'ecu_current'
                color = self.DEFAULT_COLORS['ecu_current']
            elif 'ecu voltage' in col_lower:
                signal_type = 'voltage'
                color = self.DEFAULT_COLORS['voltage']
            elif 'mc-(p1)' in col_lower:
                signal_type = 'pressure_mc'
                color = '#FF4500'  # Красно-оранжевый для MC
            elif 'rl-(p2)' in col_lower:
                signal_type = 'pressure_rl'
                color = '#32CD32'  # Лаймовый для RL
            elif 'fr-(p3)' in col_lower:
                signal_type = 'pressure_fr'
                color = '#1E90FF'  # Синий доджер для FR
            elif 'fl-(p4)' in col_lower:
                signal_type = 'pressure_fl'
                color = '#FF1493'  # Глубокий розовый для FL
            elif 'rr-(p5)' in col_lower:
                signal_type = 'pressure_rr'
                color = '#FFD700'  # Золотой для RR

            # Простое отображаемое имя
            display_name = col
            if 'station two' in col_lower:
                if 'mc-(p1)' in col_lower:
                    display_name = 'MC Pressure'
                elif 'rl-(p2)' in col_lower:
                    display_name = 'RL Pressure'
                elif 'fr-(p3)' in col_lower:
                    display_name = 'FR Pressure'
                elif 'fl-(p4)' in col_lower:
                    display_name = 'FL Pressure'
                elif 'rr-(p5)' in col_lower:
                    display_name = 'RR Pressure'
                elif 'motor current' in col_lower:
                    display_name = 'Motor Current'
                elif 'ecu current' in col_lower:
                    display_name = 'ECU Current'
                elif 'ecu voltage' in col_lower:
                    display_name = 'ECU Voltage'

            self.signal_info[col] = {
                'original_name': col,
                'detected_type': signal_type,
                'color': color,
                'display_name': display_name,
                'is_current': signal_type in ['motor_current', 'ecu_current'],
                'is_pressure': 'pressure' in signal_type
            }

        return self.signal_info

    def print_summary(self):
        """Простая сводка"""
        print("\n" + "="*60)
        print("ПРОСТАЯ СВОДКА СИГНАЛОВ:")
        print("="*60)

        for name, info in self.signal_info.items():
            if info['detected_type'] != 'other':  # Только интересные сигналы
                print(f"{info['display_name']}: {info['detected_type']}, цвет: {info['color']}")

# Запуск приложения
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GuiDataChooser()
    window.show()
    sys.exit(app.exec())
