import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

TMP_DIR = tempfile.mkdtemp(prefix='medical_triage_step3_')
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
        return '我是导诊助手，请问您哪里不舒服呢？'


class Step3RouteIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True

    def setUp(self):
        self.client = app.test_client()
        suffix = uuid.uuid4().hex[:8]
        self.free_username = f'front_free_{suffix}'
        self.vip_username = f'front_vip_{suffix}'
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

    def _headers(self, token):
        return {'Authorization': f'Bearer {token}'}

    @patch('medical_triage_back.web_server.get_engine', return_value=DummyEngine())
    def test_welcome_requires_token_and_returns_message(self, _mock_engine):
        unauthorized = self.client.get('/api/welcome?session_id=s1')
        self.assertEqual(unauthorized.status_code, 401)

        authorized = self.client.get('/api/welcome?session_id=s1', headers=self._headers(self.free_token))
        self.assertEqual(authorized.status_code, 200, authorized.get_json())
        data = authorized.get_json()
        self.assertIn('message', data)
        self.assertTrue(data['message'])
        self.assertEqual(data['session_id'], 's1')

    @patch('medical_triage_back.web_server.get_engine', return_value=DummyEngine())
    def test_reset_requires_token_and_succeeds(self, _mock_engine):
        unauthorized = self.client.post('/api/reset', json={'session_id': 's2'})
        self.assertEqual(unauthorized.status_code, 401)

        authorized = self.client.post('/api/reset', json={'session_id': 's2'}, headers=self._headers(self.free_token))
        self.assertEqual(authorized.status_code, 200, authorized.get_json())
        data = authorized.get_json()
        self.assertIn('message', data)
        self.assertIn('session_id', data)
        self.assertEqual(data.get('session_id'), 's2')

    @patch('medical_triage_back.web_server.save_triage_history')
    @patch('medical_triage_back.web_server.get_engine', return_value=DummyEngine())
    def test_chat_accepts_token_and_returns_tiered_result(self, _mock_engine, _mock_save):
        unauthorized = self.client.post('/api/chat', json={'session_id': 'anon', 'message': '我肚子疼'})
        self.assertEqual(unauthorized.status_code, 401)

        free = self.client.post(
            '/api/chat',
            json={'session_id': 'free_sess', 'message': '我肚子疼'},
            headers=self._headers(self.free_token)
        )
        self.assertEqual(free.status_code, 200, free.get_json())
        free_data = free.get_json()
        self.assertIn('message', free_data)
        self.assertTrue(free_data['is_complete'])
        self.assertEqual(free_data['recommended_department'], '消化内科')
        self.assertEqual(free_data['departments'], ['消化内科'])
        self.assertTrue(free_data['detail_locked'])
        self.assertEqual(free_data['detail_level'], 'basic')
        self.assertIsNone(free_data['detailed_medical_advice'])

        vip = self.client.post(
            '/api/chat',
            json={'session_id': 'vip_sess', 'message': '我肚子疼'},
            headers=self._headers(self.vip_token)
        )
        self.assertEqual(vip.status_code, 200, vip.get_json())
        vip_data = vip.get_json()
        self.assertIn('message', vip_data)
        self.assertTrue(vip_data['is_complete'])
        self.assertEqual(vip_data['recommended_department'], '消化内科')
        self.assertEqual(vip_data['departments'], ['消化内科'])
        self.assertFalse(vip_data['detail_locked'])
        self.assertEqual(vip_data['detail_level'], 'member')
        self.assertIsNotNone(vip_data['detailed_medical_advice'])
        self.assertIn('清淡饮食', vip_data['detailed_medical_advice'])


if __name__ == '__main__':
    unittest.main()
