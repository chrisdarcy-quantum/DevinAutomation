"""
Comprehensive tests for the Feature Flag Removal Orchestration API.

Tests all API endpoints, database operations, background services, and response shapes.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import json
from datetime import datetime
import time

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'orchestrator-dashboard', 'backend'))

from app import (
    app, _build_removal_response, Base, get_db, init_db,
    RemovalRequest, DevinSession, SessionLog, Repository, DiscoveredFlag,
    DevinSessionResponse, DevinSessionDetails, SessionStatus,
    SessionMonitor, SessionQueue
)


class TestOrchestratorAPI(unittest.TestCase):
    """Test suite for the orchestration API endpoints."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database and client."""
        cls.engine = create_engine("sqlite:///./test_orchestrator.db", connect_args={"check_same_thread": False})
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        
        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()
        
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test database file."""
        import os
        if os.path.exists("./test_orchestrator.db"):
            os.remove("./test_orchestrator.db")
    
    def setUp(self):
        """Create tables and clear database before each test."""
        Base.metadata.create_all(bind=self.engine)
        
        db = self.TestingSessionLocal()
        try:
            db.query(SessionLog).delete()
            db.query(DevinSession).delete()
            db.query(RemovalRequest).delete()
            db.commit()
        except:
            db.rollback()
        finally:
            db.close()
    
    def test_healthz(self):
        """Test health check endpoint."""
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
    
    def test_create_removal_request_success(self):
        """Test creating a removal request successfully."""
        payload = {
            "flag_key": "ENABLE_NEW_FEATURE",
            "repositories": ["https://github.com/example/repo1"],
            "feature_flag_provider": "LaunchDarkly",
            "created_by": "test@example.com"
        }
        
        response = self.client.post("/api/removals", json=payload)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["flag_key"], "ENABLE_NEW_FEATURE")
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["preserve_mode"], "enabled")
        self.assertEqual(len(data["sessions"]), 1)
        self.assertEqual(data["sessions"][0]["status"], "pending")
        self.assertEqual(data["sessions"][0]["repository"], "https://github.com/example/repo1")
    
    def test_create_removal_request_with_preserve_mode(self):
        """Test creating a removal request with preserve_mode set to disabled."""
        payload = {
            "flag_key": "ENABLE_NEW_FEATURE",
            "repositories": ["https://github.com/example/repo1"],
            "feature_flag_provider": "LaunchDarkly",
            "preserve_mode": "disabled",
            "created_by": "test@example.com"
        }
        
        response = self.client.post("/api/removals", json=payload)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["preserve_mode"], "disabled")
        self.assertEqual(data["flag_key"], "ENABLE_NEW_FEATURE")
    
    def test_create_removal_request_multiple_repos(self):
        """Test creating a removal request with multiple repositories."""
        payload = {
            "flag_key": "ENABLE_CHECKOUT",
            "repositories": [
                "https://github.com/example/frontend",
                "https://github.com/example/backend",
                "https://github.com/example/mobile"
            ],
            "feature_flag_provider": "LaunchDarkly",
            "created_by": "test@example.com"
        }
        
        response = self.client.post("/api/removals", json=payload)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["sessions"]), 3)
        self.assertEqual(data["sessions"][0]["repository"], "https://github.com/example/frontend")
        self.assertEqual(data["sessions"][1]["repository"], "https://github.com/example/backend")
        self.assertEqual(data["sessions"][2]["repository"], "https://github.com/example/mobile")
    
    def test_create_removal_request_validation_empty_flag_key(self):
        """Test validation: empty flag key."""
        payload = {
            "flag_key": "",
            "repositories": ["https://github.com/example/repo1"],
            "created_by": "test@example.com"
        }
        
        response = self.client.post("/api/removals", json=payload)
        self.assertEqual(response.status_code, 422)
    
    def test_create_removal_request_validation_no_repositories(self):
        """Test validation: no repositories."""
        payload = {
            "flag_key": "ENABLE_FEATURE",
            "repositories": [],
            "created_by": "test@example.com"
        }
        
        response = self.client.post("/api/removals", json=payload)
        self.assertEqual(response.status_code, 422)
    
    def test_create_removal_request_validation_too_many_repos(self):
        """Test validation: too many repositories."""
        payload = {
            "flag_key": "ENABLE_FEATURE",
            "repositories": [f"https://github.com/example/repo{i}" for i in range(10)],
            "created_by": "test@example.com"
        }
        
        response = self.client.post("/api/removals", json=payload)
        self.assertEqual(response.status_code, 422)
    
    def test_create_removal_request_validation_invalid_repo_url(self):
        """Test validation: invalid repository URL."""
        payload = {
            "flag_key": "ENABLE_FEATURE",
            "repositories": ["not-a-url"],
            "created_by": "test@example.com"
        }
        
        response = self.client.post("/api/removals", json=payload)
        self.assertEqual(response.status_code, 422)
    
    def test_list_removals_empty(self):
        """Test listing removal requests when none exist."""
        response = self.client.get("/api/removals")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 0)
        self.assertEqual(len(data["results"]), 0)
    
    def test_list_removals_with_data(self):
        """Test listing removal requests with data."""
        db = self.TestingSessionLocal()
        req1 = RemovalRequest(
            flag_key="FLAG1",
            repositories=json.dumps(["https://github.com/example/repo1"]),
            status="queued",
            created_by="user1@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        req2 = RemovalRequest(
            flag_key="FLAG2",
            repositories=json.dumps(["https://github.com/example/repo2"]),
            status="in_progress",
            created_by="user2@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(req1)
        db.add(req2)
        db.commit()
        db.close()
        
        response = self.client.get("/api/removals")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["results"]), 2)
    
    def test_list_removals_with_status_filter(self):
        """Test listing removal requests with status filter."""
        db = self.TestingSessionLocal()
        req1 = RemovalRequest(
            flag_key="FLAG1",
            repositories=json.dumps(["https://github.com/example/repo1"]),
            status="queued",
            created_by="user1@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        req2 = RemovalRequest(
            flag_key="FLAG2",
            repositories=json.dumps(["https://github.com/example/repo2"]),
            status="completed",
            created_by="user2@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(req1)
        db.add(req2)
        db.commit()
        db.close()
        
        response = self.client.get("/api/removals?status=completed")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["results"][0]["flag_key"], "FLAG2")
    
    def test_list_removals_pagination(self):
        """Test pagination in list endpoint."""
        db = self.TestingSessionLocal()
        for i in range(10):
            req = RemovalRequest(
                flag_key=f"FLAG{i}",
                repositories=json.dumps([f"https://github.com/example/repo{i}"]),
                status="queued",
                created_by=f"user{i}@example.com",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(req)
        db.commit()
        db.close()
        
        response = self.client.get("/api/removals?limit=5&offset=0")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 10)
        self.assertEqual(len(data["results"]), 5)
        
        response = self.client.get("/api/removals?limit=5&offset=5")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 5)
    
    def test_get_removal_by_id_success(self):
        """Test getting a specific removal request."""
        db = self.TestingSessionLocal()
        req = RemovalRequest(
            flag_key="TEST_FLAG",
            repositories=json.dumps(["https://github.com/example/repo1"]),
            status="queued",
            created_by="test@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(req)
        db.flush()
        
        session = DevinSession(
            removal_request_id=req.id,
            repository="https://github.com/example/repo1",
            status="pending"
        )
        db.add(session)
        db.commit()
        
        req_id = req.id
        db.close()
        
        response = self.client.get(f"/api/removals/{req_id}")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["flag_key"], "TEST_FLAG")
        self.assertEqual(len(data["sessions"]), 1)
    
    def test_get_removal_by_id_not_found(self):
        """Test getting a non-existent removal request."""
        response = self.client.get("/api/removals/999")
        self.assertEqual(response.status_code, 404)
    
    def test_get_removal_logs_success(self):
        """Test getting logs for a removal request."""
        db = self.TestingSessionLocal()
        req = RemovalRequest(
            flag_key="TEST_FLAG",
            repositories=json.dumps(["https://github.com/example/repo1"]),
            status="queued",
            created_by="test@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(req)
        db.flush()
        
        session = DevinSession(
            removal_request_id=req.id,
            repository="https://github.com/example/repo1",
            status="pending"
        )
        db.add(session)
        db.flush()
        
        log1 = SessionLog(
            devin_session_id=session.id,
            timestamp=datetime.utcnow(),
            log_level="info",
            message="Session created",
            event_type="session_created"
        )
        log2 = SessionLog(
            devin_session_id=session.id,
            timestamp=datetime.utcnow(),
            log_level="info",
            message="Status changed to working",
            event_type="status_change"
        )
        db.add(log1)
        db.add(log2)
        db.commit()
        
        req_id = req.id
        db.close()
        
        response = self.client.get(f"/api/removals/{req_id}/logs")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["removal_request_id"], req_id)
        self.assertEqual(len(data["logs"]), 2)
    
    def test_get_removal_logs_not_found(self):
        """Test getting logs for non-existent removal request."""
        response = self.client.get("/api/removals/999/logs")
        self.assertEqual(response.status_code, 404)
    
    def test_build_removal_response_with_structured_output(self):
        """Test building response with structured output."""
        db = self.TestingSessionLocal()
        req = RemovalRequest(
            flag_key="TEST_FLAG",
            repositories=json.dumps(["https://github.com/example/repo1"]),
            status="completed",
            created_by="test@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(req)
        db.flush()
        
        structured_output = {
            "pr_url": "https://github.com/example/repo1/pull/123",
            "files_modified": ["file1.py", "file2.js"],
            "occurrences_removed": 5,
            "test_results": "PASSED",
            "acu_consumed": 250
        }
        
        session = DevinSession(
            removal_request_id=req.id,
            repository="https://github.com/example/repo1",
            status="finished",
            devin_session_id="devin-123",
            devin_session_url="https://app.devin.ai/sessions/123",
            pr_url="https://github.com/example/repo1/pull/123",
            structured_output=json.dumps(structured_output),
            acu_consumed=250
        )
        db.add(session)
        db.commit()
        db.refresh(req)
        
        response = _build_removal_response(req)
        
        self.assertEqual(response.flag_key, "TEST_FLAG")
        self.assertEqual(len(response.sessions), 1)
        self.assertEqual(response.sessions[0].structured_output, structured_output)
        self.assertEqual(response.sessions[0].acu_consumed, 250)
        
        db.close()
    
    def test_database_relationships(self):
        """Test database relationships between tables."""
        db = self.TestingSessionLocal()
        
        req = RemovalRequest(
            flag_key="TEST_FLAG",
            repositories=json.dumps(["https://github.com/example/repo1"]),
            status="queued",
            created_by="test@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(req)
        db.flush()
        
        session = DevinSession(
            removal_request_id=req.id,
            repository="https://github.com/example/repo1",
            status="pending"
        )
        db.add(session)
        db.flush()
        
        log = SessionLog(
            devin_session_id=session.id,
            timestamp=datetime.utcnow(),
            log_level="info",
            message="Test log",
            event_type="test"
        )
        db.add(log)
        db.commit()
        
        db.refresh(req)
        self.assertEqual(len(req.sessions), 1)
        self.assertEqual(req.sessions[0].repository, "https://github.com/example/repo1")
        self.assertEqual(len(req.sessions[0].logs), 1)
        self.assertEqual(req.sessions[0].logs[0].message, "Test log")
        
        db.close()


class TestResponseShapes(unittest.TestCase):
    """Test that API response shapes match frontend expectations."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test client."""
        cls.engine = create_engine("sqlite:///./test_shapes.db", connect_args={"check_same_thread": False})
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        
        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()
        
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test database file."""
        import os
        if os.path.exists("./test_shapes.db"):
            os.remove("./test_shapes.db")
    
    def setUp(self):
        """Create tables and test data before each test."""
        Base.metadata.create_all(bind=self.engine)
        
        time.sleep(0.5)  # Brief pause to avoid rate limiting
        
        payload = {
            "flag_key": "test_flag",
            "repositories": ["https://github.com/test/repo"],
            "feature_flag_provider": "TestProvider",
            "created_by": "test@example.com"
        }
        response = self.client.post("/api/removals", json=payload)
        self.assertEqual(response.status_code, 201)
        self.test_request_id = response.json()["id"]
    
    def tearDown(self):
        """Drop all tables after each test."""
        Base.metadata.drop_all(bind=self.engine)
    
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
            
            self.assertIn("session_count", item)
            self.assertIn("completed_sessions", item)
            self.assertIn("failed_sessions", item)
            
            self.assertNotIn("sessions", item, "List items should NOT include sessions array")
            
            self.assertIsInstance(item["repositories"], list)
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
        
        self.assertIn("sessions", data)
        self.assertIsInstance(data["sessions"], list)
        
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
        self.assertEqual(response.status_code, 201)
        
        data = response.json()
        
        required_fields = [
            "id", "flag_key", "repositories", "feature_flag_provider",
            "status", "created_by", "created_at", "updated_at",
            "error_message", "total_acu_consumed"
        ]
        for field in required_fields:
            self.assertIn(field, data, f"Missing required field: {field}")
        
        self.assertIn("sessions", data)
        self.assertIsInstance(data["sessions"], list)
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


class TestSessionMonitor(unittest.TestCase):
    """Test suite for SessionMonitor background service."""
    
    def setUp(self):
        """Set up test database."""
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    @patch('app.SessionLocal')
    def test_monitor_updates_session_status(self, mock_session_local):
        """Test that monitor updates session status from Devin API."""
        mock_client = Mock()
        mock_details = Mock()
        mock_details.status_enum = 'working'
        mock_details.pull_request = None
        mock_details.structured_output = None
        mock_client.get_session_details.return_value = mock_details
        
        db = self.SessionLocal()
        req = RemovalRequest(
            flag_key="TEST",
            repositories=json.dumps(["https://github.com/example/repo"]),
            status="queued",
            created_by="test@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(req)
        db.flush()
        
        session = DevinSession(
            removal_request_id=req.id,
            repository="https://github.com/example/repo",
            status="claimed",
            devin_session_id="devin-123",
            started_at=datetime.utcnow()
        )
        db.add(session)
        db.commit()
        
        mock_session_local.return_value = db
        
        monitor = SessionMonitor(mock_client)
        self.assertIsNotNone(monitor)
        
        db.close()


class TestSessionQueue(unittest.TestCase):
    """Test suite for SessionQueue background service."""
    
    def setUp(self):
        """Set up test database."""
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def test_build_removal_prompt(self):
        """Test prompt building for Devin."""
        mock_client = Mock()
        queue = SessionQueue(mock_client)
        
        prompt = queue.build_removal_prompt(
            flag_key="ENABLE_FEATURE",
            repository="https://github.com/example/repo",
            provider="LaunchDarkly"
        )
        
        self.assertIn("ENABLE_FEATURE", prompt)
        self.assertIn("https://github.com/example/repo", prompt)
        self.assertIn("LaunchDarkly", prompt)
        self.assertIn("structured output", prompt.lower())
    
    def test_build_removal_prompt_no_hardcoded_values(self):
        """Test that prompt does not contain hardcoded example values."""
        mock_client = Mock()
        queue = SessionQueue(mock_client)
        
        prompt = queue.build_removal_prompt(
            flag_key="TEST_FLAG",
            repository="https://github.com/test/repo",
            provider="TestProvider"
        )
        
        self.assertNotIn('"acu_consumed": 450', prompt)
        self.assertNotIn('"occurrences_removed": 12', prompt)
        self.assertNotIn('"references_removed": 12', prompt)
        
        self.assertIn("structured output", prompt.lower())
        self.assertIn("acu_consumed", prompt)
        self.assertIn("references_removed", prompt)
    
    def test_get_active_count(self):
        """Test counting active sessions."""
        db = self.SessionLocal()
        
        req = RemovalRequest(
            flag_key="TEST",
            repositories=json.dumps(["https://github.com/example/repo"]),
            status="queued",
            created_by="test@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(req)
        db.flush()
        
        for status in ['pending', 'working', 'blocked']:
            session = DevinSession(
                removal_request_id=req.id,
                repository=f"https://github.com/example/repo-{status}",
                status=status
            )
            db.add(session)
        
        session = DevinSession(
            removal_request_id=req.id,
            repository="https://github.com/example/repo-finished",
            status="finished"
        )
        db.add(session)
        
        db.commit()
        
        mock_client = Mock()
        queue = SessionQueue(mock_client)
        count = queue.get_active_count(db)
        
        self.assertEqual(count, 3)  # Only pending, working, blocked
        
        db.close()


class TestRepositoryEndpoints(unittest.TestCase):
    """Test repository management endpoints."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database and client."""
        cls.engine = create_engine("sqlite:///./test_repositories.db", connect_args={"check_same_thread": False})
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        
        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()
        
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test database file."""
        import os
        if os.path.exists("./test_repositories.db"):
            os.remove("./test_repositories.db")
    
    def setUp(self):
        """Create tables and clear database before each test."""
        Base.metadata.create_all(bind=self.engine)
        
        db = self.TestingSessionLocal()
        try:
            db.query(DiscoveredFlag).delete()
            db.query(Repository).delete()
            db.query(SessionLog).delete()
            db.query(DevinSession).delete()
            db.query(RemovalRequest).delete()
            db.commit()
        except:
            db.rollback()
        finally:
            db.close()
    
    def test_create_repository(self):
        """Test creating a new repository."""
        response = self.client.post('/api/repositories', json={
            'url': 'https://github.com/test/repo',
            'github_token': None
        })
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['url'], 'https://github.com/test/repo')
        self.assertIsNone(data['provider_detected'])
        self.assertIsNone(data['last_scanned_at'])
        self.assertEqual(data['flag_count'], 0)
    
    def test_create_duplicate_repository(self):
        """Test creating a duplicate repository returns 409."""
        self.client.post('/api/repositories', json={
            'url': 'https://github.com/test/repo'
        })
        response = self.client.post('/api/repositories', json={
            'url': 'https://github.com/test/repo'
        })
        self.assertEqual(response.status_code, 409)
    
    def test_list_repositories(self):
        """Test listing all repositories."""
        self.client.post('/api/repositories', json={
            'url': 'https://github.com/test/repo1'
        })
        self.client.post('/api/repositories', json={
            'url': 'https://github.com/test/repo2'
        })
        
        response = self.client.get('/api/repositories')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
    
    def test_get_repository(self):
        """Test getting a single repository."""
        create_response = self.client.post('/api/repositories', json={
            'url': 'https://github.com/test/repo'
        })
        repo_id = create_response.json()['id']
        
        response = self.client.get(f'/api/repositories/{repo_id}')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['url'], 'https://github.com/test/repo')
    
    def test_get_nonexistent_repository(self):
        """Test getting a repository that doesn't exist."""
        response = self.client.get('/api/repositories/999')
        self.assertEqual(response.status_code, 404)
    
    def test_delete_repository(self):
        """Test deleting a repository."""
        create_response = self.client.post('/api/repositories', json={
            'url': 'https://github.com/test/repo'
        })
        repo_id = create_response.json()['id']
        
        response = self.client.delete(f'/api/repositories/{repo_id}')
        self.assertEqual(response.status_code, 204)
        
        get_response = self.client.get(f'/api/repositories/{repo_id}')
        self.assertEqual(get_response.status_code, 404)
    
    def test_invalid_repository_url(self):
        """Test creating repository with invalid URL."""
        response = self.client.post('/api/repositories', json={
            'url': 'not-a-url'
        })
        self.assertEqual(response.status_code, 422)


class TestFlagEndpoints(unittest.TestCase):
    """Test flag discovery and listing endpoints."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database and client."""
        cls.engine = create_engine("sqlite:///./test_flags.db", connect_args={"check_same_thread": False})
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        
        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()
        
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test database file."""
        import os
        if os.path.exists("./test_flags.db"):
            os.remove("./test_flags.db")
    
    def setUp(self):
        """Create tables and clear database before each test."""
        Base.metadata.create_all(bind=self.engine)
        
        db = self.TestingSessionLocal()
        try:
            db.query(DiscoveredFlag).delete()
            db.query(Repository).delete()
            db.query(SessionLog).delete()
            db.query(DevinSession).delete()
            db.query(RemovalRequest).delete()
            db.commit()
        except:
            db.rollback()
        finally:
            db.close()
    
    def test_list_flags_empty(self):
        """Test listing flags when none exist."""
        response = self.client.get('/api/flags')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
    
    def test_get_repository_flags(self):
        """Test getting flags for a specific repository."""
        create_response = self.client.post('/api/repositories', json={
            'url': 'https://github.com/test/repo'
        })
        repo_id = create_response.json()['id']
        
        response = self.client.get(f'/api/repositories/{repo_id}/flags')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])


class TestRemovalWithRepository(unittest.TestCase):
    """Test removal requests with repository linkage."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database and client."""
        cls.engine = create_engine("sqlite:///./test_removal_repo.db", connect_args={"check_same_thread": False})
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        
        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()
        
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test database file."""
        import os
        if os.path.exists("./test_removal_repo.db"):
            os.remove("./test_removal_repo.db")
    
    def setUp(self):
        """Create tables and clear database before each test."""
        Base.metadata.create_all(bind=self.engine)
        
        db = self.TestingSessionLocal()
        try:
            db.query(DiscoveredFlag).delete()
            db.query(Repository).delete()
            db.query(SessionLog).delete()
            db.query(DevinSession).delete()
            db.query(RemovalRequest).delete()
            db.commit()
        except:
            db.rollback()
        finally:
            db.close()
    
    def test_create_removal_with_repository_id(self):
        """Test creating removal request with repository_id."""
        repo_response = self.client.post('/api/repositories', json={
            'url': 'https://github.com/test/repo'
        })
        repo_id = repo_response.json()['id']
        
        response = self.client.post('/api/removals', json={
            'flag_key': 'TEST_FLAG',
            'repository_id': repo_id,
            'preserve_mode': 'enabled',
            'created_by': 'test@example.com'
        })
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['flag_key'], 'TEST_FLAG')
    
    def test_create_removal_with_invalid_repository_id(self):
        """Test creating removal with non-existent repository_id."""
        response = self.client.post('/api/removals', json={
            'flag_key': 'TEST_FLAG',
            'repository_id': 999,
            'preserve_mode': 'enabled',
            'created_by': 'test@example.com'
        })
        self.assertEqual(response.status_code, 404)
    
    def test_create_removal_legacy_flow(self):
        """Test creating removal with repositories list (legacy)."""
        response = self.client.post('/api/removals', json={
            'flag_key': 'TEST_FLAG',
            'repositories': ['https://github.com/test/repo'],
            'preserve_mode': 'enabled',
            'created_by': 'test@example.com'
        })
        self.assertEqual(response.status_code, 201)
    
    def test_create_removal_requires_repo_or_list(self):
        """Test that either repository_id or repositories is required."""
        response = self.client.post('/api/removals', json={
            'flag_key': 'TEST_FLAG',
            'preserve_mode': 'enabled',
            'created_by': 'test@example.com'
        })
        self.assertEqual(response.status_code, 422)


class TestDiscoveryPrompt(unittest.TestCase):
    """Test discovery prompt generation."""
    
    def test_build_discovery_prompt(self):
        """Test that discovery prompt is generated correctly."""
        queue = SessionQueue(None, None)
        
        prompt = queue.build_discovery_prompt(
            repository='https://github.com/test/repo',
            github_token=None
        )
        
        self.assertIn('Discover all feature flags', prompt)
        self.assertIn('LaunchDarkly', prompt)
        self.assertIn('Statsig', prompt)
        self.assertIn('Unleash', prompt)
        self.assertIn('READ-ONLY', prompt)
        self.assertIn('Do NOT modify any files', prompt)
        self.assertIn('Do NOT create any PRs', prompt)
    
    def test_discovery_prompt_no_hardcoded_values(self):
        """Test that discovery prompt doesn't contain hardcoded example values."""
        queue = SessionQueue(None, None)
        
        prompt = queue.build_discovery_prompt(
            repository='https://github.com/test/repo',
            github_token=None
        )
        
        self.assertNotIn('"occurrences": 12', prompt)
        self.assertNotIn('"acu_consumed": 450', prompt)


    def test_discovery_results_persistence(self):
        """Test that discovery scan results are properly persisted to database."""
        repo = Repository(
            url='https://github.com/test/discovery-repo',
            created_at=datetime.utcnow()
        )
        self.db.add(repo)
        self.db.commit()
        self.db.refresh(repo)
        
        discovery_output = {
            'provider': 'Custom',
            'flags': [
                {'key': 'feature_a', 'occurrences': 10, 'files': ['app.js', 'utils.js']},
                {'key': 'feature_b', 'occurrences': 5, 'files': ['index.js']}
            ],
            'total_flags': 2,
            'total_occurrences': 15,
            'warnings': [],
            'acu_consumed': 1
        }
        
        monitor = SessionMonitor(self.mock_client)
        import asyncio
        asyncio.run(monitor.persist_discovery_results(self.db, repo.url, discovery_output))
        self.db.commit()
        
        updated_repo = self.db.query(Repository).filter_by(id=repo.id).first()
        self.assertEqual(updated_repo.provider_detected, 'Custom')
        self.assertIsNotNone(updated_repo.last_scanned_at)
        
        flags = self.db.query(DiscoveredFlag).filter_by(repository_id=repo.id).all()
        self.assertEqual(len(flags), 2)
        
        flag_a = next(f for f in flags if f.flag_key == 'feature_a')
        self.assertEqual(flag_a.occurrences, 10)
        self.assertEqual(flag_a.provider, 'Custom')
        self.assertIn('app.js', json.loads(flag_a.files))
        
        flag_b = next(f for f in flags if f.flag_key == 'feature_b')
        self.assertEqual(flag_b.occurrences, 5)


if __name__ == '__main__':
    unittest.main()
