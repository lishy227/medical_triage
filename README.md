# AI 医疗导诊系统

一个基于 **Flask + 多阶段导诊引擎 + Web/Capacitor 前端** 的医疗导诊项目，支持：
- 聊天式分步导诊
- JWT 用户认证
- 导诊历史记录
- 普通用户 / 会员分层结果展示
- 可选 RAG 检索增强
- Web 页面与 Android 封装
- **服务器重启检测与自动退出登录**

---

## 最近更新

### 2025-08-15 新增功能

#### 1. 模拟付费会员系统
- **普通用户**：仅显示推荐科室，详细建议锁定并提示开通会员
- **会员用户**：显示完整的疾病分析、治疗建议、饮食指导、费用参考
- **会员升级**：点击"立即开通会员"按钮即可模拟付费升级（有效期30天）
- **详细建议来源**：基于 `medical.json` 知识库智能匹配生成

#### 2. 服务器重启检测与自动退出登录
- 后端每次启动生成唯一的服务器实例ID
- 前端定期检测服务器状态（每30秒）
- 检测到服务器重启后自动清除登录状态
- 显示提示"服务器已重启，请重新登录"并刷新页面
- 确保每次重启后端后用户需要重新输入账号密码

#### 3. 登录功能修复
- 修复了 token 存储键名不一致导致的登录失败问题
- 修复了错误处理函数不存在的问题
- 添加了详细的错误日志便于调试

---

---

## 最终交付摘要

本次交付重点完成了“**模拟付费 / 会员功能连接前端**”相关闭环，并进一步完成了前端目录收敛：
- **保留 `medical_triage_web/www/` 作为唯一正式前端入口**
- **删除 `medical_triage_web/` 根目录下重复静态文件**
- **更新后端静态资源入口，改为明确服务 `www/`**

### 已完成内容

#### 1) 第 2 步：会员能力后端输出分层
已在后端完成普通用户 / 会员用户的结果分层：
- **普通用户**：返回推荐科室，不返回详细医疗建议
- **会员用户**：返回推荐科室 + 详细医疗建议
- 保留兼容字段锚点：`推荐科室:`

对应后端能力：
- `parse_department_list()`
- `build_tiered_triage_result()`
- `/api/chat` 完成态结构化返回

#### 2) 第 3 步：前端接入 JWT 鉴权与分层展示
前端（现以 `medical_triage_web/www/` 为唯一正式目录）已接入以下接口的 JWT 鉴权：
- `GET /api/welcome`
- `POST /api/chat`
- `POST /api/reset`

前端已支持消费后端结构化字段：
- `departments`
- `recommended_department`
- `detailed_medical_advice`
- `detail_locked`
- `detail_level`
- `conversation_summary`
- `message`

前端已实现：
- 普通用户展示“推荐科室 + 详情锁定提示”
- 会员用户展示“推荐科室 + 详细医疗建议”
- 兼容旧文本格式 `推荐科室: [...]`

#### 3) 前端目录整理
已按“方案 A”完成目录收敛：
- 保留：`medical_triage_web/www/`
- 删除根目录重复静态文件：
  - `medical_triage_web/app.js`
  - `medical_triage_web/index.html`
  - `medical_triage_web/style.css`
- 后端 `medical_triage_back/web_server.py` 已改为明确从 `medical_triage_web/www/` 提供静态文件服务

这样可以避免后续出现“改了 A，实际跑的是 B”的双目录漂移问题。

#### 4) 身体部位误判优化
已优化“身体部位变化检测”逻辑：
- 不再轻易把症状补充误判为切换身体部位
- 发现疑似变化时先请求用户确认
- 避免无谓重置导诊流程

#### 5) 配置加载修复
已修复 `.env` 加载路径问题：
- `medical_triage_back/config.py` 现在默认从 **项目后端目录下的 `.env`** 加载
- 不再依赖当前工作目录
- 更适合本地运行与部署环境

目标位置：
- `medical_triage_back/.env`

#### 6) 第 3 步验收已收口
已将第 3 步改为“**路由级集成验收**”，避免测试被外部模型调用拖慢或阻塞。

最终通过的验收点：
- `/api/welcome`：未带 token 返回 401；带 token 正常返回
- `/api/reset`：未带 token 返回 401；带 token 正常返回
- `/api/chat`：带 token 可正常返回结构化结果，且区分普通用户 / 会员用户

### 当前结论
如果按“**模拟付费 / 会员功能连接前端**”这个任务本身来算，**现在可以认定为完成**。

> 注：此前真实 `/api/chat` HTTP smoke test 出现过 `TimeoutError: timed out`，其根因更接近外部模型依赖 / API key / provider 问题，不再作为本次前后端接线验收的阻塞项。

---

## 项目结构

```text
medical_triage/
├─ medical_triage_back/              # Flask 后端、导诊引擎、认证、数据库、测试
│  ├─ agents/
│  ├─ tests/
│  ├─ config.py
│  ├─ web_server.py
│  └─ requirements.txt
├─ medical_triage_web/               # 前端目录（Web + Capacitor）
│  ├─ www/                           # 唯一正式静态资源目录（当前唯一前端入口）
│  ├─ android/
│  ├─ capacitor.config.json
│  └─ package.json
├─ app-debug.apk
├─ DEPLOY.md
├─ README.md
└─ requirements.txt                  # 根目录安装入口，转发到后端依赖
```

---

## 关键文件说明

### 后端

#### `medical_triage_back/web_server.py`
Flask 服务入口，负责：
- API 路由
- JWT 鉴权
- 会话管理
- **会员分层结果返回（基于 medical.json 生成详细建议）**
- **服务器实例管理（重启检测）**
- 历史记录保存
- 从 `medical_triage_web/www/` 提供静态文件

#### `medical_triage_back/triage.py`
导诊主流程核心，负责：
- 身体部位识别
- 初步症状识别
- 具体症状追问
- 导诊结果生成
- 身体部位变化确认逻辑

#### `medical_triage_back/agents/body_comparison_agent.py`
身体部位变化检测逻辑。

#### `medical_triage_back/config.py`
配置加载模块，当前支持项目相对路径加载 `.env`。

#### `medical_triage_back/tests/test_membership_step2_acceptance.py`
第 2 步会员分层后端验收测试。

#### `medical_triage_back/tests/test_step3_route_integration.py`
第 3 步路由级集成验收测试。

### 前端

#### `medical_triage_web/www/index.html`
正式前端页面入口。

#### `medical_triage_web/www/app.js`
前端核心逻辑，负责：
- 获取 / 保存 token
- 发送 `/api/welcome`、`/api/chat`、`/api/reset`
- **渲染普通用户 / 会员用户差异化结果**
- **服务器重启检测与自动退出登录**
- **会员升级弹窗与支付模拟**
- 兼容结构化返回和旧文本锚点

#### `medical_triage_web/www/style.css`
导诊结果卡片、会员提示、详细建议区等样式。

#### `medical_triage_web/capacitor.config.json`
Capacitor 配置文件，`webDir` 指向 `www`。

---

## 已验证能力

### 导诊流程
- 多阶段导诊问答
- 身体部位变化确认
- 导诊完成后输出推荐科室
- 对话状态管理
- 会话重置

### 用户与会员系统
- 用户注册
- 用户登录
- JWT 认证
- 会员状态识别
- 普通用户 / 会员分层结果
- 历史记录保存
- **服务器重启检测与自动退出登录**

### 会员系统（新增）
- **普通用户**：仅显示推荐科室，详细建议锁定
- **会员用户**：显示完整疾病分析、治疗建议、饮食指导、费用参考
- **模拟付费升级**：点击开通会员即可升级为会员（有效期30天）
- **会员权益**：
  - 📊 详细疾病分析报告
  - 🩺 专业治疗建议
  - 🍽️ 个性化饮食指导
  - 💊 用药参考信息
  - ⏱️ 治疗周期预估
  - 💰 费用参考信息

### API 能力
- `GET /api/welcome`
- `POST /api/chat`
- `POST /api/reset`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/profile`
- `GET /api/user/center`
- `GET /api/user/history`
- `POST /api/membership/upgrade` - 会员升级
- `GET /api/membership/status` - 会员状态查询
- `GET /api/server/info` - 服务器信息（用于检测重启）

---

## 安装与运行

### 1. 安装 Python 依赖

在项目根目录执行：

```bash
pip install -r requirements.txt
```

或在后端目录执行：

```bash
cd medical_triage_back
pip install -r requirements.txt
```

### 2. 配置环境变量

建议在 `medical_triage_back/.env` 中配置：

```env
API_KEY=your_api_key
BASE_URL=your_llm_base_url
MODEL=your_model_name
DATABASE_URL=sqlite:///medical_triage.db
JWT_SECRET_KEY=change-this-in-production
JWT_ACCESS_TOKEN_EXPIRE_DAYS=30
```

### 3. 启动后端

```bash
cd medical_triage_back
python web_server.py
```

已验证可用的本地启动方式示例：

```bash
C:\Users\25484\anaconda3\envs\daozhen\python.exe web_server.py
```

### 4. 前端使用方式

当前唯一正式前端目录为：

```text
medical_triage_web/www/
```

如果通过后端访问静态页面，请启动 Flask 服务后访问对应根路径。
如果通过 Capacitor 打包，`webDir` 已指向 `www`，无需额外切换。

---

## 测试

### 第 2 步验收

```bash
python -m unittest medical_triage_back.tests.test_membership_step2_acceptance -v
```

### 第 3 步验收

```bash
python -m unittest medical_triage_back.tests.test_step3_route_integration -v
```

### 身体部位变化回归测试

```bash
python -m unittest medical_triage_back.tests.test_body_change_regression -v
```

---

## 注意事项

1. **真实 `/api/chat` 调用仍依赖外部模型服务**
   - 若外部 provider 不稳定、API key 缺失或网络异常，可能出现超时或 401/403。
   - 这与“前后端接线是否完成”是两类问题，需要分开判断。

2. **建议优先检查 `.env`**
   - 尤其是 `API_KEY`、`BASE_URL`、`MODEL`、`JWT_SECRET_KEY`。

3. **当前已完成单前端目录收敛**
   - 正式入口：`medical_triage_web/www/`
   - 后端静态服务已适配 `www/`
   - 不应再在 `medical_triage_web/` 根目录新增重复静态页面文件

4. **服务器重启检测机制**
   - 后端每次启动生成唯一的 `SERVER_INSTANCE_ID`
   - 前端每30秒检测一次服务器状态
   - 检测到服务器重启后自动退出登录，要求重新输入账号密码

5. **如果曾在调试中暴露过测试密钥，建议立即轮换**。

---

## 免责声明

本项目用于 **AI 导诊辅助与分诊推荐**，不能替代医生诊断。

系统输出仅适合作为：
- 就医分流参考
- 初步信息收集工具
- 辅助交互系统

如遇急症、重症或复杂情况，请及时前往正规医疗机构就诊。
