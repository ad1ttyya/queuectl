# QueueCTL - Architecture & Design Document

## Overview

QueueCTL is a CLI-based background job queue system designed for single-machine deployments. It provides persistent job storage, multi-worker processing, automatic retries with exponential backoff, and a Dead Letter Queue (DLQ) for failed jobs.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Interface                          │
│                    (queuectl/cli.py)                        │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
┌────────▼────────┐    ┌────────▼────────┐
│  Job Storage     │    │ Worker Manager  │
│  (SQLite DB)     │    │ (Multiprocess)  │
│                  │    │                 │
│  - Jobs          │    │  - Worker 1     │
│  - Config        │    │  - Worker 2     │
│  - State Mgmt    │    │  - Worker N     │
└──────────────────┘    └─────────────────┘
         │                       │
         └───────────┬───────────┘
                     │
            ┌────────▼────────┐
            │   Worker Process│
            │  (Job Execution)│
            └─────────────────┘
```

## Core Components

### 1. Storage Layer (`queuectl/storage.py`)

**Purpose**: Manages persistent job storage using SQLite.

**Key Features**:
- **Atomic Operations**: Uses SQLite transactions and atomic UPDATE statements
- **Job Locking**: Prevents race conditions with atomic WHERE clauses
- **Configuration Management**: Stores config values in database
- **State Management**: Tracks job lifecycle (pending → processing → completed/failed → dead)

**Database Schema**:
```sql
jobs:
  - id (PRIMARY KEY)
  - command
  - state (pending/processing/completed/failed/dead)
  - attempts
  - max_retries
  - created_at
  - updated_at
  - locked_by (worker_id)
  - locked_at
  - retry_at (for exponential backoff)

config:
  - key (PRIMARY KEY)
  - value
```

**Race Condition Prevention**:
- Uses atomic `UPDATE ... WHERE` clauses
- `get_next_pending_job()` uses UPDATE with subquery to select and lock in one operation
- SQLite connection timeout (10s) handles concurrent access

### 2. Worker Process (`queuectl/worker.py`)

**Purpose**: Executes jobs in separate processes.

**Key Features**:
- **Command Execution**: Runs shell commands with timeout (5 minutes)
- **Retry Logic**: Implements exponential backoff
- **Graceful Shutdown**: Finishes current job before exiting
- **Signal Handling**: Handles SIGINT/SIGTERM gracefully

**Worker Lifecycle**:
1. Poll for pending/failed jobs
2. Atomically lock a job
3. Execute command
4. Update job state based on result
5. Handle retries with exponential backoff
6. Move to DLQ after max retries

**Exponential Backoff**:
```
delay = backoff_base ^ attempts
Example (base=2):
  Attempt 1: 2 seconds
  Attempt 2: 4 seconds
  Attempt 3: 8 seconds
```

### 3. CLI Interface (`queuectl/cli.py`)

**Purpose**: Provides command-line interface for all operations.

**Commands**:
- `enqueue`: Add jobs to queue
- `worker start/stop`: Manage workers
- `status`: Show job statistics
- `list`: List jobs by state
- `dlq list/retry`: Manage Dead Letter Queue
- `config set/get`: Manage configuration

## Data Flow

### Job Enqueue Flow

```
User → CLI → Storage.create_job()
  ↓
SQLite INSERT (state='pending')
  ↓
Job available for workers
```

### Job Processing Flow

```
Worker polls → Storage.get_next_pending_job()
  ↓
Atomic UPDATE (state='processing', locked_by=worker_id)
  ↓
Worker.execute_command()
  ↓
Success? → UPDATE (state='completed')
  ↓
Failure? → Increment attempts
  ↓
attempts >= max_retries? → UPDATE (state='dead') [DLQ]
  ↓
Else → UPDATE (state='failed', retry_at=now+backoff)
  ↓
Wait for retry_at → Back to pending
```

## Concurrency Model

### Multi-Worker Processing

- **Process-based**: Uses `multiprocessing` for true parallelism
- **Job Locking**: Atomic database operations prevent duplicate processing
- **No Shared State**: Each worker has its own process and storage connection
- **Database-Level Locking**: SQLite handles concurrent access

### Race Condition Prevention

1. **Atomic Job Selection**:
   ```sql
   UPDATE jobs SET state='processing', locked_by=?
   WHERE id IN (SELECT id FROM jobs WHERE state='pending' LIMIT 1)
   AND state='pending'
   ```
   Only one worker can successfully update a job.

2. **Lock Validation**:
   ```sql
   UPDATE jobs SET ...
   WHERE id=? AND (state='pending' OR state='failed')
   ```
   Ensures job is still in lockable state.

3. **Transaction Isolation**:
   - All operations use SQLite transactions
   - Proper commit/rollback handling
   - Connection timeout prevents deadlocks

## Persistence Strategy

### SQLite Database

- **File-based**: `queuectl.db` in current directory
- **ACID Compliance**: Ensures data integrity
- **WAL Mode**: Better concurrency (SQLite default)
- **Transaction Safety**: All operations wrapped in transactions

### Data Persistence

- **Jobs**: All job data persists across restarts
- **Configuration**: Config values stored in database
- **State**: Job states and attempts tracked
- **History**: Complete job lifecycle maintained

## Error Handling

### Job Execution Errors

- **Command Not Found**: Returns exit code != 0 → triggers retry
- **Command Timeout**: 5-minute timeout → triggers retry
- **Command Failure**: Exit code != 0 → triggers retry

### Retry Strategy

1. **Exponential Backoff**: Delay increases exponentially
2. **Max Retries**: Configurable limit (default: 3)
3. **DLQ**: Failed jobs moved to Dead Letter Queue
4. **Manual Retry**: DLQ jobs can be manually retried

### Worker Errors

- **Graceful Shutdown**: Workers finish current job before exit
- **Signal Handling**: SIGINT/SIGTERM handled gracefully
- **Process Isolation**: Worker crashes don't affect other workers

## Configuration Management

### Config Storage

- **Database-backed**: Config stored in SQLite
- **Persistent**: Survives restarts
- **No Hardcoded Values**: All defaults from config storage

### Configurable Values

- `max_retries`: Maximum retry attempts (default: 3)
- `backoff_base`: Exponential backoff base (default: 2.0)

### Config Usage

- **Job Creation**: Uses config default if not specified
- **Worker Initialization**: Reads backoff_base from config
- **Runtime Changes**: Config changes affect new jobs/workers

## Design Decisions

### Why SQLite?

- **Zero Configuration**: No setup required
- **File-based**: Easy to backup and inspect
- **ACID Compliance**: Data integrity guaranteed
- **Single Machine**: Suitable for assignment requirements
- **Lightweight**: Minimal dependencies

### Why Multiprocessing?

- **True Parallelism**: Avoids Python GIL limitations
- **Process Isolation**: Worker crashes don't affect others
- **Scalability**: Can run multiple workers efficiently
- **Simplicity**: Easier than threading for I/O-bound tasks

### Why Atomic Database Operations?

- **Race Condition Prevention**: Ensures only one worker processes a job
- **No External Locks**: Database handles concurrency
- **Simplicity**: No need for distributed locking mechanisms
- **Reliability**: SQLite guarantees atomicity

### Why Polling Instead of Event-Driven?

- **Simplicity**: Easier to implement and debug
- **No Dependencies**: No need for message queues or pub/sub
- **Adequate Performance**: Polling interval (0.5s) is acceptable
- **Reliability**: No event loss or missed notifications

## Trade-offs

### Limitations

1. **Single Machine**: Not designed for distributed deployments
2. **File-based Storage**: SQLite has concurrency limits
3. **Polling Overhead**: Workers poll every 0.5 seconds
4. **No Job Priorities**: FIFO processing only

### Future Enhancements

1. **Job Priorities**: Add priority field and sorting
2. **Scheduled Jobs**: Add cron-like scheduling
3. **Job Dependencies**: Support job chains
4. **Distributed Storage**: Support PostgreSQL/Redis
5. **Event-driven**: Use database triggers or message queues
6. **Web UI**: Add web interface for monitoring

## Testing Strategy

### Validation Script

- **Basic Job Completion**: Tests successful job execution
- **Failed Job Retry**: Tests retry mechanism and DLQ
- **Multiple Workers**: Tests concurrent processing
- **Persistence**: Tests data survival across restarts
- **DLQ Retry**: Tests manual retry from DLQ

### Manual Testing

- **CLI Commands**: All commands tested manually
- **Worker Behavior**: Tested with multiple workers
- **Error Scenarios**: Tested with invalid commands
- **Restart Scenarios**: Tested persistence

## Security Considerations

### Command Execution

- **Shell Execution**: Commands run with `shell=True`
- **No Sandboxing**: Commands run with full system access
- **User Responsibility**: Users must trust the commands they enqueue
- **Timeout Protection**: 5-minute timeout prevents hanging commands

### Database Security

- **File Permissions**: Database file should have appropriate permissions
- **No Authentication**: SQLite has no built-in authentication
- **Local Access Only**: Database file is local to the machine

## Performance Characteristics

### Throughput

- **Job Processing**: Limited by command execution time
- **Worker Count**: Scales with number of workers
- **Database**: SQLite handles moderate job volumes well

### Latency

- **Polling Interval**: 0.5 seconds between polls
- **Job Locking**: Atomic operations are fast (<1ms)
- **Command Execution**: Depends on command complexity

### Resource Usage

- **Memory**: ~10-20MB per worker process
- **Disk**: SQLite database grows with job history
- **CPU**: Minimal overhead for polling and locking

## Conclusion

QueueCTL is designed as a simple, reliable, and production-grade job queue system for single-machine deployments. It prioritizes correctness (atomic operations, persistence) over advanced features (distributed processing, job priorities). The architecture is modular, testable, and maintainable.

