# 🏥 AI 医疗导诊系统 — 项目整理报告

> 整理时间：2026-05-19  
> 基于对全部源码的逐文件审查，梳理项目结构、架构设计和代码现状

---

## 一、项目概览

| 维度 | 描述 |
|---|---|
| **项目名称** | AI 医疗导诊系统 (medical_triage) |
| **核心功能** | 基于 LLM 多智能体协作，通过多轮对话引导用户描述症状 → 自动推荐就诊科室 → 疾病百科增强 |
| **技术栈** | Python 3.10+ / FastAPI / OpenAI SDK / SQLAlchemy 2.0 / Pydantic v2 / Tenacity |
| **AI 引擎** | 阿里云 DashScope (Qwen-Plus) |
| **LLM 温度** | 验证类 0.3，生成类 0.7 |
| **前端** | Vanilla JS (ES Modules) + Capacitor (Android APK) |
| **数据库** | SQLite（开发） / MySQL（生产），SQLAlchemy ORM |
| **认证** | JWT HS256 + bcrypt (12 rounds) |
| **总代码量** | 后端 ~2900 行，前端 ~2800 行（不含 vendor） |

---

## 二、目录结构（按职责分层）

```
medical_triage/
├── README.md                           # 项目说明 + 使用教程
├── DEPLOY.md                           # 部署文档（含阿里云部署步骤）
├── medical_triage.db                   # SQLite 数据库（根目录副本）
├── app-debug.apk                       # Android 调试包 (3.7MB)
│
├── medical_triage_back/                # 后端（Python / FastAPI）
│   ├── web_server.py        [16K]      # ★ FastAPI 入口 · 全部路由 · 会员分层逻辑
│   ├── triage.py            [24K]      # ★ 核心导诊引擎 · TriageState · 4 阶段状态机
│   ├── config.py            [4.3K]     # Pydantic Settings · .env 加载 · 单例
│   ├── database.py          [8.7K]     # SQLAlchemy 模型（User, TriageHistory）
│   ├── auth.py              [4.7K]     # JWT + bcrypt · FastAPI Depends 注入
│   ├── session_manager.py   [8.9K]     # 双后端会话（内存/Redis）· 自动降级
│   ├── rag_retriever.py     [14K]      # ★ RAG 检索 · 症状倒排索引 · 疾病解释生成
│   ├── social.py            [6.3K]     # 评论/点赞模型 · 敏感词过滤
│   ├── social_routes.py     [9.9K]     # 社交 API 路由 (FastAPI Router)
│   ├── deploy.py            [1.8K]     # 生产部署 (Waitress)
│   ├── main.py              [1.5K]     # 备用 CLI 入口
│   ├── table.json           [101K]     # 症状-科室映射数据（3854 条）
│   ├── requirements.txt     [1.3K]     # Python 依赖清单
│   ├── .env                            # 环境变量（API Key 等，不纳入 Git）
│   │
│   ├── agents/              # ★ 四大智能体
│   │   ├── base_agent.py            #   基类 · LLM 调用 · Tenacity 重试(3次) · JSON 解析
│   │   ├── input_validation_agent.py#   输入验证 · 类型判为 1(部位)/2(症状)/3(无关)
│   │   ├── body_comparison_agent.py #   部位变更检测 · 别名映射(24区) · 家族归并(13族)
│   │   ├── intent_judgment_agent.py #   意图匹配 · 选项定位 · LLM 兜底
│   │   └── question_generation_agent.py# 追问生成 · 日常口语化 · 单题选择
│   │
│   ├── knowledge_base/      # 医学知识库
│   │   ├── loader.py            [12K]  # Disease 模型 · JSONL 加载 · 索引
│   │   ├── medical.json         [47MB] # 8808 条疾病数据（JSONL 格式）
│   │   └── README.md            [6.8K] # 数据来源：QASystemOnMedicalKG
│   │
│   └── tests/               # 测试套件
│       ├── test_session_manager.py        # SessionManager 单元 + 性能12用例
│       ├── test_session_serialization.py  # TriageState 序列化测试
│       ├── test_membership_step2_acceptance.py # 会员功能 2 用例验收
│       ├── test_step3_route_integration.py     # 路由集成测试
│       └── benchmark_performance.py            # 独立性能基准
│
└── medical_triage_web/       # 前端（Vanilla JS + Capacitor）
    ├── www/
    │   ├── index.html            [8.4K]  # 主页面 · 聊天区 + 侧边栏
    │   ├── style.css             [25K]   # 全局样式 · 会员标识 · 阶段指示器
    │   ├── app.js                [612B]  # 入口 · 导入模块
    │   └── js/
    │       ├── app.js            [3.4K]  # 模块装配 · 事件绑定 · 启动
    │       ├── core.js           [6.4K]  # API 配置 · HTTP 封装 · 服务器检测
    │       ├── auth.js           [8.0K]  # 登录/注册 · 个人中心 · 会员升级
    │       ├── chat.js           [5.5K]  # 导诊对话 · 阶段指示器 · 科室推荐展示
    │       ├── social.js         [9.4K]  # 评论列表 · 回复 · 点赞
    │       └── ui.js             [25K]   # DOM 渲染 · 弹窗 · 加载动画
    └── android/                  # Capacitor Android 原生项目
```

---

## 三、核心架构设计

### 3.1 请求处理全链路

```
HTTP Request (FastAPI)
    │
    ├─ auth.py: get_current_user()  ← Depends 注入，Bearer Token 解析
    │
    ├─ session_manager.py: get_engine(session_id)
    │   └─ 后端选择：Redis (生产) > Memory (开发，自动降级)
    │   └─ 状态恢复：TriageState.from_dict() → TriageEngine
    │
    └─ web_server.py: chat()
        ├─ engine.process(message)           ← triage.py
        │   ├─ _handle_pending_body_change_confirmation()  ← 优先处理确认分支
        │   ├─ [Agent 1] _validate_input()   ← input_validation_agent
        │   ├─ [Agent 2] _check_body_change()← body_comparison_agent
        │   ├─ [Agent 3] _judge_intent()     ← intent_judgment_agent
        │   └─ [Agent 4] _generate_question()← question_generation_agent
        │
        ├─ is_complete → 会员分层判断
        │   ├─ free    → 仅科室推荐
        │   └─ member  → 科室推荐 + detailed_medical_advice
        │       └─ generate_detailed_advice() → 遍历 medical.json 匹配
        │
        └─ sessions.save_engine() → 持久化到 Redis/Memory
```

### 3.2 四阶段导诊状态机

```
BODY_PART (0) → INITIAL_SYMPTOM (1) → SPECIFIC_SYMPTOM (2) → COMPLETED (3)

Stage 0: "请问您哪里不舒服？"          → 用户选身体部位（24 种）
Stage 1: "这种感觉是...？"              → 用户选初步症状（查 table.json）
Stage 2: "请再具体描述一下..."          → 用户选具体症状（查 table.json）
Stage 3: 推荐科室 + RAG 疾病解释        → 结束
```

### 3.3 四大智能体职责

| 智能体 | 职责 | 实现方式 |
|---|---|---|
| **InputValidationAgent** | 判输入是 1(部位)/2(症状)/3(无关) | 关键词 → 上下文 → LLM(0.3) → 回退逻辑 |
| **BodyComparisonAgent** | 部位变更检测（纯规则，无 LLM 调用） | 24 种部位别名映射 + 13 族区域归并 + 信心阈值判定 |
| **IntentJudgmentAgent** | 用户回答匹配到哪个选项 | 字母/数字选择 → 直接文本匹配 → LLM(0.3) 兜底 |
| **QuestionGenerationAgent** | 生成追问题目 | LLM(0.7)，要求口语化、单题选择 |

**关键设计细节：**
- BodyComparisonAgent 是纯粹的规则引擎，不调用 LLM（避免延迟 + 成本）
- 部位变更检测采用保守策略：需同时满足 "家族不同" + "明确新部位陈述" 才触发
- 不会自动重置，而是弹出确认提示："要改查新部位吗？（是/否）"
- InputValidationAgent 有多级回退：关键词 → 上下文分析 → LLM → 默认认为医学相关

---

## 四、关键模块详细说明

### 4.1 triage.py — 核心引擎

- **TriageState**: dataclass，包含 stage/records/options/messages/pending_body_change
  - `.to_dict()` / `.from_dict()` 完整序列化，支撑会话持久化
- **SymptomRepository**: 单例模式，从 table.json 加载症状-科室映射
  - `find_initial_symptoms(body_part)` → 该部位的所有初步症状
  - `find_specific_symptoms(body_part, init_symptom)` → 具体症状列表
  - `find_departments(body_part, init_symptom, spec_symptom)` → 推荐科室
- **TriageEngine**: 协调四个 Agent，管理状态机流转
  - 支持 `saved_state` 参数恢复历史会话
  - `_handle_pending_body_change_confirmation()` 优先处理用户对部位变更的确认

### 4.2 session_manager.py — 双后端会话

```
SessionManager
├── MemorySessionBackend (dict + 惰性过期清理)
└── RedisSessionBackend (scan + setex + 自动续期)
    策略：Redis 可用 → Redis，否则自动降级内存 + 打印警告
```

### 4.3 rag_retriever.py — 知识检索增强

- **DiseaseRAGRetriever**: 基于症状倒排索引 + 模糊匹配
  - 精确匹配 (score=1.0) → 包含匹配 (score=0.7)
  - 单例加载，避免 47MB 重复加载
- **DiseaseExplanationGenerator**: 将检索结果生成用户友好回复
  - 疾病简介 / 病因 / 推荐科室 / 建议检查 / 治疗方式 / 药物 / 饮食 / 预防

### 4.4 web_server.py — FastAPI 路由层

- **会员分层逻辑**（核心差异化）：
  ```python
  if user.is_member:
      result['detailed_medical_advice'] = generate_detailed_advice(...)
      result['detail_level'] = 'member'
      result['detail_locked'] = False
  else:
      result['detail_level'] = 'basic'
      result['detail_locked'] = True   # 前端据此显示会员升级提示
  ```
- **generate_detailed_advice()**: 遍历 8808 条疾病，按名称+症状+描述匹配打分，取 Top 3

### 4.5 database.py — 数据模型

| 表 | 关键字段 | 说明 |
|---|---|---|
| **users** | id, username, password_hash, membership_type, member_* | 用户 + 会员过期时间 |
| **triage_history** | id, user_id(FK), symptom_input, triage_result(JSON), conversation_log(JSON) | 每次导诊完成保存 |
| **comments** | id, user_id, target_type, target_id, content, parent_id, like_count | 评论+回复 |
| **likes** | id, user_id, target_type, target_id (UNIQUE) | 点赞记录 |

---

## 五、API 接口全集

### 认证
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 注册（username≥3, password≥6） |
| POST | `/api/auth/login` | 登录，返回 JWT |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/auth/profile` | 获取当前用户资料 |

### 导诊核心
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/welcome?session_id=` | 获取欢迎消息 |
| POST | `/api/chat` | **核心**：发送消息，返回回复 + is_complete + 科室 + 建议 |
| POST | `/api/reset` | 重置会话 |

### 会员
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/membership/upgrade` | 模拟升级（30 天有效期） |
| GET | `/api/membership/status` | 查询会员状态 |

### 用户中心
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/user/center` | 个人中心（含历史记录数） |
| GET | `/api/user/history?limit=` | 获取历史记录列表 |

### 社交
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/comments` | 获取评论列表（分页、排序） |
| POST | `/api/comments` | 发表评论/回复 |
| DELETE | `/api/comments/{id}` | 删除评论（软删除） |
| GET | `/api/comments/{id}/replies` | 获取回复列表 |
| POST | `/api/likes` | 点赞 |
| DELETE | `/api/likes` | 取消点赞 |
| GET | `/api/likes/status` | 查询点赞状态 |

### 系统
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/server/info` | 服务器实例 ID（用于重启检测） |
| GET | `/docs` | 自动生成的 OpenAPI 文档 |

---

## 六、数据流 & 状态管理

### 会话生命周期
```
创建: session_id → SessionManager.get_engine() → new TriageEngine
持久: engine.save_state() → backend.save(sid, state_dict, ttl=1800s)
恢复: backend.load(sid) → state_dict → TriageEngine(saved_state=state_dict)
清理: 30 分钟 TTL（内存惰性清理 / Redis EXPIRE）
```

### TriageState 序列化
```json
{
  "stage": 2,                     // Stage enum → int
  "records": ["头颅", "钝痛", "持续性"],
  "options": ["内科普通门诊", "神经内科"],
  "messages": [{...}, {...}],
  "pending_body_change": null     // 部位变更待确认状态
}
```

---

## 七、前端架构要点

- **模块化**: 6 个 ES Module (core / auth / chat / social / ui / app)
- **认证**: JWT 存储在 localStorage，`buildAuthHeaders()` 统一注入
- **会员 UI**: CSS 变量 `--member-badge` 控制标识展示，`detail_locked` 控制内容遮蔽
- **阶段指示器**: chat.js 维护步骤进度条，根据 stage 实时更新
- **API Base**: 可配置 `/api` 前缀，支持不同环境切换
- **Android 打包**: Capacitor 封装，`build-android.bat` 一键构建

---

## 八、已知设计决策与注意事项

1. **BodyComparisonAgent 纯规则引擎**：不调用 LLM，避免延迟（这是有意设计）
2. **table.json 101KB**：3854 条症状-科室映射，SymptomRepository 单例加载
3. **medical.json 47MB**：8808 条疾病，惰性加载 + 模块级缓存
4. **RAG 双路径共存**：
   - 路径 A：triage.py 中的 `DiseaseRAGRetriever`（症状检索式，完成时调用）
   - 路径 B：web_server.py 中的 `generate_detailed_advice()`（直接遍历匹配，仅会员）
5. **会话 30 分钟 TTL**：无论内存还是 Redis，均设置 30 分钟过期
6. **输入验证多级回退**：关键词 → 上下文 → LLM → 默认(=2)，确保 LLM 不可用时系统不崩溃
7. **确认词严格匹配**：`is_affirmative()` / `is_negative()` 用 frozenset 精确匹配，避免误判
8. **软删除评论**：status='deleted'，数据不真正移除

---

## 九、当前环境状态

| 配置项 | 当前值 |
|---|---|
| LLM | Qwen-Plus via DashScope |
| 数据库 | MySQL (root:123456@localhost/medical_triage) |
| Redis | redis://localhost:6379/0 (已配置，Redis 容器正在运行) |
| JWT 密钥 | 已设置强密钥 |
| 端口 | 5001 |

---

## 十、潜在改进方向（供参考）

1. **BodyComparisonAgent** 目前不调用 LLM，对复杂语义的变更检测可能漏判
2. **generate_detailed_advice()** 每次全量遍历 8808 条疾病，O(n) 复杂度，可加索引
3. **RAG 双路径**：triage.py 和 web_server.py 各有一套疾病检索逻辑，有重复
4. **测试覆盖**：前端无自动化测试，后端只有 session + 会员相关的测试
5. **前端 app.legacy.js.back (46KB)**：疑似旧版代码备份，可清理
6. **根目录 medical_triage.db (61KB)**：与后端目录的 medical_triage.db (74KB) 重复
7. **会员升级为模拟实现**：POST `/api/membership/upgrade` 无支付流程
8. **无 WebSocket**：当前全部 HTTP 轮询/请求-响应模式
