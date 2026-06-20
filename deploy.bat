@echo off
setlocal
title Almadan Git Otomatik Yukleyici
cd /d "E:\Almadan\proje"

where git >nul 2>nul
if %errorlevel% neq 0 (
    echo -------------------------------------------------------------
    echo HATA: Bilgisayarinizda Git programi kurulu degil!
    echo -------------------------------------------------------------
    echo Lutfen su adresten Git indirip kurun:
    echo https://git-scm.com/download/win
    echo.
    echo Git kurduktan sonra bu dosyayi tekrar calistirabilirsiniz.
    echo -------------------------------------------------------------
    pause
    exit /b
)

echo =============================================================
echo               ALMADAN OTOMATIK GITHUB YUKLEME
echo =============================================================
echo.

if not exist ".git" (
    echo [KURULUM] Bu klasor ilk kez Git deposu haline getiriliyor...
    git init -b main
    if errorlevel 1 goto :error
)

for /f "delims=" %%i in ('git config user.name 2^>nul') do set "GIT_NAME=%%i"
if not defined GIT_NAME (
    set /p "GIT_NAME=GitHub kullanici adiniz: "
    if not defined GIT_NAME goto :error
    git config user.name "%GIT_NAME%"
)

for /f "delims=" %%i in ('git config user.email 2^>nul') do set "GIT_EMAIL=%%i"
if not defined GIT_EMAIL (
    set /p "GIT_EMAIL=GitHub e-posta adresiniz: "
    if not defined GIT_EMAIL goto :error
    git config user.email "%GIT_EMAIL%"
)

git remote get-url origin >nul 2>nul
if errorlevel 1 (
    echo.
    echo GitHub'da bos bir depo olusturun:
    echo https://github.com/new
    echo Ornek adres: https://github.com/KULLANICI_ADI/almadan.git
    echo.
    set /p "REPO_URL=GitHub depo adresini buraya yapistirin: "
    if not defined REPO_URL goto :error
    git remote add origin "%REPO_URL%"
    if errorlevel 1 goto :error
)

echo [1/3] Degisiklikler taranip ekleniyor...
git add .
if errorlevel 1 goto :error

echo.
echo [2/3] Paket (Commit) olusturuluyor...
for /f "tokens=1-3 delims=/" %%a in ("%date%") do set "GUN=%%a.%%b.%%c"
for /f "tokens=1-2 delims=:" %%a in ("%time%") do set "SAAT=%%a:%%b"
for /f %%c in ('git diff --cached --name-only ^| find /c /v ""') do set "DOSYA_SAYISI=%%c"
if "%DOSYA_SAYISI%"=="0" set "DOSYA_SAYISI=?"
set "COMMIT_MSG=Guncelleme %GUN% %SAAT% - %DOSYA_SAYISI% dosya degisti"
echo Commit mesaji: %COMMIT_MSG%
git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    git diff --cached --quiet
    if errorlevel 1 goto :error
    echo Yeni degisiklik olmadigi icin mevcut paket gonderilecek.
)

echo.
echo [3/3] Kodlar GitHub deposuna gonderiliyor...
git branch -M main
git push -u origin main
if errorlevel 1 goto :error

echo.
echo =============================================================
echo [BASARILI] Kodlar GitHub'a yuklendi!
echo Render/Vercel bu depoya bagliysa yeni surumu otomatik yayinlar.
echo =============================================================
echo.
pause
exit /b 0

:error
echo.
echo =============================================================
echo [HATA] Islem tamamlanamadi.
echo Yukaridaki ilk hata satirini kontrol edin.
echo =============================================================
echo.
pause
exit /b 1
