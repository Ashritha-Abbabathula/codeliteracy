@echo off
rem Runs all three Experiment 10 tests against CodeLiteracy on this laptop:
rem   1. Newman  (Postman collection)   - API testing
rem   2. Locust                         - performance testing
rem   3. Selenium WebDriver + pytest    - browser automation
rem Start the app with start.bat FIRST and leave its two windows open.
setlocal
cd /d "%~dp0"

echo Checking that CodeLiteracy is running...
curl -s http://127.0.0.1:8000/api/health >nul 2>nul || (
  echo.
  echo The backend is not running. Double-click start.bat in the codeliteracy folder,
  echo wait until the app opens in your browser, then run this file again.
  pause & exit /b 1
)
curl -s http://localhost:5173 >nul 2>nul || (
  echo.
  echo The frontend is not running yet. Wait for start.bat to finish, then run this file again.
  pause & exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo First run: installing Selenium, pytest and Locust. This takes a minute or two...
  set "PYEXE="
  if exist "..\backend\.venv\Scripts\python.exe" set "PYEXE=..\backend\.venv\Scripts\python.exe"
  if not defined PYEXE (py -3 --version >nul 2>nul && set "PYEXE=py -3")
  if not defined PYEXE set "PYEXE=python"
  call %%PYEXE%% -m venv .venv || (echo Could not create the Python environment. & pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install --quiet selenium pytest pytest-html locust || (pause & exit /b 1)
)
if not exist reports mkdir reports

echo.
echo ================================================================
echo  PART A - API testing with Newman (Postman collection)
echo ================================================================
call npx --yes newman@6 run CodeLiteracy_API_Tests.postman_collection.json
echo.
echo  ^>^> Take a screenshot of the Newman results above now.
pause

echo.
echo ================================================================
echo  PART B - Performance testing with Locust (20 users, 30 seconds)
echo ================================================================
".venv\Scripts\locust.exe" -f locustfile.py --host http://127.0.0.1:8000 --headless -u 20 -r 5 -t 30s --only-summary --html reports\locust_report.html
start "" "reports\locust_report.html"
echo.
echo  ^>^> The Locust report has opened in your browser. Take a screenshot of it.
pause

echo.
echo ================================================================
echo  PART C - Browser testing with Selenium WebDriver
echo  (Chrome will open and run the tests by itself - don't touch it)
echo ================================================================
".venv\Scripts\python.exe" -m pytest test_codeliteracy_ui.py -v --html=reports\selenium_report.html --self-contained-html
start "" "reports\selenium_report.html"
echo.
echo  ^>^> The Selenium report has opened. Screenshots of each test are in testing\screenshots.

echo.
echo All three parts are done. Reports are in testing\reports.
pause
endlocal
