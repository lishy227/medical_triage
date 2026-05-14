# 医疗导诊 APP - Android 构建指南

## 项目结构

```
medical_triage_web/
├── www/                  # 唯一正式前端目录（HTML/CSS/JS）
├── capacitor.config.json # Capacitor 配置
├── package.json          # Node.js 依赖
├── android/              # Android 项目目录（生成后）
└── BUILD.md              # 本文件
```

## 前置要求

1. **Node.js** (v18+): https://nodejs.org/
2. **Android Studio**: https://developer.android.com/studio
3. **JDK** (v17+): Android Studio 自带或单独安装
4. **Android SDK**: 通过 Android Studio 安装

## 构建步骤

### 1. 安装依赖

```bash
cd medical_triage_web
npm install
```

### 2. 添加 Android 平台

```bash
npx cap add android
```

### 3. 同步 Web 代码到 Android 项目

```bash
npx cap sync
```

### 4. 打开 Android Studio

```bash
npx cap open android
```

### 5. 构建 APK

在 Android Studio 中：
- 等待 Gradle 同步完成
- 选择 Build → Build Bundle(s) / APK(s) → Build APK(s)
- 或使用菜单栏的 Build 按钮

APK 文件将生成在：`android/app/build/outputs/apk/debug/app-debug.apk`

## 服务器配置

应用已配置连接阿里云服务器：
- **服务器地址**: `http://47.107.108.157:5001`
- **API 端点**:
  - `GET /api/welcome?session_id=xxx` - 获取欢迎消息
  - `POST /api/chat` - 发送聊天消息
  - `POST /api/reset` - 重置对话

## 移动端适配说明

### 已完成的适配

1. **HTTP 请求**: 使用 Capacitor HTTP 插件处理跨域和混合内容
2. **配置**: `capacitor.config.json` 中启用了：
   - `cleartext: true` - 允许明文 HTTP 通信
   - `allowMixedContent: true` - 允许混合内容
3. **样式**: CSS 已包含移动端响应式设计 (`@media (max-width: 768px)`)
4. **前端源码**: 统一以 `www/` 作为唯一正式前端目录

### 网络权限

Android 应用已自动配置以下权限：
- `INTERNET` - 网络访问
- `ACCESS_NETWORK_STATE` - 网络状态检测

## 发布准备

### 调试版本
- 使用上述步骤生成的 APK 可直接安装测试

### 发布版本
1. 在 Android Studio 中选择 Build → Generate Signed Bundle/APK
2. 创建或选择密钥库 (keystore)
3. 选择 release 构建类型
4. 生成的 APK 可上传到应用商店

## 常见问题

### 1. 无法连接服务器
- 检查服务器地址是否正确
- 确保 Android 设备与服务器网络连通
- 检查服务器是否允许跨域访问

### 2. 白屏问题
- 检查 `capacitor.config.json` 中的 `webDir` 配置
- 确保 `www/` 目录下资源文件完整且路径正确

### 3. 样式问题
- 侧边栏在小屏幕上自动隐藏
- 消息气泡宽度已适配移动端

## 更新应用

修改 `www/` 中的前端代码后：
```bash
npx cap sync        # 同步 Web 资源与插件
# 然后在 Android Studio 中重新构建
```

## 联系与支持

如遇问题，请检查：
1. Android Studio 的 Logcat 日志
2. Chrome DevTools 远程调试
3. 服务器运行状态
