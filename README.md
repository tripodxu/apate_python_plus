根据apate，进行优化成python版本（https://github.com/rippod/apate）

生成恢复exe文件时需要 ' pip install pyinstaller '



pyinstaller --onefile --windowed  disguise_ui.py

pyinstaller --onefile --windowed --icon=icon.ico --clean disguise_ui.py



python -m nuitka --onefile --windows-icon-from-ico=icon.ico --windows-console-mode=disable --enable-plugin=pyqt5 --lto=yes disguise_ui.py



pyinstaller --onefile --windowed --icon=icon.ico --clean main.py
