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

## Background Services Architecture

### Session Monitor Service

**Purpose**: Continuously monitor active Devin sessions and update the database with latest status.

**Architecture**:
```python
# Background worker that runs as a FastAPI background task
class SessionMonitor:
    def __init__(self, db, devin_client):
        self.db = db
        self.devin_client = devin_client
        self.poll_interval = 10  # seconds
        self.running = True
    
    async def start(self):
        """Main monitoring loop"""
        while self.running:
            try:
                await self.poll_active_sessions()
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(self.poll_interval)
    
    async def poll_active_sessions(self):
        """Poll all active Devin sessions for status updates"""
        # Get sessions that are not yet complete
        active_sessions = self.db.query(
            devin_sessions
        ).filter(
            devin_sessions.status.in_(['pending', 'claimed', 'working', 'blocked'])
        ).all()
        
        for session in active_sessions:
            try:
                # Get latest status from Devin API
                details = self.devin_client.get_session_details(
                    session.devin_session_id
                )
                
                # Update database
                await self.update_session_status(session, details)
                
                # Log status change
                await self.log_status_change(session, details)
                
                # Check for completion
                if details.status_enum in ['finished', 'expired']:
                    await self.handle_completion(session, details)
                
                # Check for timeout
                await self.check_timeout(session)
                
            except Exception as e:
                logger.error(f"Error polling session {session.id}: {e}")
                await self.handle_poll_error(session, e)
    
    async def update_session_status(self, session, details):
        """Update session status in database"""
        self.db.update(devin_sessions).where(
            devin_sessions.id == session.id
        ).values(
            status=details.status_enum,
            pr_url=details.pull_request.get('url') if details.pull_request else None,
            structured_output=json.dumps(details.structured_output) if details.structured_output else None,
            completed_at=datetime.now() if details.status_enum in ['finished', 'expired'] else None
        )
        self.db.commit()
    
    async def check_timeout(self, session):
        """Check if session has exceeded timeout threshold"""
        if not session.started_at:
            return
        
        elapsed = (datetime.now() - session.started_at).total_seconds()
        timeout_threshold = 900  # 15 minutes
        
        if elapsed > timeout_threshold and session.status == 'working':
            logger.warning(f"Session {session.id} exceeded timeout threshold")
            await self.handle_timeout(session)
    
    async def handle_timeout(self, session):
        """Handle session timeout"""
        self.db.update(devin_sessions).where(
            devin_sessions.id == session.id
        ).values(
            status='expired',
            error_message='Session timed out after 15 minutes',
            completed_at=datetime.now()
        )
        
        await self.log_event(
            session.id, 
            'error', 
            'Session timed out after 15 minutes',
            'timeout'
        )
```

**Implementation Options**:

1. **FastAPI Background Task** (Recommended for MVP)
   ```python
   from fastapi import BackgroundTasks
   
   @app.on_event("startup")
   async def startup_event():
       monitor = SessionMonitor(db, devin_client)
       asyncio.create_task(monitor.start())
   ```
   - ✅ Simple, single-process
   - ✅ No additional infrastructure
   - ❌ Stops if app restarts
   - ❌ Single instance only

2. **Celery Worker** (Future/Production)
   ```python
   from celery import Celery
   
   @celery.task
   def poll_sessions():
       monitor = SessionMonitor(db, devin_client)
       monitor.poll_active_sessions()
   
   # Schedule every 10 seconds
   celery.conf.beat_schedule = {
       'poll-sessions': {
           'task': 'poll_sessions',
           'schedule': 10.0,
       },
   }
   ```
   - ✅ Distributed, scalable
   - ✅ Survives app restarts
   - ✅ Can run multiple workers
   - ❌ Requires Redis/RabbitMQ

**For Phase 2**: Use **FastAPI BackgroundTasks**

---

## Real-Time Updates Strategy

### Server-Sent Events (SSE)

**Why SSE over WebSockets or Polling**:
- ✅ Simpler than WebSockets (one-way communication is sufficient)
- ✅ More efficient than polling (server pushes updates)
- ✅ Native browser support (EventSource API)
- ✅ Automatic reconnection
- ✅ Works through most firewalls/proxies

**Backend Implementation**:
```python
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse
import asyncio

@app.get("/api/removals/{id}/stream")
async def stream_removal_status(id: int):
    """
    Stream real-time status updates for a removal request.
    Client connects and receives updates as they happen.
    """
    async def event_generator():
        last_update = None
        
        while True:
            # Get current status
            removal = db.query(removal_requests).filter_by(id=id).first()
            
            if not removal:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "Removal request not found"})
                }
                break
            
            # Get all sessions
            sessions = db.query(devin_sessions).filter_by(
                removal_request_id=id
            ).all()
            
            # Build status update
            status_data = {
                "removal_id": removal.id,
                "status": removal.status,
                "updated_at": removal.updated_at.isoformat(),
                "sessions": [
                    {
                        "id": s.id,
                        "repository": s.repository,
                        "status": s.status,
                        "pr_url": s.pr_url
                    }
                    for s in sessions
                ]
            }
            
            # Only send if data changed
            current_hash = hash(json.dumps(status_data, sort_keys=True))
            if current_hash != last_update:
                yield {
                    "event": "status_update",
                    "data": json.dumps(status_data)
                }
                last_update = current_hash
            
            # Send heartbeat every 30 seconds
            yield {
                "event": "heartbeat",
                "data": json.dumps({"timestamp": datetime.now().isoformat()})
            }
            
            # Exit if completed
            if removal.status in ['completed', 'failed']:
                yield {
                    "event": "complete",
                    "data": json.dumps({"status": removal.status})
                }
                break
            
            await asyncio.sleep(5)  # Poll every 5 seconds
    
    return EventSourceResponse(event_generator())
```

**Frontend Implementation**:
```typescript
// React hook for SSE
function useRemovalStatus(removalId: number) {
  const [status, setStatus] = useState<RemovalStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const eventSource = new EventSource(
      `/api/removals/${removalId}/stream`
    );

    eventSource.addEventListener('status_update', (event) => {
      const data = JSON.parse(event.data);
      setStatus(data);
    });

    eventSource.addEventListener('error', (event) => {
      const data = JSON.parse(event.data);
      setError(data.error);
      eventSource.close();
    });

    eventSource.addEventListener('complete', (event) => {
      eventSource.close();
    });

    return () => {
      eventSource.close();
    };
  }, [removalId]);

  return { status, error };
}

// Usage in component
function RemovalDetail({ id }: { id: number }) {
  const { status, error } = useRemovalStatus(id);

  return (
    <div>
      {status && (
        <div>
          <h2>Status: {status.status}</h2>
          {status.sessions.map(session => (
            <SessionCard key={session.id} session={session} />
          ))}
        </div>
      )}
    </div>
  );
}
```

**Dependencies**:
```bash
# Backend
pip install sse-starlette

# Frontend (built-in EventSource API, no extra deps needed)
```

---

## Concurrency & Rate Limiting

### Rate Limiting

**Per-User Limits**:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/api/removals")
@limiter.limit("5/minute")  # 5 requests per minute per user
async def create_removal(request: Request, body: CreateRemovalRequest):
    # ... implementation
    pass
```

**Global Concurrency Limits**:
```python
# Configuration
MAX_CONCURRENT_SESSIONS = 20
MAX_REPOS_PER_REQUEST = 5
MAX_REQUESTS_PER_USER_DAILY = 50

async def check_concurrency_limits():
    """Check if system is at capacity"""
    active_count = db.query(devin_sessions).filter(
        devin_sessions.status.in_(['pending', 'claimed', 'working'])
    ).count()
    
    if active_count >= MAX_CONCURRENT_SESSIONS:
        return {
            "allowed": False,
            "reason": "System at capacity",
            "retry_after": 300,  # 5 minutes
            "active_sessions": active_count,
            "max_sessions": MAX_CONCURRENT_SESSIONS
        }
    
    return {"allowed": True}

@app.post("/api/removals")
async def create_removal(request: Request, body: CreateRemovalRequest):
    # Check limits
    limit_check = await check_concurrency_limits()
    if not limit_check["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=limit_check,
            headers={"Retry-After": str(limit_check["retry_after"])}
        )
    
    # Validate repo count
    if len(body.repositories) > MAX_REPOS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_REPOS_PER_REQUEST} repositories per request"
        )
    
    # ... create removal
```

### Queue-Based Session Creation

**Why Queue-Based**:
- ✅ Controlled concurrency (don't overwhelm Devin API)
- ✅ Better error recovery (can retry queued items)
- ✅ Prevents rate limit issues
- ✅ Fair distribution of resources

**Implementation**:
```python
class SessionQueue:
    """Queue for managing Devin session creation"""
    
    def __init__(self, db, devin_client, max_concurrent=20):
        self.db = db
        self.devin_client = devin_client
        self.max_concurrent = max_concurrent
        self.running = True
    
    async def start(self):
        """Process queue continuously"""
        while self.running:
            try:
                # Check if we have capacity
                active_count = self.get_active_count()
                
                if active_count < self.max_concurrent:
                    # Get next pending session
                    session = self.db.query(devin_sessions).filter_by(
                        status='pending'
                    ).order_by(
                        devin_sessions.id  # FIFO
                    ).first()
                    
                    if session:
                        await self.start_session(session)
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Queue error: {e}")
                await asyncio.sleep(5)
    
    async def start_session(self, session):
        """Start a Devin session"""
        try:
            # Build prompt
            prompt = build_removal_prompt(
                flag_key=session.removal_request.flag_key,
                repository=session.repository,
                provider=session.removal_request.feature_flag_provider
            )
            
            # Create Devin session
            devin_session = self.devin_client.create_session(
                prompt=prompt,
                title=f"Remove flag: {session.removal_request.flag_key}",
                tags=["flag-removal", session.removal_request.flag_key],
                idempotent=True
            )
            
            # Update database
            self.db.update(devin_sessions).where(
                devin_sessions.id == session.id
            ).values(
                devin_session_id=devin_session.session_id,
                devin_session_url=devin_session.url,
                status='claimed',
                started_at=datetime.now()
            )
            self.db.commit()
            
            logger.info(f"Started session {session.id}: {devin_session.session_id}")
            
        except Exception as e:
            logger.error(f"Failed to start session {session.id}: {e}")
            self.db.update(devin_sessions).where(
                devin_sessions.id == session.id
            ).values(
                status='failed',
                error_message=str(e)
            )
            self.db.commit()
    
    def get_active_count(self):
        """Get count of active Devin sessions"""
        return self.db.query(devin_sessions).filter(
            devin_sessions.status.in_(['pending', 'claimed', 'working'])
        ).count()
```

**Lifecycle with Queue**:
```
User creates removal request
    ↓
Sessions created with status='pending'
    ↓
SessionQueue picks up pending sessions
    ↓
Queue checks if under MAX_CONCURRENT
    ↓
If yes: Create Devin session, set status='claimed'
If no: Wait until capacity available
    ↓
SessionMonitor polls active sessions
    ↓
On completion: status='finished', capacity freed
```

---

## Cost Management & Budget Tracking

### ACU (Anthropic Compute Units) Tracking

**Database Schema Addition**:
```sql
ALTER TABLE devin_sessions ADD COLUMN max_acu_limit INTEGER DEFAULT 500;
ALTER TABLE devin_sessions ADD COLUMN acu_consumed INTEGER;
ALTER TABLE removal_requests ADD COLUMN total_acu_consumed INTEGER DEFAULT 0;

-- Add budget tracking table
CREATE TABLE budget_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    acu_limit INTEGER NOT NULL,
    acu_consumed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_email, period_start)
);

CREATE INDEX idx_budget_user_period ON budget_tracking(user_email, period_start);
```

**Budget Enforcement**:
```python
async def check_budget(user_email: str, estimated_acu: int = 500):
    """Check if user has budget for this request"""
    today = date.today()
    period_start = date(today.year, today.month, 1)  # Monthly budget
    period_end = period_start + timedelta(days=32)
    period_end = period_end.replace(day=1) - timedelta(days=1)
    
    # Get or create budget record
    budget = db.query(budget_tracking).filter_by(
        user_email=user_email,
        period_start=period_start
    ).first()
    
    if not budget:
        budget = budget_tracking(
            user_email=user_email,
            period_start=period_start,
            period_end=period_end,
            acu_limit=10000  # Default monthly limit
        )
        db.add(budget)
        db.commit()
    
    # Check remaining budget
    remaining = budget.acu_limit - budget.acu_consumed
    
    if remaining < estimated_acu:
        return {
            "allowed": False,
            "reason": "Budget exceeded",
            "limit": budget.acu_limit,
            "consumed": budget.acu_consumed,
            "remaining": remaining,
            "period_end": budget.period_end.isoformat()
        }
    
    return {
        "allowed": True,
        "remaining": remaining
    }

@app.post("/api/removals")
async def create_removal(request: Request, body: CreateRemovalRequest):
    # Check budget
    budget_check = await check_budget(
        body.created_by,
        estimated_acu=len(body.repositories) * 500  # Estimate per repo
    )
    
    if not budget_check["allowed"]:
        raise HTTPException(
            status_code=402,  # Payment Required
            detail=budget_check
        )
    
    # ... create removal
```

**UI Budget Display**:
```typescript
// Show budget in create form
<div className="p-4 bg-blue-50 rounded">
  <h3>Estimated Cost</h3>
  <p>Repositories: {repositories.length}</p>
  <p>Estimated ACU: ~{repositories.length * 500}</p>
  <p>Your remaining budget: {budget.remaining} ACU</p>
  <p>Resets: {budget.period_end}</p>
</div>
```

**ACU Tracking from Devin**:
```python
async def update_acu_consumption(session_id: int):
    """Update ACU consumption after session completes"""
    session = db.query(devin_sessions).filter_by(id=session_id).first()
    
    # Get ACU from Devin API (if available in structured_output)
    if session.structured_output:
        output = json.loads(session.structured_output)
        acu_used = output.get('acu_consumed', 0)
        
        # Update session
        db.update(devin_sessions).where(
            devin_sessions.id == session_id
        ).values(acu_consumed=acu_used)
        
        # Update removal request total
        db.execute(f"""
            UPDATE removal_requests 
            SET total_acu_consumed = (
                SELECT SUM(acu_consumed) 
                FROM devin_sessions 
                WHERE removal_request_id = {session.removal_request_id}
            )
            WHERE id = {session.removal_request_id}
        """)
        
        # Update user budget
        request = db.query(removal_requests).filter_by(
            id=session.removal_request_id
        ).first()
        
        period_start = date.today().replace(day=1)
        db.execute(f"""
            UPDATE budget_tracking
            SET acu_consumed = acu_consumed + {acu_used}
            WHERE user_email = '{request.created_by}'
            AND period_start = '{period_start}'
        """)
        
        db.commit()
```

---

## Security & Validation

### Input Validation

**Repository URL Validation**:
```python
from urllib.parse import urlparse

ALLOWED_GITHUB_ORGS = ["example", "example-org"]  # From config

def validate_repository_url(url: str) -> tuple[bool, str]:
    """Validate repository URL"""
    try:
        parsed = urlparse(url)
        
        # Must be HTTPS GitHub URL
        if parsed.scheme != "https":
            return False, "Repository URL must use HTTPS"
        
        if parsed.netloc != "github.com":
            return False, "Only GitHub repositories are supported"
        
        # Parse owner/repo from path
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 2:
            return False, "Invalid repository URL format"
        
        owner, repo = path_parts[0], path_parts[1]
        
        # Check allowlist
        if owner not in ALLOWED_GITHUB_ORGS:
            return False, f"Organization '{owner}' is not in the allowlist"
        
        return True, ""
        
    except Exception as e:
        return False, f"Invalid URL: {str(e)}"

# Pydantic model with validation
from pydantic import BaseModel, validator

class CreateRemovalRequest(BaseModel):
    flag_key: str
    repositories: List[str]
    feature_flag_provider: Optional[str]
    created_by: str
    
    @validator('flag_key')
    def validate_flag_key(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Flag key cannot be empty")
        if len(v) > 200:
            raise ValueError("Flag key too long (max 200 characters)")
        return v.strip()
    
    @validator('repositories')
    def validate_repositories(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one repository required")
        if len(v) > MAX_REPOS_PER_REQUEST:
            raise ValueError(f"Maximum {MAX_REPOS_PER_REQUEST} repositories allowed")
        
        for url in v:
            valid, error = validate_repository_url(url)
            if not valid:
                raise ValueError(f"Invalid repository URL '{url}': {error}")
        
        return v
    
    @validator('created_by')
    def validate_email(cls, v):
        import re
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, v):
            raise ValueError("Invalid email format")
        return v.lower()
```

### Authentication (Future)

**For Phase 2**: No authentication (PoC only)

**For Phase 3+**: Add GitHub OAuth
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Verify and get current user from token"""
    # Verify GitHub OAuth token
    # Return user info
    pass

@app.post("/api/removals")
async def create_removal(
    body: CreateRemovalRequest,
    current_user: dict = Depends(get_current_user)
):
    # User is authenticated
    body.created_by = current_user["email"]
    # ... proceed
```

### CSRF Protection

```python
from fastapi_csrf_protect import CsrfProtect

@app.post("/api/removals")
async def create_removal(
    request: Request,
    csrf_protect: CsrfProtect = Depends()
):
    await csrf_protect.validate_csrf(request)
    # ... proceed
```

---

## Structured Output Contract

### Expected Schema from Devin

**Define expected output structure**:
```python
from typing import Optional, List
from pydantic import BaseModel

class DevinStructuredOutput(BaseModel):
    """Expected structure from Devin"""
    pr_url: Optional[str] = None
    files_modified: Optional[List[str]] = None
    occurrences_removed: Optional[int] = None
    test_results: Optional[str] = None
    warnings: Optional[List[str]] = None
    acu_consumed: Optional[int] = None
    
    # Handle free-form output
    raw_output: Optional[dict] = None

def parse_devin_output(structured_output: Optional[str]) -> DevinStructuredOutput:
    """
    Parse Devin's structured output with fallbacks.
    Devin may return different formats, so be flexible.
    """
    if not structured_output:
        return DevinStructuredOutput()
    
    try:
        data = json.loads(structured_output)
        
        # Try to extract known fields
        return DevinStructuredOutput(
            pr_url=data.get('pr_url') or data.get('pull_request'),
            files_modified=data.get('files_modified') or data.get('files_changed'),
            occurrences_removed=data.get('occurrences_removed') or data.get('matches_removed'),
            test_results=data.get('test_results') or data.get('tests'),
            warnings=data.get('warnings') or [],
            acu_consumed=data.get('acu_consumed'),
            raw_output=data  # Store original for debugging
        )
        
    except json.JSONDecodeError:
        # Not valid JSON, store as raw
        logger.warning(f"Could not parse structured output as JSON: {structured_output}")
        return DevinStructuredOutput(raw_output={"raw": structured_output})
    
    except Exception as e:
        logger.error(f"Error parsing structured output: {e}")
        return DevinStructuredOutput(raw_output={"error": str(e)})
```

**Prompt Template with Output Requirements**:
```python
def build_removal_prompt(flag_key: str, repository: str, provider: str) -> str:
    return f"""
Task: Remove feature flag from codebase

Flag Key: {flag_key}
Repository: {repository}
Provider: {provider or 'Unknown'}

Instructions:
1. Clone the repository
2. Search for all occurrences of "{flag_key}"
3. Remove the flag and associated code safely
4. Run tests to verify nothing breaks
5. Create a pull request

IMPORTANT: Return structured output in this EXACT JSON format:
{{
  "pr_url": "https://github.com/...",
  "files_modified": ["path/to/file1.py", "path/to/file2.js"],
  "occurrences_removed": 12,
  "test_results": "PASSED" or "FAILED" or "SKIPPED",
  "warnings": ["Any warnings or issues encountered"],
  "acu_consumed": 450
}}

If you cannot create a PR, set pr_url to null and explain in warnings.
"""
```

---

## Technology Stack

### Frontend
- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui (pre-installed)
- **Icons**: Lucide React
- **HTTP Client**: Fetch API (native) with EventSource for SSE
- **State Management**: React hooks (useState, useEffect)
- **Routing**: React Router (if needed for multi-page)

### Backend
- **Framework**: FastAPI (Python 3.8+)
- **Database**: SQLite (in-memory for proof of concept)
  - **Migration Path**: PostgreSQL for production (Phase 3+)
- **ORM**: SQLAlchemy with async support
- **API Client**: devin_api_client.py (from Phase 1)
- **Validation**: Pydantic models with custom validators
- **CORS**: Enabled for local development
- **Rate Limiting**: slowapi
- **SSE**: sse-starlette
- **Background Tasks**: asyncio + FastAPI BackgroundTasks

### Development Tools
- **Backend Server**: `uvicorn app.main:app --reload`
- **Frontend Server**: `npm run dev` (Vite)
- **Testing**: pytest (backend), Vitest (frontend)
- **Linting**: ruff (Python), ESLint (TypeScript)
- **Type Checking**: mypy (Python), tsc (TypeScript)

### Deployment
- **Backend**: Docker container on Fly.io/Railway/Render
- **Frontend**: Static hosting on Vercel/Netlify
- **Environment Variables**: .env files for local, secrets manager for production
- **Database**: SQLite file volume (Phase 2), PostgreSQL (Phase 3+)

### Dependencies
```bash
# Backend requirements.txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
pydantic==2.5.0
slowapi==0.1.9
sse-starlette==1.8.2
requests==2.31.0
python-dotenv==1.0.0

# Frontend package.json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "typescript": "^5.2.0",
    "vite": "^5.0.0",
    "tailwindcss": "^3.3.0",
    "eslint": "^8.54.0"
  }
}
```

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
