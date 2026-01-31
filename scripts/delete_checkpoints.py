#!/usr/bin/env python3
"""
Script to delete all Tinker checkpoints.

This script will:
1. List all your training runs
2. Show checkpoints for each run
3. Delete them (with confirmation)

Usage:
    python scripts/delete_tinker_checkpoints.py           # Interactive mode with confirmation
    python scripts/delete_tinker_checkpoints.py --dry-run # List checkpoints without deleting
    python scripts/delete_tinker_checkpoints.py --yes     # Delete without confirmation
"""

from dotenv import load_dotenv
load_dotenv()

import argparse
import sys
from typing import Optional

try:
    import tinker
except ImportError:
    print("Error: tinker package is not installed.")
    print("Install it with: pip install tinker")
    sys.exit(1)


def get_service_client() -> tinker.ServiceClient:
    """Create and return a Tinker ServiceClient."""
    try:
        return tinker.ServiceClient()
    except Exception as e:
        print(f"Error creating ServiceClient: {e}")
        print("Make sure TINKER_API_KEY environment variable is set.")
        sys.exit(1)


def list_training_runs(rest_client, service_client) -> list:
    """List all training runs (returns TrainingRun objects)."""
    try:
        # Try various method names that might exist
        methods_to_try = [
            ('rest_client', 'list_training_runs'),
            ('rest_client', 'list_runs'),
            ('rest_client', 'get_training_runs'),
            ('service_client', 'list_training_runs'),
        ]
        
        for client_name, method_name in methods_to_try:
            client = rest_client if client_name == 'rest_client' else service_client
            if hasattr(client, method_name):
                method = getattr(client, method_name)
                result = method()
                # Handle Future objects
                if hasattr(result, 'result'):
                    result = result.result()
                
                # Return the list of TrainingRun objects
                if isinstance(result, list):
                    return result
                
                # Handle TrainingRunsResponse or similar wrapper objects
                # Try common attribute names for the actual list
                for attr in ['training_runs', 'runs', 'data', 'items']:
                    if hasattr(result, attr):
                        items = getattr(result, attr)
                        if isinstance(items, list):
                            return items
                
                # Debug: show what attributes are available
                print(f"Found method {client_name}.{method_name}(), result type: {type(result)}")
                print(f"  Available attributes: {[a for a in dir(result) if not a.startswith('_')]}")
                return []
        
        print("No method found to list training runs.")
        print(f"Available RestClient methods: {[m for m in dir(rest_client) if not m.startswith('_')]}")
        print(f"Available ServiceClient methods: {[m for m in dir(service_client) if not m.startswith('_')]}")
        return []
        
    except Exception as e:
        print(f"Error listing training runs: {e}")
        return []


def get_run_id(run) -> str:
    """Extract the training run ID from a TrainingRun object or string."""
    if isinstance(run, str):
        return run
    if hasattr(run, 'training_run_id'):
        return run.training_run_id
    if hasattr(run, 'id'):
        return run.id
    return str(run)


def get_checkpoints_from_run(run) -> list[str]:
    """
    Extract checkpoint paths from a TrainingRun object.
    
    TrainingRun objects have last_checkpoint and last_sampler_checkpoint fields
    that contain Checkpoint objects with tinker_path.
    """
    checkpoints = []
    
    # Extract from last_checkpoint
    if hasattr(run, 'last_checkpoint') and run.last_checkpoint is not None:
        cp = run.last_checkpoint
        if hasattr(cp, 'tinker_path') and cp.tinker_path:
            checkpoints.append(cp.tinker_path)
    
    # Extract from last_sampler_checkpoint
    if hasattr(run, 'last_sampler_checkpoint') and run.last_sampler_checkpoint is not None:
        cp = run.last_sampler_checkpoint
        if hasattr(cp, 'tinker_path') and cp.tinker_path:
            checkpoints.append(cp.tinker_path)
    
    return checkpoints


def list_all_user_checkpoints(rest_client) -> list[str]:
    """
    List ALL checkpoints for the current user using list_user_checkpoints.
    
    Returns list of checkpoint paths (tinker:// URIs).
    """
    checkpoints = []
    
    try:
        if hasattr(rest_client, 'list_user_checkpoints'):
            future = rest_client.list_user_checkpoints()
            result = future.result() if hasattr(future, 'result') else future
            
            # Handle different response formats
            items = []
            if isinstance(result, list):
                items = result
            elif hasattr(result, 'checkpoints'):
                items = result.checkpoints
            elif hasattr(result, 'data'):
                items = result.data
            
            for cp in items:
                if hasattr(cp, 'tinker_path') and cp.tinker_path:
                    checkpoints.append(cp.tinker_path)
                elif isinstance(cp, str):
                    checkpoints.append(cp)
                        
    except Exception as e:
        print(f"Warning: list_user_checkpoints failed: {e}")
    
    return checkpoints


def list_checkpoints_for_run(rest_client, run_id: str) -> list[str]:
    """
    List checkpoints for a specific training run.
    
    Returns list of checkpoint paths (tinker:// URIs).
    """
    checkpoints = []
    
    try:
        if hasattr(rest_client, 'list_checkpoints'):
            future = rest_client.list_checkpoints(training_run_id=run_id)
            result = future.result() if hasattr(future, 'result') else future
            
            items = []
            if isinstance(result, list):
                items = result
            elif hasattr(result, 'checkpoints'):
                items = result.checkpoints
            
            for cp in items:
                if hasattr(cp, 'tinker_path') and cp.tinker_path:
                    checkpoints.append(cp.tinker_path)
                elif isinstance(cp, str):
                    checkpoints.append(cp)
                        
    except Exception as e:
        if '404' not in str(e):
            print(f"  Warning: list_checkpoints failed: {e}")
    
    return checkpoints


def parse_tinker_path(tinker_path: str) -> tuple[str, str]:
    """
    Parse a tinker:// path into (training_run_id, checkpoint_id).
    
    Example: tinker://a1fa1970-4c31-5654-817a-69145bc22b91:train:0/sampler_weights/name.model
    Returns: ('a1fa1970-4c31-5654-817a-69145bc22b91:train:0', 'sampler_weights/name.model')
    """
    # Remove tinker:// prefix
    path = tinker_path.replace('tinker://', '')
    
    # Split on first / after the run ID (which contains colons)
    # Format: <uuid>:train:<n>/<checkpoint_type>/<checkpoint_name>
    # Find the position after :train:N
    parts = path.split('/')
    
    # The run_id is the first part (contains uuid:train:n)
    run_id = parts[0]
    
    # The checkpoint_id is everything after the first /
    checkpoint_id = '/'.join(parts[1:])
    
    return run_id, checkpoint_id


def delete_checkpoint(rest_client, checkpoint_path: str, dry_run: bool = False) -> bool:
    """
    Delete a single checkpoint.
    
    Returns True if deletion was successful (or simulated in dry-run mode).
    """
    if dry_run:
        print(f"  [DRY RUN] Would delete: {checkpoint_path}")
        return True
    
    try:
        # Use delete_checkpoint_from_tinker_path (takes full tinker:// path)
        if hasattr(rest_client, 'delete_checkpoint_from_tinker_path'):
            future = rest_client.delete_checkpoint_from_tinker_path(checkpoint_path)
            if hasattr(future, 'result'):
                future.result()
            print(f"  Deleted: {checkpoint_path}")
            return True
        
        # Fallback: parse path and use delete_checkpoint(run_id, checkpoint_id)
        elif hasattr(rest_client, 'delete_checkpoint'):
            run_id, checkpoint_id = parse_tinker_path(checkpoint_path)
            future = rest_client.delete_checkpoint(run_id, checkpoint_id)
            if hasattr(future, 'result'):
                future.result()
            print(f"  Deleted: {checkpoint_path}")
            return True
        
        else:
            print(f"  Error: No delete method found in REST client")
            return False
            
    except Exception as e:
        print(f"  Error deleting {checkpoint_path}: {e}")
        return False


def delete_training_run(rest_client, run_id: str, dry_run: bool = False) -> bool:
    """
    Delete an entire training run and all its checkpoints.
    
    Returns True if deletion was successful.
    """
    if dry_run:
        print(f"  [DRY RUN] Would delete training run: {run_id}")
        return True
    
    try:
        # Try various deletion methods
        
        # Method 1: delete_training_run
        if hasattr(rest_client, 'delete_training_run'):
            future = rest_client.delete_training_run(run_id)
            future.result()
            print(f"  Deleted training run: {run_id}")
            return True
        
        # Method 2: delete_run
        elif hasattr(rest_client, 'delete_run'):
            future = rest_client.delete_run(run_id)
            future.result()
            print(f"  Deleted training run: {run_id}")
            return True
        
        else:
            print(f"  No delete_training_run method found, will try to delete checkpoints individually")
            return False
            
    except Exception as e:
        print(f"  Error deleting training run {run_id}: {e}")
        return False


def inspect_clients(service_client, rest_client) -> None:
    """Print available methods on the clients for debugging."""
    print("\nAvailable ServiceClient methods:")
    methods = [m for m in dir(service_client) if not m.startswith('_')]
    for method in sorted(methods):
        print(f"  - {method}")
    
    print("\nAvailable RestClient methods:")
    methods = [m for m in dir(rest_client) if not m.startswith('_')]
    for method in sorted(methods):
        print(f"  - {method}")
    
    # Try to get a sample training run and show its structure
    print("\n\nTrying to fetch sample training run...")
    try:
        result = rest_client.list_training_runs()
        if hasattr(result, 'result'):
            result = result.result()
        
        # Get the actual list
        runs = None
        for attr in ['training_runs', 'runs', 'data', 'items']:
            if hasattr(result, attr):
                runs = getattr(result, attr)
                break
        
        if runs and len(runs) > 0:
            run = runs[0]
            run_id = run.training_run_id if hasattr(run, 'training_run_id') else str(run)
            print(f"\nSample TrainingRun attributes for {run_id}:")
            for attr in dir(run):
                if not attr.startswith('_'):
                    try:
                        val = getattr(run, attr)
                        if not callable(val):
                            print(f"  - {attr}: {type(val).__name__} = {repr(val)[:100]}")
                    except:
                        pass
            
            # Try to list checkpoints for this run
            print(f"\nTrying list_checkpoints for {run_id}...")
            try:
                cp_result = rest_client.list_checkpoints(training_run_id=run_id)
                if hasattr(cp_result, 'result'):
                    cp_result = cp_result.result()
                print(f"  Result type: {type(cp_result)}")
                print(f"  Result attributes: {[a for a in dir(cp_result) if not a.startswith('_')]}")
                
                # Try to get checkpoints
                for attr in ['checkpoints', 'data', 'items']:
                    if hasattr(cp_result, attr):
                        items = getattr(cp_result, attr)
                        print(f"  {attr}: {len(items) if isinstance(items, list) else items}")
                        if isinstance(items, list) and len(items) > 0:
                            print(f"  Sample item: {items[0]}")
                        break
            except Exception as e:
                print(f"  Error: {e}")
    except Exception as e:
        print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Delete all Tinker checkpoints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="List checkpoints without deleting them"
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true", 
        help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Print available REST client methods and exit"
    )
    parser.add_argument(
        "--run-id",
        type=str,
        help="Only delete checkpoints from a specific training run"
    )
    
    args = parser.parse_args()
    
    # Create clients
    print("Connecting to Tinker...")
    service_client = get_service_client()
    rest_client = service_client.create_rest_client()
    
    # Inspect mode
    if args.inspect:
        inspect_clients(service_client, rest_client)
        return
    
    # List checkpoints
    print("\nFetching checkpoints...")
    
    if args.run_id:
        # Get checkpoints for a specific run
        all_checkpoints = list_checkpoints_for_run(rest_client, args.run_id)
        print(f"\nCheckpoints for run {args.run_id}:")
    else:
        # Get ALL user checkpoints (this matches what the dashboard shows)
        all_checkpoints = list_all_user_checkpoints(rest_client)
        print(f"\nAll checkpoints:")
    
    if all_checkpoints:
        for cp_path in all_checkpoints:
            print(f"  - {cp_path}")
    else:
        print("  (none found)")
    
    total_checkpoints = len(all_checkpoints)
    
    if total_checkpoints == 0:
        print("\nNo checkpoints found to delete.")
        return
    
    # Confirmation
    if not args.dry_run and not args.yes:
        print(f"\n{'='*60}")
        print(f"About to delete {total_checkpoints} checkpoint(s).")
        print(f"{'='*60}")
        response = input("\nAre you sure you want to proceed? [y/N] ")
        if response.lower() not in ('y', 'yes'):
            print("Aborted.")
            return
    
    # Delete
    print("\n" + ("=" * 60))
    print("DELETING" + (" (DRY RUN)" if args.dry_run else ""))
    print("=" * 60)
    
    deleted = 0
    failed = 0
    
    for cp_path in all_checkpoints:
        if delete_checkpoint(rest_client, cp_path, args.dry_run):
            deleted += 1
        else:
            failed += 1
    
    # Summary
    print("\n" + ("=" * 60))
    print("SUMMARY")
    print("=" * 60)
    if args.dry_run:
        print(f"Would delete: {deleted} checkpoint(s)")
    else:
        print(f"Deleted: {deleted} checkpoint(s)")
        if failed > 0:
            print(f"Failed: {failed} checkpoint(s)")
    
    if failed > 0:
        print("\nNote: Some deletions failed. Check errors above.")


if __name__ == "__main__":
    main()
