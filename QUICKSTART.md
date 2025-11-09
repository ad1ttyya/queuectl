# Quick Start Guide

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Install the package (optional):
```bash
pip install -e .
```

## Basic Usage

### 1. Enqueue a Job

```bash
queuectl enqueue '{"id":"job1","command":"echo Hello World"}'
```

### 2. Start Workers

```bash
queuectl worker start --count 2
```

### 3. Check Status

```bash
queuectl status
```

### 4. List Jobs

```bash
queuectl list --state pending
```

### 5. Stop Workers

```bash
queuectl worker stop
```

## Testing

Run the validation script:

```bash
python test_queuectl.py
```

## Example Workflow

```bash
# Terminal 1: Start workers
queuectl worker start --count 3

# Terminal 2: Enqueue jobs
queuectl enqueue '{"id":"job1","command":"sleep 2"}'
queuectl enqueue '{"id":"job2","command":"echo Test"}'
queuectl enqueue '{"id":"job3","command":"ls -la"}'

# Check status
queuectl status

# List completed jobs
queuectl list --state completed

# Stop workers
queuectl worker stop
```

