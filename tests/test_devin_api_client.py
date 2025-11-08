"""
Unit tests for the Devin API Client

These tests use mocking to avoid consuming ACU credits while ensuring
the client behaves correctly under various scenarios.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import time
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from devin_api_client import (
    DevinAPIClient,
    SessionResponse,
    SessionDetails,
    SessionStatus
)


class TestDevinAPIClient(unittest.TestCase):
    """Test suite for DevinAPIClient"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.api_key = "test-api-key-12345"
        self.client = DevinAPIClient(api_key=self.api_key)
        self.test_session_id = "devin-test123"
        self.test_url = f"https://app.devin.ai/sessions/{self.test_session_id}"
    
    def test_init_with_api_key(self):
        """Test client initialization with API key"""
        client = DevinAPIClient(api_key="test-key")
        self.assertEqual(client.api_key, "test-key")
        self.assertIn("Authorization", client.headers)
        self.assertEqual(client.headers["Authorization"], "Bearer test-key")
    
    def test_init_without_api_key_raises_error(self):
        """Test that missing API key raises ValueError"""
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError) as context:
                DevinAPIClient()
            self.assertIn("API key required", str(context.exception))
    
    @patch.dict('os.environ', {'DEVIN_API_KEY': 'env-api-key'})
    def test_init_with_env_var(self):
        """Test client initialization from environment variable"""
        client = DevinAPIClient()
        self.assertEqual(client.api_key, "env-api-key")
    
    @patch('requests.post')
    def test_create_session_success(self, mock_post):
        """Test successful session creation"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "session_id": self.test_session_id,
            "url": self.test_url,
            "is_new_session": True
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = self.client.create_session(
            prompt="Test prompt",
            title="Test Session",
            tags=["test"]
        )
        
        self.assertIsInstance(result, SessionResponse)
        self.assertEqual(result.session_id, self.test_session_id)
        self.assertEqual(result.url, self.test_url)
        self.assertTrue(result.is_new_session)
        
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], f"{self.client.BASE_URL}/sessions")
        self.assertIn("prompt", call_args[1]["json"])
        self.assertEqual(call_args[1]["json"]["prompt"], "Test prompt")
    
    @patch('requests.post')
    def test_create_session_with_all_parameters(self, mock_post):
        """Test session creation with all optional parameters"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "session_id": self.test_session_id,
            "url": self.test_url
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = self.client.create_session(
            prompt="Test prompt",
            snapshot_id="snap-123",
            unlisted=True,
            idempotent=True,
            max_acu_limit=100,
            secret_ids=["secret1", "secret2"],
            knowledge_ids=["knowledge1"],
            tags=["tag1", "tag2"],
            title="Custom Title"
        )
        
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        
        self.assertEqual(payload["prompt"], "Test prompt")
        self.assertEqual(payload["snapshot_id"], "snap-123")
        self.assertTrue(payload["unlisted"])
        self.assertTrue(payload["idempotent"])
        self.assertEqual(payload["max_acu_limit"], 100)
        self.assertEqual(payload["secret_ids"], ["secret1", "secret2"])
        self.assertEqual(payload["knowledge_ids"], ["knowledge1"])
        self.assertEqual(payload["tags"], ["tag1", "tag2"])
        self.assertEqual(payload["title"], "Custom Title")
    
    @patch('requests.post')
    def test_create_session_http_error(self, mock_post):
        """Test session creation with HTTP error"""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")
        mock_post.return_value = mock_response
        
        with self.assertRaises(Exception):
            self.client.create_session(prompt="Test")
    
    @patch('requests.get')
    def test_get_session_details_success(self, mock_get):
        """Test successful session details retrieval"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "session_id": self.test_session_id,
            "status": "running",
            "status_enum": "working",
            "title": "Test Session",
            "created_at": "2024-01-01T00:00:00.000000+00:00",
            "updated_at": "2024-01-01T00:05:00.000000+00:00",
            "snapshot_id": None,
            "playbook_id": None,
            "tags": ["test"],
            "pull_request": None,
            "structured_output": {"result": "success"},
            "messages": [
                {
                    "type": "initial_user_message",
                    "message": "Test prompt",
                    "timestamp": "2024-01-01T00:00:00.000000+00:00"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = self.client.get_session_details(self.test_session_id)
        
        self.assertIsInstance(result, SessionDetails)
        self.assertEqual(result.session_id, self.test_session_id)
        self.assertEqual(result.status, "running")
        self.assertEqual(result.status_enum, "working")
        self.assertEqual(result.title, "Test Session")
        self.assertEqual(result.tags, ["test"])
        self.assertEqual(result.structured_output, {"result": "success"})
        self.assertEqual(len(result.messages), 1)
        
        mock_get.assert_called_once_with(
            f"{self.client.BASE_URL}/sessions/{self.test_session_id}",
            headers=self.client.headers
        )
    
    @patch('requests.get')
    def test_get_session_details_with_pr(self, mock_get):
        """Test session details with pull request"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "session_id": self.test_session_id,
            "status": "finished",
            "status_enum": "finished",
            "title": "Test Session",
            "created_at": "2024-01-01T00:00:00.000000+00:00",
            "updated_at": "2024-01-01T00:10:00.000000+00:00",
            "pull_request": {
                "url": "https://github.com/test/repo/pull/123"
            },
            "structured_output": None,
            "messages": []
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = self.client.get_session_details(self.test_session_id)
        
        self.assertIsNotNone(result.pull_request)
        self.assertEqual(result.pull_request["url"], "https://github.com/test/repo/pull/123")
    
    @patch('requests.post')
    def test_send_message_success(self, mock_post):
        """Test sending message to session"""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = self.client.send_message(self.test_session_id, "Follow-up message")
        
        self.assertEqual(result, {"status": "ok"})
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("message", call_args[1]["json"])
        self.assertEqual(call_args[1]["json"]["message"], "Follow-up message")
    
    @patch('requests.get')
    def test_list_sessions_success(self, mock_get):
        """Test listing all sessions"""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"session_id": "session1", "title": "Session 1"},
            {"session_id": "session2", "title": "Session 2"}
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = self.client.list_sessions()
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["session_id"], "session1")
        self.assertEqual(result[1]["session_id"], "session2")
    
    @patch('requests.get')
    @patch('time.sleep')
    def test_wait_for_completion_finished(self, mock_sleep, mock_get):
        """Test waiting for session to finish"""
        responses = [
            {"session_id": self.test_session_id, "status": "running", "status_enum": "working",
             "created_at": "2024-01-01T00:00:00.000000+00:00", "updated_at": "2024-01-01T00:01:00.000000+00:00",
             "title": "Test", "messages": []},
            {"session_id": self.test_session_id, "status": "running", "status_enum": "working",
             "created_at": "2024-01-01T00:00:00.000000+00:00", "updated_at": "2024-01-01T00:02:00.000000+00:00",
             "title": "Test", "messages": []},
            {"session_id": self.test_session_id, "status": "finished", "status_enum": "finished",
             "created_at": "2024-01-01T00:00:00.000000+00:00", "updated_at": "2024-01-01T00:03:00.000000+00:00",
             "title": "Test", "messages": [], "structured_output": {"result": "success"}}
        ]
        
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = responses
        mock_get.return_value = mock_response
        
        result = self.client.wait_for_completion(
            self.test_session_id,
            poll_interval=1,
            verbose=False
        )
        
        self.assertEqual(result.status_enum, "finished")
        self.assertEqual(result.structured_output, {"result": "success"})
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
    
    @patch('requests.get')
    @patch('time.sleep')
    def test_wait_for_completion_blocked(self, mock_sleep, mock_get):
        """Test waiting for session that gets blocked"""
        responses = [
            {"session_id": self.test_session_id, "status": "running", "status_enum": "working",
             "created_at": "2024-01-01T00:00:00.000000+00:00", "updated_at": "2024-01-01T00:01:00.000000+00:00",
             "title": "Test", "messages": []},
            {"session_id": self.test_session_id, "status": "blocked", "status_enum": "blocked",
             "created_at": "2024-01-01T00:00:00.000000+00:00", "updated_at": "2024-01-01T00:02:00.000000+00:00",
             "title": "Test", "messages": []}
        ]
        
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = responses
        mock_get.return_value = mock_response
        
        result = self.client.wait_for_completion(
            self.test_session_id,
            poll_interval=1,
            verbose=False
        )
        
        self.assertEqual(result.status_enum, "blocked")
        self.assertEqual(mock_get.call_count, 2)
    
    @patch('requests.get')
    @patch('time.sleep')
    @patch('time.time')
    def test_wait_for_completion_timeout(self, mock_time, mock_sleep, mock_get):
        """Test timeout when waiting for completion"""
        mock_time.side_effect = [0, 5, 10, 15, 20, 25]
        
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "session_id": self.test_session_id,
            "status": "running",
            "status_enum": "working",
            "created_at": "2024-01-01T00:00:00.000000+00:00",
            "updated_at": "2024-01-01T00:01:00.000000+00:00",
            "title": "Test",
            "messages": []
        }
        mock_get.return_value = mock_response
        
        with self.assertRaises(TimeoutError) as context:
            self.client.wait_for_completion(
                self.test_session_id,
                poll_interval=1,
                timeout=10,
                verbose=False
            )
        
        self.assertIn("did not complete within 10 seconds", str(context.exception))
    
    @patch('requests.get')
    def test_get_session_messages(self, mock_get):
        """Test retrieving session messages"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "session_id": self.test_session_id,
            "status": "finished",
            "status_enum": "finished",
            "created_at": "2024-01-01T00:00:00.000000+00:00",
            "updated_at": "2024-01-01T00:03:00.000000+00:00",
            "title": "Test",
            "messages": [
                {"type": "initial_user_message", "message": "Test prompt"},
                {"type": "devin_message", "message": "Working on it"},
                {"type": "devin_message", "message": "Done!"}
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        messages = self.client.get_session_messages(self.test_session_id)
        
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["type"], "initial_user_message")
        self.assertEqual(messages[2]["message"], "Done!")
    
    @patch('requests.get')
    def test_get_session_output(self, mock_get):
        """Test retrieving structured output"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "session_id": self.test_session_id,
            "status": "finished",
            "status_enum": "finished",
            "created_at": "2024-01-01T00:00:00.000000+00:00",
            "updated_at": "2024-01-01T00:03:00.000000+00:00",
            "title": "Test",
            "structured_output": {
                "files_modified": 3,
                "tests_passed": True,
                "result": "success"
            },
            "messages": []
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        output = self.client.get_session_output(self.test_session_id)
        
        self.assertIsNotNone(output)
        self.assertEqual(output["files_modified"], 3)
        self.assertTrue(output["tests_passed"])
        self.assertEqual(output["result"], "success")
    
    @patch('requests.get')
    def test_get_session_output_none(self, mock_get):
        """Test retrieving output when none exists"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "session_id": self.test_session_id,
            "status": "finished",
            "status_enum": "finished",
            "created_at": "2024-01-01T00:00:00.000000+00:00",
            "updated_at": "2024-01-01T00:03:00.000000+00:00",
            "title": "Test",
            "structured_output": None,
            "messages": []
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        output = self.client.get_session_output(self.test_session_id)
        
        self.assertIsNone(output)


class TestSessionStatus(unittest.TestCase):
    """Test SessionStatus enum"""
    
    def test_status_values(self):
        """Test that all expected status values exist"""
        self.assertEqual(SessionStatus.WORKING.value, "working")
        self.assertEqual(SessionStatus.BLOCKED.value, "blocked")
        self.assertEqual(SessionStatus.FINISHED.value, "finished")
        self.assertEqual(SessionStatus.EXPIRED.value, "expired")


class TestDataClasses(unittest.TestCase):
    """Test data classes"""
    
    def test_session_response(self):
        """Test SessionResponse dataclass"""
        response = SessionResponse(
            session_id="test-123",
            url="https://app.devin.ai/sessions/test-123",
            is_new_session=True
        )
        
        self.assertEqual(response.session_id, "test-123")
        self.assertEqual(response.url, "https://app.devin.ai/sessions/test-123")
        self.assertTrue(response.is_new_session)
    
    def test_session_details(self):
        """Test SessionDetails dataclass"""
        details = SessionDetails(
            session_id="test-123",
            status="finished",
            status_enum="finished",
            title="Test Session",
            created_at="2024-01-01T00:00:00.000000+00:00",
            updated_at="2024-01-01T00:03:00.000000+00:00",
            snapshot_id=None,
            playbook_id=None,
            tags=["test"],
            pull_request={"url": "https://github.com/test/repo/pull/1"},
            structured_output={"result": "success"},
            messages=[]
        )
        
        self.assertEqual(details.session_id, "test-123")
        self.assertEqual(details.status_enum, "finished")
        self.assertEqual(details.tags, ["test"])
        self.assertIsNotNone(details.pull_request)
        self.assertEqual(details.structured_output["result"], "success")


if __name__ == '__main__':
    unittest.main()
