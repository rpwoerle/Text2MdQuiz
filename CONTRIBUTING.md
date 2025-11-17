# Contributing to Text2MdQuiz

Thank you for considering contributing! Here's how you can help:

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/Text2MdQuiz.git
   cd Text2MdQuiz
   ```
3. **Set up the development environment**:
   ```bash
   pip install -r requirements.txt
   cp .env.example .env
   # Edit .env and add your OPENAI_API_KEY
   ```

## Development Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**:
   - Follow the existing code style (Black formatting, line length 100)
   - Add tests for new functionality
   - Update documentation as needed

3. **Run tests**:
   ```bash
   pytest -q
   ```

4. **Format code**:
   ```bash
   python -m black -l 100 text2mdquiz.py tests/
   ```

5. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Add: brief description of your changes"
   ```

6. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request** on GitHub

## Guidelines

- **Code style**: Use Black formatter with 100-character line length
- **Type hints**: Include type hints for all function parameters and returns
- **Docstrings**: Add docstrings for public functions
- **Tests**: Write tests for new features using pytest
- **Commits**: Write clear, descriptive commit messages

## Ideas for Contributions

- Support for additional question types
- Multi-language improvements
- Better error handling and user feedback
- Performance optimizations
- Documentation improvements
- Example prompts and templates
- Integration with other quiz platforms

## Questions?

Open an issue on GitHub if you have questions or need help!
