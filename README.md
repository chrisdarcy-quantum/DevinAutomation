# Devin Automation: Feature Flag Removal System

A lightweight orchestration dashboard that uses Devin AI to automate the removal of stale feature flags from codebases.

## Project Status

**Phase 1: Complete** ✅

Phase 1 focused on understanding and validating Devin's API capabilities. See [PHASE1_FINDINGS.md](PHASE1_FINDINGS.md) for detailed research findings.

## Phase 1 Deliverables

### 1. Devin API Client (`devin_api_client.py`)

A complete Python client for interacting with the Devin AI API, featuring:

- ✅ Session creation with full parameter support
- ✅ Status monitoring with polling
- ✅ Result retrieval with structured output
- ✅ Message history access
- ✅ Timeout handling
- ✅ Comprehensive error handling
- ✅ Verbose logging option

### 2. Research Documentation (`PHASE1_FINDINGS.md`)

Comprehensive documentation covering:

- API capabilities and endpoints
- Authentication requirements
- Session lifecycle management
- Status monitoring strategies
- Result retrieval methods
- Limitations and failure modes
- Session duration estimates
- Best practices and recommendations

## Quick Start

### Prerequisites

- Python 3.7+
- Devin API key from [https://app.devin.ai/settings/api-keys](https://app.devin.ai/settings/api-keys)

### Installation

```bash
# Clone the repository
git clone https://github.com/chrisdarcy-quantum/DevinAutomation.git
cd DevinAutomation

# Install dependencies
pip3 install -r requirements.txt

# Set your API key
export DEVIN_API_KEY='your-api-key-here'
```

### Usage

#### Basic Example

```python
from devin_api_client import DevinAPIClient

# Initialize client
client = DevinAPIClient()

# Create a session
session = client.create_session(
    prompt="Review PR #123 and check for security issues",
    title="Security Review",
    tags=["security", "pr-review"]
)

print(f"Session created: {session.url}")

# Monitor until completion
details = client.wait_for_completion(session.session_id)

# Get results
if details.pull_request:
    print(f"PR created: {details.pull_request['url']}")

if details.structured_output:
    print(f"Results: {details.structured_output}")
```

#### Running the Demo

```bash
# Set your API key
export DEVIN_API_KEY='your-api-key-here'

# Run the demo
python3 devin_api_client.py
```

The demo will:
1. Create a test session with a simple "hello world" task
2. Monitor the session status in real-time
3. Display the final results including messages and output

## Testing

The project includes a comprehensive test suite to ensure no regressions.

### Running Tests

```bash
# Run all tests
python3 -m unittest test_devin_api_client -v

# Run specific test class
python3 -m unittest test_devin_api_client.TestDevinAPIClient -v

# Run specific test
python3 -m unittest test_devin_api_client.TestDevinAPIClient.test_create_session_success -v
```

### Test Coverage

The test suite covers:
- ✅ Client initialization (with/without API key)
- ✅ Session creation (success and error cases)
- ✅ Session details retrieval
- ✅ Status monitoring and polling
- ✅ Timeout handling
- ✅ Message retrieval
- ✅ Structured output parsing
- ✅ Error handling for all failure modes

All tests use mocking to avoid consuming ACU credits.

**Test Results:** 19 tests, all passing ✅

## API Client Reference

### DevinAPIClient

Main client class for interacting with the Devin API.

#### Methods

##### `__init__(api_key=None)`
Initialize the client with an API key (or use `DEVIN_API_KEY` env var).

##### `create_session(prompt, **options)`
Create a new Devin session.

**Parameters:**
- `prompt` (str, required): Task description for Devin
- `snapshot_id` (str, optional): Machine snapshot ID
- `unlisted` (bool, optional): Make session unlisted
- `idempotent` (bool, optional): Enable idempotent creation (default: True)
- `max_acu_limit` (int, optional): Maximum ACU limit
- `secret_ids` (list, optional): Secret IDs to use
- `knowledge_ids` (list, optional): Knowledge IDs to use
- `tags` (list, optional): Session tags
- `title` (str, optional): Custom session title

**Returns:** `SessionResponse` with `session_id` and `url`

##### `get_session_details(session_id)`
Retrieve detailed information about a session.

**Returns:** `SessionDetails` object with full session information

##### `wait_for_completion(session_id, poll_interval=5, timeout=None, verbose=True)`
Wait for a session to complete (blocked, finished, or expired).

**Parameters:**
- `session_id` (str): Session ID to monitor
- `poll_interval` (int): Seconds between checks (default: 5)
- `timeout` (int, optional): Maximum seconds to wait
- `verbose` (bool): Print status updates (default: True)

**Returns:** Final `SessionDetails` when complete

##### `send_message(session_id, message)`
Send a message to an active session.

##### `list_sessions()`
List all sessions for your organization.

##### `get_session_messages(session_id)`
Get all messages from a session.

##### `get_session_output(session_id)`
Get structured output from a completed session.

## Phase 1 Success Criteria

All Phase 1 objectives have been achieved:

- ✅ Can create a Devin session via API
- ✅ Can monitor session status (pending → running → completed/failed)
- ✅ Can retrieve Devin's output (logs, files changed, errors)
- ✅ Understand typical session duration for code scanning tasks (5-15 minutes)
- ✅ Know how to cancel/timeout runaway sessions

## Key Findings

### Session Lifecycle

1. **Create Session** (~1-2 seconds)
   - POST to `/v1/sessions` with prompt
   - Receive `session_id` and `url`

2. **Monitor Progress** (variable, typically 5-15 minutes)
   - Poll GET `/v1/sessions/{session_id}` every 5-10 seconds
   - Check `status_enum` for completion states

3. **Retrieve Results** (immediate)
   - Parse `structured_output` from final session details
   - Extract PR URL if created
   - Review message history for logs

### Status Values

- `working`: Devin is actively working
- `blocked`: Waiting for user input
- `finished`: Task completed
- `expired`: Session timed out

### Typical Durations

- Simple tasks: 2-5 minutes
- Code scanning: 3-8 minutes
- Feature flag removal: 5-15 minutes
- PR reviews: 5-10 minutes

### Limitations

- API is in alpha (may change)
- No webhooks (polling required)
- Better suited for focused tasks
- May require user intervention when blocked
- Session timeouts for long-running tasks

## Error Handling

The client handles common error scenarios:

- **401 Unauthorized**: Invalid API key
- **404 Not Found**: Invalid session ID
- **429 Rate Limited**: Too many requests
- **500 Server Error**: Temporary API issues
- **Timeout**: Session exceeded time limit
- **Blocked**: Devin needs user input

## Next Steps: Phase 2

With Phase 1 complete, the next phase will focus on:

1. Building the dashboard UI for session management
2. Implementing feature flag detection logic
3. Creating prompt templates for flag removal
4. Building results display and PR tracking
5. Adding batch processing capabilities
6. Implementing cost tracking and budgets

## Resources

- [Devin API Documentation](https://docs.devin.ai/api-reference/overview)
- [API Examples](https://docs.devin.ai/api-reference/examples)
- [Get API Key](https://app.devin.ai/settings/api-keys)
- [Phase 1 Findings](PHASE1_FINDINGS.md)

## License

This project is for demonstration and research purposes.

## Support

For questions about the Devin API, contact: support@cognition.ai

For questions about this project, contact: Chris.darcy5@gmail.com

