# AWS Scanner

A comprehensive AWS resource scanner that identifies all cost-incurring and deletable resources across your AWS account.

## Features

- Scans all AWS regions automatically
- Identifies resources that incur costs
- Provides cost estimates for each resource
- Generates detailed markdown reports
- Groups resources by service and region
- Shows top 10 most expensive resources
- Concurrent scanning for performance
- Proper error handling and retry logic
- Rich terminal output with progress bars

## Supported Services

- **EC2**: Instances, EBS Volumes, Snapshots, Elastic IPs, NAT Gateways
- **S3**: Buckets (with object count and size sampling)
- **RDS**: DB Instances, DB Clusters, DB Snapshots
- **Lambda**: Functions
- **DynamoDB**: Tables
- **ELB**: Classic Load Balancers, Application/Network/Gateway Load Balancers
- **VPC**: VPC Endpoints, Transit Gateways
- **ECS**: Clusters, Services, Task Definitions
- **EKS**: Clusters
- **CloudFront**: Distributions
- **Route53**: Hosted Zones
- **API Gateway**: REST APIs, HTTP APIs

## Prerequisites

- Python 3.8+
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager
- AWS credentials configured as environment variables:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - Optional: `AWS_SESSION_TOKEN` (for temporary credentials)

## Installation

### Step 1: Install uv (if not already installed)

```bash
# On macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Verify installation
uv --version
```

### Step 2: Clone the repository

```bash
git clone https://github.com/stuartMoorhouse/aws-scanner.git
cd aws-scanner
```

### Step 3: Set up the Python environment

```bash
# Create a virtual environment with Python 3.8+
uv venv

# Install all dependencies from pyproject.toml
uv pip sync pyproject.toml
```

## Usage

### Step 1: Set AWS credentials

```bash
# Option 1: Use environment variables
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key

# Option 2: Use AWS profile
export AWS_PROFILE=your-profile-name
```

### Step 2: Run the scanner

```bash
# Option 1: Use the provided script (recommended)
./run_scanner.sh

# Option 2: Run directly with uv
uv run python scan_aws.py

# Option 3: If you need to specify options
uv run python scan_aws.py --regions us-east-1 us-west-2 --output my-report.md
```

### Step 3: Review the report

The scanner will generate a markdown report (default: `aws-resources-report.md`) with all discovered resources and their costs.

### Advanced Usage

```bash
# Scan specific regions only
uv run python scan_aws.py --regions us-east-1 us-west-2

# Skip certain services
uv run python scan_aws.py --skip-services EC2 S3

# Save report to custom location
uv run python scan_aws.py --output my-report.md

# Disable progress bars for CI/CD
uv run python scan_aws.py --no-progress

# Use custom configuration file
uv run python scan_aws.py --config scanner-config.json
```

### Command Line Options

```
Options:
  --regions REGIONS [REGIONS ...]
                        Specific regions to scan (default: all regions)
  --skip-regions SKIP_REGIONS [SKIP_REGIONS ...]
                        Regions to skip
  --services SERVICES [SERVICES ...]
                        Specific services to scan (default: all services)
  --skip-services SKIP_SERVICES [SKIP_SERVICES ...]
                        Services to skip
  --output OUTPUT       Output file path (default: aws-resources-report.md)
  --format {markdown,json,csv}
                        Output format (default: markdown)
  --log-level {DEBUG,INFO,WARNING,ERROR}
                        Logging level (default: INFO)
  --config CONFIG       Path to configuration file
  --no-progress         Disable progress bars
```

## Development

### Setting up development environment

```bash
# Install development dependencies
uv pip sync pyproject.toml --extra dev

# Or use uv's dev mode
uv pip install -e ".[dev]"
```

### Running tests

```bash
# Run all tests
./run_tests.sh

# Or manually
uv run pytest
uv run mypy aws_scanner
uv run black --check .
uv run flake8 aws_scanner
```

### Code formatting

```bash
# Format code
uv run black aws_scanner tests

# Sort imports
uv run isort aws_scanner tests
```

## Configuration

Create a `scanner-config.json` file:

```json
{
  "max_concurrent_regions": 10,
  "max_concurrent_services": 5,
  "skip_regions": ["us-gov-west-1"],
  "log_level": "INFO",
  "requests_per_second": 10.0
}
```

Or use environment variables:

```bash
export AWS_SCANNER_MAX_CONCURRENT_REGIONS=5
export AWS_SCANNER_SKIP_REGIONS=us-gov-west-1,cn-north-1
export AWS_SCANNER_LOG_LEVEL=DEBUG
```

## Output

The scanner generates a comprehensive markdown report including:
- Total resource count and estimated monthly cost
- Table of contents for easy navigation
- Summary by service
- Detailed resource listings grouped by service and region
- Cost breakdown with top 10 most expensive resources

## Security Notes

- Never commit AWS credentials to version control
- The scanner uses read-only API calls
- Consider using IAM roles with minimal required permissions
- **Important**: The generated report (`aws-resources-report.md`) contains sensitive information about your AWS infrastructure including IP addresses, resource IDs, and naming conventions. This file is automatically excluded from git via `.gitignore` - never commit it to your repository
- Copy `.env.example` to `.env` and add your AWS credentials (`.env` is also gitignored)

## IAM Permissions

The scanner requires read permissions for each service. Example policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:Describe*",
        "s3:ListBuckets",
        "s3:GetBucketLocation",
        "s3:GetBucketTagging",
        "s3:ListBucket",
        "rds:Describe*",
        "lambda:List*",
        "dynamodb:List*",
        "dynamodb:Describe*",
        "elasticloadbalancing:Describe*",
        "vpc:Describe*",
        "ecs:List*",
        "ecs:Describe*",
        "eks:List*",
        "eks:Describe*",
        "cloudfront:List*",
        "cloudfront:Get*",
        "route53:List*",
        "route53:Get*",
        "apigateway:GET"
      ],
      "Resource": "*"
    }
  ]
}
```

## Why uv?

This project uses [uv](https://github.com/astral-sh/uv) for Python dependency management because:

- **Fast**: 10-100x faster than pip
- **Reliable**: Consistent dependency resolution
- **Simple**: No more virtual environment activation issues
- **Modern**: Built for the modern Python ecosystem
- **Cross-platform**: Works the same on all platforms

## Troubleshooting

### uv: command not found

Install uv following the [installation instructions](https://github.com/astral-sh/uv#installation).

### AWS credentials not found

Ensure your AWS credentials are set as environment variables or use AWS CLI profiles:

```bash
export AWS_PROFILE=your-profile
./run_scanner.sh
```

### Permission denied errors

Some AWS services may not be accessible with your current permissions. The scanner will continue and report which services couldn't be accessed.

## License

MIT License - see LICENSE file for details