# 模块功能总结

---

## 🩺 多阶段智能导诊

> 身体部位 → 初步症状 → 具体症状 → 科室推荐，三轮对话精准定位

- **入口**：`GET /api/welcome` → 输出"请问您哪里不舒服？"
- **阶段 0 — 身体部位**：`TriageState.stage = BODY_PART`，26 种预定义部位（头颅/眼/耳/胸部/腹部/皮肤等），用户描述后触发 Agent 验证
- **阶段 1 — 初步症状**：`SymptomRepository.find_initial_symptoms(body_part)` 查询 `table.json`，展示该部位对应的初步症状选项，如头部 → 钝痛/跳痛/针刺样痛等
- **阶段 2 — 具体症状**：`SymptomRepository.find_specific_symptoms(body_part, init_symptom)` 二次查询，进一步细化症状子类
- **阶段 3 — 完成**：`SymptomRepository.find_departments(body_part, init, spec)` 输出科室推荐，触发 `is_complete=True`
- **状态机管理**：`TriageState` dataclass 维护 stage/records/options/messages 四元组，`_advance_stage()` 驱动流转，`to_dict()/from_dict()` 支持完整序列化
- **数据源**：`table.json` 101KB，3854 条映射记录（身体部位→初步症状→具体症状→推荐科室）

---

## 🤖 多智能体协作

> 输入验证 → 部位比对 → 意图判断 → 问题生成，四个 LLM Agent 各司其职

**调用链**（`triage.py: TriageEngine.process()`）：
1. 优先处理部位变更确认 → 2. 输入验证 → 3. 部位比对 → 4. 意图判断 → 5. 问题生成

| 智能体 | 文件 | 职责 | 实现策略 |
|---|---|---|---|
| **输入验证** | `agents/input_validation_agent.py` | 判输入类型：1=身体部位、2=医学相关、3=无关 | 关键词匹配(BODY_KEYWORDS 35词) → 上下文分析 → LLM(t=0.3) → 回退默认(=2) |
| **部位比对** | `agents/body_comparison_agent.py` | 检测用户是否换了身体部位 | **纯规则引擎**：24 种部位别名映射 + 13 族区域归并(如"头颅/眼/耳/鼻→头面"、"上腹部/下腹部→腹部") + 信心阈值判定(≥0.72 才触发变更) |
| **意图判断** | `agents/intent_judgment_agent.py` | 用户回答匹配到哪个选项 | 字母/数字选择(A/B/C/第1个) → 文本匹配(完全/包含/关键词) → LLM(t=0.3) 兜底 |
| **问题生成** | `agents/question_generation_agent.py` | 生成追问题目引导用户 | LLM(t=0.7)，要求口语化、日常语言、单题选择、不超过一条，LLM 失败时回退到静态模板 |

**基类能力**：`base_agent.py` 提供 `_call_llm()`（Tenacity 重试，最多 3 次，指数退避）和 `_parse_json()`（直接解析→代码块提取→花括号提取）

**部位变更保守策略**（5 月 13 日优化后）：
- 必须同时满足：当前部位家族 ≠ 历史部位家族 + 用户有明确新部位陈述
- 同一区域内的别名词不触发（如"肚子"→"腹部"属于同一家族）
- 含有澄清标记(疼/痛/不舒服/就是/其实是)的短输入不触发
- 检测到可能变更时**不自动重置**，而是弹出确认提示"要改查新部位吗？"

---

## 📚 RAG 医学知识增强

> 基于 8,808 条疾病知识库，提供病因、检查、治疗、用药、饮食建议

**两套检索路径共存**：

| 路径 | 位置 | 触发条件 | 工作机制 |
|---|---|---|---|
| **路径 A**（症状检索式） | `rag_retriever.py: DiseaseRAGRetriever` | `TriageEngine.enable_rag=True` 且 RAG 加载成功 | 构建症状倒排索引(`_symptom_index`)，精确匹配(=1.0) + 包含匹配(=0.7)，Top-K 排序 |
| **路径 B**（全量遍历式） | `web_server.py: generate_detailed_advice()` | 导诊完成 **且** 用户是会员 | 遍历 8808 条数据，按名称/症状/描述关键词匹配打分，取 Top 3 |

**路径 A 详细**（`DiseaseExplanationGenerator.generate_explanation()`）：
- `disease_name` + `match_score` + `matched_symptoms`
- `description`（疾病简介，截取前 200 字）
- `cause`（病因，截取前 150 字）
- `departments` / `recommended_checks` / `treatment_methods`
- `common_drugs` / `recommended_foods` / `avoid_foods`
- `prevention` / `notes`（发病率、易感人群、传播途径、并发症）

**知识库**：`knowledge_base/medical.json` 47MB JSONL，8808 条，来源于 QASystemOnMedicalKG 公开项目
- 每条包含：name / desc / cause / symptom / cure_department / cure_way / cure_lasttime / cured_prob / common_drug / do_eat / not_eat / prevent / get_prob / easy_get / get_way / acompany / cost_money 等字段

**性能设计**：模块级单例缓存 `_RAG_SYSTEM_CACHE` + `_medical_cache`，首次加载 3-5s，后续命中内存

---

## 👤 会员分级体系

> 免费用户获取科室推荐，会员解锁详细医疗建议和疾病百科

**实现位置**：`web_server.py: chat()` 接口

```python
if user.is_member:
    result['detailed_medical_advice'] = generate_detailed_advice(...)
    result['detail_level'] = 'member'
    result['detail_locked'] = False
else:
    result['detail_level'] = 'basic'
    result['detail_locked'] = True   # 前端据此：遮蔽详情 + 显示"升级会员"按钮
```

**数据模型**（`database.py: User`）：
- `membership_type`：'free' | 'member'
- `member_started_at` / `member_expires_at`：会员起止时间
- `is_member` property：`type=='member' AND (未过期 OR 无过期时间)`
- 兼容迁移：旧数据库自动补充 member 字段（`_ensure_user_membership_columns()`）

**前端表现**（`medical_triage_web/www/js/chat.js`）：
- `detail_locked=True` → 科室推荐后显示遮蔽层 + "升级会员解锁详细建议"按钮
- `detail_locked=False` → 完整展示疾病知识卡片（病因/检查/治疗/药物/饮食）
- CSS 变量控制会员徽章样式

**当前为模拟实现**：`POST /api/membership/upgrade` 直接设为会员，30 天有效期，无支付流程

---

## 💬 评论社区

> 支持导诊记录评论、回复（楼中楼）、点赞互动

**数据模型**（`social.py`）：

| 表 | 关键设计 |
|---|---|
| **comments** | `parent_id` 自引用（楼中楼）· `like_count` 冗余字段 · `status` 活跃/删除/隐藏（软删除）· 复合索引 `(target_type, target_id)` |
| **likes** | 联合唯一约束 `(user_id, target_type, target_id)` 防重复点赞 |

**API 端点**（`social_routes.py`，FastAPI APIRouter，挂载在 `/api` 前缀）：

| 端点 | 功能 |
|---|---|
| `GET /api/comments?target_type=&target_id=&page=&sort=` | 分页查询（hot/new/top 排序），仅查顶层评论 |
| `POST /api/comments` | 发表评论/回复，含敏感词校验（`validate_comment_content()`） |
| `DELETE /api/comments/{id}` | 软删除，仅作者可操作 |
| `GET /api/comments/{id}/replies` | 获取楼中楼回复列表 |
| `POST /api/likes` | 点赞，后端维护 like_count |
| `DELETE /api/likes` | 取消点赞 |

**安全机制**：
- 内容长度校验 1-500 字符
- 敏感词过滤（广告/推广/加微信等 spam 类 + 不当内容）
- 回复目标一致性校验（parent 的 target_type/target_id 必须匹配）

**前端**（`www/js/social.js`）：独立面板，左侧"评论社区"按钮打开，支持浏览/发表/回复/点赞

---

## 📱 跨平台

> Web + Android APK（Capacitor 打包），一套代码多端运行

**Web 端**：纯静态 HTML5 + CSS3 + Vanilla JS
- 6 个 ES Module 文件（core/auth/chat/social/ui/app），零框架依赖
- `www/index.html` 主入口，通过 `http://localhost:5001` 访问
- FastAPI 托管静态文件（`app.mount('/', StaticFiles)`），也支持 Nginx 单独部署

**Android 端**：Capacitor 封装
- `capacitor.config.json` 配置应用元信息和 `server.url`（指向后端）
- `android/` 目录包含完整 Gradle 项目（Android Studio 直接打开）
- `build-android.bat` / `build-android.sh` 一键构建
- 已有构建产物：`app-debug.apk` 3.7MB

**架构优势**：Web 和 APK 共享同一套 `www/` 源码，修改即两端同步生效

---

## 🔐 安全认证

> JWT Token 鉴权，bcrypt 密码哈希，登录态自动恢复

**JWT 实现**（`auth.py`）：
- 算法：HS256，密钥通过 `JWT_SECRET_KEY` 环境变量注入（已设置强密钥）
- 有效期：168 小时（7 天，`JWT_ACCESS_TOKEN_EXPIRE_DAYS` 可配置）
- Payload：`{user_id, exp, iat, type:'access'}`
- FastAPI 集成：`get_current_user()` 作为 Depends 注入，自动解析 Bearer Token → 返回 User 对象（验证失败自动 401）
- 可选认证：`get_optional_user()` 用于公开接口，token 有效则返回 User，无效返回 None

**密码安全**：
- bcrypt 12 轮 salt 哈希（`hash_password()` / `verify_password()`）
- 注册密码最短 6 位，用户名 3-50 位（Pydantic Field 校验）

**前端登录态**（`www/js/auth.js`）：
- Token 存储在 localStorage
- `buildAuthHeaders()` 统一注入 `Authorization: Bearer ...`
- 页面加载时自动检测 token 有效性（静默恢复登录态）
- 登录/注册后自动刷新 UI（个人中心、会员标识）

---

## 🗄️ MySQL 数据库

> SQLite 零配置开发 + MySQL 生产无缝切换，SQLAlchemy 2.0 ORM 自动建表

**双数据库策略**（`database.py` + `config.py`）：

```ini
# .env 中一行切换：
DATABASE_URL=sqlite:///medical_triage.db                    # 本地开发（零依赖）
DATABASE_URL=mysql+pymysql://root:123456@localhost/medical_triage  # 生产环境
```

**实现细节**：

| 层面 | 设计 |
|---|---|
| **引擎管理** | `get_engine()` 单例延迟初始化，`pool_pre_ping=True` + `pool_recycle=3600` 防止连接超时 |
| **会话管理** | `get_db_session()` 上下文管理器，自动 commit/rollback/close，`expire_on_commit=False` 避免懒加载异常 |
| **ORM 模型** | SQLAlchemy 2.0 声明式映射（`mapped_column`），`User` / `TriageHistory` / `Comment` / `Like` 四张表 |
| **自动迁移** | `init_database()` 启动时自动 `create_all`，`_ensure_user_membership_columns()` 兼容旧库补充缺失字段 |
| **关联设计** | User → TriageHistory（级联删除），Comment 自引用（楼中楼），Like 联合唯一约束 |
| **JSON 字段** | `triage_result` 和 `conversation_log` 使用 SQLAlchemy `JSON` 类型，原生存取 dict/list |
| **向后兼容** | `SessionLocal` 别名支撑旧模块 (`social_routes.py`)，`get_session_factory_with_engine()` 兼容旧调用 |

**四张数据表**：

```
users
├── id (PK, autoincrement)
├── username (UNIQUE, index)
├── password_hash (bcrypt)
├── membership_type / member_started_at / member_expires_at
├── created_at / last_login
└── → triage_history (cascade delete)

triage_history
├── id (PK)
├── user_id (FK → users.id, index)
├── symptom_input (TEXT)
├── triage_result (JSON)
├── conversation_log (JSON)
└── created_at (index)

comments
├── id (PK)
├── user_id (FK → users.id)
├── target_type / target_id (复合索引)
├── content / parent_id (自引用) / like_count / status
└── created_at / updated_at

likes
├── id (PK)
├── user_id / target_type / target_id (联合唯一约束)
└── created_at
```

**当前环境**：MySQL `root@localhost/medical_triage`，与 Redis 均在本地运行

---

## 🚀 多进程 & FastAPI 高并发

> FastAPI 异步内核 + Waitress 多线程 + Redis 会话共享，单机轻松应对高并发

**异步基础 — FastAPI**（`web_server.py`）：
- 原生 `async` 路由支持（`async def chat(...)`），底层 uvicorn asyncio 事件循环
- 非阻塞 I/O：数据库查询使用同步 SQLAlchemy（`with get_db_session()`），但 FastAPI 自动在线程池中执行，不阻塞事件循环
- 自动生成 OpenAPI 文档（`http://localhost:5001/docs`）
- CORS 中间件全开放，允许任意来源跨域访问
- 后台线程预热知识库（`threading.Thread(target=load_medical_json)`），不阻塞启动

**多进程部署方案**：

| 平台 | 方案 | 命令 |
|---|---|---|
| **Windows** | Waitress 4 线程 | `python deploy.py` → `waitress.serve(app, host='0.0.0.0', port=5001, threads=4)` |
| **Linux** | Gunicorn 4 Worker | `gunicorn -w 4 -b 0.0.0.0:5001 --timeout 60 web_server:app` |
| **生产推荐** | Nginx 反向代理 | `upstream backend { server 127.0.0.1:5001; ... }` → Gunicorn 多 Worker |

**多进程下的会话一致性**（`session_manager.py`）：
```
                   ┌──────────────┐
                   │    Nginx     │
                   │  负载均衡     │
                   └──┬──┬──┬──┬─┘
                      │  │  │  │
              ┌───────┘  │  │  └───────┐
              ▼          ▼  ▼          ▼
          Worker 1   Worker 2   Worker 3   Worker 4
              │          │          │          │
              └──────────┴────┬─────┴──────────┘
                              │
                     ┌────────▼────────┐
                     │     Redis       │
                     │  triage:session:*│
                     └─────────────────┘
```

- 用户请求可能被 Nginx 分发到不同 Worker，但所有 Worker 共享 Redis 中的会话状态
- 每次请求：`SessionManager.get_engine(sid)` → Redis `GET + EXPIRE`（自动续期）
- 每次响应：`SessionManager.save_engine(sid, engine)` → Redis `SETEX`（30 分钟 TTL）
- Redis 不可达时自动降级到内存存储 + 打印警告，单进程场景不受影响

**并发性能设计要点**：
- `SymptomRepository` 单例：table.json 只加载一次，多请求共享
- `_RAG_SYSTEM_CACHE` / `_medical_cache` 模块级缓存：47MB 知识库只解析一次
- `get_config()` 使用 `@lru_cache(maxsize=1)`：配置单例
- LLM 调用通过 Tenacity 指数退避重试（最多 3 次），避免瞬态故障影响请求

---

## ♻️ 会话持久化

> 支持 Redis 共享存储，多 Worker 部署下对话不中断

**架构**（`session_manager.py`）：

```
SessionManager (门面)
  ├── MemorySessionBackend     # 开发/单进程：dict + 惰性过期清理
  └── RedisSessionBackend      # 生产/多Worker：scan + setex + 自动续期
      策略：配置 REDIS_URL 且 ping 通 → Redis；否则自动降级内存 + 打印警告
```

**关键机制**：
- **TTL**：统一 30 分钟（1800 秒），内存惰性清理（get/reset 时 purge），Redis 原生 EXPIRE
- **序列化**：`TriageState.to_dict()` → JSON → 存储，恢复时 `TriageEngine(saved_state=dict)` 重建
- **续期**：每次 `get_engine()` 命中时，自动续期 TTL
- **Key 格式**：`triage:session:{session_id}`
- **连接容错**：Redis 初始化失败 → 自动降级 + 打印警告，不影响服务可用性

**应用场景**：
- 单进程开发：零依赖，内存存储即开即用
- 多 Worker 生产：多个 Gunicorn/Waitress 进程共享 Redis 会话，用户负载均衡后对话不中断
- 当前环境已配置 Redis：`REDIS_URL=redis://localhost:6379/0`，容器已运行
