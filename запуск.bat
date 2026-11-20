@echo off
cd /d "%~dp0"
netsh advfirewall firewall set rule name="python.exe" dir=in new enable=no >nul 2>&1
netsh advfirewall firewall add rule name="Monty Hall phone" dir=in action=allow protocol=TCP localport=8501 program="%LocalAppData%\Programs\Python\Python311\python.exe" >nul 2>&1
echo Результаты пишутся в папки ПРИ и ПИ: попытка_1.xlsx, попытка_2.xlsx, попытка_3.xlsx
echo.
echo Телефон должен быть подключён к той же сети Wi-Fi, что и ноутбук.
echo Ссылка для телефона:
for /f "tokens=*" %%a in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' }).IPAddress"') do echo   http://%%a:8501
echo.
echo Ноутбук не выключайте и не закрывайте крышку, иначе страница пропадёт.
echo С мобильного интернета, без этого Wi-Fi, эта ссылка не откроется.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py
pause
