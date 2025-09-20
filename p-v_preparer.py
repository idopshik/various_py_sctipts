
import os
import sys

# Добавляем путь к folder в sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'P-V_gui_preparer'))

# Импортируем
import main_deal

if hasattr(main_deal, 'main'):
    main_deal.main()
