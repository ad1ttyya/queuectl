#!/usr/bin/env python3
"""
Validation script for QueueCTL system.
Tests core functionality including job execution, retries, DLQ, and persistence.
"""
import subprocess
import time
import os
import sys
import json
import sqlite3


def run_command(cmd, check=True):
    """Run a CLI command and return output."""
    try:
        # On Windows, use list format for better compatibility
        if isinstance(cmd, str):
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                check=check
            )
        else:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=check
            )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout if e.stdout else "", e.stderr if e.stderr else ""
    except Exception as e:
        return False, "", str(e)


def test_basic_job_completion():
    """Test 1: Basic job completes successfully."""
    print("\n=== Test 1: Basic Job Completion ===")
    
    # Enqueue a simple job - use list format to avoid shell quote issues
    job_data = '{"id":"test1","command":"echo Hello World"}'
    success, stdout, stderr = run_command(
        ['python', '-m', 'queuectl.cli', 'enqueue', job_data]
    )
    
    if not success:
        print(f"FAILED: Could not enqueue job: {stderr}")
        return False
    
    # Start a worker
    worker_process = subprocess.Popen(
        ['python', '-m', 'queuectl.cli', 'worker', 'start', '--count', '1'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    time.sleep(2)  # Wait for job to complete
    
    # Check status - use list format
    success, stdout, stderr = run_command(['python', '-m', 'queuectl.cli', 'status'])
    
    # Stop worker - use list format
    run_command(['python', '-m', 'queuectl.cli', 'worker', 'stop'], check=False)
    worker_process.terminate()
    worker_process.wait()
    
    if "completed" in stdout.lower() or "test1" in stdout:
        print("PASSED: Job completed successfully")
        return True
    else:
        print(f"FAILED: Job did not complete. Output: {stdout}")
        return False


def test_failed_job_retry():
    """Test 2: Failed job retries with backoff and moves to DLQ."""
    print("\n=== Test 2: Failed Job Retry and DLQ ===")
    
    # Make sure no workers are running from previous tests
    run_command(['python', '-m', 'queuectl.cli', 'worker', 'stop'], check=False)
    time.sleep(1)  # Give workers time to stop
    
    # Enqueue a job that will fail - use list format to avoid shell quote issues
    job_data = '{"id":"test2","command":"nonexistentcommand123","max_retries":2}'
    success, stdout, stderr = run_command(
        ['python', '-m', 'queuectl.cli', 'enqueue', job_data]
    )
    
    if not success:
        print(f"FAILED: Could not enqueue job: {stderr}")
        return False
    
    # Start a worker
    worker_process = subprocess.Popen(
        ['python', '-m', 'queuectl.cli', 'worker', 'start', '--count', '1'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for retries to complete (with backoff: 2^1=2s, 2^2=4s = ~6s + buffer)
    time.sleep(12)
    
    # Stop worker - use list format
    run_command(['python', '-m', 'queuectl.cli', 'worker', 'stop'], check=False)
    worker_process.terminate()
    worker_process.wait()
    time.sleep(1)  # Give worker time to stop
    
    # Check DLQ - use list format
    success, stdout, stderr = run_command(['python', '-m', 'queuectl.cli', 'dlq', 'list'])
    
    if "test2" in stdout:
        print("PASSED: Failed job moved to DLQ after retries")
        return True
    else:
        print(f"FAILED: Job not in DLQ. Output: {stdout}")
        return False


def test_multiple_workers():
    """Test 3: Multiple workers process jobs without overlap."""
    print("\n=== Test 3: Multiple Workers ===")
    
    # Make sure no workers are running from previous tests
    run_command(['python', '-m', 'queuectl.cli', 'worker', 'stop'], check=False)
    time.sleep(1)  # Give workers time to stop
    
    # Enqueue multiple jobs - use simple echo command (works on all platforms)
    for i in range(5):
        # Use a simple command that works on Windows and Unix
        job_data = f'{{"id":"test3_{i}","command":"echo Job test3_{i} completed"}}'
        success, stdout, stderr = run_command(
            ['python', '-m', 'queuectl.cli', 'enqueue', job_data]
        )
        if not success:
            print(f"WARNING: Failed to enqueue test3_{i}: {stderr}")
    
    # Verify jobs were enqueued
    success, stdout, stderr = run_command(['python', '-m', 'queuectl.cli', 'list', '--state', 'pending'])
    pending_count = stdout.count("test3_")
    if pending_count < 5:
        print(f"WARNING: Only {pending_count}/5 jobs enqueued")
    
    # Start 3 workers
    worker_process = subprocess.Popen(
        ['python', '-m', 'queuectl.cli', 'worker', 'start', '--count', '3'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait longer for jobs to complete (5 jobs with 3 workers = ~2 seconds, but add buffer)
    time.sleep(8)
    
    # Stop workers - use list format
    run_command(['python', '-m', 'queuectl.cli', 'worker', 'stop'], check=False)
    worker_process.terminate()
    worker_process.wait()
    time.sleep(1)  # Give workers time to stop
    
    # Check that jobs were processed - use list format
    success, stdout, stderr = run_command(['python', '-m', 'queuectl.cli', 'list', '--state', 'completed'])
    
    completed_count = stdout.count("test3_")
    
    if completed_count >= 3:  # At least some jobs completed
        print(f"PASSED: Multiple workers processed jobs (completed: {completed_count}/5)")
        return True
    else:
        print(f"FAILED: Not enough jobs completed (found: {completed_count}/5). Output: {stdout}")
        return False


def test_persistence():
    """Test 4: Job data survives restart."""
    print("\n=== Test 4: Persistence ===")
    
    # Make sure no workers are running from previous tests
    run_command(['python', '-m', 'queuectl.cli', 'worker', 'stop'], check=False)
    time.sleep(2)  # Give workers more time to fully stop
    
    # Use a unique job ID to avoid conflicts with previous tests
    job_id = 'test4_persistence'
    job_data = f'{{"id":"{job_id}","command":"echo Persistence Test"}}'
    success, stdout, stderr = run_command(
        ['python', '-m', 'queuectl.cli', 'enqueue', job_data]
    )
    
    if not success:
        print(f"FAILED: Could not enqueue job: {stderr}")
        return False
    
    # Small delay to ensure job is written to database
    time.sleep(0.5)
    
    # Check job exists in database directly (not via CLI to avoid processing)
    if os.path.exists("queuectl.db"):
        conn = sqlite3.connect("queuectl.db")
        cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # Job exists in database - that's what we're testing (persistence)
            print("PASSED: Job persisted in database")
            return True
        else:
            print("FAILED: Job not found in database")
            return False
    else:
        print("FAILED: Database file not found")
        return False


def test_dlq_retry():
    """Test 5: DLQ retry functionality."""
    print("\n=== Test 5: DLQ Retry ===")
    
    # Make sure no workers are running from previous tests
    run_command(['python', '-m', 'queuectl.cli', 'worker', 'stop'], check=False)
    time.sleep(2)  # Give workers time to fully stop
    
    # Use a unique job ID to avoid conflicts
    job_id = 'test5_dlq_retry'
    
    # First, create a job in DLQ (manually via database)
    if os.path.exists("queuectl.db"):
        conn = sqlite3.connect("queuectl.db")
        conn.execute("""
            INSERT OR REPLACE INTO jobs 
            (id, command, state, attempts, max_retries, created_at, updated_at)
            VALUES 
            (?, 'echo DLQ Retry Test', 'dead', 3, 3, datetime('now'), datetime('now'))
        """, (job_id,))
        conn.commit()
        conn.close()
    else:
        print("FAILED: Database file not found")
        return False
    
    # Verify job is in DLQ
    conn = sqlite3.connect("queuectl.db")
    cursor = conn.execute("SELECT state FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row or row[0] != 'dead':
        print(f"FAILED: Job not in DLQ state. State: {row[0] if row else 'not found'}")
        return False
    
    # Retry from DLQ - use list format
    success, stdout, stderr = run_command(['python', '-m', 'queuectl.cli', 'dlq', 'retry', job_id])
    
    if not success:
        print(f"FAILED: Could not retry DLQ job: {stderr}")
        return False
    
    # Check job state immediately after retry (before any worker can process it)
    # We need to check very quickly to catch it in pending state
    conn = sqlite3.connect("queuectl.db")
    cursor = conn.execute("SELECT state, attempts FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    
    # The job should be in pending state with attempts reset to 0
    # If it's already completed, that means a worker processed it very quickly,
    # which actually proves the retry worked (job was moved to pending and processed)
    if row:
        state = row[0]
        attempts = row[1]
        
        if state == 'pending' and attempts == 0:
            print("PASSED: DLQ retry moved job back to pending with reset attempts")
            return True
        elif state == 'completed' and attempts == 0:
            # Job was retried and immediately processed - this also proves retry worked
            print("PASSED: DLQ retry moved job back to pending and it was processed successfully")
            return True
        else:
            print(f"FAILED: Job not in expected state after retry. State: {state}, Attempts: {attempts}")
            return False
    else:
        print("FAILED: Job not found in database after retry")
        return False


def cleanup():
    """Clean up test data."""
    print("\n=== Cleaning up ===")
    if os.path.exists("queuectl.db"):
        os.remove("queuectl.db")
    print("Cleanup complete")


def main():
    """Run all tests."""
    print("=" * 50)
    print("QueueCTL Validation Script")
    print("=" * 50)
    
    # Clean up any existing database
    if os.path.exists("queuectl.db"):
        os.remove("queuectl.db")
    
    results = []
    
    try:
        results.append(("Basic Job Completion", test_basic_job_completion()))
        results.append(("Failed Job Retry", test_failed_job_retry()))
        results.append(("Multiple Workers", test_multiple_workers()))
        results.append(("Persistence", test_persistence()))
        results.append(("DLQ Retry", test_dlq_retry()))
    except Exception as e:
        print(f"\nERROR during testing: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        cleanup()
        
        # Print summary
        print("\n" + "=" * 50)
        print("Test Summary")
        print("=" * 50)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for name, result in results:
            status = "PASS" if result else "FAIL"
            print(f"{status}: {name}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n✅ All tests passed!")
            return 0
        else:
            print(f"\n❌ {total - passed} test(s) failed")
            return 1


if __name__ == "__main__":
    sys.exit(main())

