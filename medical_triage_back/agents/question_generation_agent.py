"""
问题生成智能体 - 生成询问用户的问题
"""
from typing import List, Dict

from agents.base_agent import BaseAgent


class QuestionGenerationAgent(BaseAgent):
    """
    问题生成智能体
    
    根据当前阶段和已收集信息生成询问问题
    """
    
    def process(self, stage_name: str, records: List[str], 
                options: List[str], messages: List[Dict[str, str]]) -> str:
        """
        生成询问问题
        
        Args:
            stage_name: 当前阶段名称
            records: 已收集的记录
            options: 当前可选项
            messages: 对话历史
        
        Returns:
            生成的问题
        """
        """
        生成询问问题
        
        Args:
            stage_name: 当前阶段名称
            records: 已收集的记录
            options: 当前可选项
            messages: 对话历史
        
        Returns:
            生成的问题
        """
        system_prompt = f"""现在，导诊信息还不完善，你需要通过与用户进行对话，知道用户的"{stage_name}"现在处于哪一个选项中。

注意，现在导诊未完成，请先不要推荐科室。

需要提醒你，用户是一个普通的患者，对医学术语缺乏了解，并且处于语音交流环境。因此，当你提问时：
- 不要问的太专业，以日常语言为主。
- 不要问得太长，患者记不住这么多内容。
- 每次只向用户询问一个简单选择题，注意是一个不是多个。
- 用户可能只描述了部分症状。务必探询用户可能存在的其他症状，确保全面收集信息。

通过一次次的选择题询问，逐步引导用户进行回答，从而分辨用户是属于哪个选项。

已经收集到的导诊信息如下：
{records}

仍需确定的"{stage_name}"的选项列表如下：
{options}"""
        
        llm_messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        llm_messages.extend(messages)
        
        return self._call_llm(llm_messages)
