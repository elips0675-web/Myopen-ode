# Testing Skill

When writing tests, follow these conventions:
1. Place tests in `test_*.py` files
2. Use the existing test patterns in `test_agent.py`
3. Run tests with: `python -m pytest test_*.py -v` or `python test_*.py`
4. Always verify tests pass before committing

## Python tests
- Use assert statements
- Test both success and error cases
- Keep tests independent (no shared state)

## Quick commands
```bash
python test_agent.py
```
