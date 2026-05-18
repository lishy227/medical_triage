"""
身体部位变更比较智能体 - 使用 dataclasses 和 functools 优化
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, FrozenSet, List, Optional, Set


@dataclass(frozen=True)
class BodyPartMapping:
    """身体部位映射 - 不可变数据类"""
    canonical: str
    aliases: FrozenSet[str]
    family: str


class BodyComparisonAgent:
    """判断当前症状描述的身体部位是否与历史部位明显变化。"""

    # 身体部位别名映射
    BODY_ALIASES: Dict[str, FrozenSet[str]] = {
        "头颅": frozenset({"头", "脑", "脑袋", "头部", "头颅", "后脑", "后脑勺", "额头", "太阳穴", "头顶"}),
        "眼": frozenset({"眼", "眼睛", "眼部"}),
        "耳": frozenset({"耳", "耳朵", "耳部"}),
        "鼻": frozenset({"鼻", "鼻子", "鼻部"}),
        "口腔": frozenset({"口", "嘴", "嘴巴", "牙", "牙齿", "口腔", "口腔内"}),
        "喉": frozenset({"喉", "喉咙", "咽", "嗓子", "咽喉"}),
        "面部": frozenset({"脸", "面", "面部", "面颊", "下巴"}),
        "足": frozenset({"足", "脚", "脚部", "脚踝", "踝", "脚趾"}),
        "腿": frozenset({"腿", "大腿", "小腿", "膝", "膝盖", "膝关节"}),
        "前颈部": frozenset({"前颈部", "颈前", "脖子前面", "前脖子"}),
        "后颈部": frozenset({"后颈部", "颈后", "后脖子"}),
        "胸部": frozenset({"胸", "胸口", "胸部", "乳房", "心口"}),
        "心脏": frozenset({"心脏", "心口", "心前区"}),
        "上腹部": frozenset({"上腹部", "上腹", "胃", "胃部", "心窝", "肚子上面"}),
        "下腹部": frozenset({"下腹部", "下腹", "小腹", "肚子下面"}),
        "腹部": frozenset({"腹", "腹部", "肚子", "肚", "肠", "肠道"}),
        "双髋部": frozenset({"双髋部", "髋部", "髋", "胯", "胯部"}),
        "生殖系统": frozenset({"生殖系统", "生殖器", "阴部", "私处", "肛门", "会阴"}),
        "肩膀": frozenset({"肩", "肩膀", "肩部"}),
        "胸椎": frozenset({"胸椎", "胸背部", "上背"}),
        "背部": frozenset({"背", "后背", "背部"}),
        "腰椎": frozenset({"腰椎", "腰椎部"}),
        "腰部": frozenset({"腰", "后腰", "腰部"}),
        "臀部": frozenset({"臀", "屁股", "臀部"}),
        "手": frozenset({"手", "手掌", "手指", "手腕", "腕"}),
        "手臂": frozenset({"手臂", "胳膊", "上臂", "前臂", "肘"}),
        "皮肤": frozenset({"皮肤", "皮疹", "红疹", "疙瘩", "瘙痒"}),
    }

    BODY_FAMILY: Dict[str, str] = {
        "头颅": "头面", "眼": "头面", "耳": "头面", "鼻": "头面",
        "口腔": "头面", "喉": "颈咽", "面部": "头面",
        "足": "下肢", "腿": "下肢",
        "前颈部": "颈部", "后颈部": "颈部",
        "胸部": "胸部", "心脏": "胸部",
        "上腹部": "腹部", "下腹部": "腹部", "腹部": "腹部",
        "双髋部": "髋臀", "生殖系统": "盆会阴", "臀部": "髋臀",
        "肩膀": "上肢", "手": "上肢", "手臂": "上肢",
        "胸椎": "背腰", "背部": "背腰", "腰椎": "背腰", "腰部": "背腰",
        "皮肤": "皮肤",
    }

    CLARIFY_MARKERS: FrozenSet[str] = frozenset({
        "疼", "痛", "不舒服", "难受", "胀", "酸", "麻", "刺痛", "隐痛", "绞痛",
        "还是", "就是", "不是", "有点", "一直", "偶尔", "最近", "主要是", "只是", "一直都",
        "肚子疼", "胃疼", "胸闷", "头疼", "头痛", "腹痛"
    })

    CONFIRM_SWITCH_MARKERS: FrozenSet[str] = frozenset({
        "换个部位", "另一个部位", "另外一个部位", "不是这个部位", "改成", "其实是",
        "不是这里", "不是这个地方", "重新说", "换成", "改为", "说错了"
    })

    SYMPTOM_MARKERS: FrozenSet[str] = frozenset({
        "疼", "痛", "不舒服", "难受", "发麻", "刺痛", "酸胀", "肿", "痒", "硬块"
    })

    def __init__(
        self, 
        client: Optional[Any] = None, 
        model: Optional[str] = None
    ) -> None:
        # 保留与原调用链兼容的构造签名
        self.client = client
        self.model = model

    def process(
        self,
        current_text: str,
        history_text: str,
        stage: Optional[Any] = None,
        recent_user_messages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        处理身体部位变更检测
        
        Args:
            current_text: 当前用户输入
            history_text: 历史身体部位
            stage: 当前阶段（可选）
            recent_user_messages: 最近用户消息列表（可选）
            
        Returns:
            包含检测结果的字典
        """
        current = (current_text or "").strip().lower()
        history = (history_text or "").strip().lower()
        recent_user_messages = recent_user_messages or []

        if not current or not history:
            return self._no_change("缺少当前或历史输入，无法可靠判断是否存在身体部位变化。")

        current_parts = self._extract_body_parts(current)
        history_parts = self._extract_body_parts(history)
        current_families = self._extract_body_families(current_parts)
        history_families = self._extract_body_families(history_parts)

        if not current_parts:
            return self._no_change("当前输入没有识别到明确身体部位，更像是在补充症状细节。")

        if current_parts & history_parts:
            return self._no_change(
                f"当前描述与历史描述仍指向相同身体部位：{sorted(current_parts & history_parts)}。",
                detected_body=self._format_detected_body(current_parts),
                confidence=0.08,
            )

        if current_families & history_families:
            return self._no_change(
                f"当前描述与历史记录仍属于同一身体区域：{sorted(current_families & history_families)}。",
                detected_body=self._format_detected_body(current_parts),
                confidence=0.12,
            )

        if self._looks_like_clarification(current, history, recent_user_messages):
            return self._no_change(
                "当前输入更像是在澄清或细化同一部位症状，不视为切换新的身体部位。",
                detected_body=self._format_detected_body(current_parts),
                confidence=0.18,
            )

        if not history_parts and not history_families:
            return self._no_change(
                "历史部位本身不够明确，暂不触发身体部位变化。",
                detected_body=self._format_detected_body(current_parts),
                confidence=0.15,
            )

        explicit_switch = any(marker in current for marker in self.CONFIRM_SWITCH_MARKERS)
        strong_new_part = self._is_strong_new_part_statement(current, current_parts)
        disjoint_families = current_families.isdisjoint(history_families)

        if explicit_switch and disjoint_families:
            return {
                "is_changed": True,
                "confidence": 0.93,
                "reason": f"用户明确表示切换身体部位：当前={sorted(current_parts)}，历史={sorted(history_parts)}。",
                "detected_body": self._format_detected_body(current_parts),
            }

        if disjoint_families and strong_new_part:
            return {
                "is_changed": True,
                "confidence": 0.72,
                "reason": f"当前输入较明确地指向新的身体区域：当前={sorted(current_parts)}，历史={sorted(history_parts)}。",
                "detected_body": self._format_detected_body(current_parts),
            }

        return self._no_change(
            "虽然检测到了一些部位词，但证据还不够强，默认继续当前导诊流程。",
            detected_body=self._format_detected_body(current_parts),
            confidence=0.2,
        )

    def _extract_body_parts(self, text: str) -> Set[str]:
        """从文本中提取身体部位"""
        parts: Set[str] = set()
        for canonical, aliases in self.BODY_ALIASES.items():
            if any(alias in text for alias in aliases):
                parts.add(canonical)
        return parts

    def _extract_body_families(self, parts: Set[str]) -> Set[str]:
        """提取身体部位所属的区域家族"""
        families: Set[str] = set()
        for part in parts:
            family = self.BODY_FAMILY.get(part)
            if family:
                families.add(family)
        return families

    def _looks_like_clarification(
        self, 
        current: str, 
        history: str, 
        recent_user_messages: List[str]
    ) -> bool:
        """判断当前输入是否像是在澄清或细化同一部位"""
        if any(marker in current for marker in self.CONFIRM_SWITCH_MARKERS):
            return False

        current_parts = self._extract_body_parts(current)
        history_parts = self._extract_body_parts(history)
        current_families = self._extract_body_families(current_parts)
        history_families = self._extract_body_families(history_parts)

        if len(current) <= 12 and any(marker in current for marker in self.CLARIFY_MARKERS):
            return True

        if current_families & history_families:
            return True

        if recent_user_messages:
            recent_context = " ".join(recent_user_messages[-3:]).lower()
            if history in recent_context and any(marker in current for marker in self.CLARIFY_MARKERS):
                return True

        return False

    def _is_strong_new_part_statement(self, current: str, current_parts: Set[str]) -> bool:
        """判断是否是明确的新部位陈述"""
        if not current_parts:
            return False

        if len(current) <= 4:
            return False

        # 检查是否以部位词开头
        starts_with_part = any(
            current.startswith(alias) 
            for aliases in self.BODY_ALIASES.values() 
            for alias in aliases
        )
        has_symptom_marker = any(marker in current for marker in self.SYMPTOM_MARKERS)

        return starts_with_part and has_symptom_marker

    @staticmethod
    def _format_detected_body(parts: Set[str]) -> str:
        """格式化检测到的身体部位"""
        return "、".join(sorted(parts)) if parts else ""

    @staticmethod
    def _no_change(
        reason: str, 
        detected_body: str = "", 
        confidence: float = 0.0
    ) -> Dict[str, Any]:
        """构造无变更的返回结果"""
        return {
            "is_changed": False,
            "confidence": confidence,
            "reason": reason,
            "detected_body": detected_body,
        }


# 模块级单例实例
body_comparison_agent = BodyComparisonAgent()
