# Contributing to SEPHIROTH

## Getting Started

1. Fork the repository
2. Clone your fork
3. Create a feature branch
4. Install development dependencies
5. Make your changes
6. Run tests
7. Submit a pull request

## Setup Development Environment

```bash
# Install dependencies
pip install -r requirements.txt

# Dev dependencies (pytest, pytest-cov, ruff, mypy) are already in requirements.txt

# Create .env file
cp .env.example .env
```

## Code Standards

### Python
- Use type hints
- Follow PEP 8
- Write docstrings

```bash
ruff check .
ruff format .
mypy .
```

### Medical Accuracy
- All medical features must be evidence-based
- Include citations to guidelines/papers
- Mark experimental features as such
- Add disclaimers where needed

### Testing
- Write tests for new features
- Maintain the 87% coverage gate (`pytest --cov`; CI fails below this — see `pyproject.toml`)
- Test edge cases, including adversarial cases for the Citation Guard and RAG retrieval
- If you touch `data/rag/SEED_GUIDELINES` or the Evidence Agent's prompt, run
  `python -m intelligence.evaluation.run --mode full --record` and check the
  [Evaluation](README.md#evaluation) numbers before opening a PR

## Commit Messages

Format: `[type] message`

Types:
- `[feature]` - New feature
- `[fix]` - Bug fix
- `[docs]` - Documentation
- `[test]` - Tests
- `[refactor]` - Code refactoring
- `[perf]` - Performance improvement

Example:
```
[feature] Add SGLT2i drug interaction checking

Implements checking for SGLT2 inhibitors with current medications
based on FDA guidelines. Includes unit tests and documentation.

Closes #123
```

## Pull Request Process

1. Update documentation
2. Add tests for new functionality
3. Ensure all tests pass
4. Update CHANGELOG.md
5. Reference related issues
6. Wait for review

## Medical Compliance

- All medical features must be marked as "research/educational"
- Include appropriate disclaimers
- Never claim to provide diagnosis
- Always recommend professional review
- Document evidence sources

## Integration with Open Source Projects

When integrating open source projects:
1. Respect original licenses
2. Maintain attribution
3. Don't modify core libraries
4. Create adapters/wrappers
5. Document integration points

## Areas for Contribution

- [ ] Complete agent implementations
- [ ] RAG indexing with PubMed
- [ ] Frontend development (Next.js)
- [ ] Medical imaging enhancements
- [ ] Clinical NLP improvements
- [ ] Testing and documentation
- [ ] Performance optimization
- [ ] Deployment automation

## Questions?

- Open an issue for questions
- Check existing discussions
- Review documentation

## Code of Conduct

- Be respectful
- Provide constructive feedback
- Acknowledge contributions
- Focus on the medical mission
