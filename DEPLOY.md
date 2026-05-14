# 医疗导诊系统 - 部署说明

## 功能更新

本次更新添加了以下功能：

### 1. 用户认证系统
- 用户注册（用户名 + 密码）
- 用户登录
- 退出登录
- JWT Token 认证（30天有效期）

### 2. 分诊历史记录
- 每次分诊完成后自动保存记录
- 历史记录列表查看
- 历史记录详情查看
- 历史记录删除

### 3. 个人中心
- 显示用户信息
- 显示历史记录数量
- 退出登录按钮

---

## 本地开发环境配置

### 1. 安装 MySQL

```bash
# Windows 安装 MySQL 后，创建数据库
mysql -u root -p

# 在 MySQL 中执行：
CREATE DATABASE medical_triage CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. 配置后端环境变量

编辑 `medical_triage_back/.env`：

```env
API_KEY=sk-c1fb3e7c2e2d4c63b234fa220d43897e
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL=qwen-plus

# 数据库配置（根据你的 MySQL 配置修改）
DATABASE_URL=mysql+pymysql://root:你的密码@localhost/medical_triage

# JWT配置
JWT_SECRET_KEY=your-secret-key-change-this-in-production
JWT_ACCESS_TOKEN_EXPIRE_DAYS=30
```

### 3. 安装依赖

```bash
cd medical_triage_back
pip install -r requirements.txt
```

### 4. 启动后端服务

```bash
cd medical_triage_back
python web_server.py
```

服务将在 http://localhost:5001 启动

### 5. 前端本地测试

前端可以直接在浏览器中打开 `medical_triage_web/index.html` 进行测试。

或者使用本地服务器：

```bash
cd medical_triage_web
npx serve .
```

---

## 阿里云部署

### 1. 服务器环境准备

```bash
# 连接到阿里云服务器
ssh root@47.107.108.157

# 安装 Python 3.11+
# 安装 MySQL
# 安装 Nginx（可选，用于反向代理）
```

### 2. 上传代码

```bash
# 在本地打包后端代码
cd medical_triage_back
zip -r backend.zip . -x "__pycache__/*" "*.pyc" ".git/*"

# 上传到服务器
scp backend.zip root@47.107.108.157:/opt/medical_triage/

# 在服务器上解压
ssh root@47.107.108.157 "cd /opt/medical_triage && unzip -o backend.zip"
```

### 3. 服务器配置

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
vim .env
# 修改 DATABASE_URL 为服务器 MySQL 地址
```

### 4. 使用 PM2 或 Systemd 启动服务

```bash
# 安装 PM2
npm install -g pm2

# 创建启动脚本
pm2 start "python web_server.py" --name medical-triage

# 保存配置
pm2 save
pm2 startup
```

或使用 systemd：

```bash
# 创建服务文件
sudo vim /etc/systemd/system/medical-triage.service
```

内容：

```ini
[Unit]
Description=Medical Triage Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/medical_triage
Environment=PATH=/usr/local/bin
ExecStart=/usr/local/bin/python web_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable medical-triage
sudo systemctl start medical-triage
```

### 5. 前端构建 APK

在本地构建：

```bash
cd medical_triage_web

# 确保 API_BASE 指向服务器地址
# 修改 app.js 中的 API_BASE:
# const API_BASE = 'http://47.107.108.157:5001';

# 构建 Android APK
npx cap sync android
cd android
./gradlew assembleDebug

# APK 文件位置：
# android/app/build/outputs/apk/debug/app-debug.apk
```

---

## 数据库表结构

系统会自动创建以下表：

### users 表
- id: 用户ID
- username: 用户名（唯一）
- password_hash: 密码哈希
- created_at: 创建时间
- last_login: 最后登录时间

### triage_history 表
- id: 记录ID
- user_id: 用户ID（外键）
- symptom_input: 症状输入
- triage_result: 分诊结果（JSON）
- conversation_log: 对话记录（JSON）
- created_at: 创建时间

---

## API 接口列表

### 认证接口
- `POST /api/auth/register` - 注册
- `POST /api/auth/login` - 登录
- `POST /api/auth/logout` - 登出
- `GET /api/user/profile` - 获取用户信息

### 导诊接口
- `GET /api/welcome` - 获取欢迎消息
- `POST /api/chat` - 发送消息
- `POST /api/reset` - 重置会话

### 历史记录接口
- `GET /api/history` - 获取历史列表
- `GET /api/history/{id}` - 获取历史详情
- `DELETE /api/history/{id}` - 删除历史记录

---

## 注意事项

1. **安全性**：生产环境请修改 JWT_SECRET_KEY
2. **数据库**：确保 MySQL 允许远程连接（如需要）
3. **防火墙**：开放 5001 端口
4. **HTTPS**：生产环境建议使用 HTTPS
