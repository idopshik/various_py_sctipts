import pandas as pd
import can
import re
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt
from scipy import stats
from tqdm import tqdm
import matplotlib.pyplot as plt

from canlib import canlib, kvadblib, Frame

from defs import *

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

decode_prblm = {}


# Добавляем константу порога замедления в начало файла (после импортов)
# Настройки кэширования
CACHE_ENABLED = True  # Включить кэширование
OVERWRITE_CACHE = False  # Перезаписывать кэш, даже если он есть
CACHE_DIR = "cache"  # Папка для кэша
DECEL_THRESHOLD = -0.3  # м/с², минимальное замедление для фильтрации

# Создаем папку для кэша если её нет
Path(CACHE_DIR).mkdir(exist_ok=True)



# анализ тормозной эффектиности от торможения к торможению

# Добавляем константы для детекции торможений в начало файла
BRAKING_DETECTION = {
    'min_speed_decrease': 10,      # минимальное снижение скорости для детекции торможения (км/ч)
    'min_deceleration': 0.1,       # минимальное замедление для детекции (м/с²)
    'min_pressure': 5.0,           # минимальное давление для детекции (бар)
    'min_duration': 1.0,           # минимальная длительность торможения (секунды)
    'cooldown': 2.0                # время между торможениями для разделения (секунды)
}


def advanced_braking_analysis(df):
    """
    Расширенный анализ тормозной эффективности
    """
    # Коэффициент трения (приблизительно)
    df['friction_coefficient'] = df['deceleration'] / 9.81

    # Тормозной момент (пропорционально давлению)
    df['braking_force'] = df['deceleration'] * 1000  # Примерно для легкового автомобиля

    # Эффективность в %
    max_deceleration = df['deceleration'].max()
    df['efficiency_percent'] = (df['deceleration'] / max_deceleration) * 100

    # График эффективности в %
    plt.figure(figsize=(12, 6))
    plt.scatter(df['brake_pressure'], df['efficiency_percent'], alpha=0.3, s=10)
    plt.xlabel('Давление (бар)')
    plt.ylabel('Эффективность (%)')
    plt.title('Тормозная эффективность в процентах')
    plt.grid(True)
    plt.savefig('braking_efficiency_percent.png', dpi=300)
    plt.show()




def analyze_braking_efficiency(df, pressure_col='brake_pressure', decel_col='deceleration',
                              speed_col='speed', min_speed=10, max_speed=200):
    """
    Анализ тормозной эффективности
    """
    # Фильтруем данные по скорости (торможение обычно выше 10 км/ч)
    filtered_df = df[(df[speed_col] >= min_speed) & (df[speed_col] <= max_speed)].copy()

    # Убедимся, что данные в правильных единицах измерения
    # Давление: обычно в бар, замедление: м/с², скорость: км/ч

    # Создаем scatter plot
    plt.figure(figsize=(12, 8))

    # Scatter plot зависимости замедления от давления
    plt.scatter(filtered_df[pressure_col], filtered_df[decel_col],
                alpha=0.3, s=10, c=filtered_df[speed_col], cmap='viridis')

    # Добавляем colorbar для скорости
    plt.colorbar(label='Скорость (км/ч)')

    # Линейная регрессия для общей эффективности
    slope, intercept, r_value, p_value, std_err = stats.linregress(
        filtered_df[pressure_col], filtered_df[decel_col]
    )

    # Генерируем линию регрессии
    x_range = np.linspace(filtered_df[pressure_col].min(), filtered_df[pressure_col].max(), 100)
    y_pred = slope * x_range + intercept

    plt.plot(x_range, y_pred, 'r-', linewidth=3,
             label=f'Эффективность: {slope:.3f} м/с²/бар\nR² = {r_value**2:.3f}')

    plt.xlabel('Давление в тормозной системе (бар)')
    plt.ylabel('Поперечное ускорение (замедление) (м/с²)')
    plt.title('Тормозная эффективность: Замедление vs Давление')
    plt.grid(True, alpha=0.3)
    plt.legend()

    # Сохраняем график
    plt.savefig('braking_efficiency.png', dpi=300, bbox_inches='tight')
    plt.show()

    return slope, r_value**2

# Если нужно анализировать по диапазонам скорости
def analyze_by_speed_ranges(df, pressure_col='brake_pressure', decel_col='deceleration',
                           speed_col='speed', speed_ranges=[(0, 50), (50, 100), (100, 200)]):
    """
    Анализ эффективности по диапазонам скорости
    """

    plt.figure(figsize=(14, 10))

    colors = ['blue', 'green', 'red', 'orange', 'purple']

    for i, (min_speed, max_speed) in enumerate(speed_ranges):
        # Фильтруем по диапазону скорости
        speed_df = df[(df[speed_col] >= min_speed) & (df[speed_col] < max_speed)].copy()

        if len(speed_df) > 10:  # Минимум точек для анализа
            # Линейная регрессия
            slope, intercept, r_value, p_value, std_err = stats.linregress(
                speed_df[pressure_col], speed_df[decel_col]
            )

            # Scatter plot
            plt.scatter(speed_df[pressure_col], speed_df[decel_col],
                       alpha=0.2, s=8, color=colors[i % len(colors)])

            # Линия регрессии
            x_range = np.linspace(speed_df[pressure_col].min(), speed_df[pressure_col].max(), 100)
            y_pred = slope * x_range + intercept

            plt.plot(x_range, y_pred, color=colors[i % len(colors)], linewidth=2,
                    label=f'{min_speed}-{max_speed} км/ч: {slope:.3f} м/с²/бар (R²={r_value**2:.3f})')

    plt.xlabel('Давление в тормозной системе (бар)')
    plt.ylabel('Поперечное ускорение (замедление) (м/с²)')
    plt.title('Тормозная эффективность по диапазонам скорости')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.savefig('braking_efficiency_by_speed.png', dpi=300, bbox_inches='tight')
    plt.show()



def prepare_braking_data(df):
    """
    Подготовка данных для анализа торможения
    """
    # Убедитесь, что колонки имеют правильные имена
    # Если нужно переименовать:
    df = df.rename(columns={

        'pressure': 'brake_pressure',
        'deceleration': 'deceleration',
        'speed': 'speed'
    })

    # Фильтрация: только данные при нажатии тормоза
    # (когда давление > 0 и замедление > 0)
    braking_df = df[(df['brake_pressure'] > 0) & (df['deceleration'] > 0)].copy()

    # Очистка от выбросов
    braking_df = braking_df[
        (braking_df['deceleration'] < 20) &  # Максимальное реалистичное замедление
        (braking_df['brake_pressure'] < 200)  # Максимальное реалистичное давление
    ]

    return braking_df




def message_interpreter(db, frame):
    try:
        bmsg = db.interpret(frame)
    except kvadblib.KvdNoMessage:
        if frame.id in decode_prblm:
            decode_prblm[frame.id] += 1
        else:
            decode_prblm[frame.id] = 1
        return

    if not bmsg._message.dlc == bmsg._frame.dlc:
        if "dlc_mistake" in decode_prblm:
            decode_prblm["dlc_mistake"] += 1
        else:
            decode_prblm["dlc_mistake"] = 1
        return
    return bmsg



def frameproceed(db, frame) -> None:
    if frame.id == DID_SPEED_MESSAGE_XGF or frame.id == DID_SPEED_MESSAGE_XGD:
        bmsg = message_interpreter(db, frame)
        try:
            for bsig in bmsg:
                if bsig.name == "VehicleSpeed":
                    #  self.current_speed = bsig.value
                    return {'speed': bsig.value}
        except TypeError as e:
            print(e)

    if frame.id == DID_BRAKING_PRESSURE_MESSAGE_XGF:
        bmsg = message_interpreter(db, frame)
        try:
            for bsig in bmsg:
                if bsig.name == "BrakingPressure":
                    #  self.current_pressue = bsig.value
                    return {'pressure': bsig.value}
        except TypeError as e:
            print(e)

    if frame.id == DID_BRAKING_DECELERATION_XGF:
        bmsg = message_interpreter(db, frame)
        try:
            for bsig in bmsg:
                if bsig.name == "LongitudinalAccelerationProc":
                    current_deceleration = bsig.value
                    return {'deceleration': bsig.value}

        except TypeError as e:
            print(e)


def proceed_file(ttmppath, chunk_size=50000):


    print("starting proceeding...")

    """Обрабатывает BLF файл с поддержкой кэширования"""

    # Проверяем кэш перед обработкой
    if CACHE_ENABLED and not OVERWRITE_CACHE and is_cache_valid(ttmppath):
        return load_from_cache(ttmppath)


    v_type = VESTA_DBC
    db = kvadblib.Dbc(v_type)

    chunks = []
    current_chunk = []
    last_values = {'pressure': None, 'deceleration': None, 'speed': None}

    with open(ttmppath, "rb") as rr:
        log_in = can.io.BLFReader(rr)
        log_in_iter = log_in.__iter__()
        object_count = log_in.object_count
        i = 0
        try:
            for i in tqdm(range(object_count)):





                aa = log_in_iter.__next__()

                frame = Frame(aa.arbitration_id, aa.data, timestamp=aa.timestamp)

                parsed_data = frameproceed(db, frame)

                if parsed_data:
                    last_values.update(parsed_data)

                    # Создаем запись с текущими значениями всех параметров


                    # ФИЛЬТРАЦИЯ ПО ЗАМЕДЛЕНИЮ - добавляем только если замедление выше порога
                    if last_values['deceleration'] is not None and last_values['deceleration'] <= DECEL_THRESHOLD:
                        record = {
                            'timestamp': aa.timestamp,
                            'pressure': last_values['pressure'],
                            'deceleration': last_values['deceleration'],
                            'speed': last_values['speed']
                        }
                        current_chunk.append(record)

                # Сохраняем чанк при достижении размера
                if len(current_chunk) >= chunk_size:
                    chunk_df = pd.DataFrame(current_chunk)
                    chunks.append(chunk_df)
                    current_chunk = []
                    print(f"Создан чанк {len(chunks)}")


            # Последний чанк
            if current_chunk:
                chunks.append(pd.DataFrame(current_chunk))

        except StopIteration:
            pass
            # print("end of file")
        finally:
            pass

    # Объединяем все чанки
    final_df = pd.concat(chunks, ignore_index=True)

    # Заполняем пропуски (если какие-то параметры не были в начале)
    final_df = final_df.ffill()

    return final_df



def show_interractive_graph(df):
    # Интерактивный график всех параметров
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                       subplot_titles=('Тормозное давление', 'Замедление', 'Скорость'))

    # Давление
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['pressure'],
                            mode='lines', name='Давление', line=dict(color='red')),
                 row=1, col=1)

    # Замедление
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['deceleration'],
                            mode='lines', name='Замедление', line=dict(color='green')),
                 row=2, col=1)

    # Скорость
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['speed'],
                            mode='lines', name='Скорость', line=dict(color='blue')),
                 row=3, col=1)

    fig.update_layout(height=800, title_text="Параметры торможения")
    fig.update_xaxes(title_text="Время (секунды)", row=3, col=1)
    fig.show()

    # Сохраняем как HTML
    fig.write_html("interactive_plot.html")



def show_simple_three(df):
    # Создаем график с тремя субплoтами
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 10), sharex=True)

    # Давление
    ax1.plot(df['timestamp'], df['pressure'], 'r-', linewidth=1, alpha=0.8)
    ax1.set_ylabel('Давление (бар)')
    ax1.set_title('Тормозное давление')
    ax1.grid(True, alpha=0.3)

    # Замедление
    ax2.plot(df['timestamp'], df['deceleration'], 'g-', linewidth=1, alpha=0.8)
    ax2.set_ylabel('Замедление (м/с²)')
    ax2.set_title('Поперечное ускорение (замедление)')
    ax2.grid(True, alpha=0.3)

    # Скорость
    ax3.plot(df['timestamp'], df['speed'], 'b-', linewidth=1, alpha=0.8)
    ax3.set_ylabel('Скорость (км/ч)')
    ax3.set_xlabel('Время (секунды)')
    ax3.set_title('Скорость автомобиля')
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('all_parameters.png', dpi=300, bbox_inches='tight')
    plt.show()


def doesnt_work(df):

    braking_data = df[(df['pressure'] > 5) & (df['deceleration'] > 0.5)].copy()

    plt.figure(figsize=(12, 8))
    plt.scatter(braking_data['pressure'], braking_data['deceleration'],
               alpha=0.5, s=20, c=braking_data['speed'], cmap='viridis')
    plt.colorbar(label='Скорость (км/ч)')
    plt.xlabel('Тормозное давление (бар)')
    plt.ylabel('Замедление (м/с²)')
    plt.title('Тормозная эффективность')
    plt.grid(True, alpha=0.3)
    plt.savefig('braking_efficiency.png', dpi=300, bbox_inches='tight')

# НОВАЯ ФУНКЦИЯ ДЛЯ ПОСТРОЕНИЯ ГРАФИКА DECELERATION-TIME
def plot_deceleration_time(df):
    """
    Построение графика замедления от времени
    """
    if df.empty:
        print("DataFrame пустой, невозможно построить график")
        return

    plt.figure(figsize=(15, 8))

    # Основной график замедления
    plt.plot(df['timestamp'], df['deceleration'],
             'b-', linewidth=1.5, alpha=0.8, label='Замедление')

    # Добавляем горизонтальную линию порога
    plt.axhline(y=DECEL_THRESHOLD, color='r', linestyle='--',
                alpha=0.7, label=f'Порог ({DECEL_THRESHOLD} м/с²)')

    plt.xlabel('Время (секунды)')
    plt.ylabel('Замедление (м/с²)')
    plt.title(f'График замедления от времени (фильтр: ≥{DECEL_THRESHOLD} м/с²)')
    plt.grid(True, alpha=0.3)
    plt.legend()

    # Добавляем статистику
    avg_decel = df['deceleration'].mean()
    max_decel = df['deceleration'].max()
    plt.text(0.02, 0.98, f'Среднее: {avg_decel:.2f} м/с²\nМаксимум: {max_decel:.2f} м/с²',
             transform=plt.gca().transAxes, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    plt.tight_layout()
    plt.savefig('deceleration_time_plot.png', dpi=300, bbox_inches='tight')
    plt.show()

    print(f"Построен график deceleration-time с {len(df)} точками")
    print(f"Диапазон замедления: {df['deceleration'].min():.2f} - {df['deceleration'].max():.2f} м/с²")


def get_cache_filename(blf_path):
    """Генерирует имя файла кэша на основе пути к BLF файлу"""
    filename = Path(blf_path).stem
    cache_name = f"{filename}_decel_{DECEL_THRESHOLD}.csv"
    return Path(CACHE_DIR) / cache_name

def is_cache_valid(blf_path):
    """Проверяет, существует ли актуальный кэш"""
    if not CACHE_ENABLED:
        return False

    cache_path = get_cache_filename(blf_path)
    blf_path_obj = Path(blf_path)

    # Проверяем существование кэша и исходного файла
    if not cache_path.exists() or not blf_path_obj.exists():
        return False

    # Проверяем, что кэш новее исходного файла
    cache_mtime = cache_path.stat().st_mtime
    blf_mtime = blf_path_obj.stat().st_mtime

    return cache_mtime > blf_mtime

def save_to_cache(df, blf_path):
    """Сохраняет DataFrame в кэш"""
    if not CACHE_ENABLED:
        return

    cache_path = get_cache_filename(blf_path)
    df.to_csv(cache_path, index=False)
    print(f"Данные сохранены в кэш: {cache_path}")

def load_from_cache(blf_path):
    """Загружает DataFrame из кэша"""
    cache_path = get_cache_filename(blf_path)
    df = pd.read_csv(cache_path)

    # Конвертируем timestamp обратно в float (если нужно)
    if 'timestamp' in df.columns:
        df['timestamp'] = df['timestamp'].astype(float)

    print(f"Данные загружены из кэша: {cache_path}")
    return df

def plot_deceleration_time_advanced(df):
    """
    Расширенный график с дополнительной информацией
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)

    # График замедления
    ax1.plot(df['timestamp'], df['deceleration'], 'b-', linewidth=1.5)
    ax1.axhline(DECEL_THRESHOLD, color='r', linestyle='--')
    ax1.set_ylabel('Замедление (м/с²)')
    ax1.set_title('Замедление от времени')
    ax1.grid(True, alpha=0.3)

    # График скорости (для контекста)
    ax2.plot(df['timestamp'], df['speed'], 'g-', linewidth=1.5)
    ax2.set_ylabel('Скорость (км/ч)')
    ax2.set_xlabel('Время (секунды)')
    ax2.set_title('Скорость от времени')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('deceleration_speed_plot.png', dpi=300)
    plt.show()


def print_statistics(df):
    """Вывод статистики по давлению"""
    if not df['pressure'].isna().all():
        pressure_data = df['pressure'].dropna()
        print("\n" + "="*50)
        print("СТАТИСТИКА ДАВЛЕНИЯ:")
        print("="*50)
        print(f"Всего записей: {len(pressure_data)}")
        print(f"Среднее давление: {pressure_data.mean():.2f} бар")
        print(f"Максимальное давление: {pressure_data.max():.2f} бар")
        print(f"Минимальное давление: {pressure_data.min():.2f} бар")
        print(f"Стандартное отклонение: {pressure_data.std():.2f} бар")
        print(f"Медиана: {pressure_data.median():.2f} бар")

        # Количество торможений (давление выше порога)
        braking_threshold = 5.0  # бар
        braking_events = len(pressure_data[pressure_data > braking_threshold])
        print(f"Торможений (давление > {braking_threshold} бар): {braking_events}")
        print("="*50)
def plot_pressure_time_advanced(df, window_size=100, show_speed=False, save_plot=True):
    """
    Расширенный график давления от времени с дополнительными опциями

    Parameters:
    df - DataFrame с данными
    window_size - размер окна для скользящего среднего
    show_speed - показывать скорость на втором графике
    save_plot - сохранять график в файл
    """
    if df.empty:
        print("DataFrame пустой, невозможно построить график")
        return

    if show_speed:
        # Два субплога: давление и скорость
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)

        # График давления
        ax1.plot(df['timestamp'], df['pressure'], 'r-', linewidth=1.5, alpha=0.7, label='Давление')

        # Скользящее среднее давления
        if len(df) > window_size:
            df['pressure_ma'] = df['pressure'].rolling(window=window_size, min_periods=1).mean()
            ax1.plot(df['timestamp'], df['pressure_ma'], 'r--', linewidth=2, alpha=0.9, label=f'Скользящее среднее ({window_size})')

        ax1.set_ylabel('Давление (бар)')
        ax1.set_title('Давление в тормозной системе от времени')
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        # График скорости
        ax2.plot(df['timestamp'], df['speed'], 'b-', linewidth=1.5, alpha=0.7, label='Скорость')
        ax2.set_ylabel('Скорость (км/ч)')
        ax2.set_xlabel('Время (секунды)')
        ax2.set_title('Скорость автомобиля')
        ax2.grid(True, alpha=0.3)
        ax2.legend()

    else:
        # Один график давления
        fig, ax1 = plt.subplots(1, 1, figsize=(15, 8))

        ax1.plot(df['timestamp'], df['pressure'], 'r-', linewidth=1.5, alpha=0.8, label='Давление')

        # Скользящее среднее
        if len(df) > window_size:
            df['pressure_ma'] = df['pressure'].rolling(window=window_size, min_periods=1).mean()
            ax1.plot(df['timestamp'], df['pressure_ma'], 'r--', linewidth=2, alpha=0.9, label=f'Скользящее среднее ({window_size})')

        ax1.set_xlabel('Время (секунды)')
        ax1.set_ylabel('Давление (бар)')
        ax1.set_title('Давление в тормозной системе от времени')
        ax1.grid(True, alpha=0.3)
        ax1.legend()

    plt.tight_layout()

    if save_plot:
        filename = 'pressure_time_advanced.png' if not show_speed else 'pressure_speed_time_plot.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')

    plt.show()

    # Статистика
    print_statistics(df)




def plot_pressure_time(df, show_stats=True, save_plot=True):
    """
    Построение графика давления от времени

    Parameters:
    df - DataFrame с данными
    show_stats - показывать статистику на графике
    save_plot - сохранять график в файл
    """
    if df.empty:
        print("DataFrame пустой, невозможно построить график давления")
        return

    plt.figure(figsize=(15, 8))

    # Основной график давления
    plt.plot(df['timestamp'], df['pressure'],
             'r-', linewidth=1.5, alpha=0.8, label='Давление')

    plt.xlabel('Время (секунды)')
    plt.ylabel('Давление (бар)')
    plt.title('График давления в тормозной системе от времени')
    plt.grid(True, alpha=0.3)
    plt.legend()

    # Добавляем статистику если нужно
    if show_stats:
        avg_pressure = df['pressure'].mean()
        max_pressure = df['pressure'].max()
        min_pressure = df['pressure'].min()

        stats_text = f'Среднее: {avg_pressure:.1f} бар\nМаксимум: {max_pressure:.1f} бар\nМинимум: {min_pressure:.1f} бар'

        plt.text(0.02, 0.98, stats_text,
                 transform=plt.gca().transAxes, verticalalignment='top',
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    plt.tight_layout()

    if save_plot:
        plt.savefig('pressure_time_plot.png', dpi=300, bbox_inches='tight')

    plt.show()

    # Выводим статистику в консоль
    if not df['pressure'].isna().all():
        print(f"Статистика давления:")
        print(f"  Всего точек: {len(df['pressure'].dropna())}")
        print(f"  Среднее давление: {df['pressure'].mean():.2f} бар")
        print(f"  Максимальное давление: {df['pressure'].max():.2f} бар")
        print(f"  Минимальное давление: {df['pressure'].min():.2f} бар")
        print(f"  Стандартное отклонение: {df['pressure'].std():.2f} бар")
    else:
        print("Нет данных о давлении для анализа")





def plot_pressure_deceleration_advanced(df, speed_bins=[0, 50, 100, 150, 200], save_plot=True):
    """
    Расширенный график давление-замедление с группировкой по скорости

    Parameters:
    df - DataFrame с данными
    speed_bins - границы диапазонов скорости
    save_plot - сохранять график в файл
    """
    if df.empty:
        print("DataFrame пустой, невозможно построить график")
        return

    plot_data = df.dropna(subset=['pressure', 'deceleration', 'speed'])

    if plot_data.empty:
        print("Нет данных для построения графика")
        return

    # Создаем диапазоны скорости
    speed_labels = [f'{speed_bins[i]}-{speed_bins[i+1]} км/ч' for i in range(len(speed_bins)-1)]
    plot_data['speed_range'] = pd.cut(plot_data['speed'], bins=speed_bins, labels=speed_labels)

    plt.figure(figsize=(14, 10))
    colors = plt.cm.tab10(np.linspace(0, 1, len(speed_labels)))

    for i, speed_range in enumerate(speed_labels):
        range_data = plot_data[plot_data['speed_range'] == speed_range]

        if len(range_data) > 5:  # Минимум точек для анализа
            plt.scatter(range_data['pressure'], range_data['deceleration'],
                       alpha=0.6, s=25, color=colors[i], label=speed_range)

            # Регрессия для каждого диапазона
            slope, intercept, r_value, p_value, std_err = stats.linregress(
                range_data['pressure'], range_data['deceleration']
            )

            x_range = np.linspace(range_data['pressure'].min(), range_data['pressure'].max(), 100)
            y_pred = slope * x_range + intercept

            plt.plot(x_range, y_pred, color=colors[i], linewidth=2, linestyle='--',
                    alpha=0.8, label=f'{speed_range}: {slope:.3f} м/с²/бар (R²={r_value**2:.3f})')

    plt.xlabel('Давление (бар)')
    plt.ylabel('Замедление (м/с²)')
    plt.title('Зависимость замедления от давления по диапазонам скорости')
    plt.grid(True, alpha=0.3)
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

    plt.tight_layout()

    if save_plot:
        plt.savefig('pressure_deceleration_advanced.png', dpi=300, bbox_inches='tight')

    plt.show()

    # Детальная статистика по диапазонам
    print_detailed_stats(plot_data, speed_labels)











def detect_braking_events(df, config=None):
    """
    Детектирует отдельные события торможения в данных
    """
    if config is None:
        config = BRAKING_DETECTION

    if df.empty:
        print("DataFrame пустой, невозможно детектировать торможения")
        return []

    # Создаем копию данных для работы
    data = df.copy()

    # Вычисляем производные для детекции изменений
    data['speed_diff'] = data['speed'].diff()
    data['deceleration_abs'] = data['deceleration'].abs()

    # Ищем моменты начала торможения
    braking_start_conditions = (
        (data['deceleration_abs'] >= config['min_deceleration']) &
        (data['pressure'] >= config['min_pressure']) &
        (data['speed_diff'] < 0)  # скорость уменьшается
    )

    braking_starts = data[braking_start_conditions].index.tolist()

    if not braking_starts:
        print("Не найдено событий торможения")
        return []

    # Группируем последовательные точки начала торможения в события
    braking_events = []
    current_event = None

    for i, idx in enumerate(braking_starts):
        timestamp = data.loc[idx, 'timestamp']

        if current_event is None:
            # Начало нового события
            current_event = {
                'start_index': idx,
                'start_time': timestamp,
                'end_index': idx,
                'end_time': timestamp,
                'indices': [idx]
            }
        else:
            # Проверяем, продолжается ли текущее событие
            time_diff = timestamp - current_event['end_time']

            if time_diff <= config['cooldown']:
                # Продолжение текущего события
                current_event['end_index'] = idx
                current_event['end_time'] = timestamp
                current_event['indices'].append(idx)
            else:
                # Завершаем текущее событие и начинаем новое
                if is_valid_braking_event(data, current_event, config):
                    braking_events.append(current_event)

                current_event = {
                    'start_index': idx,
                    'start_time': timestamp,
                    'end_index': idx,
                    'end_time': timestamp,
                    'indices': [idx]
                }

    # Добавляем последнее событие
    if current_event and is_valid_braking_event(data, current_event, config):
        braking_events.append(current_event)

    print(f"Обнаружено событий торможения: {len(braking_events)}")
    return braking_events

def is_valid_braking_event(data, event, config):
    """
    Проверяет, является ли событие валидным торможением
    """
    event_data = data.loc[event['indices']]

    # Проверяем длительность
    duration = event['end_time'] - event['start_time']
    if duration < config['min_duration']:
        return False

    # Проверяем снижение скорости
    speed_decrease = event_data['speed'].iloc[0] - event_data['speed'].iloc[-1]
    if speed_decrease < config['min_speed_decrease']:
        return False

    # Проверяем, что есть достаточное замедление
    max_deceleration = event_data['deceleration_abs'].max()
    if max_deceleration < config['min_deceleration']:
        return False

    return True

def extract_braking_event_data(df, event):
    """
    Извлекает данные для конкретного события торможения
    """
    return df.loc[event['indices']].copy()

def calculate_braking_efficiency(event_data):
    """
    Вычисляет эффективность торможения для события
    """
    if len(event_data) < 2:
        return None

    # Линейная регрессия давление-замедление
    slope, intercept, r_value, p_value, std_err = stats.linregress(
        event_data['pressure'], event_data['deceleration'].abs()
    )

    # Основные метрики
    max_pressure = event_data['pressure'].max()
    max_deceleration = event_data['deceleration'].abs().max()
    speed_decrease = event_data['speed'].iloc[0] - event_data['speed'].iloc[-1]
    duration = event_data['timestamp'].iloc[-1] - event_data['timestamp'].iloc[0]

    return {
        'efficiency': slope,  # м/с²/бар
        'r_squared': r_value**2,
        'max_pressure': max_pressure,
        'max_deceleration': max_deceleration,
        'speed_decrease': speed_decrease,
        'duration': duration,
        'start_speed': event_data['speed'].iloc[0],
        'end_speed': event_data['speed'].iloc[-1],
        'data_points': len(event_data)
    }

def analyze_braking_events(df, config=None):
    """
    Анализирует все события торможения и возвращает статистику
    """
    events = detect_braking_events(df, config)

    if not events:
        return None

    results = []

    for i, event in enumerate(events):
        event_data = extract_braking_event_data(df, event)
        efficiency = calculate_braking_efficiency(event_data)

        if efficiency:
            result = {
                'event_id': i + 1,
                'start_time': event['start_time'],
                'end_time': event['end_time'],
                **efficiency
            }
            results.append(result)

    return pd.DataFrame(results)

def plot_braking_events_timeline(df, braking_events):
    """
    Визуализирует временную линию с событиями торможения
    """
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), sharex=True)

    # Скорость с отметками торможений
    ax1.plot(df['timestamp'], df['speed'], 'b-', alpha=0.7, label='Скорость')
    for event in braking_events:
        ax1.axvspan(event['start_time'], event['end_time'], alpha=0.3, color='red')
    ax1.set_ylabel('Скорость (км/ч)')
    ax1.set_title('Скорость и события торможения')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # Давление
    ax2.plot(df['timestamp'], df['pressure'], 'r-', alpha=0.7, label='Давление')
    for event in braking_events:
        ax2.axvspan(event['start_time'], event['end_time'], alpha=0.3, color='red')
    ax2.set_ylabel('Давление (бар)')
    ax2.grid(True, alpha=0.3)

    # Замедление
    ax3.plot(df['timestamp'], df['deceleration'].abs(), 'g-', alpha=0.7, label='Замедление')
    for event in braking_events:
        ax3.axvspan(event['start_time'], event['end_time'], alpha=0.3, color='red')
    ax3.set_xlabel('Время (секунды)')
    ax3.set_ylabel('Замедление (м/с²)')
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('braking_events_timeline.png', dpi=300)
    plt.show()

def plot_braking_efficiency_trend(braking_stats):
    """
    График эффективности торможений по времени
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))

    # Эффективность по событиям
    ax1.plot(braking_stats['event_id'], braking_stats['efficiency'],
             'bo-', linewidth=2, markersize=8, label='Эффективность')
    ax1.set_xlabel('Номер торможения')
    ax1.set_ylabel('Эффективность (м/с²/бар)')
    ax1.set_title('Эффективность торможений по порядку')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # Эффективность по времени
    ax2.scatter(braking_stats['start_time'], braking_stats['efficiency'],
               c=braking_stats['start_speed'], cmap='viridis', s=100)
    ax2.set_xlabel('Время начала торможения')
    ax2.set_ylabel('Эффективность (м/с²/бар)')
    ax2.set_title('Эффективность торможений по времени')
    plt.colorbar(ax2.collections[0], ax=ax2, label='Начальная скорость (км/ч)')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('braking_efficiency_trend.png', dpi=300)
    plt.show()

def plot_efficiency_vs_speed(braking_stats):
    """
    Зависимость эффективности от начальной скорости
    """
    plt.figure(figsize=(12, 8))

    scatter = plt.scatter(braking_stats['start_speed'], braking_stats['efficiency'],
                         c=braking_stats['max_pressure'], cmap='plasma', s=100, alpha=0.7)

    plt.colorbar(scatter, label='Максимальное давление (бар)')
    plt.xlabel('Начальная скорость (км/ч)')
    plt.ylabel('Эффективность (м/с²/бар)')
    plt.title('Зависимость эффективности от начальной скорости и давления')
    plt.grid(True, alpha=0.3)

    # Линейная регрессия
    if len(braking_stats) > 2:
        slope, intercept, r_value, p_value, std_err = stats.linregress(
            braking_stats['start_speed'], braking_stats['efficiency']
        )

        x_range = np.linspace(braking_stats['start_speed'].min(),
                             braking_stats['start_speed'].max(), 100)
        y_pred = slope * x_range + intercept

        plt.plot(x_range, y_pred, 'r-', linewidth=2,
                label=f'Тренд: y = {slope:.4f}x + {intercept:.3f}\nR² = {r_value**2:.3f}')
        plt.legend()

    plt.tight_layout()
    plt.savefig('efficiency_vs_speed.png', dpi=300)
    plt.show()


def run_complex_braking_to_braking_analysis(df):
    if not df.empty:
        # Анализ отдельных торможений
        braking_events = detect_braking_events(df)
        braking_stats = analyze_braking_events(df)

        if braking_stats is not None:
            print("\nСТАТИСТИКА ТОРМОЖЕНИЙ:")
            print("="*50)
            print(braking_stats)

            print(f"\nСредняя эффективность: {braking_stats['efficiency'].mean():.4f} м/с²/бар")
            print(f"Стабильность эффективности: {braking_stats['efficiency'].std():.4f} м/с²/бар")

            # Визуализация
            plot_braking_events_timeline(df, braking_events)
            plot_braking_efficiency_trend(braking_stats)
            plot_efficiency_vs_speed(braking_stats)






# замороченный интерактивный график
#
#
#

def create_interactive_braking_efficiency_plot(braking_stats):
    """
    Создает интерактивный график эффективности торможений с фильтрацией по скорости
    """
    if braking_stats is None or braking_stats.empty:
        print("Нет данных для построения графика")
        return

    # Создаем интерактивный график
    fig = go.Figure()

    # Добавляем scatter plot эффективности
    fig.add_trace(go.Scatter(
        x=braking_stats['start_time'],
        y=braking_stats['efficiency'],
        mode='markers+lines',
        marker=dict(
            size=10,
            color=braking_stats['start_speed'],
            colorscale='Viridis',
            colorbar=dict(title='Начальная<br>скорость (км/ч)'),
            showscale=True
        ),
        line=dict(color='lightblue', width=1),
        hovertemplate=
        '<b>Торможение %{text}</b><br>' +
        'Время: %{x:.1f} сек<br>' +
        'Эффективность: %{y:.3f} м/с²/бар<br>' +
        'Начальная скорость: %{marker.color:.1f} км/ч<br>' +
        'Макс. давление: %{customdata[0]:.1f} бар<br>' +
        'Снижение скорости: %{customdata[1]:.1f} км/ч<br>' +
        '<extra></extra>',
        text=[f'#{i+1}' for i in range(len(braking_stats))],
        customdata=np.column_stack((
            braking_stats['max_pressure'],
            braking_stats['speed_decrease']
        ))
    ))

    # Добавляем ползунок для фильтрации по скорости
    speed_min = braking_stats['start_speed'].min()
    speed_max = braking_stats['start_speed'].max()

    fig.update_layout(
        title=dict(
            text='Интерактивная эффективность торможений по времени',
            x=0.5,
            font=dict(size=16)
        ),
        xaxis=dict(
            title='Время начала торможения (секунды)',
            gridcolor='lightgray'
        ),
        yaxis=dict(
            title='Эффективность торможения (м/с²/бар)',
            gridcolor='lightgray'
        ),
        plot_bgcolor='white',
        hovermode='closest',
        sliders=[{
            'active': 0,
            'steps': [{
                'method': 'restyle',
                'label': f'{int(speed_min)}-{int(speed_max)} км/ч',
                'args': [
                    {'marker.color': [braking_stats['start_speed']]},
                    {'marker.colorscale': 'Viridis'}
                ]
            }] + [
                {
                    'method': 'restyle',
                    'label': f'{speed} км/ч',
                    'args': [
                        {
                            'marker.color': [
                                braking_stats['start_speed'].apply(
                                    lambda x: x if speed - 10 <= x <= speed + 10 else None
                                )
                            ]
                        }
                    ]
                }
                for speed in range(int(speed_min), int(speed_max) + 1, 20)
            ]
        }]
    )

    # Добавляем кнопки для фильтрации
    fig.update_layout(
        updatemenus=[
            {
                'buttons': [
                    {
                        'method': 'restyle',
                        'label': 'Все скорости',
                        'args': [
                            {'marker.color': [braking_stats['start_speed']]},
                            {'marker.colorscale': 'Viridis'}
                        ]
                    },
                    {
                        'method': 'restyle',
                        'label': 'Низкая скорость (< 60 км/ч)',
                        'args': [
                            {
                                'marker.color': [
                                    braking_stats['start_speed'].apply(
                                        lambda x: x if x < 60 else None
                                    )
                                ]
                            }
                        ]
                    },
                    {
                        'method': 'restyle',
                        'label': 'Средняя скорость (60-100 км/ч)',
                        'args': [
                            {
                                'marker.color': [
                                    braking_stats['start_speed'].apply(
                                        lambda x: x if 60 <= x <= 100 else None
                                    )
                                ]
                            }
                        ]
                    },
                    {
                        'method': 'restyle',
                        'label': 'Высокая скорость (> 100 км/ч)',
                        'args': [
                            {
                                'marker.color': [
                                    braking_stats['start_speed'].apply(
                                        lambda x: x if x > 100 else None
                                    )
                                ]
                            }
                        ]
                    }
                ],
                'direction': 'down',
                'showactive': True,
                'x': 0.1,
                'y': 1.15
            }
        ]
    )

    # Сохраняем и показываем
    fig.write_html("interactive_braking_efficiency.html")
    fig.show()

    print("Интерактивный график сохранен как 'interactive_braking_efficiency.html'")

def create_advanced_interactive_dashboard(braking_stats):
    """
    Создает продвинутую интерактивную dashboard с несколькими графиками
    """
    if braking_stats is None or braking_stats.empty:
        return

    # Создаем dashboard с 4 графиками
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            'Эффективность по времени',
            'Эффективность vs Начальная скорость',
            'Эффективность vs Макс. давление',
            'Распределение эффективности'
        ),
        specs=[[{"secondary_y": False}, {"secondary_y": False}],
               [{"secondary_y": False}, {"secondary_y": False}]]
    )

    # 1. Эффективность по времени
    fig.add_trace(
        go.Scatter(
            x=braking_stats['start_time'],
            y=braking_stats['efficiency'],
            mode='markers+lines',
            marker=dict(
                size=8,
                color=braking_stats['start_speed'],
                colorscale='Viridis',
                showscale=False
            ),
            name='Эффективность',
            hovertemplate='Время: %{x:.1f}с<br>Эфф.: %{y:.3f} м/с²/бар<br>Скорость: %{marker.color} км/ч'
        ),
        row=1, col=1
    )

    # 2. Эффективность vs Скорость
    fig.add_trace(
        go.Scatter(
            x=braking_stats['start_speed'],
            y=braking_stats['efficiency'],
            mode='markers',
            marker=dict(
                size=8,
                color=braking_stats['max_pressure'],
                colorscale='Plasma',
                showscale=True,
                colorbar=dict(title='Макс. давление', x=1.0)
            ),
            name='Эфф. vs Скорость',
            hovertemplate='Скорость: %{x} км/ч<br>Эфф.: %{y:.3f} м/с²/бар<br>Давление: %{marker.color} бар'
        ),
        row=1, col=2
    )

    # 3. Эффективность vs Давление
    fig.add_trace(
        go.Scatter(
            x=braking_stats['max_pressure'],
            y=braking_stats['efficiency'],
            mode='markers',
            marker=dict(
                size=8,
                color=braking_stats['start_speed'],
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(title='Скорость', x=1.0)
            ),
            name='Эфф. vs Давление',
            hovertemplate='Давление: %{x} бар<br>Эфф.: %{y:.3f} м/с²/бар<br>Скорость: %{marker.color} км/ч'
        ),
        row=2, col=1
    )

    # 4. Гистограмма эффективности
    fig.add_trace(
        go.Histogram(
            x=braking_stats['efficiency'],
            nbinsx=20,
            name='Распределение',
            marker_color='lightblue',
            hovertemplate='Эфф.: %{x} м/с²/бар<br>Количество: %{y}'
        ),
        row=2, col=2
    )

    # Обновляем layout
    fig.update_layout(
        title_text='Dashboard эффективности торможений',
        height=800,
        showlegend=False
    )

    # Подписи осей
    fig.update_xaxes(title_text='Время (секунды)', row=1, col=1)
    fig.update_yaxes(title_text='Эффективность (м/с²/бар)', row=1, col=1)

    fig.update_xaxes(title_text='Начальная скорость (км/ч)', row=1, col=2)
    fig.update_yaxes(title_text='Эффективность (м/с²/бар)', row=1, col=2)

    fig.update_xaxes(title_text='Макс. давление (бар)', row=2, col=1)
    fig.update_yaxes(title_text='Эффективность (м/с²/бар)', row=2, col=1)

    fig.update_xaxes(title_text='Эффективность (м/с²/бар)', row=2, col=2)
    fig.update_yaxes(title_text='Количество', row=2, col=2)

    # Сохраняем и показываем
    fig.write_html("braking_efficiency_dashboard.html")
    fig.show()

    print("Dashboard сохранен как 'braking_efficiency_dashboard.html'")

def create_speed_filter_plot(braking_stats):
    """
    График с возможностью выбора диапазона скоростей
    """
    from plotly.express import scatter

    fig = scatter(
        braking_stats,
        x='start_time',
        y='efficiency',
        color='start_speed',
        size='max_pressure',
        hover_data=['speed_decrease', 'duration', 'r_squared'],
        labels={
            'start_time': 'Время начала торможения (секунды)',
            'efficiency': 'Эффективность (м/с²/бар)',
            'start_speed': 'Начальная скорость (км/ч)',
            'max_pressure': 'Макс. давление (бар)'
        },
        title='Эффективность торможений: выберите диапазон скорости'
    )

    # Добавляем диапазонный слайдер для скорости
    fig.update_layout(
        sliders=[{
            'active': 0,
            'steps': [
                {
                    'method': 'restyle',
                    'label': f'{min_speed}-{max_speed} км/ч',
                    'args': [{
                        'marker.color': [
                            braking_stats['start_speed'].apply(
                                lambda x: x if min_speed <= x <= max_speed else None
                            )
                        ]
                    }]
                }
                for min_speed, max_speed in [
                    (0, 200),
                    (0, 50), (50, 100), (100, 150), (150, 200)
                ]
            ]
        }]
    )

    fig.write_html("speed_filter_plot.html")
    fig.show()

def fire_interractive_graph(df):
    if not df.empty:
        # Анализ отдельных торможений
        braking_stats = analyze_braking_events(df)

        if braking_stats is not None:
            print("\nСоздание интерактивных графиков...")

            # Базовый интерактивный график
            create_interactive_braking_efficiency_plot(braking_stats)

            # Продвинутая dashboard
            create_advanced_interactive_dashboard(braking_stats)

            # График с фильтром скорости
            create_speed_filter_plot(braking_stats)

            print("\nИнтерактивные графики созданы!")
            print("Откройте файлы .html в браузере для взаимодействия")








if __name__ == "__main__":

    blf_file_path = "C:\\Users\\belousov\\Documents\\PyScripts\\CanBLF\\logs\\bogo_log.blf"
    #  df = proceed_file("C:\\Users\\belousov\\Documents\\PyScripts\\CanBLF\\logs\\sample_log.blf")
    #  blf_file_path = "C:\\Users\\belousov\\Documents\\PyScripts\\CanBLF\\logs\\Vesta_ESC2025_04_22_13_56_48_high_mue_70_no_blocking.blf"

    # Проверяем кэш
    if CACHE_ENABLED and not OVERWRITE_CACHE and is_cache_valid(blf_file_path):
        print("Загружаем данные из кэша...")
        df = load_from_cache(blf_file_path)
    else:
        print("Обрабатываем файл...")
        df = proceed_file(blf_file_path)

        # Сохраняем в кэш после обработки
        if CACHE_ENABLED and not df.empty:
            save_to_cache(df, blf_file_path)

    if not df.empty:
        print(df.head())
        print(f"\nСтатистика после фильтрации:")
        print(f"Всего записей: {len(df)}")
        print(f"Среднее замедление: {df['deceleration'].mean():.2f} м/с²")
        print(f"Максимальное замедление: {df['deceleration'].max():.2f} м/с²")

        # Строим график
        #  plot_deceleration_time(df)

        # Дополнительные анализы
        #  braking_df = prepare_braking_data(df)

        #  plot_pressure_time(df)
        #  plot_pressure_time_advanced(df)


        #  slope, r_squared = analyze_braking_efficiency(braking_df)
        #  analyze_by_speed_ranges(braking_df)
        #  plot_deceleration_time(df)
        #  plot_deceleration_time_advanced(df)

        #  plot_pressure_deceleration_advanced(df)
        run_complex_braking_to_braking_analysis(df)

        fire_interractive_graph(df)

    else:
        print("Нет данных для анализа")

