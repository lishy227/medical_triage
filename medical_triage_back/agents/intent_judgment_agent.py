"""
意图判断智能体 - 判断用户回答匹配哪个选项
"""
from typing import List, Dict, Optional, Any

from agents.base_agent import BaseAgent


class IntentJudgmentAgent(BaseAgent):
    """
    意图判断智能体
    
    根据对话历史判断用户属于当前阶段的哪个选项
    """
    
    def process(self, stage_name: str, options: List[str], 
                messages: List[Dict[str, str]]) -> int:
        """
        判断用户意图，匹配选项
        
        Args:
            stage_name: 当前阶段名称（如"身体部位"、"初步症状"）
            options: 当前可选项列表
            messages: 对话历史
        
        Returns:
            匹配的索引，-1表示未匹配
        """
        # 获取最后一条用户消息和助手消息
        last_user_msg = None
        last_assistant_msg = None
        
        for msg in reversed(messages):
            if msg.get("role") == "user" and last_user_msg is None:
                last_user_msg = msg.get("content", "").strip()
            elif msg.get("role") == "assistant" and last_assistant_msg is None:
                last_assistant_msg = msg.get("content", "").strip()
            if last_user_msg and last_assistant_msg:
                break
        
        if not last_user_msg:
            return -1
        
        # ====== 关键修复：检查是否是选择类问题的回答 ======
        # 如果上一条助手消息包含选项列表（A/B/C/D 或 1/2/3/4）
        if last_assistant_msg and self._is_choice_question(last_assistant_msg):
            # 尝试匹配用户选择
            choice_index = self._match_choice_answer(last_user_msg, last_assistant_msg, options)
            if choice_index >= 0:
                return choice_index
        
        # ====== 快速匹配：检查用户输入是否直接匹配某个选项 ======
        for i, option in enumerate(options):
            # 完全匹配或包含关系
            if option.lower() in last_user_msg.lower() or last_user_msg.lower() in option.lower():
                return i
            
            # 关键词匹配
            option_keywords = self._extract_keywords(option)
            user_keywords = self._extract_keywords(last_user_msg)
            
            # 如果有关键词匹配
            if any(kw in user_keywords for kw in option_keywords):
                return i
        
        # ====== 使用 LLM 进行更复杂的判断 ======
        return self._llm_judgment(stage_name, options, messages, last_user_msg, last_assistant_msg)
    
    def _is_choice_question(self, assistant_msg: str) -> bool:
        """判断是否是选择类问题（包含 A/B/C/D 或选项列表）"""
        import re
        # 检查是否包含选项标记
        if re.search(r'[A-D][\.、\s]', assistant_msg) or re.search(r'\d+[\.、\s]', assistant_msg):
            return True
        # 检查是否包含 "- " 或 "• " 开头的列表
        if re.search(r'[-•]\s+', assistant_msg):
            return True
        return False
    
    def _match_choice_answer(self, user_msg: str, assistant_msg: str, options: List[str]) -> int:
        """匹配用户的选择回答"""
        import re
        user_msg_lower = user_msg.lower().strip()
        
        # 1. 检查是否直接说选项字母（A、B、C、D）
        letter_match = re.match(r'^([a-d])[\.、\s]*', user_msg_lower)
        if letter_match:
            letter = letter_match.group(1).upper()
            index = ord(letter) - ord('A')
            if 0 <= index < len(options):
                return index
        
        # 2. 检查是否说数字（第1个、第2个）
        number_match = re.match(r'第?([1-9])[\.、\s个]*', user_msg_lower)
        if number_match:
            index = int(number_match.group(1)) - 1
            if 0 <= index < len(options):
                return index
        
        # 3. 检查是否直接复述选项内容
        for i, option in enumerate(options):
            option_lower = option.lower()
            # 完全匹配
            if option_lower == user_msg_lower:
                return i
            # 包含匹配
            if option_lower in user_msg_lower or user_msg_lower in option_lower:
                return i
            # 关键词匹配（提取核心词）
            option_core = option_lower.replace('时', '').replace('后', '').replace('前', '').strip()
            if len(option_core) >= 2 and option_core in user_msg_lower:
                return i
        
        return -1
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取文本中的关键词"""
        # 去除常见虚词，提取有意义的词
        stop_words = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        words = text.lower().replace('，', ',').replace('。', '.').replace('、', ',').split()
        keywords = []
        for word in words:
            word = word.strip('.,!?;:')
            if len(word) >= 2 and word not in stop_words:
                keywords.append(word)
        return keywords
    
    def _llm_judgment(self, stage_name: str, options: List[str], 
                      messages: List[Dict[str, str]], 
                      last_user_msg: str, 
                      last_assistant_msg: Optional[str]) -> int:
        """使用 LLM 进行意图判断"""
        
        system_prompt = f"""你是一位医疗导诊助手，负责判断用户的回答对应哪个选项。

### 判断规则
1. **直接匹配**：用户的回答与某个选项内容相同或高度相似 → 返回该选项索引
2. **关键词匹配**：用户的回答包含某个选项的核心关键词 → 返回该选项索引  
3. **语义匹配**：用户的回答与某个选项语义相近 → 返回该选项索引
4. **无法匹配**：用户的回答与所有选项都不相关 → 返回 -1

### 重要提示
- 用户可能用不同的方式表达同一个意思（如"头顶发沉"对应"头痛"）
- 优先选择最相关的选项，而不是返回 -1
- 如果用户描述了症状，即使不完全匹配，也选择最接近的选项

### 输出格式（严格JSON）
{{"index": 0}} 或 {{"index": -1}}

当前阶段：{stage_name}
选项列表：{options}
用户回答：{last_user_msg}"""
        
        llm_messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        llm_messages.extend(messages)
        
        response: str = self._call_llm(llm_messages)
        
        # 解析JSON
        result: Optional[Dict[str, Any]] = self._parse_json(response)
        if result and "index" in result:
            index = int(result["index"])
            # 确保索引在有效范围内
            if 0 <= index < len(options):
                return index
            else:
                print(f"警告: LLM 返回的索引 {index} 超出范围 (0-{len(options)-1})")
                return -1
        
        # 回退：检查是否直接包含某个选项
        last_content: str = messages[-1].get("content", "") if messages else ""
        for i, option in enumerate(options):
            if option in last_content:
                return i
        
        return -1
