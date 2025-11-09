"""CLI interface for QueueCTL."""
import click
import json
import os
import sys
from tabulate import tabulate
from .storage import JobStorage
from .worker import WorkerManager


# Global storage instance
storage = None
worker_manager = None


def get_storage():
    """Get or create storage instance."""
    global storage
    if storage is None:
        storage = JobStorage()
    return storage


def get_worker_manager():
    """Get or create worker manager instance."""
    global worker_manager
    if worker_manager is None:
        worker_manager = WorkerManager(get_storage())
    return worker_manager


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """QueueCTL - CLI-based background job queue system."""
    pass


@cli.command()
@click.argument('job_data', type=str)
def enqueue(job_data):
    """Enqueue a new job.
    
    JOB_DATA: JSON string with job details, e.g. '{"id":"job1","command":"sleep 2"}'
    """
    try:
        data = json.loads(job_data)
        job_id = data.get("id")
        command = data.get("command")
        max_retries = data.get("max_retries")  # None if not specified, will use config default
        
        if not job_id or not command:
            click.echo("Error: 'id' and 'command' are required fields", err=True)
            sys.exit(1)
        
        storage = get_storage()
        
        # Check if job already exists
        existing = storage.get_job(job_id)
        if existing:
            click.echo(f"Error: Job '{job_id}' already exists", err=True)
            sys.exit(1)
        
        # create_job will use config default if max_retries is None
        job = storage.create_job(job_id, command, max_retries)
        click.echo(f"Job '{job_id}' enqueued successfully")
        click.echo(f"  Command: {command}")
        click.echo(f"  Max retries: {job['max_retries']}")
        
    except json.JSONDecodeError:
        click.echo("Error: Invalid JSON format", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.group()
def worker():
    """Manage worker processes."""
    pass


@worker.command()
@click.option('--count', default=1, type=int, help='Number of workers to start')
def start(count):
    """Start worker processes."""
    if count < 1:
        click.echo("Error: Worker count must be at least 1", err=True)
        sys.exit(1)
    
    manager = get_worker_manager()
    
    if manager.processes:
        click.echo("Error: Workers are already running. Stop them first.", err=True)
        sys.exit(1)
    
    manager.start_workers(count)
    click.echo(f"Started {count} worker(s)")


@worker.command()
def stop():
    """Stop all running worker processes gracefully."""
    manager = get_worker_manager()
    manager.stop_workers()


@cli.command()
def status():
    """Show summary of all job states and active workers."""
    storage = get_storage()
    manager = get_worker_manager()
    
    # Get job statistics
    stats = storage.get_job_stats()
    
    # Count active workers
    active_workers = sum(1 for p in manager.processes if p.is_alive()) if manager.processes else 0
    
    # Display status
    click.echo("\n=== Queue Status ===")
    click.echo(f"Active Workers: {active_workers}")
    click.echo("\nJob States:")
    
    table = [
        ["Pending", stats["pending"]],
        ["Processing", stats["processing"]],
        ["Completed", stats["completed"]],
        ["Failed", stats["failed"]],
        ["Dead (DLQ)", stats["dead"]],
    ]
    
    click.echo(tabulate(table, headers=["State", "Count"], tablefmt="simple"))
    
    total = sum(stats.values())
    click.echo(f"\nTotal Jobs: {total}")


@cli.command()
@click.option('--state', type=click.Choice(['pending', 'processing', 'completed', 'failed', 'dead'], case_sensitive=False),
              help='Filter jobs by state')
def list(state):
    """List jobs, optionally filtered by state."""
    storage = get_storage()
    jobs = storage.list_jobs(state)
    
    if not jobs:
        state_msg = f" with state '{state}'" if state else ""
        click.echo(f"No jobs found{state_msg}")
        return
    
    # Prepare table data
    table_data = []
    for job in jobs:
        table_data.append([
            job["id"],
            job["command"][:50] + ("..." if len(job["command"]) > 50 else ""),
            job["state"],
            f"{job['attempts']}/{job['max_retries']}",
            job["created_at"][:19] + "Z",
        ])
    
    headers = ["ID", "Command", "State", "Attempts", "Created At"]
    click.echo(tabulate(table_data, headers=headers, tablefmt="simple"))


@cli.group()
def dlq():
    """Manage Dead Letter Queue."""
    pass


@dlq.command()
def list():
    """List all jobs in the Dead Letter Queue."""
    storage = get_storage()
    jobs = storage.list_jobs("dead")
    
    if not jobs:
        click.echo("No jobs in Dead Letter Queue")
        return
    
    table_data = []
    for job in jobs:
        table_data.append([
            job["id"],
            job["command"][:50] + ("..." if len(job["command"]) > 50 else ""),
            job["attempts"],
            job["created_at"][:19] + "Z",
            job["updated_at"][:19] + "Z",
        ])
    
    headers = ["ID", "Command", "Attempts", "Created At", "Last Updated"]
    click.echo(tabulate(table_data, headers=headers, tablefmt="simple"))


@dlq.command()
@click.argument('job_id', type=str)
def retry(job_id):
    """Retry a job from the Dead Letter Queue."""
    storage = get_storage()
    job = storage.get_job(job_id)
    
    if not job:
        click.echo(f"Error: Job '{job_id}' not found", err=True)
        sys.exit(1)
    
    if job["state"] != "dead":
        click.echo(f"Error: Job '{job_id}' is not in DLQ (current state: {job['state']})", err=True)
        sys.exit(1)
    
    # Reset job to pending with fresh attempts
    storage.update_job_state(job_id, "pending", attempts=0)
    click.echo(f"Job '{job_id}' moved back to pending queue")


@cli.group()
def config():
    """Manage configuration."""
    pass


@config.command()
@click.argument('key', type=str)
@click.argument('value', type=str)
def set(key, value):
    """Set a configuration value.
    
    KEY: Configuration key (e.g., 'max-retries', 'backoff-base')
    VALUE: Configuration value
    """
    storage = get_storage()
    
    # Normalize key names
    key_map = {
        "max-retries": "max_retries",
        "max_retries": "max_retries",
        "backoff-base": "backoff_base",
        "backoff_base": "backoff_base",
    }
    
    normalized_key = key_map.get(key, key)
    
    # Validate value for numeric configs
    if normalized_key in ["max_retries"]:
        try:
            int(value)
        except ValueError:
            click.echo(f"Error: '{key}' must be an integer", err=True)
            sys.exit(1)
    elif normalized_key in ["backoff_base"]:
        try:
            float(value)
        except ValueError:
            click.echo(f"Error: '{key}' must be a number", err=True)
            sys.exit(1)
    
    storage.set_config(normalized_key, value)
    click.echo(f"Configuration '{key}' set to '{value}'")


@config.command()
@click.argument('key', type=str, required=False)
def get(key):
    """Get configuration value(s).
    
    KEY: Configuration key (optional, shows all if omitted)
    """
    storage = get_storage()
    
    if key:
        # Normalize key name
        key_map = {
            "max-retries": "max_retries",
            "max_retries": "max_retries",
            "backoff-base": "backoff_base",
            "backoff_base": "backoff_base",
        }
        normalized_key = key_map.get(key, key)
        value = storage.get_config(normalized_key)
        
        if value:
            click.echo(f"{key}: {value}")
        else:
            click.echo(f"Configuration '{key}' not found", err=True)
            sys.exit(1)
    else:
        # Show all config
        max_retries = storage.get_config("max_retries", "3")
        backoff_base = storage.get_config("backoff_base", "2")
        
        click.echo("Current Configuration:")
        click.echo(f"  max-retries: {max_retries}")
        click.echo(f"  backoff-base: {backoff_base}")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()

