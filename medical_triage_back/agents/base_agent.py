"""
智能体基类 - 使用 Tenacity 实现重试机制
"""
import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class BaseAgent(ABC):
    """智能体基类 - 提供LLM调用和通用工具方法"""
    
    def __init__(self, client: OpenAI, model: str) -> None:
        self.client: OpenAI = client
        self.model: str = model
    
    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _call_llm(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        timeout: float = 30.0
    ) -> str:
        """
        调用LLM，带重试机制
        
        使用 Tenacity 实现指数退避重试，最多3次
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            timeout: 超时时间（秒）
            
        Returns:
            LLM响应文本
            
        Raises:
            Exception: 重试3次后仍失败
        """
        completion: Any = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            timeout=timeout,
        )
        return completion.choices[0].message.content or ""
    
    @abstractmethod
    def process(self, *args: Any, **kwargs: Any) -> Any:
        """处理逻辑，子类实现"""
        pass
    
    def _parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        从文本中提取JSON
        
        尝试多种方式解析：
        1. 直接解析
        2. 从代码块中提取
        3. 从花括号中提取
        
        Args:
            text: 包含JSON的文本
            
        Returns:
            解析后的字典，失败返回None
        """
        if not text:
            return None
        
        text = text.strip()
        
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 从代码块中提取
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 从花括号中提取
        match = re.search(r'\{[^{}]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        
        return None
