"""Worker process implementation."""
import subprocess
import time
import signal
import sys
import os
from datetime import datetime
from typing import Optional
from .storage import JobStorage


class Worker:
    """Worker process that executes jobs."""
    
    def __init__(self, worker_id: str, storage: JobStorage, backoff_base: float = 2.0):
        self.worker_id = worker_id
        self.storage = storage
        self.backoff_base = backoff_base
        self.running = True
        self.current_job = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        print(f"\n[Worker {self.worker_id}] Received shutdown signal. Finishing current job...")
        self.running = False
    
    def _calculate_backoff(self, attempts: int) -> float:
        """Calculate exponential backoff delay."""
        return self.backoff_base ** attempts
    
    def _execute_command(self, command: str):
        """Execute a shell command and return (success, output)."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Command timed out after 5 minutes"
        except Exception as e:
            return False, str(e)
    
    def process_job(self, job: dict) -> bool:
        """Process a single job. Returns True if job was processed successfully."""
        job_id = job["id"]
        command = job["command"]
        attempts = job["attempts"]
        max_retries = job["max_retries"]
        
        print(f"[Worker {self.worker_id}] Processing job {job_id}: {command}")
        
        # Execute the command
        success, output = self._execute_command(command)
        
        if success:
            # Job completed successfully
            self.storage.update_job_state(job_id, "completed")
            print(f"[Worker {self.worker_id}] Job {job_id} completed successfully")
            return True
        else:
            # Job failed
            new_attempts = self.storage.increment_attempts(job_id)
            print(f"[Worker {self.worker_id}] Job {job_id} failed (attempt {new_attempts}/{max_retries}): {output[:100]}")
            
            if new_attempts >= max_retries:
                # Move to DLQ
                self.storage.update_job_state(job_id, "dead")
                print(f"[Worker {self.worker_id}] Job {job_id} moved to DLQ after {new_attempts} attempts")
            else:
                # Mark as failed for retry
                # Calculate backoff delay
                delay = self._calculate_backoff(new_attempts)
                # Calculate retry time
                retry_time = datetime.utcnow()
                retry_time = retry_time.replace(microsecond=0)
                retry_time = retry_time.timestamp() + delay
                retry_at = datetime.fromtimestamp(retry_time).isoformat() + "Z"
                
                self.storage.update_job_state(job_id, "failed", retry_at=retry_at)
                print(f"[Worker {self.worker_id}] Job {job_id} will retry after {delay:.2f} seconds")
            
            return False
    
    def run(self):
        """Main worker loop."""
        print(f"[Worker {self.worker_id}] Started")
        
        while self.running:
            # Get next pending job
            job = self.storage.get_next_pending_job(self.worker_id)
            
            if job:
                self.current_job = job
                self.process_job(job)
                self.current_job = None
            else:
                # No jobs available, wait a bit
                time.sleep(0.5)
        
        # If we have a current job, finish it before exiting
        if self.current_job:
            print(f"[Worker {self.worker_id}] Finishing current job before shutdown...")
            self.process_job(self.current_job)
        
        print(f"[Worker {self.worker_id}] Stopped")


class WorkerManager:
    """Manages multiple worker processes."""
    
    def __init__(self, storage: JobStorage):
        self.storage = storage
        self.workers = []
        self.processes = []
    
    def start_workers(self, count: int):
        """Start multiple worker processes."""
        import multiprocessing
        
        backoff_base = float(self.storage.get_config("backoff_base", "2.0"))
        
        for i in range(count):
            worker_id = f"worker-{i+1}"
            process = multiprocessing.Process(
                target=self._worker_process,
                args=(worker_id, backoff_base)
            )
            process.start()
            self.processes.append(process)
            print(f"Started {worker_id} (PID: {process.pid})")
    
    def _worker_process(self, worker_id: str, backoff_base: float):
        """Worker process entry point."""
        worker = Worker(worker_id, self.storage, backoff_base)
        worker.run()
    
    def stop_workers(self):
        """Stop all worker processes gracefully."""
        if not self.processes:
            print("No workers running")
            return
        
        print(f"Stopping {len(self.processes)} workers...")
        
        # Send SIGTERM to all processes
        for process in self.processes:
            if process.is_alive():
                process.terminate()
        
        # Wait for graceful shutdown (max 30 seconds)
        for process in self.processes:
            process.join(timeout=30)
            if process.is_alive():
                print(f"Force killing worker {process.pid}")
                process.kill()
                process.join()
        
        self.processes = []
        print("All workers stopped")

