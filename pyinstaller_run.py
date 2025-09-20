#!/usr/bin/env python3
"""
Простой скрипт для сборки с PyInstaller
"""

import os
import sys
import subprocess

def main():
    # Активируем виртуальное окружение (если нужно)
    python_exe = sys.executable

    script_name = "Endu_tdms_analysis.py"
    icon_option = "--icon=endu_tdms_app.ico" if os.path.exists("endu_tdms_app.ico") else ""

    # ПРОСТАЯ команда PyInstaller - собираем в папку (не onefile)
    cmd = [
        python_exe, "-m", "PyInstaller",
        script_name,
        "--name=EnduTDMS",
        "--windowed",  # без консоли
        "--onefile",    # ← ВАЖНО: эта опция создает один исполняемый файл
        "--clean",     # очистка перед сборкой
        "--noconfirm", # не спрашивать подтверждение
        icon_option
    ]

    # Убираем пустые элементы
    cmd = [x for x in cmd if x]

    print("🚀 Запускаем PyInstaller...")
    print("📦 Команда:", " ".join(cmd))

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print("✅ Сборка завершена успешно!")
        print("📁 Папка с результатом: dist/EnduTDMS/")

    except subprocess.CalledProcessError as e:
        print("❌ Ошибка сборки:")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
