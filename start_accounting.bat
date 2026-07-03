@echo off
cd /d E:\my\amazon_syria\src

REM تفعيل البيئة الافتراضية
call ..\Scripts\activate

REM تشغيل السيرفر
start "" /min python manage.py runserver 127.0.0.1:8000

REM فتح كروم بوضع تطبيق
start "" "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --app="http://127.0.0.1:8000/"
