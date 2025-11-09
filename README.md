# QueueCTL - Background Job Queue System

A production-grade CLI-based background job queue system with worker processes, automatic retries with exponential backoff, and Dead Letter Queue (DLQ) support.

## 📹 Demo Video

**Working CLI Demo**: [Watch the demo video here](https://drive.google.com/file/d/1v96yPTWFXBciIk82M91NW8ltkmshn8ub/view?usp=drive_link)

The demo video shows all features including job enqueueing, worker processing, retry mechanism, DLQ functionality, configuration management, and persistence testing.

## 📚 Documentation

- **[README.md](README.md)** - This file (setup, usage, examples)
- **[DESIGN.md](DESIGN.md)** - Architecture and design documentation

## 🚀 Features

- ✅ **Job Queue Management** - Enqueue and manage background jobs
- ✅ **Multiple Workers** - Run multiple worker processes in parallel
- ✅ **Automatic Retries** - Exponential backoff retry mechanism
- ✅ **Dead Letter Queue** - Handle permanently failed jobs
- ✅ **Persistent Storage** - SQLite-based persistence across restarts
- ✅ **Job Locking** - Prevents duplicate processing
- ✅ **Graceful Shutdown** - Workers finish current jobs before exiting
- ✅ **Configuration Management** - Configurable retry count and backoff base
- ✅ **Clean CLI Interface** - Intuitive command-line interface

## 📋 Requirements

- Python 3.8 or higher
- pip (Python package manager)

## 🔧 Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd Flam-Assignment
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install the package (optional, for global access):
```bash
pip install -e .
```

## 📖 Usage

### Basic Commands

#### Enqueue a Job

Add a new job to the queue:

```bash
queuectl enqueue '{"id":"job1","command":"echo Hello World"}'
```

With custom max retries:
```bash
queuectl enqueue '{"id":"job2","command":"sleep 5","max_retries":5}'
```

#### Start Workers

Start worker processes to process jobs:

```bash
# Start a single worker
queuectl worker start

# Start multiple workers
queuectl worker start --count 3
```

#### Stop Workers

Stop all running workers gracefully:

```bash
queuectl worker stop
```

#### Check Status

View summary of job states and active workers:

```bash
queuectl status
```

Example output:
```
=== Queue Status ===
Active Workers: 3

Job States:
State        Count
---------  -------
Pending          5
Processing       2
Completed       10
Failed           1
Dead (DLQ)       2

Total Jobs: 20
```

#### List Jobs

List all jobs or filter by state:

```bash
# List all jobs
queuectl list

# List pending jobs
queuectl list --state pending

# List completed jobs
queuectl list --state completed

# List failed jobs
queuectl list --state failed
```

#### Dead Letter Queue (DLQ)

View jobs in the Dead Letter Queue:

```bash
queuectl dlq list
```

Retry a job from DLQ:

```bash
queuectl dlq retry job1
```

#### Configuration

View current configuration:

```bash
queuectl config get
```

Get a specific config value:

```bash
queuectl config get max-retries
```

Set configuration values:

```bash
# Set max retries
queuectl config set max-retries 5

# Set backoff base
queuectl config set backoff-base 3
```

## 🏗️ Architecture

### Job Lifecycle

```
pending → processing → completed
    ↓
  failed → (retry with backoff) → pending
    ↓
  dead (DLQ)
```

### Job States

| State | Description |
|-------|-------------|
| `pending` | Waiting to be picked up by a worker |
| `processing` | Currently being executed by a worker |
| `completed` | Successfully executed |
| `failed` | Failed, but retryable |
| `dead` | Permanently failed (moved to DLQ) |

### Job Structure

Each job contains the following fields:

```json
{
  "id": "unique-job-id",
  "command": "echo 'Hello World'",
  "state": "pending",
  "attempts": 0,
  "max_retries": 3,
  "created_at": "2025-11-04T10:30:00Z",
  "updated_at": "2025-11-04T10:30:00Z"
}
```

### Data Persistence

Jobs are stored in a SQLite database (`queuectl.db`) in the current directory. This ensures:

- ✅ **Jobs persist across restarts** - All job data is saved to disk
- ✅ **Configuration is saved** - Config values persist in database
- ✅ **Job history is maintained** - All job states and attempts are tracked
- ✅ **No data loss** - Database uses WAL mode and proper transaction handling

### Worker Process

Workers:
- Poll for pending jobs
- Lock jobs to prevent duplicate processing
- Execute commands using shell
- Handle retries with exponential backoff
- Move failed jobs to DLQ after max retries
- Support graceful shutdown (finish current job before exit)

### Retry Mechanism

Failed jobs are automatically retried with exponential backoff:

- **Backoff Formula**: `delay = base ^ attempts` seconds
- **Default Base**: 2.0 (configurable)
- **Example**: 
  - Attempt 1: 2 seconds
  - Attempt 2: 4 seconds
  - Attempt 3: 8 seconds

After `max_retries` attempts, jobs are moved to the Dead Letter Queue.

## 🧪 Testing

### Quick Test Run

**Run the test script:**
```bash
python test_queuectl.py
```

### Prerequisites

Before running tests, make sure dependencies are installed:

```bash
pip install -r requirements.txt
```

Optionally, install the package in development mode:

```bash
pip install -e .
```

### Test Cases

The test suite includes 5 test cases:

1. ✅ **Basic job completion** - Tests successful job execution
2. ✅ **Failed job retry and DLQ** - Tests retry mechanism and DLQ
3. ✅ **Multiple workers processing** - Tests concurrent processing
4. ✅ **Job persistence** - Tests data survival across restarts
5. ✅ **DLQ retry functionality** - Tests manual retry from DLQ

### Testing Instructions

Run the validation script to test core functionality:

```bash
python test_queuectl.py
```

This script tests all core features including job execution, retries, DLQ, persistence, and multiple workers.

### Manual Testing Examples

#### Test 1: Basic Job Execution

```bash
# Terminal 1: Start a worker
queuectl worker start --count 1

# Terminal 2: Enqueue a job
queuectl enqueue '{"id":"test1","command":"echo Hello World"}'

# Check status
queuectl status
queuectl list --state completed
```

#### Test 2: Failed Job with Retries

```bash
# Enqueue a job that will fail
queuectl enqueue '{"id":"test2","command":"nonexistentcommand","max_retries":3}'

# Start worker and watch retries
queuectl worker start --count 1

# Wait for retries to complete, then check DLQ
queuectl dlq list
```

#### Test 3: Multiple Workers

```bash
# Enqueue multiple jobs
for i in {1..10}; do
  queuectl enqueue "{\"id\":\"job$i\",\"command\":\"sleep 1\"}"
done

# Start 3 workers
queuectl worker start --count 3

# Monitor status
queuectl status
```

#### Test 4: Persistence

```bash
# Enqueue a job
queuectl enqueue '{"id":"persist1","command":"echo Test"}'

# Stop workers
queuectl worker stop

# Restart workers (job should still be there)
queuectl worker start --count 1

# Check that job persists
queuectl list --state pending
```

## 📁 Project Structure

```
.
├── queuectl/
│   ├── __init__.py          # Package initialization
│   ├── cli.py               # CLI interface
│   ├── storage.py           # SQLite storage layer
│   └── worker.py            # Worker process implementation
├── test_queuectl.py         # Validation script
├── requirements.txt         # Python dependencies
├── setup.py                # Package setup
└── README.md               # This file
```

## 🔍 Implementation Details

### Job Locking

Jobs are locked using database-level updates with WHERE clauses to ensure atomicity:

```sql
UPDATE jobs 
SET state = 'processing', locked_by = ?, locked_at = ?
WHERE id = ? AND state = 'pending'
```

This prevents multiple workers from processing the same job.

### Exponential Backoff

The backoff delay is calculated as:

```python
delay = backoff_base ** attempts
```

Where:
- `backoff_base` is configurable (default: 2.0)
- `attempts` is the current attempt count (1-indexed)

### Graceful Shutdown

Workers handle SIGINT and SIGTERM signals:
1. Set `running = False` flag
2. Finish current job if any
3. Exit cleanly

### Command Execution

Jobs execute shell commands using `subprocess.run()`:
- Commands run with shell=True
- Output is captured
- Exit codes determine success/failure
- 5-minute timeout per command

## ⚙️ Configuration

Default configuration values (stored in database, not hardcoded):

- `max_retries`: 3
- `backoff_base`: 2.0

These can be changed using the `config set` command. Configuration values are:
- **Persistent**: Stored in SQLite database
- **Used as defaults**: When creating jobs without explicit `max_retries`, the config value is used
- **Applied to workers**: Workers read `backoff_base` from config when starting

Note: Configuration changes affect new jobs and workers, not existing jobs.

## 🔒 Race Condition Prevention

The system uses **atomic database operations** to prevent race conditions and duplicate job execution:

1. **Job Locking**: Uses atomic `UPDATE ... WHERE` clauses to ensure only one worker can lock a job:
   ```sql
   UPDATE jobs 
   SET state = 'processing', locked_by = ?, ...
   WHERE id = ? AND (state = 'pending' OR state = 'failed')
   ```

2. **Atomic Job Selection**: `get_next_pending_job()` uses atomic UPDATE with subquery to select and lock jobs in a single operation, preventing multiple workers from selecting the same job.

3. **Database Transactions**: All operations use SQLite transactions with proper commit/rollback handling.

4. **Connection Timeout**: SQLite connections use a 10-second timeout to handle concurrent access gracefully.

## 🎯 Assumptions & Trade-offs

### Assumptions

1. **Single Machine**: Designed for single-machine deployment (not distributed)
2. **File-based Storage**: SQLite is sufficient for moderate job volumes
3. **Shell Commands**: Jobs execute as shell commands (security consideration)
4. **Synchronous Workers**: Workers poll for jobs (not event-driven)

### Trade-offs

1. **SQLite vs. PostgreSQL/Redis**: 
   - Chose SQLite for simplicity and zero-configuration
   - Suitable for single-machine deployments
   - Can be swapped for distributed storage if needed

2. **Polling vs. Event-driven**:
   - Chose polling for simplicity
   - Small overhead for low job volumes
   - Could be improved with database triggers or message queues

3. **File-based Config vs. Environment Variables**:
   - Config stored in database for persistence
   - Simple and consistent with job storage
   - **No hardcoded values** - all defaults come from config storage

4. **Process-based Workers vs. Thread-based**:
   - Chose multiprocessing for true parallelism
   - Better isolation and GIL avoidance
   - Slightly higher memory overhead

## 🐛 Troubleshooting

### Workers not processing jobs

1. Check if workers are running: `queuectl status`
2. Verify jobs are in pending state: `queuectl list --state pending`
3. Check database file exists: `ls queuectl.db`

### Jobs stuck in processing state

This can happen if a worker crashes. You can manually reset:

```bash
# Access database directly
sqlite3 queuectl.db
UPDATE jobs SET state = 'pending', locked_by = NULL WHERE state = 'processing';
```

### Database locked errors

SQLite uses file-level locking. If you see locking errors:
- Ensure only one instance is accessing the database
- Check for stale worker processes: `ps aux | grep queuectl`

## 📝 License

This project is part of a technical assignment.

## 👤 Author

Developed as part of the Backend Developer Internship Assignment.

## 🔗 Repository

**GitHub Repository**: [View on GitHub](https://github.com/ad1ttyya/queuectl)

## 📝 Additional Documentation

- **[DESIGN.md](DESIGN.md)** - Detailed architecture and design documentation

---

## ✅ Checklist

- [x] Working CLI application (`queuectl`)
- [x] Persistent job storage (SQLite) - **Jobs survive restarts**
- [x] Multiple worker support - **No race conditions, atomic locking**
- [x] Retry mechanism with exponential backoff - **Fully implemented**
- [x] Dead Letter Queue - **DLQ operational with retry support**
- [x] Configuration management - **No hardcoded values, all from config storage**
- [x] Clean CLI interface with help texts
- [x] Comprehensive README.md
- [x] Code structured with clear separation of concerns
- [x] Validation script for core flows
- [x] **Race condition prevention** - Atomic database operations
- [x] **Persistence verified** - SQLite with proper transaction handling

