"""
Devin API Client - Phase 1 Implementation

This module provides a Python client for interacting with the Devin AI API.
It demonstrates the core capabilities needed for the Feature Flag Removal System:
- Creating Devin sessions
- Monitoring session status
- Retrieving session results

API Documentation: https://docs.devin.ai/api-reference/overview
"""

import os
import time
import json
from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from enum import Enum
import requests


class SessionStatus(Enum):
    """Devin session status values"""
    WORKING = "working"
    BLOCKED = "blocked"
    EXPIRED = "expired"
    FINISHED = "finished"
    SUSPEND_REQUESTED = "suspend_requested"
    SUSPEND_REQUESTED_FRONTEND = "suspend_requested_frontend"
    RESUME_REQUESTED = "resume_requested"
    RESUME_REQUESTED_FRONTEND = "resume_requested_frontend"
    RESUMED = "resumed"


@dataclass
class SessionResponse:
    """Response from creating a Devin session"""
    session_id: str
    url: str
    is_new_session: Optional[bool] = None


@dataclass
class SessionDetails:
    """Detailed information about a Devin session"""
    session_id: str
    status: str
    status_enum: Optional[str]
    title: Optional[str]
    created_at: str
    updated_at: str
    snapshot_id: Optional[str]
    playbook_id: Optional[str]
    tags: Optional[List[str]]
    pull_request: Optional[Dict[str, str]]
    structured_output: Optional[Dict[str, Any]]
    messages: Optional[List[Dict[str, Any]]]


class DevinAPIClient:
    """
    Client for interacting with the Devin AI API.
    
    This client provides methods to:
    - Create new Devin sessions
    - Monitor session status
    - Retrieve session results
    - Send messages to active sessions
    
    Usage:
        client = DevinAPIClient(api_key="your-api-key")
        session = client.create_session("Review PR #123")
        details = client.wait_for_completion(session.session_id)
    """
    
    BASE_URL = "https://api.devin.ai/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Devin API client.
        
        Args:
            api_key: Devin API key. If not provided, will look for DEVIN_API_KEY env var.
        
        Raises:
            ValueError: If no API key is provided or found in environment.
        """
        self.api_key = api_key or os.getenv("DEVIN_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key required. Provide via api_key parameter or DEVIN_API_KEY env var. "
                "Get your API key from https://app.devin.ai/settings/api-keys"
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def create_session(
        self,
        prompt: str,
        snapshot_id: Optional[str] = None,
        unlisted: Optional[bool] = None,
        idempotent: Optional[bool] = True,
        max_acu_limit: Optional[int] = None,
        secret_ids: Optional[List[str]] = None,
        knowledge_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        title: Optional[str] = None
    ) -> SessionResponse:
        """
        Create a new Devin session.
        
        Args:
            prompt: The task description for Devin
            snapshot_id: ID of a machine snapshot to use
            unlisted: Whether the session should be unlisted
            idempotent: Enable idempotent session creation (default: True)
            max_acu_limit: Maximum ACU limit for the session
            secret_ids: List of secret IDs to use (None = all, [] = none)
            knowledge_ids: List of knowledge IDs to use (None = all, [] = none)
            tags: List of tags to add to the session
            title: Custom title for the session
        
        Returns:
            SessionResponse with session_id and url
        
        Raises:
            requests.HTTPError: If the API request fails
        """
        payload = {"prompt": prompt}
        
        if snapshot_id is not None:
            payload["snapshot_id"] = snapshot_id
        if unlisted is not None:
            payload["unlisted"] = unlisted
        if idempotent is not None:
            payload["idempotent"] = idempotent
        if max_acu_limit is not None:
            payload["max_acu_limit"] = max_acu_limit
        if secret_ids is not None:
            payload["secret_ids"] = secret_ids
        if knowledge_ids is not None:
            payload["knowledge_ids"] = knowledge_ids
        if tags is not None:
            payload["tags"] = tags
        if title is not None:
            payload["title"] = title
        
        response = requests.post(
            f"{self.BASE_URL}/sessions",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        
        data = response.json()
        return SessionResponse(
            session_id=data["session_id"],
            url=data["url"],
            is_new_session=data.get("is_new_session")
        )
    
    def get_session_details(self, session_id: str) -> SessionDetails:
        """
        Retrieve detailed information about a session.
        
        Args:
            session_id: The session ID to query
        
        Returns:
            SessionDetails object with full session information
        
        Raises:
            requests.HTTPError: If the API request fails
        """
        response = requests.get(
            f"{self.BASE_URL}/sessions/{session_id}",
            headers=self.headers
        )
        response.raise_for_status()
        
        data = response.json()
        return SessionDetails(
            session_id=data["session_id"],
            status=data["status"],
            status_enum=data.get("status_enum"),
            title=data.get("title"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            snapshot_id=data.get("snapshot_id"),
            playbook_id=data.get("playbook_id"),
            tags=data.get("tags"),
            pull_request=data.get("pull_request"),
            structured_output=data.get("structured_output"),
            messages=data.get("messages")
        )
    
    def send_message(self, session_id: str, message: str) -> Dict[str, Any]:
        """
        Send a message to an active Devin session.
        
        Args:
            session_id: The session ID
            message: The message to send to Devin
        
        Returns:
            Response from the API
        
        Raises:
            requests.HTTPError: If the API request fails
        """
        response = requests.post(
            f"{self.BASE_URL}/sessions/{session_id}/messages",
            headers=self.headers,
            json={"message": message}
        )
        response.raise_for_status()
        return response.json()
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all sessions for the organization.
        
        Returns:
            List of session objects
        
        Raises:
            requests.HTTPError: If the API request fails
        """
        response = requests.get(
            f"{self.BASE_URL}/sessions",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
    
    def wait_for_completion(
        self,
        session_id: str,
        poll_interval: int = 5,
        timeout: Optional[int] = None,
        verbose: bool = True
    ) -> SessionDetails:
        """
        Wait for a session to complete (blocked, finished, or expired status).
        
        Args:
            session_id: The session ID to monitor
            poll_interval: Seconds between status checks (default: 5)
            timeout: Maximum seconds to wait (None = no timeout)
            verbose: Print status updates (default: True)
        
        Returns:
            Final SessionDetails when session completes
        
        Raises:
            TimeoutError: If timeout is reached
            requests.HTTPError: If the API request fails
        """
        start_time = time.time()
        
        while True:
            details = self.get_session_details(session_id)
            
            if verbose:
                elapsed = int(time.time() - start_time)
                print(f"[{elapsed}s] Status: {details.status_enum or details.status}")
            
            if details.status_enum in ["blocked", "finished", "expired"]:
                if verbose:
                    print(f"Session completed with status: {details.status_enum}")
                return details
            
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(
                    f"Session did not complete within {timeout} seconds. "
                    f"Last status: {details.status_enum}"
                )
            
            time.sleep(poll_interval)
    
    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages from a session.
        
        Args:
            session_id: The session ID
        
        Returns:
            List of message objects
        """
        details = self.get_session_details(session_id)
        return details.messages or []
    
    def get_session_output(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the structured output from a completed session.
        
        Args:
            session_id: The session ID
        
        Returns:
            Structured output dictionary, or None if not available
        """
        details = self.get_session_details(session_id)
        return details.structured_output


def main():
    """
    Example usage of the Devin API client.
    
    This demonstrates the complete workflow:
    1. Create a session
    2. Monitor its status
    3. Retrieve results
    """
    print("=" * 60)
    print("Devin API Client - Phase 1 Demo")
    print("=" * 60)
    print()
    
    api_key = os.getenv("DEVIN_API_KEY")
    if not api_key:
        print("ERROR: DEVIN_API_KEY environment variable not set")
        print("Get your API key from: https://app.devin.ai/settings/api-keys")
        print()
        print("Set it with: export DEVIN_API_KEY='your-key-here'")
        return
    
    try:
        client = DevinAPIClient(api_key=api_key)
        print("✓ API client initialized")
        print()
        
        print("Creating a test session...")
        session = client.create_session(
            prompt="Create a simple hello world Python script that prints 'Hello from Devin!'",
            title="Phase 1 API Test",
            tags=["api-test", "phase1"],
            idempotent=True
        )
        
        print(f"✓ Session created!")
        print(f"  Session ID: {session.session_id}")
        print(f"  URL: {session.url}")
        print(f"  Is New: {session.is_new_session}")
        print()
        
        print("Monitoring session status...")
        print("(This may take several minutes)")
        print()
        
        final_details = client.wait_for_completion(
            session.session_id,
            poll_interval=10,
            timeout=600,
            verbose=True
        )
        
        print()
        print("=" * 60)
        print("Session Complete!")
        print("=" * 60)
        print(f"Final Status: {final_details.status_enum}")
        print(f"Title: {final_details.title}")
        print(f"Created: {final_details.created_at}")
        print(f"Updated: {final_details.updated_at}")
        
        if final_details.pull_request:
            print(f"Pull Request: {final_details.pull_request.get('url')}")
        
        if final_details.structured_output:
            print()
            print("Structured Output:")
            print(json.dumps(final_details.structured_output, indent=2))
        
        if final_details.messages:
            print()
            print(f"Total Messages: {len(final_details.messages)}")
            print()
            print("Last 3 messages:")
            for msg in final_details.messages[-3:]:
                msg_type = msg.get("type", "unknown")
                content = msg.get("message", "")
                timestamp = msg.get("timestamp", "")
                print(f"  [{msg_type}] {timestamp}")
                print(f"    {content[:100]}...")
                print()
        
    except requests.HTTPError as e:
        print(f"API Error: {e}")
        print(f"Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
    except TimeoutError as e:
        print(f"Timeout: {e}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
