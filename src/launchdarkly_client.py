"""
LaunchDarkly Integration Client

This module provides functionality to:
- Retrieve feature flags from LaunchDarkly API
- Scan codebases for flag references
- Compare LaunchDarkly flags with codebase usage
- Identify stale or missing flags

API Documentation: https://apidocs.launchdarkly.com/
"""

import os
import re
import requests
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LaunchDarklyFlag:
    """Represents a feature flag from LaunchDarkly"""
    key: str
    name: str
    kind: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    archived: bool = False
    temporary: bool = False


@dataclass
class CodeReference:
    """Represents a reference to a flag in code"""
    flag_key: str
    file_path: str
    line_number: int
    line_content: str


@dataclass
class FlagComparison:
    """Comparison results between LaunchDarkly and codebase"""
    flags_in_ld_only: List[str]
    flags_in_code_only: List[str]
    flags_in_both: List[str]
    code_references: Dict[str, List[CodeReference]]


class LaunchDarklyClient:
    """
    Client for interacting with LaunchDarkly API and scanning codebases.
    
    Usage:
        client = LaunchDarklyClient(api_token="your-token", project_key="your-project")
        flags = client.get_flags()
        code_flags = client.scan_codebase("/path/to/repo")
        comparison = client.compare_flags(flags, code_flags)
    """
    
    BASE_URL = "https://app.launchdarkly.com/api/v2"
    
    def __init__(self, api_token: Optional[str] = None, project_key: Optional[str] = None):
        """
        Initialize the LaunchDarkly client.
        
        Args:
            api_token: LaunchDarkly API access token. If not provided, will look for 
                      LAUNCHDARKLY_API_TOKEN env var.
            project_key: LaunchDarkly project key. If not provided, will look for
                        LAUNCHDARKLY_PROJECT_KEY env var.
        
        Raises:
            ValueError: If no API token or project key is provided or found in environment.
        """
        self.api_token = api_token or os.getenv("LAUNCHDARKLY_API_TOKEN")
        if not self.api_token:
            raise ValueError(
                "API token required. Provide via api_token parameter or LAUNCHDARKLY_API_TOKEN env var. "
                "Get your API token from LaunchDarkly Account Settings > Authorization"
            )
        
        self.project_key = project_key or os.getenv("LAUNCHDARKLY_PROJECT_KEY")
        if not self.project_key:
            raise ValueError(
                "Project key required. Provide via project_key parameter or LAUNCHDARKLY_PROJECT_KEY env var."
            )
        
        self.headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json"
        }
    
    def get_flags(self, environment: Optional[str] = None) -> List[LaunchDarklyFlag]:
        """
        Retrieve all feature flags from LaunchDarkly for the configured project.
        
        Args:
            environment: Optional environment key to filter flags
        
        Returns:
            List of LaunchDarklyFlag objects
        
        Raises:
            requests.HTTPError: If the API request fails
        """
        url = f"{self.BASE_URL}/flags/{self.project_key}"
        params = {}
        
        if environment:
            params['env'] = environment
        
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        flags = []
        
        for item in data.get('items', []):
            flag = LaunchDarklyFlag(
                key=item['key'],
                name=item.get('name', ''),
                kind=item.get('kind', 'boolean'),
                description=item.get('description'),
                tags=item.get('tags', []),
                archived=item.get('archived', False),
                temporary=item.get('temporary', False)
            )
            flags.append(flag)
        
        return flags
    
    def scan_codebase(
        self, 
        repo_path: str, 
        file_patterns: Optional[List[str]] = None,
        flag_patterns: Optional[List[str]] = None
    ) -> Dict[str, List[CodeReference]]:
        """
        Scan a codebase for feature flag references.
        
        Args:
            repo_path: Path to the repository to scan
            file_patterns: List of glob patterns for files to scan (default: common code files)
            flag_patterns: List of regex patterns to match flag usage (default: common patterns)
        
        Returns:
            Dictionary mapping flag keys to lists of CodeReference objects
        """
        if file_patterns is None:
            file_patterns = [
                '**/*.js',
                '**/*.ts',
                '**/*.jsx',
                '**/*.tsx',
                '**/*.py',
                '**/*.java',
                '**/*.go',
                '**/*.rb',
                '**/*.php',
                '**/*.cs',
                '**/*.swift',
                '**/*.kt'
            ]
        
        if flag_patterns is None:
            flag_patterns = [
                r'ldClient\.variation\(["\']([^"\']+)["\']',
                r'client\.variation\(["\']([^"\']+)["\']',
                r'variation\(["\']([^"\']+)["\']',
                r'isEnabled\(["\']([^"\']+)["\']',
                r'getFlag\(["\']([^"\']+)["\']',
                r'checkFlag\(["\']([^"\']+)["\']',
                r'featureFlag\(["\']([^"\']+)["\']',
                r'["\']([a-z0-9\-]+)["\']',
            ]
        
        repo_path_obj = Path(repo_path)
        if not repo_path_obj.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        
        flag_references: Dict[str, List[CodeReference]] = {}
        compiled_patterns = [re.compile(pattern) for pattern in flag_patterns]
        
        for pattern in file_patterns:
            for file_path in repo_path_obj.glob(pattern):
                if file_path.is_file() and not self._should_skip_file(file_path):
                    self._scan_file(file_path, repo_path_obj, compiled_patterns, flag_references)
        
        return flag_references
    
    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if a file should be skipped during scanning"""
        skip_dirs = {
            'node_modules', '.git', 'dist', 'build', '__pycache__', 
            '.venv', 'venv', 'vendor', 'target', '.next', '.nuxt'
        }
        
        for part in file_path.parts:
            if part in skip_dirs:
                return True
        
        return False
    
    def _scan_file(
        self, 
        file_path: Path, 
        repo_root: Path, 
        patterns: List[re.Pattern],
        flag_references: Dict[str, List[CodeReference]]
    ):
        """Scan a single file for flag references"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, start=1):
                    for pattern in patterns:
                        matches = pattern.finditer(line)
                        for match in matches:
                            flag_key = match.group(1)
                            
                            if self._is_valid_flag_key(flag_key):
                                relative_path = file_path.relative_to(repo_root)
                                
                                ref = CodeReference(
                                    flag_key=flag_key,
                                    file_path=str(relative_path),
                                    line_number=line_num,
                                    line_content=line.strip()
                                )
                                
                                if flag_key not in flag_references:
                                    flag_references[flag_key] = []
                                flag_references[flag_key].append(ref)
        except Exception as e:
            pass
    
    def _is_valid_flag_key(self, key: str) -> bool:
        """Check if a string looks like a valid flag key"""
        if len(key) < 3 or len(key) > 100:
            return False
        
        if not re.match(r'^[a-z0-9\-_.]+$', key, re.IGNORECASE):
            return False
        
        common_false_positives = {
            'true', 'false', 'null', 'undefined', 'none', 'yes', 'no',
            'on', 'off', 'enabled', 'disabled', 'active', 'inactive',
            'id', 'key', 'name', 'type', 'value', 'data', 'error', 'success'
        }
        
        if key.lower() in common_false_positives:
            return False
        
        return True
    
    def compare_flags(
        self, 
        ld_flags: List[LaunchDarklyFlag], 
        code_references: Dict[str, List[CodeReference]]
    ) -> FlagComparison:
        """
        Compare flags from LaunchDarkly with flags found in code.
        
        Args:
            ld_flags: List of flags from LaunchDarkly
            code_references: Dictionary of flag references found in code
        
        Returns:
            FlagComparison object with the comparison results
        """
        ld_flag_keys = {flag.key for flag in ld_flags}
        code_flag_keys = set(code_references.keys())
        
        flags_in_ld_only = sorted(list(ld_flag_keys - code_flag_keys))
        flags_in_code_only = sorted(list(code_flag_keys - ld_flag_keys))
        flags_in_both = sorted(list(ld_flag_keys & code_flag_keys))
        
        return FlagComparison(
            flags_in_ld_only=flags_in_ld_only,
            flags_in_code_only=flags_in_code_only,
            flags_in_both=flags_in_both,
            code_references=code_references
        )
    
    def print_comparison_report(
        self, 
        comparison: FlagComparison,
        ld_flags: List[LaunchDarklyFlag],
        verbose: bool = False
    ):
        """
        Print a formatted comparison report.
        
        Args:
            comparison: FlagComparison object with comparison results
            ld_flags: List of LaunchDarklyFlag objects for additional details
            verbose: Whether to print detailed code references
        """
        print("\n" + "=" * 80)
        print("LAUNCHDARKLY FLAG COMPARISON REPORT")
        print("=" * 80)
        
        ld_flag_map = {flag.key: flag for flag in ld_flags}
        
        print(f"\n📊 SUMMARY")
        print(f"   Flags in LaunchDarkly only:  {len(comparison.flags_in_ld_only)}")
        print(f"   Flags in codebase only:      {len(comparison.flags_in_code_only)}")
        print(f"   Flags in both:               {len(comparison.flags_in_both)}")
        
        if comparison.flags_in_ld_only:
            print(f"\n⚠️  FLAGS IN LAUNCHDARKLY BUT NOT IN CODE ({len(comparison.flags_in_ld_only)})")
            print("   These flags may be stale and candidates for removal:")
            for flag_key in comparison.flags_in_ld_only:
                flag = ld_flag_map.get(flag_key)
                if flag:
                    status = " [ARCHIVED]" if flag.archived else ""
                    temp = " [TEMPORARY]" if flag.temporary else ""
                    print(f"   - {flag_key}{status}{temp}")
                    if flag.description:
                        print(f"     Description: {flag.description}")
        
        if comparison.flags_in_code_only:
            print(f"\n🔍 FLAGS IN CODE BUT NOT IN LAUNCHDARKLY ({len(comparison.flags_in_code_only)})")
            print("   These flags may be hardcoded or using a different system:")
            for flag_key in comparison.flags_in_code_only:
                refs = comparison.code_references.get(flag_key, [])
                print(f"   - {flag_key} ({len(refs)} reference{'s' if len(refs) != 1 else ''})")
                if verbose and refs:
                    for ref in refs[:3]:
                        print(f"     {ref.file_path}:{ref.line_number}")
                    if len(refs) > 3:
                        print(f"     ... and {len(refs) - 3} more")
        
        if comparison.flags_in_both:
            print(f"\n✅ FLAGS IN BOTH LAUNCHDARKLY AND CODE ({len(comparison.flags_in_both)})")
            if verbose:
                for flag_key in comparison.flags_in_both:
                    refs = comparison.code_references.get(flag_key, [])
                    flag = ld_flag_map.get(flag_key)
                    status = " [ARCHIVED]" if flag and flag.archived else ""
                    print(f"   - {flag_key}{status} ({len(refs)} reference{'s' if len(refs) != 1 else ''})")
            else:
                print("   Use --verbose to see details")
        
        print("\n" + "=" * 80 + "\n")


def main():
    """
    Example usage of the LaunchDarkly client.
    
    This demonstrates:
    1. Retrieving flags from LaunchDarkly
    2. Scanning a codebase for flag references
    3. Comparing and reporting differences
    """
    print("=" * 80)
    print("LaunchDarkly Integration Client - Demo")
    print("=" * 80)
    print()
    
    api_token = os.getenv("LAUNCHDARKLY_API_TOKEN")
    project_key = os.getenv("LAUNCHDARKLY_PROJECT_KEY")
    repo_path = os.getenv("REPO_PATH", ".")
    
    if not api_token:
        print("ERROR: LAUNCHDARKLY_API_TOKEN environment variable not set")
        print("Get your API token from: LaunchDarkly Account Settings > Authorization")
        print()
        print("Set it with: export LAUNCHDARKLY_API_TOKEN='your-token-here'")
        return
    
    if not project_key:
        print("ERROR: LAUNCHDARKLY_PROJECT_KEY environment variable not set")
        print()
        print("Set it with: export LAUNCHDARKLY_PROJECT_KEY='your-project-key'")
        return
    
    try:
        client = LaunchDarklyClient(api_token=api_token, project_key=project_key)
        print("✓ LaunchDarkly client initialized")
        print(f"  Project: {project_key}")
        print()
        
        print("Retrieving flags from LaunchDarkly...")
        ld_flags = client.get_flags()
        print(f"✓ Retrieved {len(ld_flags)} flags from LaunchDarkly")
        print()
        
        print(f"Scanning codebase at: {repo_path}")
        code_references = client.scan_codebase(repo_path)
        unique_flags = len(code_references)
        total_refs = sum(len(refs) for refs in code_references.values())
        print(f"✓ Found {unique_flags} unique flags with {total_refs} total references")
        print()
        
        print("Comparing flags...")
        comparison = client.compare_flags(ld_flags, code_references)
        
        client.print_comparison_report(comparison, ld_flags, verbose=True)
        
    except requests.HTTPError as e:
        print(f"API Error: {e}")
        if hasattr(e, 'response'):
            print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
