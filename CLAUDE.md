# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AWS Scanner is a tool for scanning and analyzing AWS resources. As this is a new project, follow these guidelines when implementing features.

## Technology Stack

- **Language**: TypeScript (recommended for AWS SDK v3 support)
- **Runtime**: Node.js
- **AWS SDK**: AWS SDK v3 (@aws-sdk/client-*)
- **Testing**: Jest or Vitest
- **Linting**: ESLint with TypeScript support

## Common Commands

Once the project is initialized, use these commands:

```bash
# Initialize project
npm init -y
npm install typescript @types/node --save-dev
npx tsc --init

# Install AWS SDK (example)
npm install @aws-sdk/client-ec2 @aws-sdk/client-s3

# Development
npm run dev      # Run in development mode
npm run build    # Build TypeScript
npm run test     # Run tests
npm run lint     # Run ESLint
```

## Architecture Guidelines

### Directory Structure
```
aws-scanner/
├── src/
│   ├── scanners/       # Service-specific scanners
│   ├── utils/          # Shared utilities
│   ├── types/          # TypeScript types
│   └── index.ts        # Main entry point
├── tests/              # Test files
└── config/             # Configuration files
```

### Key Design Patterns

1. **Scanner Interface**: Each AWS service scanner should implement a common interface:
   ```typescript
   interface Scanner {
     scan(): Promise<ScanResult>
     getServiceName(): string
   }
   ```

2. **Credential Management**: Use AWS SDK's built-in credential chain. Never hardcode credentials.

3. **Error Handling**: Wrap AWS API calls with proper error handling for rate limits and access errors.

4. **Pagination**: Always handle paginated results from AWS APIs using the SDK's pagination helpers.

## AWS-Specific Guidelines

1. **Authentication**: Rely on AWS SDK credential chain (environment variables, IAM roles, ~/.aws/credentials)

2. **Regions**: Support multi-region scanning with parallel execution where appropriate

3. **Rate Limiting**: Implement exponential backoff for API rate limit errors

4. **Permissions**: Document required IAM permissions for each scanner in comments

5. **Resource Tagging**: Support filtering by tags when scanning resources

## Development Workflow

1. Each scanner module should be self-contained and testable
2. Use async/await patterns consistently
3. Implement proper logging with structured output
4. Mock AWS services in tests using aws-sdk-client-mock
5. Handle AWS service limits gracefully