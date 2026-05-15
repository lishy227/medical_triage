# RAG增强功能使用说明

## 功能概述

RAG（检索增强生成）功能基于 `medical.json` 医学知识库，在原有导诊流程基础上，增加了：

- ✅ **疾病解释** - 说明可能是什么疾病
- ✅ **就医建议** - 推荐检查项目
- ✅ **治疗信息** - 治疗方式、周期、药物
- ✅ **饮食建议** - 宜吃/忌吃食物
- ✅ **预防建议** - 预防措施

## 架构设计

```
用户输入症状
    ↓
原有导诊流程（table.json）
    ↓
确定科室
    ↓
RAG检索（medical.json）→ 生成增强回复
    ↓
输出：科室 + 疾病解释 + 建议
```

## 文件结构

```
medical_triage_back/
├── knowledge_base/
│   ├── medical.json      # 8,809条疾病数据
│   ├── README.md         # 数据说明文档
│   └── loader.py         # 数据加载工具
├── rag_retriever.py      # RAG检索和解释生成
├── triage.py             # 增强的导诊引擎
├── web_server.py         # 支持RAG的Web服务
└── test_rag.py           # 测试脚本
```

## 快速开始

### 1. 启动Web服务

```bash
cd medical_triage_back
python web_server.py
```

启动时会自动加载RAG系统：
```
构建症状索引...
索引构建完成，共 XXXX 个症状条目
RAG系统加载成功
```

### 2. 使用Web界面

打开浏览器访问 `http://localhost:5001`

完成导诊后，会自动显示增强的回复，包含：
- 疾病匹配结果
- 科室推荐
- 建议检查
- 治疗方式
- 饮食建议
- 预防建议

### 3. API调用

```javascript
// 创建会话（启用RAG）
fetch('/api/welcome?session_id=xxx&enable_rag=true')

// 发送消息
fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        session_id: 'xxx',
        message: '头疼'
    })
})
```

## 测试RAG功能

```bash
python test_rag.py
```

测试内容包括：
1. 症状检索测试
2. 解释生成测试
3. 与TriageEngine集成测试

## 核心类说明

### DiseaseRAGRetriever

```python
from rag_retriever import DiseaseRAGRetriever

retriever = DiseaseRAGRetriever()

# 检索相关疾病
results = retriever.retrieve(
    symptoms=["头痛", "发热"],
    body_part="头颅",
    top_k=5
)

for r in results:
    print(f"{r.name}: {r.score}")
```

### DiseaseExplanationGenerator

```python
from rag_retriever import DiseaseExplanationGenerator

generator = DiseaseExplanationGenerator(retriever)

# 生成增强回复
response = generator.generate_enhanced_response(
    user_symptoms=["头痛", "发热"],
    body_part="头颅",
    department_recommendation=["内科"]
)

print(response)
```

## 配置选项

### 启用/禁用RAG

**Web服务启动时：**
```python
# 默认启用RAG
engine = TriageEngine(config, enable_rag=True)

# 禁用RAG（纯原有功能）
engine = TriageEngine(config, enable_rag=False)
```

**API调用时：**
```javascript
// 启用RAG（默认）
/api/welcome?session_id=xxx&enable_rag=true

// 禁用RAG
/api/welcome?session_id=xxx&enable_rag=false
```

## 自定义扩展

### 添加更多检索维度

在 `rag_retriever.py` 中修改 `DiseaseRAGRetriever.retrieve()`：

```python
def retrieve(self, symptoms, body_part=None, age_group=None, top_k=5):
    # 添加年龄、性别等过滤条件
    ...
```

### 自定义回复格式

在 `DiseaseExplanationGenerator.generate_enhanced_response()` 中修改模板。

### 接入向量数据库

如需更精准的语义检索，可接入ChromaDB：

```python
import chromadb

# 初始化向量数据库
client = chromadb.Client()
collection = client.create_collection("diseases")

# 添加文档
for disease in kb.diseases:
    collection.add(
        documents=[disease.to_rag_text()],
        ids=[disease.name]
    )

# 语义检索
results = collection.query(
    query_texts=["头痛发烧"],
    n_results=5
)
```

## 性能优化

### 当前实现
- 症状倒排索引 - O(1)查找
- 关键词匹配 - 快速筛选
- 懒加载 - 首次使用时构建索引

### 优化建议
1. **预加载索引** - 启动时构建索引
2. **向量检索** - 使用embedding语义匹配
3. **缓存** - 缓存常见症状的检索结果
4. **增量更新** - 只加载更新的疾病数据

## 故障排除

### RAG系统未加载

**现象：** 启动时显示 `警告: RAG模块未加载`

**解决：**
```bash
# 检查文件是否存在
ls knowledge_base/medical.json

# 检查Python路径
python -c "import sys; print(sys.path)"
```

### 检索结果不准确

**原因：** 症状描述不匹配

**解决：**
- 扩展同义词映射
- 使用模糊匹配
- 接入向量语义检索

### 回复生成慢

**原因：** 数据量大，检索耗时

**解决：**
- 使用更小的测试数据集
- 添加检索结果缓存
- 异步生成回复

## 注意事项

⚠️ **免责声明**：
- RAG生成的信息仅供参考，不构成医疗建议
- 数据来源于公开网络，可能存在滞后或不准确
- 实际就医请遵循专业医生指导

## 更新日志

### 2026-05-12
- 实现基础RAG检索功能
- 添加疾病解释生成
- 集成到Web服务
- 支持启用/禁用切换

## 后续计划

- [ ] 向量语义检索
- [ ] 多轮对话上下文
- [ ] 用户反馈收集
- [ ] 症状图片识别
