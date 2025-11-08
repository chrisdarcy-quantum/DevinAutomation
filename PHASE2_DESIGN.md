# Phase 2: Orchestration Layer Design

## Overview

This document defines the architecture, database schema, API endpoints, and UI design for the Feature Flag Removal System's orchestration layer. The system follows a clear separation of concerns: the dashboard provides a thin UI/API layer while Devin AI handles all code execution.

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Create       │  │ View         │  │ Monitor      │         │
│  │ Removal      │  │ Requests     │  │ Progress     │         │
│  │ Request      │  │ List         │  │ & Logs       │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Layer (FastAPI)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ POST         │  │ GET          │  │ GET          │         │
│  │ /removals    │  │ /removals    │  │ /removals/   │         │
│  │              │  │              │  │ {id}/logs    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Business Logic Layer                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Orchestration Service                                     │  │
│  │  • Validate removal requests                             │  │
│  │  • Create Devin sessions via API client                  │  │
│  │  • Track session status                                  │  │
│  │  • Store results and logs                                │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Data Access Layer                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ In-Memory Database (SQLite)                              │  │
│  │  • removal_requests table                                │  │
│  │  • devin_sessions table                                  │  │
│  │  • session_logs table                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Services                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Devin AI API (via devin_api_client.py)                   │  │
│  │  • Create sessions                                       │  │
│  │  • Monitor status                                        │  │
│  │  • Retrieve results                                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

**Frontend (React + TypeScript + Tailwind)**
- Thin UI layer for user interaction
- Form for creating removal requests
- List view for all requests with status indicators
- Detail view for individual requests with logs
- Real-time status updates via polling

**Backend (FastAPI + Python)**
- RESTful API endpoints
- Request validation and business logic
- Devin session orchestration
- Database operations
- Error handling and logging

**Devin API Client (Phase 1)**
- Wrapper around Devin AI API
- Session creation and monitoring
- Result retrieval
- Already implemented and tested

**Database (SQLite In-Memory)**
- Stores removal requests
- Tracks Devin sessions
- Stores logs and results
- **Note**: Data will be lost on restart (proof of concept)

---

## Database Schema

### Entity Relationship Diagram

```
┌─────────────────────────┐
│  removal_requests       │
├─────────────────────────┤
│ id (PK)                 │
│ flag_key                │
│ repositories            │◄────┐
│ feature_flag_provider   │     │
│ status                  │     │
│ created_by              │     │
│ created_at              │     │
│ updated_at              │     │
│ error_message           │     │
└─────────────────────────┘     │
                                │ 1:N
                                │
┌─────────────────────────┐     │
│  devin_sessions         │     │
├─────────────────────────┤     │
│ id (PK)                 │     │
│ removal_request_id (FK) │─────┘
│ repository              │
│ devin_session_id        │
│ devin_session_url       │
│ status                  │
│ pr_url                  │
│ structured_output       │
│ started_at              │
│ completed_at            │
│ error_message           │
└─────────────────────────┘
         │
         │ 1:N
         │
         ▼
┌─────────────────────────┐
│  session_logs           │
├─────────────────────────┤
│ id (PK)                 │
│ devin_session_id (FK)   │
│ timestamp               │
│ log_level               │
│ message                 │
│ event_type              │
└─────────────────────────┘
```

### Table Definitions

#### `removal_requests`

Stores high-level removal requests from users.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Unique identifier |
| `flag_key` | TEXT | NOT NULL | Feature flag key to remove (e.g., "ENABLE_NEW_CHECKOUT") |
| `repositories` | TEXT | NOT NULL | JSON array of repository URLs |
| `feature_flag_provider` | TEXT | NULL | Provider name (e.g., "LaunchDarkly", "Split.io") - text field for now |
| `status` | TEXT | NOT NULL | Request status: "queued", "in_progress", "completed", "failed", "partial" |
| `created_by` | TEXT | NOT NULL | User identifier (email or username) |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | When request was created |
| `updated_at` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | Last update timestamp |
| `error_message` | TEXT | NULL | Error message if request failed |

**Status Values:**
- `queued`: Request created, waiting to start
- `in_progress`: One or more Devin sessions are active
- `completed`: All sessions completed successfully
- `failed`: All sessions failed
- `partial`: Some sessions succeeded, some failed

#### `devin_sessions`

Tracks individual Devin sessions (one per repository in a removal request).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Unique identifier |
| `removal_request_id` | INTEGER | NOT NULL, FOREIGN KEY | Links to removal_requests.id |
| `repository` | TEXT | NOT NULL | Repository URL this session is working on |
| `devin_session_id` | TEXT | NULL | Devin API session ID (e.g., "devin-abc123") |
| `devin_session_url` | TEXT | NULL | URL to view session in Devin web app |
| `status` | TEXT | NOT NULL | Session status: "pending", "claimed", "working", "blocked", "finished", "expired", "failed" |
| `pr_url` | TEXT | NULL | Pull request URL if created |
| `structured_output` | TEXT | NULL | JSON structured output from Devin |
| `started_at` | TIMESTAMP | NULL | When Devin session started |
| `completed_at` | TIMESTAMP | NULL | When Devin session completed |
| `error_message` | TEXT | NULL | Error message if session failed |

**Status Values** (from Devin API):
- `pending`: Session created but not yet claimed by Devin
- `claimed`: Devin has claimed the session
- `working`: Devin is actively working
- `blocked`: Devin is waiting for user input
- `finished`: Session completed successfully
- `expired`: Session timed out
- `failed`: Session failed with error

#### `session_logs`

Stores log entries from Devin sessions for debugging and monitoring.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Unique identifier |
| `devin_session_id` | INTEGER | NOT NULL, FOREIGN KEY | Links to devin_sessions.id |
| `timestamp` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | When log entry was created |
| `log_level` | TEXT | NOT NULL | Log level: "info", "warning", "error", "debug" |
| `message` | TEXT | NOT NULL | Log message content |
| `event_type` | TEXT | NULL | Event type: "status_change", "message", "error", "pr_created" |

**Event Types:**
- `status_change`: Session status changed
- `message`: Message from Devin
- `error`: Error occurred
- `pr_created`: Pull request was created

### Indexes

```sql
-- Speed up queries by removal request
CREATE INDEX idx_devin_sessions_removal_request 
ON devin_sessions(removal_request_id);

-- Speed up queries by status
CREATE INDEX idx_removal_requests_status 
ON removal_requests(status);

CREATE INDEX idx_devin_sessions_status 
ON devin_sessions(status);

-- Speed up log queries
CREATE INDEX idx_session_logs_devin_session 
ON session_logs(devin_session_id, timestamp);
```

---

## API Endpoints

### Base URL
- Development: `http://localhost:8000`
- Production: `https://api.{domain}/v1`

### Authentication
For Phase 2, no authentication required (proof of concept). Future phases will add API key or OAuth authentication.

### Endpoints

#### 1. Create Removal Request

**Endpoint:** `POST /api/removals`

**Description:** Create a new feature flag removal request. This will create Devin sessions for each repository.

**Request Body:**
```json
{
  "flag_key": "ENABLE_NEW_CHECKOUT",
  "repositories": [
    "https://github.com/example/frontend-app",
    "https://github.com/example/backend-api"
  ],
  "feature_flag_provider": "LaunchDarkly",
  "created_by": "user@example.com"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "flag_key": "ENABLE_NEW_CHECKOUT",
  "repositories": [
    "https://github.com/example/frontend-app",
    "https://github.com/example/backend-api"
  ],
  "feature_flag_provider": "LaunchDarkly",
  "status": "queued",
  "created_by": "user@example.com",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "sessions": [
    {
      "id": 1,
      "repository": "https://github.com/example/frontend-app",
      "status": "pending"
    },
    {
      "id": 2,
      "repository": "https://github.com/example/backend-api",
      "status": "pending"
    }
  ]
}
```

**Error Responses:**
- `400 Bad Request`: Invalid input (missing fields, invalid repository URLs)
- `500 Internal Server Error`: Failed to create Devin sessions

#### 2. List All Removal Requests

**Endpoint:** `GET /api/removals`

**Description:** Get a list of all removal requests with pagination and filtering.

**Query Parameters:**
- `status` (optional): Filter by status (queued, in_progress, completed, failed, partial)
- `limit` (optional): Number of results per page (default: 20, max: 100)
- `offset` (optional): Pagination offset (default: 0)
- `sort` (optional): Sort field (created_at, updated_at) (default: created_at)
- `order` (optional): Sort order (asc, desc) (default: desc)

**Example:** `GET /api/removals?status=in_progress&limit=10`

**Response (200 OK):**
```json
{
  "total": 45,
  "limit": 10,
  "offset": 0,
  "results": [
    {
      "id": 1,
      "flag_key": "ENABLE_NEW_CHECKOUT",
      "repositories": ["https://github.com/example/frontend-app"],
      "feature_flag_provider": "LaunchDarkly",
      "status": "in_progress",
      "created_by": "user@example.com",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:35:00Z",
      "session_count": 2,
      "completed_sessions": 1,
      "failed_sessions": 0
    }
  ]
}
```

#### 3. Get Removal Request Details

**Endpoint:** `GET /api/removals/{id}`

**Description:** Get detailed information about a specific removal request, including all Devin sessions.

**Path Parameters:**
- `id`: Removal request ID

**Response (200 OK):**
```json
{
  "id": 1,
  "flag_key": "ENABLE_NEW_CHECKOUT",
  "repositories": [
    "https://github.com/example/frontend-app",
    "https://github.com/example/backend-api"
  ],
  "feature_flag_provider": "LaunchDarkly",
  "status": "in_progress",
  "created_by": "user@example.com",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:35:00Z",
  "error_message": null,
  "sessions": [
    {
      "id": 1,
      "repository": "https://github.com/example/frontend-app",
      "devin_session_id": "devin-abc123",
      "devin_session_url": "https://app.devin.ai/sessions/abc123",
      "status": "finished",
      "pr_url": "https://github.com/example/frontend-app/pull/456",
      "structured_output": {
        "files_modified": 5,
        "flag_occurrences_removed": 12
      },
      "started_at": "2024-01-15T10:30:05Z",
      "completed_at": "2024-01-15T10:38:22Z",
      "error_message": null
    },
    {
      "id": 2,
      "repository": "https://github.com/example/backend-api",
      "devin_session_id": "devin-def456",
      "devin_session_url": "https://app.devin.ai/sessions/def456",
      "status": "working",
      "pr_url": null,
      "structured_output": null,
      "started_at": "2024-01-15T10:30:05Z",
      "completed_at": null,
      "error_message": null
    }
  ]
}
```

**Error Responses:**
- `404 Not Found`: Removal request not found

#### 4. Get Session Logs

**Endpoint:** `GET /api/removals/{id}/logs`

**Description:** Stream or retrieve logs for all Devin sessions in a removal request.

**Path Parameters:**
- `id`: Removal request ID

**Query Parameters:**
- `session_id` (optional): Filter logs for specific Devin session
- `level` (optional): Filter by log level (info, warning, error, debug)
- `since` (optional): ISO 8601 timestamp to get logs since
- `limit` (optional): Number of log entries (default: 100, max: 1000)

**Example:** `GET /api/removals/1/logs?session_id=1&level=error`

**Response (200 OK):**
```json
{
  "removal_request_id": 1,
  "logs": [
    {
      "id": 1,
      "devin_session_id": 1,
      "timestamp": "2024-01-15T10:30:05Z",
      "log_level": "info",
      "message": "Devin session created: devin-abc123",
      "event_type": "status_change"
    },
    {
      "id": 2,
      "devin_session_id": 1,
      "timestamp": "2024-01-15T10:30:15Z",
      "log_level": "info",
      "message": "Status changed: pending -> working",
      "event_type": "status_change"
    },
    {
      "id": 3,
      "devin_session_id": 1,
      "timestamp": "2024-01-15T10:35:42Z",
      "log_level": "info",
      "message": "Found 12 occurrences of flag 'ENABLE_NEW_CHECKOUT' in 5 files",
      "event_type": "message"
    },
    {
      "id": 4,
      "devin_session_id": 1,
      "timestamp": "2024-01-15T10:38:22Z",
      "log_level": "info",
      "message": "Pull request created: https://github.com/example/frontend-app/pull/456",
      "event_type": "pr_created"
    }
  ]
}
```

**Error Responses:**
- `404 Not Found`: Removal request not found

#### 5. Cancel Removal Request (Future)

**Endpoint:** `DELETE /api/removals/{id}`

**Description:** Cancel an in-progress removal request and stop all Devin sessions.

**Note:** Not implemented in Phase 2, but included in design for future phases.

---

## UI Wireframes

### 1. Dashboard Home / Request List

```
┌────────────────────────────────────────────────────────────────────┐
│  Feature Flag Removal Dashboard                    [+ New Request] │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Filter: [All ▼] [Queued] [In Progress] [Completed] [Failed]      │
│  Search: [Search by flag key or repository...]                     │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ ENABLE_NEW_CHECKOUT                        🟢 In Progress    │ │
│  │ 2 repositories • Created by user@example.com                 │ │
│  │ Started: 5 minutes ago • Updated: 2 minutes ago              │ │
│  │                                                              │ │
│  │ Progress: ████████░░ 1/2 sessions completed                 │ │
│  │                                                              │ │
│  │ ✅ frontend-app: PR #456 created                            │ │
│  │ ⏳ backend-api: Working...                                  │ │
│  │                                                              │ │
│  │ [View Details →]                                            │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ OLD_PAYMENT_FLOW                           ✅ Completed      │ │
│  │ 1 repository • Created by admin@example.com                  │ │
│  │ Started: 2 hours ago • Completed: 1 hour ago                 │ │
│  │                                                              │ │
│  │ ✅ payment-service: PR #789 created                         │ │
│  │                                                              │ │
│  │ [View Details →]                                            │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ BETA_FEATURE_X                             ❌ Failed         │ │
│  │ 3 repositories • Created by dev@example.com                  │ │
│  │ Started: 1 day ago • Failed: 1 day ago                       │ │
│  │                                                              │ │
│  │ ❌ Error: Devin session timed out after 15 minutes          │ │
│  │                                                              │ │
│  │ [View Details →] [Retry]                                    │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Showing 1-3 of 45 requests                    [← 1 2 3 ... 15 →] │
└────────────────────────────────────────────────────────────────────┘
```

**Key Features:**
- Status indicators with color coding (🟢 green = in progress, ✅ green = completed, ❌ red = failed)
- Progress bars showing completion percentage
- Quick summary of each request
- Filter and search capabilities
- Pagination for large lists

### 2. Create New Removal Request

```
┌────────────────────────────────────────────────────────────────────┐
│  ← Back to Dashboard                                                │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Create New Feature Flag Removal Request                           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Feature Flag Key *                                           │ │
│  │ [ENABLE_NEW_CHECKOUT                                       ] │ │
│  │ The exact key used in your codebase                          │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Target Repositories *                                        │ │
│  │ [https://github.com/example/frontend-app               ] [+] │ │
│  │ [https://github.com/example/backend-api                ] [×] │ │
│  │ [                                                      ] [+] │ │
│  │ Add repository URLs (one per line or use + button)           │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Feature Flag Provider (Optional)                             │ │
│  │ [LaunchDarkly                                              ] │ │
│  │ e.g., LaunchDarkly, Split.io, Unleash, etc.                  │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Your Email *                                                 │ │
│  │ [user@example.com                                          ] │ │
│  │ For notifications and tracking                               │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ℹ️  Devin will:                                                   │
│  • Search for all occurrences of the flag in each repository      │
│  • Remove the flag and associated code                            │
│  • Run tests to ensure nothing breaks                             │
│  • Create a pull request with the changes                         │
│                                                                     │
│  Estimated time: 5-15 minutes per repository                       │
│                                                                     │
│  [Cancel]                                    [Create Request →]    │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

**Key Features:**
- Clear form with validation
- Dynamic repository input (add/remove)
- Helpful hints and descriptions
- Estimated time information
- Clear call-to-action

### 3. Request Detail View

```
┌────────────────────────────────────────────────────────────────────┐
│  ← Back to Dashboard                                                │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ENABLE_NEW_CHECKOUT                           🟢 In Progress      │
│  Created by user@example.com • 5 minutes ago                       │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Request Details                                              │ │
│  │                                                              │ │
│  │ Flag Key: ENABLE_NEW_CHECKOUT                                │ │
│  │ Provider: LaunchDarkly                                       │ │
│  │ Status: In Progress (1/2 sessions completed)                 │ │
│  │ Started: 2024-01-15 10:30:00                                 │ │
│  │ Last Updated: 2024-01-15 10:35:00                            │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ 📦 frontend-app                            ✅ Completed       │ │
│  │ https://github.com/example/frontend-app                      │ │
│  │                                                              │ │
│  │ Devin Session: devin-abc123                                  │ │
│  │ [View in Devin →]                                           │ │
│  │                                                              │ │
│  │ Status: Finished                                             │ │
│  │ Duration: 8 minutes 17 seconds                               │ │
│  │                                                              │ │
│  │ Results:                                                     │ │
│  │ • Files modified: 5                                          │ │
│  │ • Flag occurrences removed: 12                               │ │
│  │ • Tests passed: ✅                                           │ │
│  │                                                              │ │
│  │ Pull Request: #456                                           │ │
│  │ [View PR on GitHub →]                                       │ │
│  │                                                              │ │
│  │ ▼ View Logs                                                  │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ 📦 backend-api                             ⏳ Working         │ │
│  │ https://github.com/example/backend-api                       │ │
│  │                                                              │ │
│  │ Devin Session: devin-def456                                  │ │
│  │ [View in Devin →]                                           │ │
│  │                                                              │ │
│  │ Status: Working                                              │ │
│  │ Duration: 5 minutes 12 seconds (ongoing)                     │ │
│  │                                                              │ │
│  │ Latest Activity:                                             │ │
│  │ • Scanning codebase for flag references...                   │ │
│  │ • Found 8 occurrences in 3 files                             │ │
│  │ • Analyzing code dependencies...                             │ │
│  │                                                              │ │
│  │ ▼ View Live Logs                                             │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

**Key Features:**
- Detailed overview of request
- Per-repository session status
- Links to Devin sessions and PRs
- Expandable log sections
- Real-time updates for in-progress sessions

### 4. Logs View (Expanded)

```
┌────────────────────────────────────────────────────────────────────┐
│  Logs: backend-api (devin-def456)                     [Collapse ▲] │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Filter: [All Levels ▼] [Auto-refresh: ON]  [Download Logs]       │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ 10:30:05  ℹ️  INFO     Session created: devin-def456         │ │
│  │ 10:30:15  ℹ️  INFO     Status: pending → working             │ │
│  │ 10:31:22  ℹ️  INFO     Cloning repository...                 │ │
│  │ 10:31:45  ℹ️  INFO     Repository cloned successfully        │ │
│  │ 10:32:10  ℹ️  INFO     Scanning for flag: ENABLE_NEW_CHECKOUT│ │
│  │ 10:33:05  ℹ️  INFO     Found 8 occurrences in 3 files:       │ │
│  │                        - src/api/checkout.py (3)              │ │
│  │                        - src/services/payment.py (4)          │ │
│  │                        - tests/test_checkout.py (1)           │ │
│  │ 10:33:30  ℹ️  INFO     Analyzing code dependencies...        │ │
│  │ 10:34:15  ℹ️  INFO     Creating removal plan...              │ │
│  │ 10:35:00  ℹ️  INFO     Removing flag from checkout.py...     │ │
│  │ 10:35:12  ⚠️  WARNING  Complex conditional found, reviewing...│ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Showing latest 100 entries • Last updated: 2 seconds ago          │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

**Key Features:**
- Chronological log display
- Log level indicators (ℹ️ info, ⚠️ warning, ❌ error)
- Auto-refresh for live logs
- Filter by log level
- Download logs option

### 5. Error State Examples

#### Session Timeout Error
```
┌────────────────────────────────────────────────────────────────────┐
│  📦 backend-api                                ❌ Failed            │
│  https://github.com/example/backend-api                            │
│                                                                     │
│  ❌ Error: Session Timeout                                         │
│                                                                     │
│  The Devin session exceeded the 15-minute timeout limit.           │
│  This usually happens when:                                        │
│  • The repository is very large                                    │
│  • The flag has many complex occurrences                           │
│  • Devin encountered an unexpected issue                           │
│                                                                     │
│  Recommendations:                                                  │
│  • Review the logs to see where Devin got stuck                    │
│  • Try breaking the removal into smaller chunks                    │
│  • Contact support if the issue persists                           │
│                                                                     │
│  [View Logs] [Retry with Extended Timeout] [Contact Support]      │
└────────────────────────────────────────────────────────────────────┘
```

#### Authentication Error
```
┌────────────────────────────────────────────────────────────────────┐
│  📦 private-repo                               ❌ Failed            │
│  https://github.com/example/private-repo                           │
│                                                                     │
│  ❌ Error: Authentication Failed                                   │
│                                                                     │
│  Devin could not access the repository. This usually means:        │
│  • The repository is private and Devin lacks access                │
│  • GitHub credentials are missing or expired                       │
│  • Repository URL is incorrect                                     │
│                                                                     │
│  To fix this:                                                      │
│  1. Verify the repository URL is correct                           │
│  2. Ensure Devin has access to the repository                      │
│  3. Check that GitHub credentials are configured                   │
│                                                                     │
│  [View Logs] [Update Credentials] [Retry]                         │
└────────────────────────────────────────────────────────────────────┘
```

#### No Matches Found
```
┌────────────────────────────────────────────────────────────────────┐
│  📦 frontend-app                               ⚠️  Completed       │
│  https://github.com/example/frontend-app                           │
│                                                                     │
│  ⚠️  Warning: No Flag Occurrences Found                            │
│                                                                     │
│  Devin searched the entire repository but could not find any       │
│  occurrences of the flag key "ENABLE_NEW_CHECKOUT".                │
│                                                                     │
│  Possible reasons:                                                 │
│  • The flag has already been removed                               │
│  • The flag key is spelled differently in the code                 │
│  • The flag is defined in a different repository                   │
│                                                                     │
│  Devin Session: devin-abc123                                       │
│  [View in Devin →] [View Logs]                                    │
└────────────────────────────────────────────────────────────────────┘
```

#### Devin Blocked (Needs Input)
```
┌────────────────────────────────────────────────────────────────────┐
│  📦 backend-api                                🟡 Blocked           │
│  https://github.com/example/backend-api                            │
│                                                                     │
│  🟡 Devin Needs Your Input                                         │
│                                                                     │
│  Devin has paused and is waiting for clarification:                │
│                                                                     │
│  "I found the flag in a complex conditional with multiple          │
│  branches. Should I remove the entire conditional or just the      │
│  flag check? Please review the code and advise."                   │
│                                                                     │
│  [View in Devin →] [Respond to Devin]                             │
│                                                                     │
│  Note: You can respond directly in the Devin web interface.        │
│  The dashboard will update automatically once Devin continues.     │
└────────────────────────────────────────────────────────────────────┘
```

---

## Error States & Handling

### Error Categories

#### 1. User Input Errors (400 Bad Request)

**Scenarios:**
- Missing required fields (flag_key, repositories, created_by)
- Invalid repository URLs
- Empty repository list
- Invalid email format

**Handling:**
- Validate on frontend before submission
- Show inline validation errors
- Provide helpful error messages
- Prevent form submission until fixed

**Example Error Response:**
```json
{
  "error": "Validation Error",
  "details": {
    "repositories": [
      "Invalid URL: 'not-a-url' is not a valid repository URL"
    ],
    "created_by": [
      "Invalid email format"
    ]
  }
}
```

#### 2. Devin API Errors (500 Internal Server Error)

**Scenarios:**
- Devin API is down or unreachable
- Invalid Devin API key
- Rate limiting from Devin API
- Network timeout

**Handling:**
- Retry with exponential backoff (3 attempts)
- Log error details for debugging
- Show user-friendly error message
- Provide option to retry manually

**Example Error Response:**
```json
{
  "error": "Devin API Error",
  "message": "Failed to create Devin session: API rate limit exceeded",
  "retry_after": 60,
  "support_contact": "support@example.com"
}
```

#### 3. Session Timeout (408 Request Timeout)

**Scenarios:**
- Devin session exceeds 15-minute timeout
- Session expires due to inactivity
- Session stuck in "working" state

**Handling:**
- Mark session as "expired" in database
- Log timeout event
- Show timeout error in UI
- Provide option to retry with extended timeout
- Suggest breaking into smaller tasks

**Database Update:**
```sql
UPDATE devin_sessions 
SET status = 'expired', 
    error_message = 'Session timed out after 15 minutes',
    completed_at = CURRENT_TIMESTAMP
WHERE id = ?
```

#### 4. Authentication/Authorization Errors (401/403)

**Scenarios:**
- Repository is private and Devin lacks access
- GitHub credentials missing or expired
- Insufficient permissions to create PR

**Handling:**
- Detect auth errors from Devin messages
- Mark session as "failed" with auth error
- Show clear instructions to fix
- Provide link to credential management
- Allow retry after credentials updated

**UI Message:**
```
❌ Authentication Failed

Devin could not access the repository. Please ensure:
1. The repository exists and URL is correct
2. Devin has been granted access to the repository
3. GitHub credentials are configured in settings

[Update Credentials] [Retry]
```

#### 5. No Matches Found (200 OK with warning)

**Scenarios:**
- Flag key not found in repository
- Flag already removed
- Typo in flag key

**Handling:**
- Mark session as "finished" (not failed)
- Set warning flag in structured_output
- Show warning message in UI
- Suggest checking flag key spelling
- Provide link to Devin session for review

**Structured Output:**
```json
{
  "status": "completed_with_warning",
  "warning": "No occurrences of flag 'ENABLE_NEW_CHECKOUT' found",
  "files_scanned": 247,
  "suggestions": [
    "Verify the flag key is spelled correctly",
    "Check if the flag has already been removed",
    "Ensure you're searching the correct repository"
  ]
}
```

#### 6. Devin Blocked (Needs User Input)

**Scenarios:**
- Devin needs clarification on complex code
- Devin asks for approval before making changes
- Devin encounters ambiguous situation

**Handling:**
- Detect "blocked" status from Devin API
- Update session status to "blocked"
- Show notification in UI
- Provide link to Devin web interface
- Poll for status changes
- Auto-update when Devin continues

**UI Notification:**
```
🟡 Devin Needs Your Input

Devin has paused and is waiting for your response.
Click "View in Devin" to see the question and respond.

[View in Devin →] [Dismiss]
```

#### 7. Partial Completion

**Scenarios:**
- Some repositories succeed, others fail
- Mixed results across multiple sessions

**Handling:**
- Calculate completion percentage
- Show per-repository status
- Mark overall request as "partial"
- Highlight failed sessions
- Provide retry option for failed sessions only

**Status Calculation:**
```python
def calculate_request_status(sessions):
    total = len(sessions)
    completed = sum(1 for s in sessions if s.status == 'finished')
    failed = sum(1 for s in sessions if s.status in ['failed', 'expired'])
    
    if completed == total:
        return 'completed'
    elif failed == total:
        return 'failed'
    elif completed > 0 or failed > 0:
        return 'partial'
    else:
        return 'in_progress'
```

### Error Recovery Strategies

#### Automatic Retry
- Retry transient errors (network, rate limit) automatically
- Use exponential backoff: 1s, 2s, 4s
- Max 3 retry attempts
- Log all retry attempts

#### Manual Retry
- Provide "Retry" button for failed sessions
- Allow retry with different parameters
- Preserve original request for audit trail
- Create new Devin session for retry

#### Graceful Degradation
- If one repository fails, continue with others
- Show partial results
- Allow user to fix and retry failed ones
- Don't block entire request on single failure

#### Monitoring & Alerting
- Log all errors to database
- Track error rates and patterns
- Alert on high error rates
- Provide error analytics dashboard

---

## Technology Stack

### Frontend
- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui (pre-installed)
- **Icons**: Lucide React
- **HTTP Client**: Fetch API / Axios
- **State Management**: React hooks (useState, useEffect)
- **Routing**: React Router (if needed for multi-page)

### Backend
- **Framework**: FastAPI (Python 3.8+)
- **Database**: SQLite (in-memory for proof of concept)
- **ORM**: SQLAlchemy (optional, can use raw SQL)
- **API Client**: devin_api_client.py (from Phase 1)
- **Validation**: Pydantic models
- **CORS**: Enabled for local development

### Development Tools
- **Backend Server**: `poetry run fastapi dev app/main.py`
- **Frontend Server**: `npm run dev` (Vite)
- **Testing**: pytest (backend), Jest/Vitest (frontend)
- **Linting**: ruff (Python), ESLint (TypeScript)

### Deployment
- **Backend**: Deploy via `deploy` tool (FastAPI to Fly.io)
- **Frontend**: Deploy via `deploy` tool (static site)
- **Environment Variables**: .env files for configuration

---

## Implementation Plan

### Phase 2A: Backend Implementation
1. Create FastAPI app structure
2. Implement database models and schema
3. Create API endpoints
4. Integrate devin_api_client.py
5. Add error handling and logging
6. Test endpoints with curl

### Phase 2B: Frontend Implementation
1. Create React app with Vite
2. Build UI components (forms, lists, detail views)
3. Implement API integration
4. Add real-time status updates
5. Style with Tailwind CSS
6. Test locally

### Phase 2C: Integration & Testing
1. Test full workflow end-to-end
2. Fix any integration issues
3. Polish UI/UX
4. Add error handling
5. Test error scenarios

### Phase 2D: Deployment
1. Deploy backend to production
2. Update frontend with production API URL
3. Deploy frontend
4. Test deployed app
5. Document deployment process

---

## Success Criteria Validation

✅ **Clear separation: dashboard = thin UI/API, Devin = execution engine**
- Dashboard only handles UI and API endpoints
- All code execution delegated to Devin via API
- No code analysis or modification in dashboard

✅ **Database can store request → session → result lifecycle**
- `removal_requests` table tracks high-level requests
- `devin_sessions` table tracks individual Devin sessions
- `session_logs` table stores detailed logs
- Foreign key relationships maintain data integrity

✅ **UI mockups show the user journey**
- Dashboard home with request list
- Create new request form
- Request detail view with session status
- Logs view with real-time updates
- Error states with clear messaging

✅ **Error states are explicitly designed**
- User input errors (validation)
- Devin API errors (retry logic)
- Session timeouts (extended timeout option)
- Authentication errors (credential management)
- No matches found (helpful suggestions)
- Devin blocked (link to respond)
- Partial completion (per-repository status)

---

## Next Steps

After Phase 2 design approval:

1. **Implement Backend** (Phase 2A)
   - Set up FastAPI project structure
   - Create database models
   - Implement API endpoints
   - Integrate Devin API client

2. **Implement Frontend** (Phase 2B)
   - Set up React + Vite project
   - Build UI components
   - Connect to backend API
   - Add real-time updates

3. **Test & Deploy** (Phase 2C & 2D)
   - End-to-end testing
   - Deploy backend and frontend
   - Production testing
   - Documentation

4. **Phase 3: Prompt Engineering**
   - Design optimal prompts for Devin
   - Test flag removal accuracy
   - Iterate on prompt templates
   - Add structured output parsing

---

## Appendix

### Sample Devin Prompt Template

```
Task: Remove feature flag from codebase

Flag Key: {flag_key}
Repository: {repository_url}
Provider: {feature_flag_provider}

Instructions:
1. Clone the repository
2. Search for all occurrences of the flag key "{flag_key}"
3. Analyze each occurrence and determine safe removal strategy
4. Remove the flag and associated conditional code
5. Ensure code still compiles and tests pass
6. Create a pull request with:
   - Title: "Remove feature flag: {flag_key}"
   - Description: List of files modified and changes made
   - Label: "feature-flag-removal"

Important:
- Do NOT remove code that is still needed
- Preserve the "enabled" code path
- Remove the "disabled" code path
- Run all tests before creating PR
- If tests fail, investigate and fix
- If you need clarification, ask before proceeding

Expected Output:
- Pull request URL
- Number of files modified
- Number of flag occurrences removed
- Test results
```

### Database Initialization SQL

```sql
-- Create tables
CREATE TABLE IF NOT EXISTS removal_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flag_key TEXT NOT NULL,
    repositories TEXT NOT NULL,
    feature_flag_provider TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    created_by TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS devin_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    removal_request_id INTEGER NOT NULL,
    repository TEXT NOT NULL,
    devin_session_id TEXT,
    devin_session_url TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    pr_url TEXT,
    structured_output TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    FOREIGN KEY (removal_request_id) REFERENCES removal_requests(id)
);

CREATE TABLE IF NOT EXISTS session_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    devin_session_id INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    log_level TEXT NOT NULL,
    message TEXT NOT NULL,
    event_type TEXT,
    FOREIGN KEY (devin_session_id) REFERENCES devin_sessions(id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_devin_sessions_removal_request 
ON devin_sessions(removal_request_id);

CREATE INDEX IF NOT EXISTS idx_removal_requests_status 
ON removal_requests(status);

CREATE INDEX IF NOT EXISTS idx_devin_sessions_status 
ON devin_sessions(status);

CREATE INDEX IF NOT EXISTS idx_session_logs_devin_session 
ON session_logs(devin_session_id, timestamp);
```

---

**End of Phase 2 Design Document**
