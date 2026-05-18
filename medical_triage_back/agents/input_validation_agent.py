"""
输入验证智能体 - 判断用户输入类型
"""
import re
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent


class InputValidationAgent(BaseAgent):
    """
    输入验证智能体
    
    判断用户输入类型：
    1 = 包含身体部位
    2 = 医学相关但无身体部位
    3 = 与问诊无关
    """
    
    # 常见的确认/否定词
    CONFIRM_WORDS: frozenset[str] = frozenset([
        '有', '没有', '无', '是', '否', '对', '不对', '没错', '是的', '不是',
        '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
        '第一个', '第二个', '第三个', '最后一个'
    ])
    
    # 身体部位关键词
    BODY_KEYWORDS: frozenset[str] = frozenset([
        '头', '脑', '脑袋', '头部', '眼', '眼睛', '耳', '耳朵', '鼻', '鼻子', 
        '口', '口腔', '嘴', '喉咙', '喉', '颈', '脖子', '胸', '乳房', '心脏', 
        '心', '腹', '肚子', '胃', '肠', '腰', '背', '肩', '手臂', '手', '手指',
        '腿', '脚', '足', '膝盖', '关节', '屁股', '臀', '生殖器', '阴部', '肛门',
        '皮肤', '脸', '面', '额', '额头', '太阳穴', '后脑', '后脑勺', '头顶'
    ])
    
    # 症状询问指示词
    SYMPTOM_QUESTION_INDICATORS: frozenset[str] = frozenset([
        "感觉", "症状", "是否", "有没有", "怎么样", "如何",
        "确认", "选择", "符合", "哪个", "哪一种",
        "疼痛", "难受", "不舒服", "晕", "胀", "痛"
    ])
    
    # 无关词
    UNRELATED_WORDS: frozenset[str] = frozenset([
        "天气", "股票", "新闻", "电影", "游戏", "吃饭", "睡觉"
    ])
    
    def process(
        self, 
        user_input: str, 
        current_stage: int, 
        confirmed_body_part: Optional[str] = None,
        last_assistant_message: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> int:
        """
        验证用户输入类型
        
        Args:
            user_input: 用户输入
            current_stage: 当前导诊阶段
            confirmed_body_part: 已确认的身体部位（如果有）
            last_assistant_message: 上一条助手消息（用于判断是否为回答）
            conversation_history: 完整对话历史（用于上下文理解）
        
        Returns:
            输入类型: 1/2/3
        """
        user_input = user_input.strip()
        user_input_lower = user_input.lower()
        
        # 1. 快速检查：是否包含身体部位关键词
        if any(kw in user_input_lower for kw in self.BODY_KEYWORDS):
            return 1
        
        # 2. 检查是否是对上一个问题的简单回答
        if last_assistant_message:
            if self._is_simple_answer(user_input, last_assistant_message):
                return 2
            if self._is_choice_answer(user_input, last_assistant_message):
                return 2
        
        # 3. 基于对话历史进行上下文理解
        if conversation_history and len(conversation_history) >= 2:
            context_type = self._analyze_context(user_input, conversation_history)
            if context_type is not None:
                return context_type
        
        # 4. 使用LLM进行判断
        return self._llm_validation(
            user_input, 
            current_stage, 
            confirmed_body_part
        )
    
    def _is_simple_answer(
        self, 
        user_input: str, 
        last_assistant_message: str
    ) -> bool:
        """
        判断用户输入是否是对上一个问题的简单回答
        
        如果上一条消息是询问（包含问号、"是否"等），
        且用户输入是简单确认词，则认为是有效回答
        """
        # 检查是否是确认词
        if not self._is_confirm_word(user_input):
            return False
        
        # 检查上一条是否是问题
        question_indicators = {'?', '？', '是否', '有没有', '请选择', '哪个', '选项'}
        is_question = any(indicator in last_assistant_message for indicator in question_indicators)
        
        return is_question
    
    def _is_choice_answer(self, user_input: str, last_assistant_message: str) -> bool:
        """
        判断用户输入是否是对选择问题的回答
        
        例如：
        - 机器人问："这种感觉主要发生在：- 清晨刚起床时 - 疲劳时..."
        - 用户答："清晨刚起床时" → 这是有效回答
        """
        user_input_clean = user_input.strip().lower()
        
        # 提取上一条消息中的选项
        option_patterns = [
            r'[-•]\s*([^\n]+)',  # - 选项 或 • 选项
            r'\d+[\.、]\s*([^\n]+)',  # 1. 选项 或 1、选项
        ]
        
        options_found = []
        for pattern in option_patterns:
            matches = re.findall(pattern, last_assistant_message)
            options_found.extend(m.strip() for m in matches if len(m.strip()) > 1)
        
        # 检查用户输入是否匹配或包含某个选项
        for option in options_found:
            option_lower = option.lower()
            # 完全匹配或包含匹配
            if (user_input_clean == option_lower or 
                option_lower in user_input_clean or 
                user_input_clean in option_lower):
                return True
            # 模糊匹配
            option_keywords = option_lower.replace('时', '').replace('间', '').split()
            for keyword in option_keywords:
                if len(keyword) >= 2 and keyword in user_input_clean:
                    return True
        
        return False
    
    def _is_confirm_word(self, user_input: str) -> bool:
        """检查是否是确认/选择词"""
        user_input_lower = user_input.lower().strip()
        
        # 直接匹配
        if user_input_lower in self.CONFIRM_WORDS:
            return True
        
        # 数字（1-2位）
        if user_input_lower.isdigit() and len(user_input_lower) <= 2:
            return True
        
        # 第X个
        if re.match(r'第[一二三四五六七八九十0-9]+个', user_input_lower):
            return True
        
        return False
    
    def _analyze_context(
        self, 
        user_input: str, 
        conversation_history: List[Dict[str, str]]
    ) -> Optional[int]:
        """
        基于完整对话历史分析用户输入的上下文
        
        Returns:
            - 1: 包含身体部位
            - 2: 医学相关
            - 3: 无关
            - None: 无法确定
        """
        user_input_clean = user_input.strip().lower()
        
        # 获取最近几轮对话
        recent_messages = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
        
        # 检查是否在症状询问的上下文中
        assistant_questions = [
            msg for msg in recent_messages 
            if msg.get("role") == "assistant"
        ]
        
        if not assistant_questions:
            return None
        
        last_question = assistant_questions[-1].get("content", "")
        
        # 如果上一条是症状确认类问题，用户的简短回答应被视为医学相关
        is_symptom_question = any(
            indicator in last_question 
            for indicator in self.SYMPTOM_QUESTION_INDICATORS
        )
        
        if is_symptom_question and len(user_input) <= 15:
            # 排除明显无关的词
            if not any(word in user_input_clean for word in self.UNRELATED_WORDS):
                return 2
        
        return None
    
    def _llm_validation(
        self, 
        user_input: str, 
        current_stage: int,
        confirmed_body_part: Optional[str]
    ) -> int:
        """使用LLM进行输入验证"""
        
        context_hint = ""
        if current_stage > 0 and confirmed_body_part:
            context_hint = f"""\n（注意：
- 用户之前已说明身体部位是{confirmed_body_part}
- 当前是在询问症状细节
- 用户的回答可能是简单的确认词如"有"/"无"/数字选择等，这些应被视为医学相关）"""
        
        system_prompt = f"""判断用户输入是否包含身体部位，如果是输出1。
如果不包含身体部位，但和医学相关（如症状描述、疾病名称、感受描述、确认词如"有"/"无"/数字选择等）输出2。
如果和医学无关则输出3。

示例：
Q：我的脑袋有些不舒服
A：{{"number":1}}

Q：晕晕的
A：{{"number":2}}

Q：有
A：{{"number":2}}

Q：无
A：{{"number":2}}

Q：1
A：{{"number":2}}

Q：第二个
A：{{"number":2}}

Q：今天天气怎么样
A：{{"number":3}}
{context_hint}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
        
        try:
            response = self._call_llm(messages, temperature=0.3)
        except Exception as e:
            # LLM调用失败，使用回退逻辑
            print(f"LLM验证失败: {e}，使用回退逻辑")
            return self._fallback_validation(user_input)
        
        # 解析JSON
        result: Optional[Dict[str, Any]] = self._parse_json(response)
        if result and "number" in result:
            return int(result["number"])
        
        # 回退到字符匹配
        if "1" in response:
            return 1
        elif "2" in response:
            return 2
        elif "3" in response:
            return 3
        
        return self._fallback_validation(user_input)
    
    def _fallback_validation(self, user_input: str) -> int:
        """回退验证逻辑（当LLM失败时使用）"""
        # 如果是简单确认词，认为是医学相关
        if self._is_confirm_word(user_input):
            return 2
        
        # 默认认为是医学相关
        return 2
