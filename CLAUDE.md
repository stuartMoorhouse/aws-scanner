# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AWS Scanner is a tool for scanning and analyzing AWS resources. This Python-based tool provides comprehensive resource discovery and analysis across multiple AWS services.

## Technology Stack

- **Language**: Python 3.8+
- **Package Manager**: uv (replaces pip/pip-tools)
- **AWS SDK**: boto3
- **Testing**: pytest
- **Linting**: flake8, black
- **Type Checking**: mypy (optional)

## Setting Up Development Environment

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv

# Install all dependencies from pyproject.toml
uv pip sync pyproject.toml

# Install with development dependencies
uv pip sync pyproject.toml --extra dev
```

## Common Commands

```bash
# Run the scanner
uv run python scan_aws.py

# Run tests
uv run pytest

# Format code
uv run black .

# Lint code
uv run flake8

# Type check
uv run mypy aws_scanner

# Install a new dependency
uv pip install boto3

# Update dependencies
uv pip compile pyproject.toml -o requirements.txt
```

## Architecture Guidelines

### Directory Structure
```
aws-scanner/
├── aws_scanner/
│   ├── __init__.py
│   ├── scanners/       # Service-specific scanners
│   │   ├── __init__.py
│   │   ├── base_scanner.py
│   │   └── *_scanner.py
│   └── types.py        # Type definitions
├── tests/              # Test files
├── scan_aws.py         # Main entry point
└── requirements.txt    # Python dependencies
```

### Key Design Patterns

1. **Scanner Base Class**: Each AWS service scanner inherits from `BaseScanner`:
   ```python
   class BaseScanner:
       def scan(self) -> List[Dict[str, Any]]:
           """Scan AWS resources for this service"""
           pass
   ```

2. **Credential Management**: Use boto3's built-in credential chain. Never hardcode credentials.

3. **Error Handling**: Wrap AWS API calls with proper error handling for rate limits and access errors.

4. **Pagination**: Always handle paginated results from AWS APIs using boto3's pagination helpers.

## AWS-Specific Guidelines

1. **Authentication**: Rely on boto3 credential chain (environment variables, IAM roles, ~/.aws/credentials)

2. **Regions**: Support multi-region scanning with concurrent execution where appropriate

3. **Rate Limiting**: Implement exponential backoff for API rate limit errors

4. **Permissions**: Document required IAM permissions for each scanner in docstrings

5. **Resource Tagging**: Support filtering by tags when scanning resources

## Development Workflow

1. Each scanner module should be self-contained and testable
2. Use type hints for better code clarity
3. Implement proper logging with structured output
4. Mock AWS services in tests using moto or boto3-stubs
5. Handle AWS service limits gracefully
6. Use async operations where beneficial (with aioboto3)

## Python-Specific Guidelines

1. **Dependencies**: 
   - Manage dependencies in `pyproject.toml` 
   - Use `uv pip sync` for reproducible installs
   - Pin versions for stability
2. **Code Style**: Follow PEP 8 and use black for formatting
3. **Documentation**: Use docstrings for all public methods
4. **Error Messages**: Provide clear, actionable error messages
5. **Performance**: Use generators for large result sets to minimize memory usage

## Quick Start with UV

```bash
# Step 1: Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Step 2: Clone and enter directory
git clone https://github.com/stuartMoorhouse/aws-scanner.git
cd aws-scanner

# Step 3: Set up environment
uv venv
uv pip sync pyproject.toml

# Step 4: Set AWS credentials
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret

# Step 5: Run scanner
uv run python scan_aws.py
```