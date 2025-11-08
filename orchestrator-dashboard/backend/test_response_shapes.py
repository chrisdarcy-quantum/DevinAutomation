"""
Tests to lock the response shapes for list and detail endpoints.
This prevents regressions where the frontend expects certain fields.
"""
import unittest
from fastapi.testclient import TestClient
from app import app, Base, engine

class TestResponseShapes(unittest.TestCase):
    """Test that API response shapes match frontend expectations."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test client."""
        cls.client = TestClient(app)
    
    def setUp(self):
        """Create tables and test data before each test."""
        Base.metadata.create_all(bind=engine)
        
        import time
        time.sleep(15)  # Wait for rate limit window to reset (5 per minute = 12 second window)
        
        payload = {
            "flag_key": "test_flag",
            "repositories": ["https://github.com/test/repo"],
            "feature_flag_provider": "TestProvider",
            "created_by": "test@example.com"
        }
        response = self.client.post("/api/removals", json=payload)
        self.assertEqual(response.status_code, 201)  # POST returns 201 Created
        self.test_request_id = response.json()["id"]
    
    def tearDown(self):
        """Drop all tables after each test."""
        Base.metadata.drop_all(bind=engine)
    
    def test_list_endpoint_response_shape(self):
        """Test that GET /api/removals returns correct shape for list items."""
        response = self.client.get("/api/removals")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        self.assertIn("results", data)
        self.assertIn("total", data)
        self.assertIn("limit", data)
        self.assertIn("offset", data)
        
        self.assertIsInstance(data["results"], list)
        
        if len(data["results"]) > 0:
            item = data["results"][0]
            
            required_fields = [
                "id", "flag_key", "repositories", "feature_flag_provider",
                "status", "created_by", "created_at", "updated_at"
            ]
            for field in required_fields:
                self.assertIn(field, item, f"Missing required field: {field}")
            
            self.assertIn("session_count", item, "List items must have session_count")
            self.assertIn("completed_sessions", item, "List items must have completed_sessions")
            self.assertIn("failed_sessions", item, "List items must have failed_sessions")
            
            self.assertNotIn("sessions", item, "List items should NOT include sessions array")
            
            self.assertIsInstance(item["repositories"], list, "repositories must be an array")
            
            self.assertIsInstance(item["session_count"], int)
            self.assertIsInstance(item["completed_sessions"], int)
            self.assertIsInstance(item["failed_sessions"], int)
    
    def test_detail_endpoint_response_shape(self):
        """Test that GET /api/removals/{id} returns correct shape with sessions."""
        response = self.client.get(f"/api/removals/{self.test_request_id}")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        required_fields = [
            "id", "flag_key", "repositories", "feature_flag_provider",
            "status", "created_by", "created_at", "updated_at",
            "error_message", "total_acu_consumed"
        ]
        for field in required_fields:
            self.assertIn(field, data, f"Missing required field: {field}")
        
        self.assertIn("sessions", data, "Detail endpoint must include sessions array")
        self.assertIsInstance(data["sessions"], list, "sessions must be an array")
        
        if len(data["sessions"]) > 0:
            session = data["sessions"][0]
            
            session_fields = [
                "id", "repository", "devin_session_id", "devin_session_url",
                "status", "pr_url", "structured_output", "started_at",
                "completed_at", "error_message", "acu_consumed"
            ]
            for field in session_fields:
                self.assertIn(field, session, f"Missing session field: {field}")
            
            self.assertIn("repository", session)
            self.assertNotIn("repository_url", session)
    
    def test_create_endpoint_response_shape(self):
        """Test that POST /api/removals returns correct shape with sessions."""
        payload = {
            "flag_key": "new_test_flag",
            "repositories": ["https://github.com/test/repo2"],
            "feature_flag_provider": "TestProvider",
            "created_by": "test@example.com"
        }
        
        response = self.client.post("/api/removals", json=payload)
        self.assertEqual(response.status_code, 201)  # POST returns 201 Created
        
        data = response.json()
        
        required_fields = [
            "id", "flag_key", "repositories", "feature_flag_provider",
            "status", "created_by", "created_at", "updated_at",
            "error_message", "total_acu_consumed"
        ]
        for field in required_fields:
            self.assertIn(field, data, f"Missing required field: {field}")
        
        self.assertIn("sessions", data, "Create endpoint must include sessions array")
        self.assertIsInstance(data["sessions"], list, "sessions must be an array")
        
        self.assertEqual(len(data["sessions"]), len(payload["repositories"]))
        
        if len(data["sessions"]) > 0:
            session = data["sessions"][0]
            
            self.assertIn("repository", session)
            self.assertNotIn("repository_url", session)
            
            self.assertEqual(session["repository"], payload["repositories"][0])
    
    def test_repositories_always_array(self):
        """Test that repositories field is always an array in all endpoints."""
        response = self.client.get("/api/removals")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        if len(data["results"]) > 0:
            for item in data["results"]:
                self.assertIsInstance(item["repositories"], list)
        
        response = self.client.get(f"/api/removals/{self.test_request_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data["repositories"], list)
    
    def test_session_counts_match_actual_sessions(self):
        """Test that session_count fields match actual session counts."""
        response = self.client.get("/api/removals")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        if len(data["results"]) > 0:
            item = data["results"][0]
            
            detail_response = self.client.get(f"/api/removals/{item['id']}")
            detail_data = detail_response.json()
            
            self.assertEqual(item["session_count"], len(detail_data["sessions"]))
            
            completed = sum(1 for s in detail_data["sessions"] if s["status"] == "finished")
            failed = sum(1 for s in detail_data["sessions"] if s["status"] == "failed")
            
            self.assertEqual(item["completed_sessions"], completed)
            self.assertEqual(item["failed_sessions"], failed)

if __name__ == '__main__':
    unittest.main()
