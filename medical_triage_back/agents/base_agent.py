"""
智能体基类
"""
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod

from openai import OpenAI


class BaseAgent(ABC):
    """智能体基类"""
    
    def __init__(self, client: OpenAI, model: str) -> None:
        self.client: OpenAI = client
        self.model: str = model
    
    def _call_llm(self, messages: List[Dict[str, str]], timeout: float = 30.0) -> str:
        """调用LLM，带超时设置"""
        try:
            completion: Any = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                timeout=timeout
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"LLM调用失败: {e}")
            return ""
    
    @abstractmethod
    def process(self, *args: Any, **kwargs: Any) -> Any:
        """处理逻辑，子类实现"""
        pass
    
    def _parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """从文本中提取JSON"""
        import json
        import re
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        match = re.search(r'\{[^}]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        
        return None
