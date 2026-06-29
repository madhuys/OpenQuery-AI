@echo off
echo Starting OpenQuery AI Service...
echo.

echo Installing dependencies...
pip install -r requirements.txt
echo.

echo Starting FastAPI backend...
start "FastAPI Backend" cmd /k "python main.py"

timeout /t 3 /nobreak > nul

echo Starting Streamlit frontend...
start "Streamlit Frontend" cmd /k "streamlit run app.py"

echo.
echo Both services are starting...
echo FastAPI will run on http://localhost:8000
echo Streamlit will run on http://localhost:8501
echo.
pause
