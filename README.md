# AI 医疗导诊系统

一个基于多智能体协作的 AI 医疗导诊应用，支持 Web 和 Android 双端运行。系统通过自然语言对话收集用户症状信息，智能推荐就诊科室，并为会员用户提供详细的医疗建议。

## 📋 项目简介

### 解决的问题

- **就医迷茫**：帮助患者根据症状快速找到合适的就诊科室，减少盲目挂号
- **资源优化**：缓解医院导诊台压力，提升就医效率
- **健康科普**：为会员用户提供疾病知识、饮食建议等专业健康指导

### 核心功能

- 🤖 **AI 智能导诊**：多轮对话收集症状，精准推荐科室
- 👤 **用户系统**：支持注册登录，保存历史导诊记录
- 💎 **会员分级**：普通用户基础导诊，会员享受详细医疗建议
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
│   ├── web_server.py             # Web 服务入口
│   ├── triage.py                 # 核心导诊引擎
│   ├── auth.py                   # 用户认证模块
│   ├── database.py               # 数据库模型
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

```bash
# Web 服务（推荐）
python web_server.py

# 或 CLI 交互模式
python main.py
```

Web 服务默认运行在 `http://localhost:5001`

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
| **OpenAI SDK** | 调用大模型 API |
| **DashScope** | 阿里云大模型服务 |

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

### 系统接口

- `GET /api/server/info` - 服务器信息（用于重启检测）

## 🔐 安全特性

- **JWT 认证**：基于 Token 的无状态认证
- **密码加密**：使用 bcrypt 存储密码哈希
- **输入验证**：多层输入校验，防止注入攻击
- **CORS 保护**：跨域请求控制
- **服务器重启检测**：自动检测后端重启并退出登录

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

### 使用 Gunicorn（生产环境）

```bash
gunicorn -w 4 -b 0.0.0.0:5001 web_server:app
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
**更新日期**：2026-05-15
