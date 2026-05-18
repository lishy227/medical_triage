"""
测试：TriageState 序列化 / 反序列化

验证：
  1. to_dict() 产出纯 JSON 安全的数据
  2. from_dict() 完整恢复状态（含 Stage enum）
  3. 序列化-反序列化往返一致性
  4. pending_body_change（复杂嵌套结构）正确处理
  5. 空状态、中间状态、完成状态全覆盖
"""
import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from triage import Stage, TriageState


class TestTriageStateSerialization(unittest.TestCase):
    """TriageState 序列化测试"""

    def test_empty_state_roundtrip(self):
        """空状态：to_dict → from_dict 往返"""
        original = TriageState()
        original.options = ["头颅", "眼", "耳"]

        d = original.to_dict()
        restored = TriageState.from_dict(d)

        self.assertEqual(restored.stage, Stage.BODY_PART)
        self.assertEqual(restored.records, [])
        self.assertEqual(restored.options, ["头颅", "眼", "耳"])
        self.assertEqual(restored.messages, [])
        self.assertIsNone(restored.pending_body_change)

    def test_mid_conversation_roundtrip(self):
        """中间状态：3 条消息 + 2 个阶段"""
        original = TriageState(
            stage=Stage.INITIAL_SYMPTOM,
            records=["头颅", "头痛"],
            options=["持续性钝痛", "搏动性跳痛", "针刺样痛"],
            messages=[
                {"role": "user", "content": "我头疼"},
                {"role": "assistant", "content": "请描述头痛的性质"},
                {"role": "user", "content": "持续性钝痛"},
            ],
        )

        d = original.to_dict()
        restored = TriageState.from_dict(d)

        self.assertEqual(restored.stage, Stage.INITIAL_SYMPTOM)
        self.assertEqual(restored.records, ["头颅", "头痛"])
        self.assertEqual(len(restored.messages), 3)
        self.assertEqual(restored.messages[0]["role"], "user")
        self.assertEqual(restored.messages[0]["content"], "我头疼")

    def test_completed_state_roundtrip(self):
        """完成状态：3 个 records + 4 条消息"""
        original = TriageState(
            stage=Stage.COMPLETED,
            records=["头颅", "头痛", "持续性钝痛"],
            options=[],
            messages=[
                {"role": "user", "content": "我头疼"},
                {"role": "assistant", "content": "什么性质？"},
                {"role": "user", "content": "持续性钝痛"},
                {"role": "assistant", "content": "推荐科室：神经内科"},
            ],
        )

        d = original.to_dict()
        restored = TriageState.from_dict(d)

        self.assertEqual(restored.stage, Stage.COMPLETED)
        self.assertEqual(len(restored.records), 3)
        self.assertEqual(restored.records[-1], "持续性钝痛")

    def test_pending_body_change_roundtrip(self):
        """pending_body_change（嵌套 dict）正确序列化"""
        original = TriageState(
            stage=Stage.SPECIFIC_SYMPTOM,
            records=["头颅", "头痛"],
            options=["持续性钝痛", "搏动性跳痛"],
            messages=[],
            pending_body_change={
                "candidate_input": "肚子疼",
                "comparison_result": {"is_changed": True, "detected_body": "腹部", "confidence": 0.92},
                "previous_stage": 2,
                "previous_records": ["头颅", "头痛"],
                "previous_options": ["持续性钝痛"],
                "reminder_message": "检测到部位变更",
                "followup_question": "继续吗？",
            },
        )

        d = original.to_dict()
        restored = TriageState.from_dict(d)

        self.assertIsNotNone(restored.pending_body_change)
        self.assertEqual(
            restored.pending_body_change["candidate_input"], "肚子疼"
        )
        self.assertEqual(
            restored.pending_body_change["comparison_result"]["confidence"], 0.92
        )

    def test_json_serializable(self):
        """to_dict() 产出可被 json.dumps 序列化的纯数据"""
        state = TriageState(
            stage=Stage.SPECIFIC_SYMPTOM,
            records=["头颅", "头痛"],
            options=["钝痛", "跳痛"],
            messages=[{"role": "user", "content": "头疼"}],
            pending_body_change={"candidate_input": "test"},
        )

        d = state.to_dict()
        # 不应抛出异常
        json_str = json.dumps(d, ensure_ascii=False)
        self.assertIsInstance(json_str, str)
        # 确认可以解析回来
        parsed = json.loads(json_str)
        self.assertEqual(parsed["stage"], 2)  # SPECIFIC_SYMPTOM = 2

    def test_reset_after_restore(self):
        """从 dict 恢复后 reset 仍正常工作"""
        state = TriageState.from_dict({
            "stage": 2,
            "records": ["头颅", "头痛"],
            "options": ["钝痛"],
            "messages": [{"role": "user", "content": "x"}],
            "pending_body_change": None,
        })

        state.reset(["头颅", "眼", "耳"])
        self.assertEqual(state.stage, Stage.BODY_PART)
        self.assertEqual(state.records, [])
        self.assertEqual(state.options, ["头颅", "眼", "耳"])
        self.assertEqual(state.messages, [])
        self.assertIsNone(state.pending_body_change)

    def test_stage_enum_conversion(self):
        """验证 Stage int → enum 正确映射"""
        for stage in Stage:
            state = TriageState(stage=stage)
            d = state.to_dict()
            restored = TriageState.from_dict(d)
            self.assertEqual(restored.stage, stage)


class TestSerializationPerformance(unittest.TestCase):
    """序列化性能基准"""

    def test_serialization_speed(self):
        """to_dict + from_dict 应 < 1ms（纯 dict 操作，不走 IO）"""
        state = TriageState(
            stage=Stage.SPECIFIC_SYMPTOM,
            records=["头颅", "头痛", "持续性钝痛"],
            options=["钝痛", "跳痛", "针刺痛", "胀痛"],
            messages=[
                {"role": "user", "content": "我头疼"},
                {"role": "assistant", "content": "什么性质？"},
                {"role": "user", "content": "持续性钝痛"},
            ],
            pending_body_change={
                "candidate_input": "test",
                "comparison_result": {"is_changed": True, "confidence": 0.9},
                "previous_records": ["头颅", "头痛"],
            },
        )

        iterations = 10000
        start = time.perf_counter()
        for _ in range(iterations):
            d = state.to_dict()
            TriageState.from_dict(d)
        elapsed = time.perf_counter() - start

        avg_us = (elapsed / iterations) * 1_000_000
        print(f"\n  序列化往返 × {iterations} 次: {elapsed:.3f}s ({avg_us:.1f}μs/次)")
        self.assertLess(avg_us, 1000, f"单次序列化应 < 1ms, 实际 {avg_us:.1f}μs")


if __name__ == "__main__":
    unittest.main()
