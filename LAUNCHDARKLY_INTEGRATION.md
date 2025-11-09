# LaunchDarkly Integration

This document describes the LaunchDarkly integration functionality added to DevinAutomation.

## Overview

The LaunchDarkly integration allows you to:

1. **Retrieve feature flags** from LaunchDarkly via REST API
2. **Scan codebases** for feature flag references
3. **Compare and identify differences** between LaunchDarkly flags and code usage
4. **Identify stale flags** that exist in LaunchDarkly but are no longer referenced in code

This functionality is useful for:
- Finding feature flags that can be safely removed
- Identifying flags that are referenced in code but missing from LaunchDarkly
- Auditing feature flag usage across your codebase

## Installation

The LaunchDarkly client is included in the `src/` directory and requires only the `requests` library:

```bash
pip install -r requirements.txt
```

## Configuration

The LaunchDarkly client requires two pieces of configuration:

### 1. API Access Token

Get your API access token from LaunchDarkly:
1. Go to **Account Settings > Authorization** in LaunchDarkly
2. Create a new **Personal Access Token** or **Service Token**
3. Give it **read** permissions for feature flags

Set the token as an environment variable:

```bash
export LAUNCHDARKLY_API_TOKEN='your-api-token-here'
```

### 2. Project Key

Find your project key in LaunchDarkly:
1. Go to your project settings
2. Copy the **Project Key** (e.g., `default`, `my-project`)

Set the project key as an environment variable:

```bash
export LAUNCHDARKLY_PROJECT_KEY='your-project-key'
```

## Usage

### Quick Start with Demo Script

The easiest way to test the integration is with the demo script:

```bash
# Set your credentials
export LAUNCHDARKLY_API_TOKEN='your-token'
export LAUNCHDARKLY_PROJECT_KEY='your-project-key'

# Run the demo on a repository
python3 demo_launchdarkly.py /path/to/your/repo
```

Example with the checkout_system repository:

```bash
python3 demo_launchdarkly.py ../checkout_system
```

### Using the LaunchDarkly Client in Code

```python
from src.launchdarkly_client import LaunchDarklyClient

# Initialize the client
client = LaunchDarklyClient(
    api_token='your-token',
    project_key='your-project-key'
)

# Retrieve flags from LaunchDarkly
ld_flags = client.get_flags()
print(f"Found {len(ld_flags)} flags in LaunchDarkly")

# Scan a codebase for flag references
code_references = client.scan_codebase('/path/to/repo')
print(f"Found {len(code_references)} unique flags in code")

# Compare and generate report
comparison = client.compare_flags(ld_flags, code_references)
client.print_comparison_report(comparison, ld_flags, verbose=True)
```

## API Reference

### LaunchDarklyClient

Main client class for LaunchDarkly integration.

#### `__init__(api_token, project_key)`

Initialize the client.

**Parameters:**
- `api_token` (str): LaunchDarkly API access token
- `project_key` (str): LaunchDarkly project key

#### `get_flags(environment=None)`

Retrieve all feature flags from LaunchDarkly.

**Parameters:**
- `environment` (str, optional): Filter by environment key

**Returns:** List of `LaunchDarklyFlag` objects

#### `scan_codebase(repo_path, file_patterns=None, flag_patterns=None)`

Scan a codebase for feature flag references.

**Parameters:**
- `repo_path` (str): Path to repository
- `file_patterns` (list, optional): Glob patterns for files to scan
- `flag_patterns` (list, optional): Regex patterns to match flag usage

**Returns:** Dictionary mapping flag keys to lists of `CodeReference` objects

**Default file patterns:**
- `**/*.js`, `**/*.ts`, `**/*.jsx`, `**/*.tsx`
- `**/*.py`, `**/*.java`, `**/*.go`
- `**/*.rb`, `**/*.php`, `**/*.cs`
- `**/*.swift`, `**/*.kt`

**Default flag patterns:**
- `ldClient.variation('flag-key')`
- `client.variation('flag-key')`
- `variation('flag-key')`
- `isEnabled('flag-key')`
- `getFlag('flag-key')`
- And more...

#### `compare_flags(ld_flags, code_references)`

Compare LaunchDarkly flags with code references.

**Parameters:**
- `ld_flags` (list): List of `LaunchDarklyFlag` objects
- `code_references` (dict): Dictionary of code references

**Returns:** `FlagComparison` object

#### `print_comparison_report(comparison, ld_flags, verbose=False)`

Print a formatted comparison report.

**Parameters:**
- `comparison` (FlagComparison): Comparison results
- `ld_flags` (list): List of LaunchDarkly flags
- `verbose` (bool): Show detailed references

## Data Classes

### LaunchDarklyFlag

Represents a feature flag from LaunchDarkly.

**Attributes:**
- `key` (str): Flag key
- `name` (str): Flag name
- `kind` (str): Flag type (boolean, multivariate, etc.)
- `description` (str, optional): Flag description
- `tags` (list, optional): Flag tags
- `archived` (bool): Whether flag is archived
- `temporary` (bool): Whether flag is marked as temporary

### CodeReference

Represents a reference to a flag in code.

**Attributes:**
- `flag_key` (str): The flag key
- `file_path` (str): Relative path to file
- `line_number` (int): Line number
- `line_content` (str): Content of the line

### FlagComparison

Results of comparing LaunchDarkly flags with code.

**Attributes:**
- `flags_in_ld_only` (list): Flags only in LaunchDarkly (potential stale flags)
- `flags_in_code_only` (list): Flags only in code (potential missing flags)
- `flags_in_both` (list): Flags in both LaunchDarkly and code
- `code_references` (dict): All code references found

## Example Output

```
================================================================================
LAUNCHDARKLY FLAG COMPARISON REPORT
================================================================================

📊 SUMMARY
   Flags in LaunchDarkly only:  3
   Flags in codebase only:      1
   Flags in both:               7

⚠️  FLAGS IN LAUNCHDARKLY BUT NOT IN CODE (3)
   These flags may be stale and candidates for removal:
   - old-feature-flag [ARCHIVED]
     Description: Legacy feature that was removed
   - unused-experiment [TEMPORARY]
   - deprecated-toggle

🔍 FLAGS IN CODE BUT NOT IN LAUNCHDARKLY (1)
   These flags may be hardcoded or using a different system:
   - local-dev-flag (2 references)
     server.js:45
     app.js:123

✅ FLAGS IN BOTH LAUNCHDARKLY AND CODE (7)
   - enable-dark-mode (5 references)
   - show-new-header (3 references)
   - enable-premium-features (8 references)
   ...

================================================================================
```

## Integration with Devin Automation

This LaunchDarkly integration can be used with Devin AI to automate flag removal:

1. **Scan for stale flags** using the LaunchDarkly client
2. **Create a Devin session** to remove the stale flags
3. **Monitor progress** and review the PR created by Devin

Example workflow:

```python
from src.launchdarkly_client import LaunchDarklyClient
from src.devin_api_client import DevinAPIClient

# Find stale flags
ld_client = LaunchDarklyClient(api_token='...', project_key='...')
ld_flags = ld_client.get_flags()
code_refs = ld_client.scan_codebase('/path/to/repo')
comparison = ld_client.compare_flags(ld_flags, code_refs)

# Create Devin session to remove stale flags
if comparison.flags_in_ld_only:
    devin_client = DevinAPIClient()
    prompt = f"Remove these stale feature flags: {', '.join(comparison.flags_in_ld_only[:5])}"
    session = devin_client.create_session(prompt)
    print(f"Devin session created: {session.url}")
```

## Troubleshooting

### Authentication Errors

**Error:** `401 Unauthorized`

**Solution:** Check that your API token is valid and has the correct permissions. The token needs read access to feature flags.

### No Flags Found

**Error:** Retrieved 0 flags from LaunchDarkly

**Solution:** 
- Verify the project key is correct
- Check that flags exist in your LaunchDarkly project
- Ensure your API token has access to the project

### False Positives in Code Scanning

The scanner may detect strings that look like flag keys but aren't actually flags.

**Solution:** The scanner includes filtering for common false positives, but you can customize the patterns:

```python
# Use custom flag patterns
custom_patterns = [
    r'ldClient\.variation\(["\']([^"\']+)["\']',
    r'featureFlags\.get\(["\']([^"\']+)["\']'
]

code_refs = client.scan_codebase(
    repo_path='/path/to/repo',
    flag_patterns=custom_patterns
)
```

## API Rate Limits

LaunchDarkly API has rate limits. The client does not currently implement rate limiting or retries.

For large projects with many flags, consider:
- Caching flag data locally
- Implementing exponential backoff for retries
- Using pagination if available

## Future Enhancements

Potential improvements for this integration:

- [ ] Support for multiple environments
- [ ] Flag usage statistics from LaunchDarkly
- [ ] Integration with LaunchDarkly's code references feature
- [ ] Automatic PR creation for flag removal
- [ ] Support for LaunchDarkly webhooks
- [ ] Batch processing for multiple repositories
- [ ] Export reports to JSON/CSV

## Resources

- [LaunchDarkly API Documentation](https://apidocs.launchdarkly.com/)
- [LaunchDarkly REST API Reference](https://apidocs.launchdarkly.com/tag/Feature-flags)
- [Get API Access Token](https://app.launchdarkly.com/settings/authorization)

## Support

For questions about this integration, contact: Chris.darcy5@gmail.com
