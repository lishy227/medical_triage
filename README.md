# 🏥 AI 医疗导诊系统

基于 LLM 多智能体协作的智能医疗导诊系统，通过多轮对话引导用户描述症状，自动推荐就诊科室，并结合医学知识图谱提供疾病解释、治疗建议和用药参考。

## 技术栈

| 层级 | 技术方案 |
|---|---|
| **AI 引擎** | 阿里云 DashScope (qwen-plus) · 多智能体协作 · RAG 知识检索 |
| **后端** | Python 3.10+ · FastAPI · SQLAlchemy 2.0 · Pydantic · Uvicorn |
| **前端** | HTML5 + CSS3 · Vanilla JS (ES Modules) · Capacitor |
| **数据库** | SQLite（开发） / MySQL（生产） |
| **认证** | JWT + bcrypt · 会员分级（免费 / 付费） |
| **会话** | 内存 / Redis 双后端，自动降级 |
| **知识库** | 8,808 种疾病，5,998 个症状条目 · MySQL（生产）/ JSON 文件（开发）自动回退 |

## 功能亮点

- **🩺 多阶段智能导诊**：身体部位 → 初步症状 → 具体症状 → 科室推荐，三轮对话精准定位
- **🤖 多智能体协作**：输入验证 → 部位比对 → 意图判断 → 问题生成，四个 LLM Agent 各司其职
- **📚 RAG 医学知识增强**：基于 8,808 条疾病知识库，提供病因、检查、治疗、用药、饮食建议
- **👤 会员分级体系**：免费用户获取科室推荐，会员解锁详细医疗建议和疾病百科
- **💬 评论社区**：支持导诊记录评论、回复（楼中楼）、点赞互动
- **📱 跨平台**：Web + Android APK（Capacitor 打包），一套代码多端运行
- **🔐 安全认证**：JWT Token 鉴权，bcrypt 密码哈希，登录态自动恢复
- **♻️ 会话持久化**：支持 Redis 共享存储，多 Worker 部署下对话不中断

## 环境依赖

- Python 3.10+
- MySQL 5.7+（生产环境，可选；开发使用 SQLite 零依赖）
- Redis 6.0+（可选，用于多进程会话共享）
- Node.js 18+ + npm（仅 Android 打包需要）

## 安装部署

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd medical_triage
```

### 2. 配置环境变量

```bash
cd medical_triage_back
cp .env.example .env   # 如无 .env.example，直接编辑 .env
```

编辑 `.env`：

```ini
# LLM 配置（阿里云 DashScope）
API_KEY=sk-your-api-key-here
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL=qwen-plus

# 数据库
DATABASE_URL=sqlite:///medical_triage.db          # 本地开发
# DATABASE_URL=mysql+pymysql://root:password@localhost/medical_triage  # 生产

# JWT（运行 python -c "import secrets; print(secrets.token_urlsafe(43))" 生成）
JWT_SECRET_KEY=your_jwt_secret_here

# Redis（可选，不填则使用内存存储）
# REDIS_URL=redis://localhost:6379/0
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 初始化数据库

首次运行时自动建表，无需手动操作。

### 5. 疾病知识库导入 MySQL

> `medical.json` 含 8,808 条疾病数据，文件 47MB。默认以 JSON 文件加载（首次请求 3-5 秒，内存 +100MB）。
> 执行本步骤后，疾病数据存入 MySQL 数据库，检索走 SQL 查询，启动内存降至 <50MB。

#### 为什么做这一步

| | JSON 文件加载 | MySQL 数据库 |
|---|---|---|
| 启动内存 | 每 Worker +100MB（4 Worker ≈ 400MB） | 零额外内存 |
| 内存原理 | `json.loads()` × 8808 → Python dict 全部驻留堆 | InnoDB 按页读磁盘，不驻留内存 |
| 首请求 | 3-5 秒（加载到内存） | 毫秒（SQL 查询） |
| 多 Worker | 每个进程独立加载，内存叠加 | 共享同一份数据库文件 |

**低内存服务器（<2GB）强烈推荐。**

#### 执行导入

```bash
cd medical_triage_back

# 首次导入（流式逐行写入，不占内存，约 30 秒）
python setup_diseases.py
```

导入进程输出示例：
```
==================================================
医疗知识库 — 疾病表初始化
==================================================
表已就绪: diseases
表为空，开始导入...
  已导入 200 条...
  已导入 400 条...
  ...
  已导入 8800 条...

导入完成: 共 8808 条, 新导入 8808 条, 跳过 0 条, 总计 8808 条
```

#### 常用命令

```bash
python setup_diseases.py             # 首次导入 / 增量追加（跳过已存在的）
python setup_diseases.py --status    # 查看当前表记录数 + 示例数据
python setup_diseases.py --force     # 删除旧表，全部重建
```

#### 验证

```bash
python setup_diseases.py --status
# 输出：
# 疾病表记录数: 8808
# 示例疾病: 偏头痛, 紧张性头痛, 丛集性头痛
```

#### 工作原理

```
未执行 setup_diseases.py：
  请求 → search_diseases() → diseases 表不存在 → 秒抛异常
      → 自动回退 _load_diseases_from_json()
      → 读 47MB 文件到内存 → 业务正常（功能无差异）

执行后重启：
  请求 → search_diseases() → SELECT FROM diseases
      → MySQL 返回匹配结果 → 零内存加载
```

> 未执行本步骤时系统功能完全正常，仅在内存和首请求速度上有差异。
> 导入后需重启服务（`python deploy.py`）才能切换到 MySQL 后端。

## 启动命令

### 本地开发

```bash
cd medical_triage_back
python web_server.py
# 浏览器访问 http://localhost:5001
```

### 生产部署

```bash
cd medical_triage_back
python deploy.py
# 使用 Uvicorn ASGI 服务器，4 Worker，监听 0.0.0.0:5001
```

也可直接用 Gunicorn（Linux/macOS）：

```bash
gunicorn -w 4 -b 0.0.0.0:5001 --timeout 60 web_server:app
```

### Android APK 打包

```bash
cd medical_triage_web
npm install
npx cap sync android
npx cap open android     # 在 Android Studio 中构建
```

## 使用教程

### 1. 注册 / 登录

打开页面后点击右上角「注册」，输入用户名和密码（至少 6 位）。注册成功后自动登录。

### 2. 开始导诊

1. 在输入框描述症状，例如：`我头痛`
2. 系统识别身体部位「头颅」，询问初步症状类型（持续性钝痛 / 搏动性跳痛 / 针刺样痛）
3. 选择具体症状后，系统给出**科室推荐**和**匹配疾病信息**
4. 完成导诊后可开始新对话

### 3. 会员功能

- 免费用户：看到科室推荐 + 基础指导
- 会员用户（点击「升级会员」）：额外获得详细的疾病百科、治疗建议、用药参考、饮食指导

### 4. 社区互动

点击左侧「评论社区」按钮，浏览其他用户的导诊记录和评论，支持回复和点赞。

## 项目目录结构

```
medical_triage/
├── README.md
├── DEPLOY.md                           # 部署详细文档
├── .gitignore
│
├── medical_triage_back/                # 后端服务
│   ├── web_server.py                   # FastAPI 主入口 · 路由注册 · 会话管理
│   ├── triage.py                       # 核心导诊引擎 · TriageEngine · TriageState
│   ├── config.py                       # Pydantic 配置管理（.env 加载）
│   ├── database.py                     # SQLAlchemy 模型（User, TriageHistory, DiseaseModel）
│   ├── auth.py                         # JWT + bcrypt 认证模块
│   ├── session_manager.py              # 双后端会话存储（内存 / Redis）
│   ├── rag_retriever.py                # RAG 检索 · 疾病匹配 · 解释生成（MySQL/JSON 双后端）
│   ├── social.py                       # 评论 / 点赞模型 + 敏感词过滤
│   ├── social_routes.py                # 社交 API 路由
│   ├── deploy.py                       # 生产部署脚本（Uvicorn）
│   ├── setup_diseases.py               # 疾病知识库导入 MySQL 工具
│   ├── main.py                         # 备用 CLI 入口
│   ├── requirements.txt                # Python 依赖清单
│   ├── table.json                      # 症状-科室映射数据
│   ├── .env                            # 环境变量（不提交 Git）
│   │
│   ├── agents/                         # 四智能体
│   │   ├── base_agent.py               #   基类 · LLM 调用 · 重试机制 · JSON 解析
│   │   ├── input_validation_agent.py   #   输入验证 · 类型判断（部位/症状/无关）
│   │   ├── body_comparison_agent.py    #   部位变更检测 · 确认机制
│   │   ├── intent_judgment_agent.py    #   意图匹配 · 选择项定位
│   │   └── question_generation_agent.py#   问题生成 · 追问构建
│   │
│   ├── knowledge_base/                 # 医学知识库
│   │   ├── loader.py                   #   数据加载 · Disease 模型 · 索引构建
│   │   ├── medical.json                #   8,808 条疾病数据（JSONL）
│   │   └── README.md                   #   数据来源说明
│   │
│   └── tests/                          # 测试
│       ├── test_session_serialization.py   # TriageState 序列化测试
│       ├── test_session_manager.py         # SessionManager 行为 + 性能测试
│       ├── test_membership_step2_acceptance.py  # 会员功能验收
│       ├── test_step3_route_integration.py      # 路由集成测试
│       └── benchmark_performance.py            # 独立性能基准
│
└── medical_triage_web/                 # 前端
    ├── capacitor.config.json           # Capacitor 配置
    ├── package.json                    # Node 依赖
    ├── android/                        # Android 原生项目
    ├── build-android.bat               # 一键打包脚本
    │
    └── www/                            # Web 前端源码
        ├── index.html                  # 主页面
        ├── style.css                   # 全局样式
        ├── app.js                      # 入口（导入 js/ 模块）
        └── js/                         # JS 模块
            ├── core.js                 #   API 基础配置 · HTTP 封装 · 服务器检测
            ├── ui.js                   #   DOM 操作 · 弹窗 · 加载动画
            ├── auth.js                 #   登录/注册 · 个人中心 · 会员升级
            ├── chat.js                 #   导诊对话 · 消息发送 · 阶段指示器
            ├── social.js               #   评论 · 回复 · 点赞
            └── app.js                  #   模块装配 · 事件绑定 · 启动引导
```

## 核心架构

```
用户输入 → InputValidationAgent (类型判断)
         → BodyComparisonAgent  (部位变更检测)
         → IntentJudgmentAgent  (意图匹配)
         → QuestionGeneration   (追问生成)
         → 回复用户

完成时 → SymptomRepository (症状→科室查询)
       → DiseaseRAGRetriever (疾病知识检索)
       → 返回科室 + 疾病解释 + 建议
```

**会员分层**：`/api/chat` 根据 `membership_type` 控制返回内容：
- `free` → 仅科室推荐
- `member` → 科室推荐 + 详细医疗建议（病因、检查、治疗、用药、饮食）

## 注意事项

- **医学免责**：本系统仅供参考和学习研究，不构成医疗诊断。如有不适请及时就医。
- **API Key 安全**：`.env` 文件包含 API 密钥，已加入 `.gitignore`，切勿提交到版本库。
- **知识库数据**：疾病数据来源于公开的医学知识图谱项目 QASystemOnMedicalKG，仅供学习使用。
- **JWT 密钥**：生产环境务必使用 `secrets.token_urlsafe(43)` 生成强密钥替换默认值。
- **会话存储**：未配置 Redis 时使用进程内存，服务器重启会丢失所有活跃会话。多 Worker 部署请配置 Redis。
- **前端访问**：必须通过 `http://localhost:5001` 访问，直接双击打开 HTML 文件会导致 JS 模块加载失败。

## 常见问题

### Q: 启动报 `ModuleNotFoundError`
```bash
pip install -r requirements.txt   # 确保已安装所有依赖
```

### Q: 注册/登录按钮无反应
确认通过 `http://localhost:5001` 访问，而非直接打开 HTML 文件。

### Q: RAG 系统加载失败
知识库文件 `medical.json` 过大（~50MB），首次加载可能耗时 3-5 秒。后续请求命中缓存，无需重新加载。

**低内存服务器**：执行 `python setup_diseases.py` 将知识库导入 MySQL，启动内存从 47MB+ 降至 <50MB，此后疾病检索走数据库查询，不再加载 JSON 文件。

### Q: 如何切换数据库
修改 `.env` 中的 `DATABASE_URL`：
- SQLite：`sqlite:///medical_triage.db`
- MySQL：`mysql+pymysql://user:password@host/medical_triage`

### Q: 如何启用 Redis 会话共享
1. 安装 Redis 并启动服务
2. `pip install redis`
3. `.env` 中添加 `REDIS_URL=redis://localhost:6379/0`
4. 重启服务

### Q: 如何部署到公网

建议架构：Nginx 反向代理 → Uvicorn 多 Worker → Redis 会话 → MySQL（含 diseases 表）

```bash
# 1. 服务器安装 MySQL + Redis 并启动
# 2. 克隆项目，修改 .env 为 MySQL 连接串 + Redis URL
# 3. 安装依赖
pip install -r requirements.txt
# 4. 导入疾病知识库到 MySQL（重要：避免 4 Worker × 47MB = OOM）
python setup_diseases.py
# 5. 启动服务
python deploy.py
# 6. 配置 Nginx 反向代理到 :5001
```

## License

本项目仅供学习和研究使用。疾病知识库数据来源于 [QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG)。
