#!/bin/bash
# Android 构建脚本

echo "🚀 开始构建医疗导诊 Android APP..."

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "❌ 未找到 Node.js，请先安装: https://nodejs.org/"
    exit 1
fi

# 安装依赖
echo "📦 安装依赖..."
npm install

# 检查是否已添加 Android 平台
if [ ! -d "android" ]; then
    echo "📱 添加 Android 平台..."
    npx cap add android
else
    echo "📱 Android 平台已存在"
fi

# 同步代码
echo "🔄 同步 Web 代码到 Android..."
npx cap sync

# 检查 Android Studio
if command -v studio &> /dev/null; then
    echo "✅ 打开 Android Studio..."
    npx cap open android
else
    echo "⚠️ 未找到 Android Studio 命令"
    echo "请手动打开 Android Studio 并导入 android/ 目录"
fi

echo ""
echo "✅ 构建准备完成！"
echo ""
echo "下一步："
echo "1. 在 Android Studio 中等待 Gradle 同步"
echo "2. 选择 Build → Build Bundle(s) / APK(s) → Build APK(s)"
echo "3. APK 将生成在: android/app/build/outputs/apk/debug/app-debug.apk"
echo ""
