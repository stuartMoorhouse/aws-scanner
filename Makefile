# Makefile for AWS Scanner

.PHONY: help install dev test format lint clean run

# Default target
help:
	@echo "AWS Scanner - Available commands:"
	@echo "  make install    - Install production dependencies"
	@echo "  make dev        - Install development dependencies"
	@echo "  make test       - Run all tests"
	@echo "  make format     - Format code with black and isort"
	@echo "  make lint       - Run linting checks"
	@echo "  make clean      - Clean up generated files"
	@echo "  make run        - Run the scanner"

# Install production dependencies
install:
	@echo "Installing production dependencies..."
	@uv venv
	@uv pip sync pyproject.toml

# Install development dependencies
dev:
	@echo "Installing development dependencies..."
	@uv venv
	@uv pip sync pyproject.toml --extra dev

# Run tests
test: dev
	@echo "Running tests..."
	@uv run pytest tests/unit -v
	@echo "\nRunning type checks..."
	@uv run mypy aws_scanner
	@echo "\nRunning linting..."
	@uv run flake8 aws_scanner --max-line-length=100
	@echo "\nChecking code formatting..."
	@uv run black --check aws_scanner tests

# Format code
format: dev
	@echo "Formatting code..."
	@uv run black aws_scanner tests
	@uv run isort aws_scanner tests

# Run linting
lint: dev
	@echo "Running linting checks..."
	@uv run flake8 aws_scanner --max-line-length=100
	@uv run mypy aws_scanner

# Clean up generated files
clean:
	@echo "Cleaning up..."
	@rm -rf .venv
	@rm -rf __pycache__
	@rm -rf .pytest_cache
	@rm -rf .mypy_cache
	@rm -rf htmlcov
	@rm -rf .coverage
	@rm -rf build
	@rm -rf dist
	@rm -rf *.egg-info
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete

# Run the scanner
run: install
	@if [ -z "$$AWS_ACCESS_KEY_ID" ] || [ -z "$$AWS_SECRET_ACCESS_KEY" ]; then \
		echo "Error: AWS credentials not set!"; \
		echo "Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"; \
		exit 1; \
	fi
	@uv run python scan_aws.py