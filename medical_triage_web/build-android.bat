@echo off
echo 开始构建医疗导诊 Android APP...

:: 检查 Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Node.js，请先安装: https://nodejs.org/
    pause
    exit /b 1
)

echo [1/4] 安装依赖...
call npm install
if errorlevel 1 (
    echo [错误] npm install 失败
    pause
    exit /b 1
)

:: 检查是否已添加 Android 平台
if not exist "android" (
    echo [2/4] 添加 Android 平台...
    call npx cap add android
    if errorlevel 1 (
        echo [错误] 添加 Android 平台失败
        pause
        exit /b 1
    )
) else (
    echo [2/4] Android 平台已存在，跳过
)

echo [3/4] 同步 Web 代码到 Android...
call npx cap sync
if errorlevel 1 (
    echo [错误] 同步失败
    pause
    exit /b 1
)

echo [4/4] 构建准备完成！
echo.
echo ==========================================
echo 下一步操作：
echo ==========================================
echo 1. 打开 Android Studio
echo 2. 选择 "Open" 并导入 android/ 文件夹
echo 3. 等待 Gradle 同步完成
echo 4. 选择 Build -^> Build APK(s)
echo 5. APK 位置: android/app/build/outputs/apk/debug/app-debug.apk
echo ==========================================
echo.

:: 尝试自动打开 Android Studio
where studio.bat >nul 2>&1
if %errorlevel% == 0 (
    echo 正在打开 Android Studio...
    call npx cap open android
) else (
    echo [提示] 未找到 Android Studio 命令，请手动打开
)

pause
