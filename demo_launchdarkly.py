#!/usr/bin/env python3
"""
Demo script for LaunchDarkly integration.

This script demonstrates how to:
1. Retrieve flags from LaunchDarkly API
2. Scan a codebase for flag references
3. Compare and identify differences

Usage:
    export LAUNCHDARKLY_API_TOKEN='your-token'
    export LAUNCHDARKLY_PROJECT_KEY='your-project-key'
    python3 demo_launchdarkly.py /path/to/repo
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from launchdarkly_client import LaunchDarklyClient


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 demo_launchdarkly.py <repo_path>")
        print()
        print("Example:")
        print("  export LAUNCHDARKLY_API_TOKEN='your-token'")
        print("  export LAUNCHDARKLY_PROJECT_KEY='your-project-key'")
        print("  python3 demo_launchdarkly.py /path/to/checkout_system")
        sys.exit(1)
    
    repo_path = sys.argv[1]
    
    print("=" * 80)
    print("LaunchDarkly Integration Demo")
    print("=" * 80)
    print()
    
    api_token = os.getenv("LAUNCHDARKLY_API_TOKEN")
    project_key = os.getenv("LAUNCHDARKLY_PROJECT_KEY")
    
    if not api_token:
        print("ERROR: LAUNCHDARKLY_API_TOKEN environment variable not set")
        print("Get your API token from: LaunchDarkly Account Settings > Authorization")
        print()
        print("Set it with: export LAUNCHDARKLY_API_TOKEN='your-token-here'")
        sys.exit(1)
    
    if not project_key:
        print("ERROR: LAUNCHDARKLY_PROJECT_KEY environment variable not set")
        print()
        print("Set it with: export LAUNCHDARKLY_PROJECT_KEY='your-project-key'")
        sys.exit(1)
    
    try:
        client = LaunchDarklyClient(api_token=api_token, project_key=project_key)
        print(f"✓ LaunchDarkly client initialized")
        print(f"  Project: {project_key}")
        print()
        
        print("Step 1: Retrieving flags from LaunchDarkly...")
        ld_flags = client.get_flags()
        print(f"✓ Retrieved {len(ld_flags)} flags from LaunchDarkly")
        
        if ld_flags:
            print("\nSample flags:")
            for flag in ld_flags[:5]:
                print(f"  - {flag.key} ({flag.kind})")
                if flag.description:
                    print(f"    {flag.description}")
        print()
        
        print(f"Step 2: Scanning codebase at: {repo_path}")
        code_references = client.scan_codebase(repo_path)
        unique_flags = len(code_references)
        total_refs = sum(len(refs) for refs in code_references.values())
        print(f"✓ Found {unique_flags} unique flags with {total_refs} total references")
        
        if code_references:
            print("\nSample code references:")
            for flag_key, refs in list(code_references.items())[:5]:
                print(f"  - {flag_key}: {len(refs)} reference(s)")
                if refs:
                    print(f"    {refs[0].file_path}:{refs[0].line_number}")
        print()
        
        print("Step 3: Comparing flags...")
        comparison = client.compare_flags(ld_flags, code_references)
        
        client.print_comparison_report(comparison, ld_flags, verbose=True)
        
        print("Demo completed successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
