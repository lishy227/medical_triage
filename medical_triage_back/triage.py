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

数据流：
用户输入 → 输入验证 → 身体部位比对 → 意图判断 → 推进阶段/生成问题 → 返回回复
"""
import json
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import IntEnum

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
    print("警告: RAG模块未加载，将使用基础导诊功能")


class Stage(IntEnum):
    """
    导诊阶段枚举
    
    定义导诊流程的四个阶段：
    - BODY_PART (0): 询问身体部位阶段
    - INITIAL_SYMPTOM (1): 询问初步症状阶段
    - SPECIFIC_SYMPTOM (2): 询问具体症状阶段
    - COMPLETED (3): 导诊完成阶段
    """
    BODY_PART = 0
    INITIAL_SYMPTOM = 1
    SPECIFIC_SYMPTOM = 2
    COMPLETED = 3


@dataclass
class TriageState:
    """
    导诊状态数据类
    
    存储单个导诊会话的完整状态，包括：
    - stage: 当前导诊阶段
    - records: 已收集的信息 [身体部位, 初步症状, 具体症状]
    - options: 当前阶段的可选项列表
    - messages: 对话历史（用于上下文理解）
    - pending_body_change: 待确认的身体部位变更（如果有）
    
    使用dataclass简化定义，自动实现__init__等方法。
    """
    stage: Stage = Stage.BODY_PART
    records: List[str] = field(default_factory=list)  # [身体部位, 初步症状, 具体症状]
    options: List[str] = field(default_factory=list)  # 当前阶段的可选项
    messages: List[Dict[str, str]] = field(default_factory=list)  # 对话历史
    pending_body_change: Optional[Dict[str, Any]] = None  # 待确认的身体部位变更
    
    def reset(self, initial_options: List[str]) -> None:
        """重置状态"""
        self.stage = Stage.BODY_PART
        self.records = []
        self.options = initial_options
        self.messages = []
        self.pending_body_change = None


class SymptomRepository:
    """
    症状数据仓库
    
    从JSON文件加载症状-科室映射数据，提供查询接口：
    - 根据身体部位查询初步症状列表
    - 根据身体部位和初步症状查询具体症状列表
    - 根据完整信息查询推荐科室
    
    数据格式（table.json）：
    [
        {
            "身体部位": "头部",
            "初步症状": "头痛",
            "具体症状": "偏头痛",
            "推荐科室": "神经内科"
        },
        ...
    ]
    """
    
    def __init__(self, data_file: str, encoding: str = "utf-8") -> None:
        """
        初始化症状数据仓库
        
        Args:
            data_file: JSON数据文件路径
            encoding: 文件编码，默认utf-8
        """
        self._data: List[Dict[str, Any]] = self._load_data(data_file, encoding)
    
    def _load_data(self, file_path: str, encoding: str) -> List[Dict[str, Any]]:
        """
        加载JSON数据文件
        
        Args:
            file_path: 文件路径
            encoding: 文件编码
            
        Returns:
            解析后的JSON数据列表，如果加载失败返回空列表
        """
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return json.load(f)
        except Exception as e:
            print(f"加载数据文件失败: {e}")
            return []
    
    def find_initial_symptoms(self, body_part: str) -> List[str]:
        """
        根据身体部位查找初步症状列表
        
        从数据仓库中筛选指定身体部位对应的所有初步症状，
        去重后返回列表。
        
        Args:
            body_part: 身体部位名称（如"头部"、"胸部"）
            
        Returns:
            初步症状名称列表（去重）
            
        示例：
            >>> repo.find_initial_symptoms("头部")
            ['头痛', '头晕', '头部外伤', ...]
        """
        symptoms: List[str] = []
        for item in self._data:
            if item.get('身体部位') == body_part:
                symptom = item.get('初步症状')
                if symptom and symptom not in symptoms:
                    symptoms.append(symptom)
        return symptoms
    
    def find_specific_symptoms(self, body_part: str, initial_symptom: str) -> List[str]:
        """
        根据身体部位和初步症状查找具体症状列表
        
        在已确定身体部位和初步症状的基础上，
        查询更具体的症状描述。
        
        Args:
            body_part: 身体部位名称
            initial_symptom: 初步症状名称
            
        Returns:
            具体症状描述列表（去重）
            
        示例：
            >>> repo.find_specific_symptoms("头部", "头痛")
            ['偏头痛', '持续性头痛', '阵发性头痛', ...]
        """
        symptoms: List[str] = []
        for item in self._data:
            if (item.get('身体部位') == body_part and 
                item.get('初步症状') == initial_symptom):
                specific = item.get('具体症状')
                if specific and specific not in symptoms:
                    symptoms.append(specific)
        return symptoms
    
    def find_departments(self, body_part: str, initial_symptom: str, 
                        specific_symptom: str) -> List[str]:
        """
        查找推荐科室
        
        根据完整的症状信息（身体部位、初步症状、具体症状），
        查询推荐的就诊科室。
        
        Args:
            body_part: 身体部位名称
            initial_symptom: 初步症状名称
            specific_symptom: 具体症状描述
            
        Returns:
            推荐科室列表（可能有多个）
            
        示例：
            >>> repo.find_departments("头部", "头痛", "偏头痛")
            ['神经内科', '疼痛科']
        """
        departments: List[str] = []
        for item in self._data:
            if (item.get('身体部位') == body_part and 
                item.get('初步症状') == initial_symptom and
                item.get('具体症状') == specific_symptom):
                dept = item.get('推荐科室')
                if dept and dept not in departments:
                    departments.append(dept)
        return departments


class TriageEngine:
    """
    导诊引擎 - 协调多个智能体完成导诊流程
    
    多智能体协作：
    1. InputValidationAgent 验证输入类型
    2. BodyComparisonAgent 检查身体部位是否改变
    3. IntentJudgmentAgent 判断用户意图
    4. QuestionGenerationAgent 生成询问问题
    
    RAG增强：
    - 导诊完成后，使用medical.json生成疾病解释和建议
    """
    
    def __init__(self, config: Config, enable_rag: bool = True) -> None:
        self.config: Config = config
        
        # LLM客户端
        self.client: OpenAI = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )
        
        # 数据仓库
        self.repository: SymptomRepository = SymptomRepository(config.data_file, config.encoding)
        
        # 状态
        self.state: TriageState = TriageState()
        self.state.options = config.body_types.copy()
        
        # 初始化智能体
        self.input_validator: InputValidationAgent = InputValidationAgent(self.client, config.model)
        self.body_comparator: BodyComparisonAgent = BodyComparisonAgent(self.client, config.model)
        self.intent_judger: IntentJudgmentAgent = IntentJudgmentAgent(self.client, config.model)
        self.question_generator: QuestionGenerationAgent = QuestionGenerationAgent(self.client, config.model)
        
        # 初始化RAG系统（可选）
        self.rag_retriever: Optional[DiseaseRAGRetriever] = None
        self.rag_generator: Optional[DiseaseExplanationGenerator] = None
        self.enable_rag: bool = enable_rag and RAG_AVAILABLE
        
        if self.enable_rag:
            try:
                from rag_retriever import create_rag_system
                self.rag_retriever, self.rag_generator = create_rag_system()
                print("RAG系统加载成功")
            except Exception as e:
                print(f"RAG系统加载失败: {e}")
                self.enable_rag = False
    
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

        # 优先处理“是否重置流程”的确认分支
        pending_reset_response = self._handle_pending_body_change_confirmation(user_input)
        if pending_reset_response is not None:
            return pending_reset_response
        
        # ========== 智能体1: 输入验证 ==========
        confirmed_body: Optional[str] = self.state.records[0] if self.state.records else None
        last_assistant_msg: Optional[str] = self._get_last_assistant_message()
        input_type: int = self.input_validator.process(
            user_input, 
            self.state.stage, 
            confirmed_body,
            last_assistant_msg,
            self.state.messages  # 传递完整对话历史
        )
        
        if input_type == 3:
            # 无关输入 - 改为回退到上一个问题，而不是强制重置
            self.state.messages.pop()  # 移除无效输入
            
            # 获取上一个问题（如果有）
            last_question = self._get_last_assistant_message()
            if last_question:
                # 重新询问上一个问题，给用户重新回答的机会
                return f"抱歉，我没有理解您的回答。{last_question}", False
            else:
                # 如果没有上一个问题，返回初始欢迎消息
                return f"抱歉，我没有理解您的回答。{self.get_welcome_message()}", False
        
        if self.state.stage == Stage.BODY_PART and input_type == 2:
            # 阶段0但没有身体部位 - 同样改为回退而不是强制重置
            self.state.messages.pop()  # 移除无效输入
            
            # 生成友好的提示，引导用户输入身体部位
            last_question = self._get_last_assistant_message()
            if last_question:
                return f"请先告诉我您哪个身体部位不舒服，我们再继续聊症状。{last_question}", False
            else:
                return "请先告诉我您哪个身体部位不舒服？比如头部、胸部、腹部等。", False
        
        # ========== 智能体2: 身体部位比对 ==========
        if input_type == 1 and self.state.stage > Stage.BODY_PART:
            comparison_result = self.body_comparator.process(
                user_input, 
                self.state.records[0],
                self.state.stage,
                self._get_recent_user_messages()
            )
            if comparison_result.get("is_changed"):
                reminder = self._build_body_change_confirmation_message(comparison_result, user_input)
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
        
        # ========== 智能体3: 意图判断 ==========
        stage_name: str = self.config.stage_names[self.state.stage]
        matched_index: int = self.intent_judger.process(
            stage_name,
            self.state.options,
            self.state.messages
        )
        
        if matched_index != -1:
            # 匹配成功，推进阶段
            return self._advance_stage(matched_index)
        else:
            # ========== 智能体4: 问题生成 ==========
            question: str = self.question_generator.process(
                stage_name,
                self.state.records,
                self.state.options,
                self.state.messages
            )
            self.state.messages.append({"role": "assistant", "content": question})
            return question, False
    
    def _advance_stage(self, matched_index: int) -> Tuple[str, bool]:
        """
        推进到下一阶段
        
        Args:
            matched_index: 匹配的选项索引
        
        Returns:
            Tuple[回复消息, 是否完成]
        """
        # 检查索引是否有效
        if matched_index < 0 or matched_index >= len(self.state.options):
            print(f"错误: 索引 {matched_index} 超出范围，options: {self.state.options}")
            return "抱歉，我没有理解您的选择，请重新回答。", False
        
        selected: str = self.state.options[matched_index]
        self.state.records.append(selected)
        
        # 推进阶段
        self.state.stage = Stage(self.state.stage + 1)
        
        if self.state.stage == Stage.INITIAL_SYMPTOM:
            # 进入初步症状阶段
            new_options: List[str] = self.repository.find_initial_symptoms(selected)
            self.state.options = new_options
            
            stage_name: str = self.config.stage_names[self.state.stage]
            question: str = self.question_generator.process(
                stage_name,
                self.state.records,
                self.state.options,
                self.state.messages
            )
            self.state.messages.append({"role": "assistant", "content": question})
            
            # 不输出症状列表，只输出问题
            return question, False
            
        elif self.state.stage == Stage.SPECIFIC_SYMPTOM:
            # 进入具体症状阶段
            new_options: List[str] = self.repository.find_specific_symptoms(
                self.state.records[0], selected
            )
            self.state.options = new_options
            
            stage_name: str = self.config.stage_names[self.state.stage]
            question: str = self.question_generator.process(
                stage_name,
                self.state.records,
                self.state.options,
                self.state.messages
            )
            self.state.messages.append({"role": "assistant", "content": question})
            
            # 不输出症状列表，只输出问题
            return question, False
            
        elif self.state.stage == Stage.COMPLETED:
            # 导诊完成
            body_part: str = self.state.records[0]
            initial_symptom: str = self.state.records[1]
            specific_symptom: str = self.state.records[2]
            
            departments: List[str] = self.repository.find_departments(
                body_part,
                initial_symptom,
                specific_symptom
            )
            
            # 构建基础响应
            depts_str = "、".join(departments) if departments else "暂无推荐"
            base_response = (
                f"🎉 导诊完成！\n\n"
                f"📍 身体部位：{body_part}\n"
                f"🔍 症状描述：{specific_symptom or initial_symptom}\n\n"
                f"🏥 推荐科室：{depts_str}"
            )
            
            # RAG增强：生成疾病解释和建议
            if self.enable_rag and self.rag_generator:
                try:
                    # 提取症状关键词
                    symptoms = self._extract_symptoms(initial_symptom, specific_symptom)
                    
                    # 生成增强回复
                    enhanced_response = self.rag_generator.generate_enhanced_response(
                        user_symptoms=symptoms,
                        body_part=body_part,
                        department_recommendation=departments
                    )
                    
                    return enhanced_response, True
                    
                except Exception as e:
                    print(f"RAG增强失败: {e}")
                    return base_response, True
            
            return base_response, True
        
        return "继续询问", False
    
    def _get_last_assistant_message(self) -> Optional[str]:
        """获取最后一条助手消息"""
        for msg in reversed(self.state.messages):
            if msg.get("role") == "assistant":
                return msg.get("content", "")
        return None

    def _get_recent_user_messages(self, limit: int = 3) -> List[str]:
        """获取最近几条用户消息，用于辅助判断是否真的切换了身体部位。"""
        recent_messages: List[str] = []
        for msg in reversed(self.state.messages):
            if msg.get("role") == "user":
                recent_messages.append(msg.get("content", ""))
            if len(recent_messages) >= limit:
                break
        return list(reversed(recent_messages))

    def _handle_pending_body_change_confirmation(self, user_input: str) -> Optional[Tuple[str, bool]]:
        """处理待确认的身体部位变化。"""
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

        # 若用户没有明确表示重置，而是继续回答症状，则直接忽略这次提醒，继续当前流程
        self.state.pending_body_change = None
        return None

    def _build_body_change_confirmation_message(self, comparison_result: Dict[str, Any], user_input: str) -> str:
        """构造身体部位变更确认提示。"""
        detected_body = comparison_result.get("detected_body") or user_input
        current_body = self.state.records[0] if self.state.records else "当前部位"
        confidence = comparison_result.get("confidence", 0.0)

        if confidence >= 0.85:
            prefix = "我检测到您刚才提到的身体部位可能已经变了"
        else:
            prefix = "我怀疑您刚才提到了新的身体部位"

        return (
            f"{prefix}（当前记录：{current_body}；新输入：{detected_body}）。\n"
            "如果您想改查新的部位，请回复“是”或“重置”；"
            "如果不是，请回复“否”，或者直接继续描述当前症状。"
        )

    def _rebuild_current_question(self) -> str:
        """根据当前阶段重建应继续追问的问题，避免把提醒文本当成上一轮问题。"""
        stage = self.state.stage

        if stage == 1:
            return "您这种不舒服，是哪里难受，还是摸到了包块？"

        if stage == 2:
            body_part = self.state.records[0] if self.state.records else "该部位"
            initial_symptom = self.state.records[1] if len(self.state.records) > 1 else ""
            if body_part and initial_symptom:
                return f"明白了。关于{body_part}的“{initial_symptom}”，请再具体描述一下，比如持续时间、程度，或还有没有其他伴随症状？"
            return "请再具体描述一下症状，比如持续时间、程度，或还有没有其他伴随症状？"

        return "请继续描述您的不适。"

    @staticmethod
    def _is_affirmative(text: str) -> bool:
        normalized = text.replace("，", "").replace("。", "").replace(" ", "")
        return normalized in {"是", "好的", "好", "要", "需要", "确认", "重新开始", "重置", "重新导诊", "开始吧"}

    @staticmethod
    def _is_negative(text: str) -> bool:
        normalized = text.replace("，", "").replace("。", "").replace(" ", "")
        return normalized in {"否", "不用", "不需要", "不是", "继续", "继续当前流程", "不用重置", "不重置"}
    
    def reset(self) -> None:
        """重置导诊流程"""
        self.state.reset(self.config.body_types.copy())

    def get_pending_confirmation(self) -> Optional[Dict[str, Any]]:
        """获取当前待确认状态，供接口层返回更明确的交互信号。"""
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
    
    def _extract_symptoms(self, initial_symptom: str, specific_symptom: str) -> List[str]:
        """
        从症状描述中提取症状关键词
        
        Args:
            initial_symptom: 初步症状
            specific_symptom: 具体症状
            
        Returns:
            症状关键词列表
        """
        symptoms = []
        
        # 添加初步症状
        if initial_symptom:
            # 提取主要症状词（去除修饰语）
            symptom = initial_symptom.replace("头痛", "头痛").replace("头晕", "头晕")
            symptoms.append(symptom)
        
        # 从具体症状中提取关键词
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
    
    def get_conversation_summary(self) -> List[Dict[str, str]]:
        """获取对话摘要"""
        return self.state.messages.copy()
    
    def get_history_for_display(self) -> List[Dict[str, str]]:
        """获取用于展示的历史记录"""
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.state.messages
        ]
