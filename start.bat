@echo off
rem One-click start for CodeLiteracy on Windows: sets things up the first time, then opens
rem the backend and the frontend in their own windows and the app in your browser.
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python was not found. Install Python 3.11+ from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
where npm >nul 2>nul || (echo Node.js was not found. Install the LTS version from https://nodejs.org/ & pause & exit /b 1)

if not exist "backend\.venv\Scripts\python.exe" (
  echo [1/3] First run: creating the Python environment...
  python -m venv "backend\.venv" || (pause & exit /b 1)
  "backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt" || (pause & exit /b 1)
)

if not exist "backend\.env" (
  copy "backend\.env.example" "backend\.env" >nul
  echo.
  echo  backend\.env was created. Open it and paste your free Gemini key after GEMINI_API_KEY=
  echo  Get one at https://aistudio.google.com/apikey  ^(the app still opens without it,
  echo  but the AI explanations, tutor and quizzes need it^).
  echo.
  pause
)

if not exist "frontend\node_modules" (
  echo [2/3] First run: installing the frontend packages...
  pushd frontend
  call npm install || (popd & pause & exit /b 1)
  popd
)

echo [3/3] Starting CodeLiteracy...
start "CodeLiteracy backend (keep open)" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
start "CodeLiteracy frontend (keep open)" /D "%~dp0frontend" cmd /k "npm run dev"

timeout /t 6 /nobreak >nul
start "" "http://localhost:5173"
echo.
echo CodeLiteracy is opening at http://localhost:5173
echo To stop it, close the two windows titled "CodeLiteracy backend" and "CodeLiteracy frontend".
endlocal
