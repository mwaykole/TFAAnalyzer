# Contributing to TFA

Thank you for your interest in contributing to the Test Failure Analyzer!

## Getting Started

### Prerequisites

- Python 3.11+
- Git
- Access to ReportPortal (for integration testing)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/your-org/rp-tfa-analysis.git
cd rp-tfa-analysis

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-asyncio pytest-cov ruff mypy

# Copy environment template
cp .env.example .env
# Edit .env with your test credentials
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test file
pytest tests/test_domain_services.py -v
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 2. Make Changes

Follow the architecture guidelines in [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).

### 3. Test Your Changes

```bash
# Run tests
pytest tests/ -v

# Check types
mypy src/

# Check linting
ruff check src/
```

### 4. Commit

Write clear, descriptive commit messages:

```bash
git commit -m "feat: add Discord notification support

- Add DiscordNotifier implementing Notifier interface
- Add discord_webhook to NotificationConfig
- Wire into CLI investigate command"
```

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

## Code Guidelines

### Architecture

- Follow Clean Architecture principles
- Keep domain layer free of external dependencies
- Use interfaces for external integrations
- Add new adapters in `infrastructure/`

### Code Style

- Use type hints everywhere
- Write Google-style docstrings
- Keep functions focused and small
- Maximum line length: 100 characters

### Testing

- Write tests for new features
- Maintain >80% code coverage
- Use pytest fixtures and parametrize
- Mock external services in tests

## Pull Request Guidelines

### PR Title

Use conventional commits format:
- `feat: add new feature`
- `fix: resolve bug in X`
- `docs: update README`
- `refactor: improve X`
- `test: add tests for Y`

### PR Description

Include:
- Summary of changes
- Related issue numbers
- Testing instructions
- Screenshots (for UI changes)

### Checklist

Before submitting:
- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No new linting errors
- [ ] Commit messages are clear

## Adding New Features

See the [Developer Guide](DEVELOPER_GUIDE.md) for detailed instructions on:
- Adding new LLM providers
- Adding notification channels
- Adding classification patterns
- Extending the API

## Reporting Issues

### Bug Reports

Include:
- TFA version
- Python version
- Steps to reproduce
- Expected vs actual behavior
- Error messages/logs

### Feature Requests

Include:
- Use case description
- Proposed solution
- Alternative approaches considered

## Questions?

- Check the [Developer Guide](DEVELOPER_GUIDE.md)
- Review existing issues/PRs
- Ask in the team Slack channel

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
