import can
import cantools
import csv
from can.message import Message

# Конфигурация - укажите пути к вашим файлам
BLF_FILE = 'currently_under_calc.blf'
DBC_FILE = 'pressures_sensors_ni6002.dbc'
CSV_FILE = 'output.csv'

def main():
    # Загружаем базу данных CAN из DBC файла
    try:
        db = cantools.db.load_file(DBC_FILE)
        print(f"Успешно загружена DBC база: {DBC_FILE}")
        print(f"Загружено сообщений: {len(db.messages)}")
    except Exception as e:
        print(f"Ошибка загрузки DBC файла: {e}")
        return

    # Открываем BLF файл для чтения
    try:
        log = can.BLFReader(BLF_FILE)
        print(f"Успешно открыт BLF файл: {BLF_FILE}")
    except Exception as e:
        print(f"Ошибка открытия BLF файла: {e}")
        return

    # Создаем CSV файл и записываем заголовок
    try:
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            # Записываем заголовок CSV
            header = ['Timestamp', 'Arbitration_ID', 'Message_Name', 'Signals']
            writer.writerow(header)
            print(f"Создан CSV файл: {CSV_FILE}")

            # Обрабатываем каждое CAN-сообщение
            message_count = 0
            for msg in log:
                try:
                    # Парсим сообщение с помощью DBC
                    decoded = db.decode_message(msg.arbitration_id, msg.data)

                    # Форматируем сигналы в строку
                    signals_str = "; ".join([f"{key}: {value}" for key, value in decoded.items()])

                    # Получаем имя сообщения по ID
                    try:
                        msg_name = db.get_message_by_frame_id(msg.arbitration_id).name
                    except:
                        msg_name = "UNKNOWN"

                    # Записываем данные в CSV
                    row = [
                        msg.timestamp,          # Метка времени
                        hex(msg.arbitration_id),# ID сообщения в hex
                        msg_name,               # Имя сообщения из DBC
                        signals_str             # Расшифрованные сигналы
                    ]
                    writer.writerow(row)

                    message_count += 1
                    if message_count % 1000 == 0:
                        print(f"Обработано сообщений: {message_count}")

                except cantools.db.DecodeError:
                    # Пропускаем сообщения, которые не можем расшифровать
                    continue
                except Exception as e:
                    print(f"Ошибка обработки сообщения: {e}")
                    continue

            print(f"Обработка завершена. Всего обработано сообщений: {message_count}")

    except Exception as e:
        print(f"Ошибка записи в CSV файл: {e}")
        return

if __name__ == "__main__":
    main()
