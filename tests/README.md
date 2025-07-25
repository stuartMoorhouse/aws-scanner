# AWS Scanner Tests

This directory contains the test suite for AWS Scanner.

## Structure

```
tests/
├── unit/                  # Unit tests
│   ├── test_base_scanner.py   # Base scanner tests
│   ├── test_ec2_scanner.py    # EC2 scanner tests
│   ├── test_utils.py          # Utility function tests
│   ├── test_config.py         # Configuration tests
│   ├── test_types.py          # Type definition tests
│   └── test_main.py           # Main script tests
├── integration/           # Integration tests (future)
└── conftest.py           # Pytest fixtures and configuration
```

## Running Tests

### Quick Start

```bash
# Run all tests
make test

# Or manually with uv
uv run pytest
```

### Running Specific Tests

```bash
# Run only unit tests
pytest tests/unit

# Run specific test file
pytest tests/unit/test_ec2_scanner.py

# Run specific test
pytest tests/unit/test_ec2_scanner.py::TestEC2Scanner::test_scan_instances

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=aws_scanner --cov-report=html
```

### Test Markers

Tests are marked for easy filtering:

```bash
# Run only unit tests
pytest -m unit

# Skip slow tests
pytest -m "not slow"
```

## Writing Tests

### Test Structure

Each test file follows this pattern:

```python
"""Unit tests for module_name."""
import pytest
from unittest.mock import Mock, patch

from aws_scanner.module_name import FunctionToTest


class TestClassName:
    """Test cases for ClassName."""
    
    def test_specific_behavior(self):
        """Test description."""
        # Arrange
        mock_dependency = Mock()
        
        # Act
        result = FunctionToTest(mock_dependency)
        
        # Assert
        assert result == expected_value
```

### Common Fixtures

See `conftest.py` for available fixtures:

- `mock_boto_client`: Mock boto3 client
- `sample_ec2_instance`: Sample EC2 instance data
- `sample_s3_bucket`: Sample S3 bucket data
- `mock_scanner_config`: Mock scanner configuration
- `sample_resources`: List of sample resources

### Mocking AWS Services

Use `unittest.mock` for simple mocks and `moto` for complex AWS service mocking:

```python
from unittest.mock import patch, MagicMock
import boto3
from moto import mock_ec2

# Simple mock
@patch('boto3.client')
def test_with_mock(mock_client):
    mock_client.return_value.describe_instances.return_value = {...}

# Moto mock (more realistic)
@mock_ec2
def test_with_moto():
    client = boto3.client('ec2', region_name='us-east-1')
    # Moto automatically handles the API calls
```

## Coverage Goals

- Minimum coverage: 80%
- Target coverage: 90%+
- Focus on critical paths and error handling

## Best Practices

1. **Test One Thing**: Each test should verify one specific behavior
2. **Use Descriptive Names**: Test names should describe what they test
3. **Mock External Dependencies**: Don't make real AWS API calls
4. **Test Error Cases**: Include tests for error conditions
5. **Keep Tests Fast**: Unit tests should run in milliseconds
6. **Use Fixtures**: Reuse common test data via fixtures