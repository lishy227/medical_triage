# 医疗导诊 APP - Android 构建完成

## 项目状态

Android 项目已生成并配置完成！

### 项目位置
```
C:\Users\25484\.openclaw\workspace\medical_triage_web\
├── android/              # Android 项目目录
├── www/                  # Web 资源目录
├── package.json          # Node.js 配置
├── capacitor.config.json # Capacitor 配置
└── ...
```

## 构建 APK 的步骤

### 方法一：使用 Android Studio（推荐）

1. **打开 Android Studio**
   - 启动 Android Studio
   - 选择 **Open**（打开项目）
   - 选择文件夹：`C:\Users\25484\.openclaw\workspace\medical_triage_web\android`

2. **等待 Gradle 同步**
   - 首次打开会自动下载 Gradle 和依赖
   - 等待同步完成（可能需要几分钟）

3. **构建 APK**
   - 菜单栏选择 **Build → Build Bundle(s) / APK(s) → Build APK(s)**
   - 或点击工具栏的构建按钮

4. **获取 APK**
   - 构建完成后，点击右下角的提示 "locate"
   - APK 位置：`android/app/build/outputs/apk/debug/app-debug.apk`

### 方法二：命令行构建（需要配置好 Gradle）

```bash
cd android
.\gradlew.bat assembleDebug
```

## 已完成的配置

### 网络权限
- `INTERNET` - 允许网络访问
- `ACCESS_NETWORK_STATE` - 允许检测网络状态
- `android:usesCleartextTraffic="true"` - 允许明文 HTTP 通信（连接阿里云服务器必需）

### 服务器配置
- **API 地址**: `http://47.107.108.157:5001`
- 已适配 Capacitor HTTP 插件
- 支持 Android 9+ 的明文 HTTP 通信

### 移动端适配
- 响应式布局（侧边栏在小屏幕隐藏）
- 触摸友好的界面元素
- 自动调整输入框高度

## 安装到手机

### 方式 1：USB 调试
1. 开启手机的开发者选项和 USB 调试
2. 用 USB 连接电脑
3. 在 Android Studio 中点击运行按钮

### 方式 2：传输 APK
1. 将 `app-debug.apk` 复制到手机
2. 在手机上点击安装（可能需要允许未知来源应用）

## 更新 Web 代码后

如果修改了前端代码，需要重新同步：

```bash
cd C:\Users\25484\.openclaw\workspace\medical_triage_web

# www/ 就是唯一正式前端目录；修改其中的文件后直接同步
npx cap sync

# 然后在 Android Studio 中重新构建
```

## 常见问题

### 1. Gradle 下载失败
- 检查网络连接
- 配置 Gradle 代理（如需要）
- 或在 Android Studio 中首次打开时自动下载

### 2. 无法连接服务器
- 检查手机网络是否正常
- 确认服务器地址 `47.107.108.157:5001` 可访问
- 检查阿里云服务器是否运行正常

### 3. 应用白屏
- 检查 `www/` 目录下文件是否完整
- 重新运行 `npx cap sync`

## 发布版本构建

如需构建发布版 APK：
1. 在 Android Studio 中选择 **Build → Generate Signed Bundle/APK**
2. 创建密钥库（keystore）或选择已有密钥库
3. 选择 release 构建类型
4. 生成的 APK 可上传到应用商店

## 文件说明

| 文件 | 说明 |
|------|------|
| `android/app/src/main/assets/public/` | Web 资源（自动生成） |
| `android/app/src/main/AndroidManifest.xml` | 应用配置（已修改） |
| `capacitor.config.json` | Capacitor 配置 |
| `www/` | Web 源代码目录 |
