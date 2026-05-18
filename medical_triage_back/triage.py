"""
核心导诊逻辑 - 多智能体协作版 + RAG增强

功能：
- 实现多阶段医疗导诊流程（身体部位 → 初步症状 → 具体症状 → 完成）
- 协调多个AI智能体完成输入验证、意图判断、问题生成
- 支持身体部位变更检测和确认
- 可选RAG增强：基于知识库生成疾病解释和建议

智能体分工：
- InputValidationAgent: 判断输入类型（身体部位/症状/无关）
- BodyComparisonAgent: 检查身体部位是否改变
- IntentJudgmentAgent: 判断用户意图匹配哪个选项
- QuestionGenerationAgent: 生成询问问题

RAG增强（可选）：
- DiseaseRAGRetriever: 检索相关疾病
- DiseaseExplanationGenerator: 生成疾病解释和建议
"""
import json
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from config import Config
from agents.input_validation_agent import InputValidationAgent
from agents.body_comparison_agent import BodyComparisonAgent
from agents.intent_judgment_agent import IntentJudgmentAgent
from agents.question_generation_agent import QuestionGenerationAgent

# RAG模块导入（可选，失败时不影响原有功能）
try:
    from rag_retriever import DiseaseRAGRetriever, DiseaseExplanationGenerator

    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    DiseaseRAGRetriever = None
    DiseaseExplanationGenerator = None

# RAG 系统单例缓存（避免每个请求重复加载 8000+ 条知识库）
_RAG_SYSTEM_CACHE = None


def get_rag_system():
    """获取 RAG 系统单例（首次调用加载，后续命中缓存）"""
    global _RAG_SYSTEM_CACHE
    if _RAG_SYSTEM_CACHE is None:
        from rag_retriever import create_rag_system

        _RAG_SYSTEM_CACHE = create_rag_system()
    return _RAG_SYSTEM_CACHE


class Stage(IntEnum):
    """导诊阶段枚举"""
    BODY_PART = 0
    INITIAL_SYMPTOM = 1
    SPECIFIC_SYMPTOM = 2
    COMPLETED = 3


@dataclass
class TriageState:
    """导诊状态数据类"""
    stage: Stage = Stage.BODY_PART
    records: List[str] = field(default_factory=list)
    options: List[str] = field(default_factory=list)
    messages: List[Dict[str, str]] = field(default_factory=list)
    pending_body_change: Optional[Dict[str, Any]] = None

    def reset(self, initial_options: List[str]) -> None:
        """重置状态"""
        self.stage = Stage.BODY_PART
        self.records = []
        self.options = initial_options.copy()
        self.messages = []
        self.pending_body_change = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为纯 dict（Stage enum → int，可安全 JSON 序列化）"""
        return {
            "stage": int(self.stage),
            "records": list(self.records),
            "options": list(self.options),
            "messages": list(self.messages),
            "pending_body_change": (
                dict(self.pending_body_change) if self.pending_body_change else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TriageState":
        """从 dict 反序列化"""
        return cls(
            stage=Stage(data.get("stage", 0)),
            records=data.get("records", []),
            options=data.get("options", []),
            messages=data.get("messages", []),
            pending_body_change=data.get("pending_body_change"),
        )


class SymptomRepository:
    """症状数据仓库 - 从JSON文件加载症状-科室映射数据（模块级单例）"""

    _instance: Optional["SymptomRepository"] = None

    def __init__(self, data_file: str, encoding: str = "utf-8") -> None:
        self._data: List[Dict[str, Any]] = self._load_data(data_file, encoding)

    @classmethod
    def get_instance(cls, data_file: str = "table.json", encoding: str = "utf-8") -> "SymptomRepository":
        """获取单例实例（避免每次构造 TriageEngine 重复加载 table.json）"""
        if cls._instance is None:
            cls._instance = cls(data_file, encoding)
        return cls._instance
    
    def _load_data(self, file_path: str, encoding: str) -> List[Dict[str, Any]]:
        """加载JSON数据文件"""
        try:
            path = Path(file_path)
            if not path.exists():
                # 尝试在当前目录查找
                path = Path(__file__).parent / file_path
            
            with path.open('r', encoding=encoding) as f:
                return json.load(f)
        except Exception as e:
            print(f"加载数据文件失败: {e}")
            return []
    
    def find_initial_symptoms(self, body_part: str) -> List[str]:
        """根据身体部位查找初步症状列表"""
        symptoms: List[str] = []
        seen: set = set()
        
        for item in self._data:
            if item.get('身体部位') == body_part:
                symptom = item.get('初步症状')
                if symptom and symptom not in seen:
                    symptoms.append(symptom)
                    seen.add(symptom)
        return symptoms
    
    def find_specific_symptoms(self, body_part: str, initial_symptom: str) -> List[str]:
        """根据身体部位和初步症状查找具体症状列表"""
        symptoms: List[str] = []
        seen: set = set()
        
        for item in self._data:
            if (item.get('身体部位') == body_part and 
                item.get('初步症状') == initial_symptom):
                specific = item.get('具体症状')
                if specific and specific not in seen:
                    symptoms.append(specific)
                    seen.add(specific)
        return symptoms
    
    def find_departments(
        self, 
        body_part: str, 
        initial_symptom: str, 
        specific_symptom: str
    ) -> List[str]:
        """查找推荐科室"""
        departments: List[str] = []
        seen: set = set()
        
        for item in self._data:
            if (item.get('身体部位') == body_part and 
                item.get('初步症状') == initial_symptom and
                item.get('具体症状') == specific_symptom):
                dept = item.get('推荐科室')
                if dept and dept not in seen:
                    departments.append(dept)
                    seen.add(dept)
        return departments


class TriageEngine:
    """导诊引擎 - 协调多个智能体完成导诊流程"""

    def __init__(
        self,
        config: Config,
        enable_rag: bool = True,
        saved_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.config: Config = config

        # LLM客户端
        self.client: OpenAI = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )

        # 数据仓库（单例，避免重复加载 table.json）
        self.repository: SymptomRepository = SymptomRepository.get_instance(
            config.data_file,
            config.encoding,
        )

        # 状态：支持从保存的状态恢复
        if saved_state:
            self.state: TriageState = TriageState.from_dict(saved_state)
        else:
            self.state = TriageState()
            self.state.options = config.body_types.copy()

        # 初始化智能体
        self.input_validator = InputValidationAgent(self.client, config.model)
        self.body_comparator = BodyComparisonAgent(self.client, config.model)
        self.intent_judger = IntentJudgmentAgent(self.client, config.model)
        self.question_generator = QuestionGenerationAgent(self.client, config.model)

        # 初始化RAG系统（可选）
        self.rag_retriever: Optional[DiseaseRAGRetriever] = None
        self.rag_generator: Optional[DiseaseExplanationGenerator] = None
        self.enable_rag: bool = enable_rag and RAG_AVAILABLE

        if self.enable_rag:
            try:
                self.rag_retriever, self.rag_generator = get_rag_system()
                print("RAG系统加载成功")
            except Exception as e:
                print(f"RAG系统加载失败: {e}")
                self.enable_rag = False

    def save_state(self) -> Dict[str, Any]:
        """导出当前会话状态（用于外部持久化）"""
        return self.state.to_dict()
    
    def get_welcome_message(self) -> str:
        """获取欢迎消息"""
        return "我是导诊助手，请问您哪里不舒服呢？"
    
    def process(self, user_input: str) -> Tuple[str, bool]:
        """
        处理用户输入 - 协调多个智能体完成导诊
        
        Args:
            user_input: 用户输入文本
        
        Returns:
            Tuple[回复消息, 是否完成]
        """
        # 添加用户消息到历史
        self.state.messages.append({"role": "user", "content": user_input})

        # 优先处理"是否重置流程"的确认分支
        pending_reset_response = self._handle_pending_body_change_confirmation(user_input)
        if pending_reset_response is not None:
            return pending_reset_response
        
        # 智能体1: 输入验证
        input_type = self._validate_input(user_input)
        
        if input_type == 3:
            return self._handle_irrelevant_input()
        
        if self.state.stage == Stage.BODY_PART and input_type == 2:
            return self._handle_missing_body_part()
        
        # 智能体2: 身体部位比对
        if input_type == 1 and self.state.stage > Stage.BODY_PART:
            body_change_result = self._check_body_change(user_input)
            if body_change_result.get("is_changed"):
                return self._handle_body_change(body_change_result, user_input)
        
        # 智能体3: 意图判断
        matched_index = self._judge_intent()
        
        if matched_index != -1:
            return self._advance_stage(matched_index)
        else:
            # 智能体4: 问题生成
            return self._generate_question()
    
    def _validate_input(self, user_input: str) -> int:
        """验证用户输入类型"""
        confirmed_body = self.state.records[0] if self.state.records else None
        last_assistant_msg = self._get_last_assistant_message()
        
        return self.input_validator.process(
            user_input, 
            int(self.state.stage), 
            confirmed_body,
            last_assistant_msg,
            self.state.messages
        )
    
    def _handle_irrelevant_input(self) -> Tuple[str, bool]:
        """处理无关输入"""
        self.state.messages.pop()  # 移除无效输入
        last_question = self._get_last_assistant_message()
        
        if last_question:
            return f"抱歉，我没有理解您的回答。{last_question}", False
        else:
            return f"抱歉，我没有理解您的回答。{self.get_welcome_message()}", False
    
    def _handle_missing_body_part(self) -> Tuple[str, bool]:
        """处理缺少身体部位的情况"""
        self.state.messages.pop()  # 移除无效输入
        last_question = self._get_last_assistant_message()
        
        if last_question:
            return f"请先告诉我您哪个身体部位不舒服，我们再继续聊症状。{last_question}", False
        else:
            return "请先告诉我您哪个身体部位不舒服？比如头部、胸部、腹部等。", False
    
    def _check_body_change(self, user_input: str) -> Dict[str, Any]:
        """检查身体部位是否变更"""
        return self.body_comparator.process(
            user_input, 
            self.state.records[0],
            self.state.stage,
            self._get_recent_user_messages()
        )
    
    def _handle_body_change(
        self, 
        comparison_result: Dict[str, Any], 
        user_input: str
    ) -> Tuple[str, bool]:
        """处理身体部位变更"""
        reminder = self._build_body_change_confirmation_message(
            comparison_result, 
            user_input
        )
        self.state.pending_body_change = {
            "candidate_input": user_input,
            "comparison_result": comparison_result,
            "previous_stage": self.state.stage,
            "previous_records": self.state.records.copy(),
            "previous_options": self.state.options.copy(),
            "reminder_message": reminder,
            "followup_question": self._rebuild_current_question(),
        }
        self.state.messages.append({"role": "assistant", "content": reminder})
        return reminder, False
    
    def _judge_intent(self) -> int:
        """判断用户意图"""
        stage_name = self.config.stage_names[int(self.state.stage)]
        return self.intent_judger.process(
            stage_name,
            self.state.options,
            self.state.messages
        )
    
    def _generate_question(self) -> Tuple[str, bool]:
        """生成询问问题"""
        stage_name = self.config.stage_names[int(self.state.stage)]
        question = self.question_generator.process(
            stage_name,
            self.state.records,
            self.state.options,
            self.state.messages
        )
        self.state.messages.append({"role": "assistant", "content": question})
        return question, False
    
    def _advance_stage(self, matched_index: int) -> Tuple[str, bool]:
        """推进到下一阶段"""
        if matched_index < 0 or matched_index >= len(self.state.options):
            print(f"错误: 索引 {matched_index} 超出范围，options: {self.state.options}")
            return "抱歉，我没有理解您的选择，请重新回答。", False
        
        selected = self.state.options[matched_index]
        self.state.records.append(selected)
        self.state.stage = Stage(self.state.stage + 1)
        
        if self.state.stage == Stage.INITIAL_SYMPTOM:
            return self._enter_initial_symptom_stage(selected)
        elif self.state.stage == Stage.SPECIFIC_SYMPTOM:
            return self._enter_specific_symptom_stage(selected)
        elif self.state.stage == Stage.COMPLETED:
            return self._complete_triage()
        
        return "继续询问", False
    
    def _enter_initial_symptom_stage(self, body_part: str) -> Tuple[str, bool]:
        """进入初步症状阶段"""
        new_options = self.repository.find_initial_symptoms(body_part)
        self.state.options = new_options
        
        stage_name = self.config.stage_names[int(self.state.stage)]
        question = self.question_generator.process(
            stage_name,
            self.state.records,
            self.state.options,
            self.state.messages
        )
        self.state.messages.append({"role": "assistant", "content": question})
        return question, False
    
    def _enter_specific_symptom_stage(self, initial_symptom: str) -> Tuple[str, bool]:
        """进入具体症状阶段"""
        body_part = self.state.records[0]
        new_options = self.repository.find_specific_symptoms(body_part, initial_symptom)
        self.state.options = new_options
        
        stage_name = self.config.stage_names[int(self.state.stage)]
        question = self.question_generator.process(
            stage_name,
            self.state.records,
            self.state.options,
            self.state.messages
        )
        self.state.messages.append({"role": "assistant", "content": question})
        return question, False
    
    def _complete_triage(self) -> Tuple[str, bool]:
        """完成导诊"""
        body_part = self.state.records[0]
        initial_symptom = self.state.records[1]
        specific_symptom = self.state.records[2]
        
        departments = self.repository.find_departments(
            body_part,
            initial_symptom,
            specific_symptom
        )
        
        depts_str = "、".join(departments) if departments else "暂无推荐"
        base_response = (
            f"🎉 导诊完成！\n\n"
            f"📍 身体部位：{body_part}\n"
            f"🔍 症状描述：{specific_symptom or initial_symptom}\n\n"
            f"🏥 推荐科室：{depts_str}"
        )
        
        # RAG增强
        if self.enable_rag and self.rag_generator:
            try:
                symptoms = self._extract_symptoms(initial_symptom, specific_symptom)
                return self.rag_generator.generate_enhanced_response(
                    user_symptoms=symptoms,
                    body_part=body_part,
                    department_recommendation=departments
                ), True
            except Exception as e:
                print(f"RAG增强失败: {e}")
        
        return base_response, True
    
    def _get_last_assistant_message(self) -> Optional[str]:
        """获取最后一条助手消息"""
        for msg in reversed(self.state.messages):
            if msg.get("role") == "assistant":
                return msg.get("content", "")
        return None
    
    def _get_recent_user_messages(self, limit: int = 3) -> List[str]:
        """获取最近几条用户消息"""
        recent_messages: List[str] = []
        for msg in reversed(self.state.messages):
            if msg.get("role") == "user":
                recent_messages.append(msg.get("content", ""))
            if len(recent_messages) >= limit:
                break
        return list(reversed(recent_messages))
    
    def _handle_pending_body_change_confirmation(
        self, 
        user_input: str
    ) -> Optional[Tuple[str, bool]]:
        """处理待确认的身体部位变化"""
        pending = self.state.pending_body_change
        if not pending:
            return None

        normalized = (user_input or "").strip()
        
        if self._is_affirmative(normalized):
            self.state.reset(self.config.body_types.copy())
            response = (
                "已为您重新开始导诊流程。\n"
                f"{self.get_welcome_message()}"
            )
            self.state.messages.append({"role": "assistant", "content": response})
            return response, False

        if self._is_negative(normalized):
            self.state.pending_body_change = None
            followup_question = pending.get("followup_question") or self._rebuild_current_question()
            response = "好的，我们继续当前导诊流程。"
            if followup_question:
                response = f"{response}\n{followup_question}"
            self.state.messages.append({"role": "assistant", "content": response})
            return response, False

        # 用户没有明确表示，继续当前流程
        self.state.pending_body_change = None
        return None
    
    def _build_body_change_confirmation_message(
        self, 
        comparison_result: Dict[str, Any], 
        user_input: str
    ) -> str:
        """构造身体部位变更确认提示"""
        detected_body = comparison_result.get("detected_body") or user_input
        current_body = self.state.records[0] if self.state.records else "当前部位"
        confidence = comparison_result.get("confidence", 0.0)

        if confidence >= 0.85:
            prefix = "我检测到您刚才提到的身体部位可能已经变了"
        else:
            prefix = "我怀疑您刚才提到了新的身体部位"

        return (
            f"{prefix}（当前记录：{current_body}；新输入：{detected_body}）。\n"
            '如果您想改查新的部位，请回复“是”或“重置”；'
            '如果不是，请回复“否”，或者直接继续描述当前症状。'
        )
    
    def _rebuild_current_question(self) -> str:
        """根据当前阶段重建应继续追问的问题"""
        stage = self.state.stage

        if stage == Stage.INITIAL_SYMPTOM:
            return "您这种不舒服，是哪里难受，还是摸到了包块？"

        if stage == Stage.SPECIFIC_SYMPTOM:
            body_part = self.state.records[0] if self.state.records else "该部位"
            initial_symptom = self.state.records[1] if len(self.state.records) > 1 else ""
            if body_part and initial_symptom:
                return (
                    f"明白了。关于{body_part}的“{initial_symptom}”，"
                    "请再具体描述一下，比如持续时间、程度，或还有没有其他伴随症状？"
                )
            return "请再具体描述一下症状，比如持续时间、程度，或还有没有其他伴随症状？"

        return "请继续描述您的不适。"
    
    @staticmethod
    def _is_affirmative(text: str) -> bool:
        """判断是否为肯定回答"""
        normalized = text.replace("，", "").replace("。", "").replace(" ", "")
        affirmative_words = {
            "是", "好的", "好", "要", "需要", "确认", 
            "重新开始", "重置", "重新导诊", "开始吧"
        }
        return normalized in affirmative_words

    @staticmethod
    def _is_negative(text: str) -> bool:
        """判断是否为否定回答"""
        normalized = text.replace("，", "").replace("。", "").replace(" ", "")
        negative_words = {
            "否", "不用", "不需要", "不是", "继续", 
            "继续当前流程", "不用重置", "不重置"
        }
        return normalized in negative_words
    
    def reset(self) -> None:
        """重置导诊流程"""
        self.state.reset(self.config.body_types.copy())

    def get_pending_confirmation(self) -> Optional[Dict[str, Any]]:
        """获取当前待确认状态"""
        pending = self.state.pending_body_change
        if not pending:
            return None

        comparison_result = pending.get("comparison_result", {})
        return {
            "type": "body_part_change",
            "current_body": self.state.records[0] if self.state.records else "",
            "detected_body": comparison_result.get("detected_body", ""),
            "confidence": comparison_result.get("confidence", 0.0),
            "message": pending.get("reminder_message", ""),
        }
    
    def _extract_symptoms(
        self, 
        initial_symptom: str, 
        specific_symptom: str
    ) -> List[str]:
        """从症状描述中提取症状关键词"""
        symptoms = []
        
        if initial_symptom:
            symptoms.append(initial_symptom)
        
        if specific_symptom:
            # 常见症状关键词列表
            common_symptoms = [
                "头痛", "头晕", "发热", "咳嗽", "鼻塞", "流涕",
                "咽痛", "胸痛", "腹痛", "恶心", "呕吐", "腹泻",
                "乏力", "出汗", "失眠", "心悸", "胸闷", "呼吸困难"
            ]
            
            for keyword in common_symptoms:
                if keyword in specific_symptom:
                    symptoms.append(keyword)
        
        # 去重
        return list(set(symptoms)) if symptoms else [initial_symptom or "不适"]
    
    def get_department_recommendation(self) -> str:
        """获取科室推荐"""
        if len(self.state.records) < 3:
            return ""
        
        body_part = self.state.records[0]
        initial_symptom = self.state.records[1]
        specific_symptom = self.state.records[2]
        
        departments = self.repository.find_departments(
            body_part, initial_symptom, specific_symptom
        )
        return ", ".join(departments) if departments else ""
    
    def get_history_for_display(self) -> List[Dict[str, str]]:
        """获取用于展示的历史记录"""
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.state.messages
        ]
