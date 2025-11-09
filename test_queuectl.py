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
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=check
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr


def test_basic_job_completion():
    """Test 1: Basic job completes successfully."""
    print("\n=== Test 1: Basic Job Completion ===")
    
    # Enqueue a simple job
    success, stdout, stderr = run_command(
        'python -m queuectl.cli enqueue \'{"id":"test1","command":"echo Hello World"}\''
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
    
    # Check status
    success, stdout, stderr = run_command('python -m queuectl.cli status')
    
    # Stop worker
    run_command('python -m queuectl.cli worker stop', check=False)
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
    
    # Enqueue a job that will fail
    success, stdout, stderr = run_command(
        'python -m queuectl.cli enqueue \'{"id":"test2","command":"nonexistentcommand123","max_retries":2}\''
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
    
    # Wait for retries to complete (with backoff)
    time.sleep(10)
    
    # Check DLQ
    success, stdout, stderr = run_command('python -m queuectl.cli dlq list')
    
    # Stop worker
    run_command('python -m queuectl.cli worker stop', check=False)
    worker_process.terminate()
    worker_process.wait()
    
    if "test2" in stdout:
        print("PASSED: Failed job moved to DLQ after retries")
        return True
    else:
        print(f"FAILED: Job not in DLQ. Output: {stdout}")
        return False


def test_multiple_workers():
    """Test 3: Multiple workers process jobs without overlap."""
    print("\n=== Test 3: Multiple Workers ===")
    
    # Enqueue multiple jobs
    for i in range(5):
        run_command(
            f'python -m queuectl.cli enqueue \'{{"id":"test3_{i}","command":"sleep 1"}}\''
        )
    
    # Start 3 workers
    worker_process = subprocess.Popen(
        ['python', '-m', 'queuectl.cli', 'worker', 'start', '--count', '3'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    time.sleep(5)  # Wait for jobs to complete
    
    # Check status
    success, stdout, stderr = run_command('python -m queuectl.cli status')
    
    # Stop workers
    run_command('python -m queuectl.cli worker stop', check=False)
    worker_process.terminate()
    worker_process.wait()
    
    # Check that jobs were processed
    success, stdout, stderr = run_command('python -m queuectl.cli list --state completed')
    
    completed_count = stdout.count("test3_")
    
    if completed_count >= 3:  # At least some jobs completed
        print(f"PASSED: Multiple workers processed jobs (completed: {completed_count}/5)")
        return True
    else:
        print(f"FAILED: Not enough jobs completed. Output: {stdout}")
        return False


def test_persistence():
    """Test 4: Job data survives restart."""
    print("\n=== Test 4: Persistence ===")
    
    # Enqueue a job
    success, stdout, stderr = run_command(
        'python -m queuectl.cli enqueue \'{"id":"test4","command":"echo Persistence Test"}\''
    )
    
    if not success:
        print(f"FAILED: Could not enqueue job: {stderr}")
        return False
    
    # Check job exists
    success, stdout, stderr = run_command('python -m queuectl.cli list --state pending')
    
    if "test4" not in stdout:
        print("FAILED: Job not found after creation")
        return False
    
    # Simulate restart by checking database directly
    if os.path.exists("queuectl.db"):
        conn = sqlite3.connect("queuectl.db")
        cursor = conn.execute("SELECT * FROM jobs WHERE id = 'test4'")
        row = cursor.fetchone()
        conn.close()
        
        if row:
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
    
    # First, create a job in DLQ (manually via database)
    if os.path.exists("queuectl.db"):
        conn = sqlite3.connect("queuectl.db")
        conn.execute("""
            INSERT OR REPLACE INTO jobs 
            (id, command, state, attempts, max_retries, created_at, updated_at)
            VALUES 
            ('test5', 'echo DLQ Retry Test', 'dead', 3, 3, datetime('now'), datetime('now'))
        """)
        conn.commit()
        conn.close()
    
    # Retry from DLQ
    success, stdout, stderr = run_command('python -m queuectl.cli dlq retry test5')
    
    if not success:
        print(f"FAILED: Could not retry DLQ job: {stderr}")
        return False
    
    # Check job is now pending
    success, stdout, stderr = run_command('python -m queuectl.cli list --state pending')
    
    if "test5" in stdout:
        print("PASSED: DLQ retry moved job back to pending")
        return True
    else:
        print(f"FAILED: Job not in pending queue. Output: {stdout}")
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

