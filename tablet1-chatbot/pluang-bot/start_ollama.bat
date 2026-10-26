@echo off
REM ============================================================
REM START_OLLAMA.bat — Start Ollama serve dengan RAM minimal
REM Jalankan ini sebelum bot jika Ollama belum aktif
REM ============================================================

echo Mengecek apakah Ollama sudah berjalan...
curl -s --max-time 3 http://localhost:11434/api/tags >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    echo [OK] Ollama sudah berjalan di port 11434
    goto :done
)

echo Ollama belum aktif. Memulai Ollama dengan RAM minimal...
SET OLLAMA_CONTEXT_LENGTH=512
SET OLLAMA_NUM_PARALLEL=1
SET OLLAMA_MAX_LOADED_MODELS=1
SET OLLAMA_KEEP_ALIVE=10m
SET OLLAMA_FLASH_ATTENTION=false

start /B ollama serve

echo Menunggu Ollama siap...
timeout /t 8 /nobreak >nul

curl -s --max-time 5 http://localhost:11434/api/tags >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    echo [OK] Ollama berhasil dijalankan!
) ELSE (
    echo [WARN] Ollama mungkin belum siap, coba tunggu beberapa detik...
)

:done
echo Ollama status: Siap di http://localhost:11434
