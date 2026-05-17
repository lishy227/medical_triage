# AI 医疗导诊系统

一个基于多智能体协作的 AI 医疗导诊应用，支持 Web 和 Android 双端运行。系统通过自然语言对话收集用户症状信息，智能推荐就诊科室，并为会员用户提供详细的医疗建议。同时支持用户间的评论互动，形成健康交流社区。

## 📋 项目简介

### 解决的问题

- **就医迷茫**：帮助患者根据症状快速找到合适的就诊科室，减少盲目挂号
- **资源优化**：缓解医院导诊台压力，提升就医效率
- **健康科普**：为会员用户提供疾病知识、饮食建议等专业健康指导
- **用户交流**：通过评论社区让用户分享就医经验、互相帮助

### 核心功能

- 🤖 **AI 智能导诊**：多轮对话收集症状，精准推荐科室
- 👤 **用户系统**：支持注册登录，保存历史导诊记录
- 💎 **会员分级**：普通用户基础导诊，会员享受详细医疗建议
- 💬 **评论社区**：用户可随时查看和发表评论，支持点赞和楼中楼回复
- 📱 **跨平台**：Web 网页 + Android App 双端支持
- 🔄 **会话管理**：支持重置对话、查看历史记录

## 🏗️ 项目结构

```
medical_triage/
├── medical_triage_back/          # 后端服务 (Python Flask)
│   ├── agents/                   # AI 智能体模块
│   │   ├── input_validation_agent.py    # 输入验证智能体
│   │   ├── body_comparison_agent.py     # 身体部位比对智能体
│   │   ├── intent_judgment_agent.py     # 意图判断智能体
│   │   └── question_generation_agent.py # 问题生成智能体
│   ├── knowledge_base/           # 知识库
│   │   ├── medical.json          # 疾病知识库 (RAG 用)
│   │   └── loader.py             # 知识库加载器
│   ├── main.py                   # CLI 入口
│   ├── web_server.py             # Web 服务入口（已集成社交互动路由）
│   ├── deploy.py                 # 生产环境部署脚本（Waitress）
│   ├── triage.py                 # 核心导诊引擎
│   ├── auth.py                   # 用户认证模块
│   ├── database.py               # 数据库模型（已集成社交模型）
│   ├── social.py                 # 社交互动模型（评论、点赞）
│   ├── social_routes.py          # 社交互动 API 路由
│   ├── config.py                 # 配置管理
│   └── requirements.txt          # Python 依赖
│
└── medical_triage_web/           # 前端应用
    ├── www/                      # 前端源码
    │   ├── index.html            # 主页面
    │   ├── style.css             # 样式文件
    │   └── app.js                # 前端逻辑
    ├── capacitor.config.json     # Capacitor 配置
    └── package.json              # Node.js 依赖
```

## 🚀 运行方式

### 后端服务

#### 1. 环境准备

```bash
cd medical_triage_back

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

#### 2. 配置环境变量

创建 `.env` 文件：

```env
#大语言模型配置
API_KEY="你的API KEY"
BASE_URL="对应的url"
MODEL="模型名称"

# 数据库配置
# 本地开发使用 SQLite（无需安装MySQL）：
DATABASE_URL=sqlite:///medical_triage.db
# 生产环境使用 MySQL：
# DATABASE_URL=mysql+pymysql://root:password@localhost/medical_triage

# JWT配置
JWT_SECRET_KEY=your-secret-key-change-this-in-production
JWT_ACCESS_TOKEN_EXPIRE_DAYS=30
```

> 获取 API Key：[阿里云 DashScope](https://dashscope.aliyun.com/)

#### 3. 启动服务

**开发环境（本地测试）**

```bash
# Web 服务（推荐）
python web_server.py

# 或 CLI 交互模式
python main.py
```

Web 服务默认运行在 `http://localhost:5001`

**生产环境（云服务器部署）**

生产环境使用 Waitress 作为 WSGI 服务器，支持 Windows、Linux、Mac 全平台：

```bash
# 使用部署脚本一键启动（自动安装依赖）
python deploy.py

# 或手动启动
pip install waitress
waitress-serve --host=0.0.0.0 --port=5001 --threads=4 web_server:app
```

**部署说明**

- 系统采用后台异步加载医学知识库，启动后即可立即响应 API 请求
- LLM 调用默认 30 秒超时，防止因网络问题导致请求挂起
- 会员详细建议功能在知识库加载完成后自动可用，加载期间返回通用建议
- Waitress 是纯 Python 实现，跨平台兼容，无需额外配置

**常见问题：前端无法连接**

1. **检查防火墙/安全组**（最常见原因）
   ```bash
   # Ubuntu 放行 5001 端口
   sudo ufw allow 5001
   
   # CentOS 放行 5001 端口
   sudo firewall-cmd --permanent --add-port=5001/tcp
   sudo firewall-cmd --reload
   ```
   云服务器还需在控制台配置安全组规则

2. **运行诊断工具**
   ```bash
   python diagnose.py
   ```

3. **测试后端是否可访问**
   ```bash
   curl http://<服务器IP>:5001/api/server/info
   ```

### 前端应用

#### Web 网页

```bash
cd medical_triage_web

# 安装依赖
npm install

# 开发模式（直接打开 index.html 即可）
# 或使用本地服务器
npx serve www
```

#### Android App

```bash
cd medical_triage_web

# 安装依赖
npm install

# 添加 Android 平台
npx cap add android

# 同步资源
npx cap sync

# 打开 Android Studio
npx cap open android

# 在 Android Studio 中构建 APK
# Build → Build Bundle(s) / APK(s) → Build APK(s)
```

详细构建指南：[BUILD.md](medical_triage_web/BUILD.md)

## 🛠️ 技术栈

### 后端

| 技术 | 用途 |
|------|------|
| **Python 3.10+** | 主开发语言 |
| **Flask** | Web 框架 |
| **Flask-CORS** | 跨域支持 |
| **SQLAlchemy** | ORM 数据库操作 |
| **PyMySQL** | MySQL 驱动 |
| **PyJWT** | JWT 认证 |
| **bcrypt** | 密码加密 |
| **OpenAI SDK** | 调用大模型 API（带超时控制） |
| **DashScope** | 阿里云大模型服务 |
| **Waitress** | 生产环境 WSGI 服务器（跨平台） |

### 前端

| 技术 | 用途 |
|------|------|
| **HTML5** | 页面结构 |
| **CSS3** | 样式设计 |
| **JavaScript (ES6+)** | 交互逻辑 |
| **Capacitor** | 混合应用框架（Android） |
| **Fetch API** | HTTP 请求 |

### 数据库

- **SQLite**（开发环境）
- **MySQL**（生产环境，可选）

### AI 模型

- **通义千问 (Qwen)** - 阿里云 DashScope 提供的大模型服务

## 🧠 核心架构

### 多智能体协作流程

```
用户输入
    ↓
[输入验证智能体] ──→ 判断输入类型（身体部位/症状/无关）
    ↓
[身体部位比对智能体] ──→ 检测是否切换身体部位
    ↓
[意图判断智能体] ──→ 匹配用户意图与选项
    ↓
[问题生成智能体] ──→ 生成下一轮询问
    ↓
返回回复
```

### 导诊阶段

1. **阶段 0 - 身体部位**：询问用户哪里不舒服
2. **阶段 1 - 初步症状**：询问大致症状类型
3. **阶段 2 - 具体症状**：询问具体症状描述
4. **阶段 3 - 完成**：推荐就诊科室

### 会员分层

| 功能 | 普通用户 | 会员用户 |
|------|----------|----------|
| 基础导诊 | ✅ | ✅ |
| 科室推荐 | ✅ | ✅ |
| 历史记录 | ✅ | ✅ |
| 评论社区 | ✅ | ✅ |
| 疾病分析 | ❌ | ✅ |
| 治疗建议 | ❌ | ✅ |
| 饮食指导 | ❌ | ✅ |

## 📡 API 接口

### 认证接口

- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `POST /api/auth/logout` - 用户登出
- `GET /api/auth/profile` - 获取用户信息

### 导诊接口

- `GET /api/welcome` - 获取欢迎消息
- `POST /api/chat` - 发送消息（核心接口）
- `POST /api/reset` - 重置会话

### 会员接口

- `POST /api/membership/upgrade` - 升级会员
- `GET /api/membership/status` - 获取会员状态

### 用户中心

- `GET /api/user/center` - 个人中心
- `GET /api/user/history` - 历史记录

### 社交互动接口

- `GET /api/comments` - 获取评论列表（支持分页、排序）
- `POST /api/comments` - 发表评论
- `DELETE /api/comments/<id>` - 删除评论
- `GET /api/comments/<id>/replies` - 获取评论回复
- `POST /api/likes` - 点赞
- `DELETE /api/likes` - 取消点赞
- `GET /api/likes/status` - 查询点赞状态

### 系统接口

- `GET /api/server/info` - 服务器信息（用于重启检测）

## 🔐 安全与性能特性

- **JWT 认证**：基于 Token 的无状态认证
- **密码加密**：使用 bcrypt 存储密码哈希
- **输入验证**：多层输入校验，防止注入攻击
- **敏感词过滤**：评论内容自动过滤不当信息
- **CORS 保护**：跨域请求控制
- **服务器重启检测**：自动检测后端重启并退出登录
- **异步知识库加载**：大型医学知识库后台加载，不阻塞服务启动
- **LLM 超时控制**：API 调用 30 秒超时，防止请求挂起
- **多线程并发**：生产环境支持多线程并发处理请求

## 📝 配置说明

### 后端配置 (config.py)

```python
# 大模型配置
DASHSCOPE_API_KEY = "your_api_key"  # 从环境变量读取
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-turbo"

# 数据文件
DATA_FILE = "table.json"  # 症状-科室映射表
ENCODING = "utf-8"

# 身体部位列表
BODY_TYPES = ["头部", "胸部", "腹部", "四肢", "皮肤", "其他"]
```

### 前端配置 (app.js)

```javascript
// API 基础地址
const API_BASE = "http://localhost:5001";  // 开发环境
// const API_BASE = "http://your-server:5001";  // 生产环境
```

## 🧪 测试

```bash
cd medical_triage_back

# 运行测试
python -m pytest tests/
```

## 📦 部署

### 生产环境部署（推荐）

系统使用 Waitress 作为 WSGI 服务器，支持 Windows、Linux、Mac 全平台统一部署：

**快速部署（推荐）**

```bash
# 使用部署脚本一键启动（自动安装 waitress）
python deploy.py
```

**手动部署**

```bash
# 安装 waitress
pip install waitress

# 启动服务（4线程，60秒超时）
waitress-serve --host=0.0.0.0 --port=5001 --threads=4 web_server:app
```

**Nginx 反向代理配置示例**

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### Docker 部署（可选）

```dockerfile
# Dockerfile 示例
FROM python:3.10-slim
WORKDIR /app
COPY medical_triage_back/requirements.txt .
RUN pip install -r requirements.txt
COPY medical_triage_back/ .
CMD ["python", "web_server.py"]
```

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📄 许可证

本项目仅供学习和研究使用，不得用于商业医疗诊断。

## ⚠️ 免责声明

本系统提供的导诊建议仅供参考，不能替代专业医生的诊断。如有身体不适，请及时就医。

---

**作者**：lishy227  
**版本**：v1.0.0  
**更新日期**：2026-05-17
