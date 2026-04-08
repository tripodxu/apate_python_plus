According to apate, optimize it into a Python version (https://github.com/rippod/apate)

When generating the recovery exe file, you need to 'pip install pyinstaller'



pyinstaller --onefile --windowed --icon=icon.ico -n apluse --add-data "icon.ico;." --clean main.py



nuitka --standalone --onefile --windows-console-mode=disable --enable-plugin=pyqt5 --windows-icon-from-ico=icon.ico --output-filename=apluse --include-data-files=icon.ico=icon.ico --clean-cache=all main.py



### V3.1

![image-20260409010208641](README.assets/image-20260409010208641.png)



### V3.3

![image-20260409010324267](README.assets/image-20260409010324267.png)

![image-20260409010347858](README.assets/image-20260409010347858.png)
