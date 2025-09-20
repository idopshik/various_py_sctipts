import pandas as pd
from can import BLFReader
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
import psutil
import os
import gc

def print_memory_usage():
    process = psutil.Process(os.getpid())
    mem = process.memory_info().rss / 1024 ** 2
    print(f"Используется памяти: {mem:.2f} MB")

def blf_to_dataframe_chunked(blf_file, chunk_size=100000):
    """Чтение BLF файла с сохранением во временные файлы"""
    chunk_files = []
    chunk_num = 0
    messages = []

    print("Чтение BLF файла с разбивкой на чанки...")
    with BLFReader(blf_file) as reader:
        with tqdm(desc="Обработка сообщений") as pbar:
            for msg in reader:
                messages.append({
                    'timestamp': msg.timestamp,
                    'arbitration_id': msg.arbitration_id,
                    'is_extended_id': msg.is_extended_id,
                    'is_remote_frame': msg.is_remote_frame,
                    'is_error_frame': msg.is_error_frame,
                    'dlc': msg.dlc,
                    'data': msg.data.hex(),
                    'channel': msg.channel
                })
                pbar.update(1)

                # Сохраняем чанк и очищаем память
                if len(messages) >= chunk_size:
                    chunk_df = pd.DataFrame(messages)
                    chunk_file = f'temp_chunk_{chunk_num}.parquet'
                    chunk_df.to_parquet(chunk_file)
                    chunk_files.append(chunk_file)
                    chunk_num += 1
                    messages = []
                    del chunk_df
                    gc.collect()

    # Сохраняем последний чанк
    if messages:
        chunk_df = pd.DataFrame(messages)
        chunk_file = f'temp_chunk_{chunk_num}.parquet'
        chunk_df.to_parquet(chunk_file)
        chunk_files.append(chunk_file)
        del chunk_df, messages
        gc.collect()

    return chunk_files

def process_chunks_for_top_ids(chunk_files):
    """Определяем топ ID по всем чанкам"""
    id_counts = {}

    for chunk_file in tqdm(chunk_files, desc="Анализ ID по чанкам"):
        chunk_df = pd.read_parquet(chunk_file)
        chunk_counts = chunk_df['arbitration_id'].value_counts().to_dict()

        for id, count in chunk_counts.items():
            id_counts[id] = id_counts.get(id, 0) + count

        del chunk_df
        gc.collect()

    # Получаем топ-10 ID
    top_ids = sorted(id_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    top_ids = [id for id, count in top_ids]
    print(f"Топ-10 ID: {[hex(id) for id in top_ids]}")

    return top_ids

def create_frequency_data(chunk_files, top_ids, time_bins):
    """Создаем данные для графика по чанкам"""
    # Создаем пустой DataFrame для частот
    frequency_data = {id: np.zeros(len(time_bins)-1, dtype=np.int32) for id in top_ids}

    for chunk_file in tqdm(chunk_files, desc="Обработка чанков для частот"):
        chunk_df = pd.read_parquet(chunk_file)

        # Фильтруем только нужные ID
        chunk_filtered = chunk_df[chunk_df['arbitration_id'].isin(top_ids)]

        if not chunk_filtered.empty:
            # Биннинг по времени
            time_indices = np.digitize(chunk_filtered['timestamp'], time_bins) - 1
            time_indices = np.clip(time_indices, 0, len(time_bins)-2)

            for id in top_ids:
                mask = chunk_filtered['arbitration_id'] == id
                if mask.any():
                    indices = time_indices[mask]
                    counts = np.bincount(indices, minlength=len(time_bins)-1)
                    frequency_data[id] += counts

        del chunk_df, chunk_filtered
        gc.collect()

    return frequency_data

def plot_frequency_data(frequency_data, time_bins):
    """Построение графика из готовых данных"""
    print("Построение графика...")
    plt.figure(figsize=(15, 8))

    time_points = time_bins[:-1] + 0.5  # Центры интервалов

    for id, counts in tqdm(frequency_data.items(), desc="Отрисовка линий"):
        plt.plot(time_points, counts, label=f'ID_{hex(id)}', linewidth=1, alpha=0.8)

    plt.xlabel('Время (секунды)')
    plt.ylabel('Количество сообщений в секунду')
    plt.title('Частота CAN сообщений по времени')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    plt.savefig('can_frequency_optimized.png', dpi=300, bbox_inches='tight')
    print("График сохранен как 'can_frequency_optimized.png'")
    plt.show()

def cleanup_temp_files(chunk_files):
    """Очистка временных файлов"""
    for chunk_file in chunk_files:
        if os.path.exists(chunk_file):
            os.remove(chunk_file)

# Основной процесс
def main():
    try:
        print_memory_usage()

        # 1. Читаем файл с разбивкой на чанки
        chunk_files = blf_to_dataframe_chunked('bogo_log.blf', chunk_size=50000)
        print_memory_usage()

        # 2. Определяем временные интервалы по первому чанку
        first_chunk = pd.read_parquet(chunk_files[0])
        max_time = first_chunk['timestamp'].max()
        del first_chunk
        gc.collect()

        # Проверяем все чанки для точного max_time
        for chunk_file in chunk_files[1:]:
            chunk_df = pd.read_parquet(chunk_file)
            max_time = max(max_time, chunk_df['timestamp'].max())
            del chunk_df
            gc.collect()

        time_bins = np.arange(0, max_time + 2, 1)  # +2 для безопасности
        print(f"Временной диапазон: 0 - {max_time:.2f} секунд")
        print_memory_usage()

        # 3. Находим топ ID
        top_ids = process_chunks_for_top_ids(chunk_files)
        print_memory_usage()

        # 4. Собираем данные для графика
        frequency_data = create_frequency_data(chunk_files, top_ids, time_bins)
        print_memory_usage()

        # 5. Строим график
        plot_frequency_data(frequency_data, time_bins)

        # 6. Очищаем временные файлы
        cleanup_temp_files(chunk_files)

    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        # Очищаем временные файлы при ошибке
        if 'chunk_files' in locals():
            cleanup_temp_files(chunk_files)

if __name__ == "__main__":
    main()
