# GitHub Copilot Instructions

## Project Overview
Python CLI tool that generates multiple-choice quizzes from text files using OpenAI's GPT API. Target audience: K-12 students.

## Project Structure
Python CLI tool that generates quizzes (Multi-choice, Cloze, Matching) from text files using OpenAI's GPT API. Target audience: K-12 students.
text2mdquiz.py         # Standalone script with all logic
tests/
├── test_quiz_generator.py
├── test_formatter.py
└── fixtures/

## Quiz Output Format (REQUIRED)
 Questions: `## <Type>: <question text> [points]` where `<Type>` is one of `Multi-choice`, `Cloze`, `Matching`. For Cloze, omit `[points]` in the heading; points equal the sum of gap weights.
- A type of plant reproduction
- Energy transfer in cells*

## Multi-choice: Which organelle performs photosynthesis? [4]
python text2mdquiz.py input.txt [--questions 4] [--points 4] [--answers 2 3] [--type mc|cl|ma] [--output quiz.md]
- Chloroplast*
 Multi-choice: default 2 correct and 3 incorrect answers per question (configurable with --answers)
 Cloze: provide a paragraph with blanks using `{1:correct|alt1|alt2}` by default; higher weights like `{2:correct|alt1|alt2}` are also valid. Use `--gaps N` to request exactly N blanks (default: 4). Points default to number of blanks. Default number of Cloze questions is 1 unless overridden.
 Matching: provide pairs formatted `- Left = Right` (request N via `--pairs N`; default: 4; excess trimmed).
 Multi-choice total answers per question = correct + incorrect (default 5)
- Ribosome
- Vacuole*
```
- File starts with: `# Quiz`
- Questions: `## Multi-choice: <question text> [points]`
- Default points: 4 (can be overridden with --points option)
- All answers: `- <answer>`
- Correct answers: add trailing asterisk (`- <answer>*`)
- Default: 2 correct and 3 incorrect answers per question (configurable with --answers)
- Blank line between questions
- Total answers per question = correct + incorrect (default 5)

## CLI Interface
```bash
python text2mdquiz.py input.txt [--questions 4] [--points 4] [--answers 2 3] [--output quiz.md]
```
Required args: input file path
Defaults: `--questions 4`, `--points 4`, `--answers 2 3` (2 correct, 3 incorrect), `--output <input-stem>-<type>-<provider>.md` (e.g., `-multi-choice-openai.md`, `-cloze-openai.md`, `-matching-openai.md`, `-essay-openai.md`)

## OpenAI Integration
- Use OpenAI Python SDK v1: `from openai import OpenAI` then `client = OpenAI()` and `client.chat.completions.create(model="gpt-5", messages=[...])`
- System prompt: "You are an experienced K-12 teacher creating educational quizzes for students."
- User prompt: Include full text content + quiz format specification + number of questions
- The language of the quiz (questions and answers) must always match the language of the input text. Support multiple languages, especially German (Deutsch).
- Parse response to ensure format compliance

## Development Workflow
- `rundev.cmd`: Sets Python 3.14 environment and opens VS Code
- Store API key in `.env` file (never commit it)
- Use `python-dotenv` to load environment variables
- Handle API errors gracefully (rate limits, invalid keys, network issues)

## Testing Approach
- Use sample text files in `tests/fixtures/`
- Mock OpenAI API calls in tests (avoid actual API usage)
- Validate output format with regex patterns
- Test edge cases: empty files, very short text, special characters

## Key Conventions
- Use type hints throughout (`from typing import List, Dict`)
- Format with Black (line length: 100)
- Docstrings for all public functions
- Error messages should be user-friendly, not technical tracebacks