# Phase 1: Devin API Research - Findings and Documentation

## Overview

This document captures the findings from Phase 1 research into the Devin AI API capabilities. The goal was to understand what Devin can reliably do and validate the API workflow for creating sessions, monitoring status, and retrieving results.

## API Capabilities Discovered

### 1. Authentication
- **Method**: Bearer token authentication
- **API Key Location**: https://app.devin.ai/settings/api-keys
- **Header Format**: `Authorization: Bearer <token>`
- **Security**: API keys should never be shared in public repositories or client-side code

### 2. Session Creation
- **Endpoint**: `POST https://api.devin.ai/v1/sessions`
- **Required Parameters**:
  - `prompt` (string): The task description for Devin
- **Optional Parameters**:
  - `snapshot_id` (string): ID of a machine snapshot to use
  - `unlisted` (boolean): Whether the session should be unlisted
  - `idempotent` (boolean): Enable idempotent session creation (prevents duplicates)
  - `max_acu_limit` (integer): Maximum ACU limit for the session
  - `secret_ids` (array): List of secret IDs to use (null = all, [] = none)
  - `knowledge_ids` (array): List of knowledge IDs to use (null = all, [] = none)
  - `tags` (array): List of tags to add to the session
  - `title` (string): Custom title for the session
- **Response**:
  - `session_id` (string): Unique identifier for the session
  - `url` (string): URL to view the session in the web interface
  - `is_new_session` (boolean): Only present if idempotent=true

### 3. Session Monitoring
- **Endpoint**: `GET https://api.devin.ai/v1/sessions/{session_id}`
- **Polling Required**: Yes - the API does not provide webhooks or streaming
- **Recommended Poll Interval**: 5-10 seconds
- **Status Values**:
  - `working`: Devin is actively working on a task
  - `blocked`: Devin is waiting for user input or response
  - `expired`: Session has expired
  - `finished`: Session has completed
  - `suspend_requested`: Request to suspend the session
  - `suspend_requested_frontend`: Frontend-initiated suspend request
  - `resume_requested`: Request to resume the session
  - `resume_requested_frontend`: Frontend-initiated resume request
  - `resumed`: Session has been resumed

### 4. Result Retrieval
- **Session Details Include**:
  - `session_id`: Unique identifier
  - `status`: Current status string
  - `status_enum`: Enumerated status value
  - `title`: Session title
  - `created_at`: Creation timestamp (ISO 8601)
  - `updated_at`: Last update timestamp (ISO 8601)
  - `snapshot_id`: ID of machine snapshot used
  - `playbook_id`: ID of playbook used
  - `tags`: List of tags
  - `pull_request`: Object with PR URL if applicable
  - `structured_output`: Task-specific structured output
  - `messages`: Array of conversation messages

### 5. Message History
- **Message Types**:
  - `initial_user_message`: The original task prompt
  - `user_message`: Follow-up messages from user
  - `devin_message`: Responses from Devin
- **Message Fields**:
  - `type`: Message type
  - `event_id`: Unique event identifier
  - `message`: Message content
  - `timestamp`: ISO 8601 timestamp
  - `username`: User email (for user messages)
  - `origin`: Message origin (web, api, etc.)
  - `user_id`: User identifier

### 6. Additional Endpoints Available
- `POST /v1/sessions/{session_id}/messages`: Send message to active session
- `GET /v1/sessions`: List all sessions
- `POST /v1/attachments`: Upload files for Devin
- `GET /v1/attachments/{attachment_id}`: Download attachment files
- `PUT /v1/sessions/{session_id}/tags`: Update session tags
- Secrets management endpoints
- Knowledge management endpoints
- Playbooks management endpoints

## Optimal Session Configuration for Code Scanning

Based on the research, here are recommendations for code scanning tasks:

1. **Use Idempotent Sessions**: Set `idempotent=true` to prevent duplicate sessions if retrying
2. **Provide Clear Prompts**: Be specific about what to scan and what to look for
3. **Use Tags**: Tag sessions with relevant metadata (e.g., "feature-flag-scan", "repo-name")
4. **Set Titles**: Use descriptive titles for easy identification
5. **Leverage Knowledge**: Pass relevant knowledge_ids if you have documentation about the codebase
6. **Monitor Status**: Poll every 5-10 seconds to detect completion quickly
7. **Handle Blocked State**: Be prepared to send follow-up messages if Devin gets blocked

## Context Passing Strategy

To pass context (repos, credentials, flag keys) to Devin:

1. **Repository Access**: 
   - Devin can access GitHub repositories if properly authenticated
   - Use the secrets management API to provide GitHub tokens
   - Include repository URLs in the prompt

2. **Credentials**:
   - Use the secrets API to securely provide credentials
   - Pass `secret_ids` array when creating sessions
   - Never include credentials in prompts

3. **Flag Keys**:
   - Include flag keys directly in the prompt
   - Can also upload a file with flag keys using the attachments API
   - Use structured prompts to clearly identify what to search for

## Request/Response Cycle

### Typical Workflow:
1. **Create Session** (1-2 seconds)
   - POST to /v1/sessions with prompt
   - Receive session_id and url
   
2. **Monitor Progress** (variable duration)
   - Poll GET /v1/sessions/{session_id} every 5-10 seconds
   - Check status_enum for completion
   - Typical code scanning: 2-10 minutes depending on complexity
   
3. **Retrieve Results** (immediate)
   - Parse structured_output from final session details
   - Extract PR URL if Devin created one
   - Review messages for detailed logs

### Example Timeline:
- Session creation: 1s
- Devin starts working: 5-10s
- Code analysis: 1-5 minutes
- Changes implementation: 2-5 minutes
- PR creation: 30-60s
- Total: 3-11 minutes for typical feature flag removal

## Devin's Limitations and Failure Modes

### Known Limitations:

1. **API Status**: Currently in alpha - endpoints may change
2. **No Webhooks**: Must use polling for status updates
3. **Session Duration**: Long-running tasks may timeout or expire
4. **Large-Scale Tasks**: Better suited for smaller, focused tasks
5. **Reliability**: May get off-track and require user intervention (blocked state)
6. **UI/Aesthetics**: Not great at visual design tasks
7. **Mobile Development**: Cannot test on actual mobile devices
8. **Context Window**: Limited by how much code it can analyze at once

### Failure Modes:

1. **Authentication Failures** (401)
   - Invalid or expired API key
   - Missing Authorization header
   - Solution: Verify API key from settings page

2. **Session Not Found** (404)
   - Invalid session_id
   - Session expired or deleted
   - Solution: Check session_id, create new session if needed

3. **Rate Limiting** (429)
   - Too many requests
   - Solution: Implement exponential backoff

4. **Server Errors** (500)
   - Temporary API issues
   - Solution: Retry with exponential backoff

5. **Session Blocked**
   - Devin needs clarification or approval
   - Solution: Send follow-up message via messages endpoint

6. **Session Expired**
   - Session timed out
   - Solution: Create new session with same prompt

7. **Incomplete Results**
   - Session finished but task not fully completed
   - Solution: Review messages, send follow-up, or create new session

### Error Handling Best Practices:

1. Always check HTTP status codes
2. Implement retry logic with exponential backoff
3. Set reasonable timeouts (10-15 minutes for code tasks)
4. Log all API interactions for debugging
5. Handle blocked state by prompting for user input
6. Validate structured_output before using it
7. Check for PR creation in pull_request field

## Session Duration Estimates

Based on documentation and examples:

- **Simple tasks** (hello world, basic scripts): 2-5 minutes
- **Code scanning** (search for patterns): 3-8 minutes
- **Feature flag removal** (scan + modify + test): 5-15 minutes
- **PR reviews**: 5-10 minutes
- **Bug reproduction**: 5-15 minutes
- **Test writing**: 5-10 minutes

**Note**: These are estimates. Actual duration depends on:
- Codebase size
- Task complexity
- Number of files to modify
- Test suite execution time
- CI/CD pipeline duration

## Canceling/Timing Out Sessions

### Timeout Strategy:
1. Set a reasonable timeout when calling `wait_for_completion()`
2. Recommended: 10-15 minutes for code scanning tasks
3. If timeout reached, session continues running in background
4. Can check status later or create new session

### Cancellation:
- No explicit cancel endpoint documented
- Sessions will eventually expire if inactive
- Can suspend via status update (not fully documented)
- Best practice: Set appropriate ACU limits to prevent runaway costs

## Implementation Notes

### Python Client Features:
- ✅ Session creation with all optional parameters
- ✅ Status monitoring with polling
- ✅ Result retrieval with structured output
- ✅ Message history access
- ✅ Timeout handling
- ✅ Error handling with proper exceptions
- ✅ Verbose logging option
- ✅ Environment variable support for API key

### Testing Requirements:
- Requires valid DEVIN_API_KEY environment variable
- API key must have appropriate permissions
- Sessions will consume ACU credits
- Test with simple tasks first before complex operations

## Recommendations for Feature Flag Dashboard

Based on Phase 1 findings:

1. **Session Management**:
   - Store session_id in database for tracking
   - Poll status every 10 seconds
   - Display real-time status updates to user
   - Show session URL for direct access

2. **Error Handling**:
   - Implement retry logic for transient failures
   - Handle blocked state by notifying user
   - Set 15-minute timeout for flag removal tasks
   - Log all API interactions for debugging

3. **User Experience**:
   - Show estimated completion time (5-15 minutes)
   - Display progress updates from messages
   - Link to session URL for detailed view
   - Show PR URL when available

4. **Scalability**:
   - Can run multiple sessions in parallel
   - Each flag removal should be separate session
   - Use tags to group related sessions
   - Implement queue system for batch operations

5. **Cost Management**:
   - Set max_acu_limit per session
   - Monitor ACU usage via API
   - Implement budget alerts
   - Consider batching similar flags

## Success Criteria - Validation

✅ **Can create a Devin session via API**: Implemented in `DevinAPIClient.create_session()`

✅ **Can monitor session status**: Implemented in `DevinAPIClient.get_session_details()` and `wait_for_completion()`

✅ **Can retrieve Devin's output**: Implemented in `DevinAPIClient.get_session_output()` and message retrieval

✅ **Understand typical session duration**: Documented above (5-15 minutes for code tasks)

✅ **Know how to cancel/timeout runaway sessions**: Timeout handling implemented, documented above

## Next Steps for Phase 2

With Phase 1 complete, the next phase should focus on:

1. Building the dashboard UI for session management
2. Implementing the feature flag detection logic
3. Creating prompt templates for flag removal
4. Building the results display and PR tracking
5. Adding batch processing capabilities
6. Implementing cost tracking and budgets

## References

- Devin API Documentation: https://docs.devin.ai/api-reference/overview
- API Examples: https://docs.devin.ai/api-reference/examples
- Session Creation: https://docs.devin.ai/api-reference/sessions/create-a-new-devin-session
- Session Details: https://docs.devin.ai/api-reference/sessions/retrieve-details-about-an-existing-session
- Get API Key: https://app.devin.ai/settings/api-keys
