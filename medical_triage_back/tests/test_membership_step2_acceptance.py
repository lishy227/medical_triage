import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

TMP_DIR = tempfile.mkdtemp(prefix='medical_triage_step2_')
os.environ['DATABASE_URL'] = f"sqlite:///{os.path.join(TMP_DIR, 'test.db')}"

from medical_triage_back.web_server import app, get_db_session, User  # noqa: E402


class DummyEngine:
    def __init__(self):
        self.enable_rag = True
        self.state = type('State', (), {'stage': 3, 'records': ['腹部', '腹痛', '持续疼痛']})()

    def process(self, user_input):
        return (
            '🎉 导诊完成！\n\n根据您的症状，建议优先前往消化内科就诊。\n\n最终推荐结果: [消化内科]\n\n详细建议：请注意清淡饮食，必要时尽快线下就医。',
            True,
        )

    def get_pending_confirmation(self):
        return None

    def get_department_recommendation(self):
        return '消化内科'

    def get_conversation_summary(self):
        return '腹部 -> 腹痛 -> 持续疼痛'

    def get_history_for_display(self):
        return []

    def reset(self):
        pass

    def get_welcome_message(self):
        return 'welcome'


class Step2AcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True

    def setUp(self):
        self.client = app.test_client()
        suffix = uuid.uuid4().hex[:8]
        self.free_username = f'free_user_case_{suffix}'
        self.vip_username = f'vip_user_case_{suffix}'
        self.free_token = self._register_user(self.free_username, '123456')
        self.vip_token = self._register_user(self.vip_username, '123456')
        self._activate_vip(self.vip_username)

    def _register_user(self, username, password):
        resp = self.client.post('/api/auth/register', json={'username': username, 'password': password})
        self.assertEqual(resp.status_code, 201, resp.get_json())
        return resp.get_json()['token']

    def _activate_vip(self, username):
        session = get_db_session()
        try:
            user = session.query(User).filter_by(username=username).first()
            user.membership_type = 'vip'
            user.member_started_at = datetime.utcnow()
            user.member_expires_at = datetime.utcnow() + timedelta(days=30)
            session.commit()
        finally:
            session.close()

    def _chat(self, token):
        return self.client.post(
            '/api/chat',
            json={'session_id': 'acceptance-step2', 'message': '我肚子疼'},
            headers={'Authorization': f'Bearer {token}'}
        )

    @patch('medical_triage_back.web_server.save_triage_history')
    @patch('medical_triage_back.web_server.get_engine', return_value=DummyEngine())
    def test_free_user_only_gets_department(self, _mock_engine, _mock_save):
        resp = self._chat(self.free_token)
        self.assertEqual(resp.status_code, 200, resp.get_json())
        data = resp.get_json()

        self.assertTrue(data['is_complete'])
        self.assertTrue(data['detail_locked'])
        self.assertEqual(data['detail_level'], 'basic')
        self.assertEqual(data['recommended_department'], '消化内科')
        self.assertEqual(data['departments'], ['消化内科'])
        self.assertIsNone(data['detailed_medical_advice'])
        self.assertIn('最终推荐结果: [消化内科]', data['message'])
        self.assertNotIn('清淡饮食', data['message'])

    @patch('medical_triage_back.web_server.save_triage_history')
    @patch('medical_triage_back.web_server.get_engine', return_value=DummyEngine())
    def test_member_gets_detailed_advice(self, _mock_engine, _mock_save):
        resp = self._chat(self.vip_token)
        self.assertEqual(resp.status_code, 200, resp.get_json())
        data = resp.get_json()

        self.assertTrue(data['is_complete'])
        self.assertFalse(data['detail_locked'])
        self.assertEqual(data['detail_level'], 'member')
        self.assertEqual(data['recommended_department'], '消化内科')
        self.assertEqual(data['departments'], ['消化内科'])
        self.assertIsNotNone(data['detailed_medical_advice'])
        self.assertIn('清淡饮食', data['detailed_medical_advice'])
        self.assertIn('最终推荐结果: [消化内科]', data['message'])


if __name__ == '__main__':
    unittest.main()
