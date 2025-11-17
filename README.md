# Text2MdQuiz

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

Python CLI tool to generate educational quizzes from text files using OpenAI's GPT API. Supports **Multi-choice**, **Cloze** (Lückentext/fill-in-the-blank), and **Matching** questions. The quiz language automatically matches the input text (multi-language support, especially German).

Perfect for K-12 educators creating quizzes from study materials!

## Features

- 🎯 **Three question types**: Multi-choice, Cloze, Matching
- 🌍 **Multi-language support**: Quiz language matches input text
- ⚙️ **Highly configurable**: Control points, answer counts, gaps, pairs
- 📝 **Markdown output**: Clean, standardized format
- 🧪 **Well-tested**: Comprehensive test suite included

## Quick Start

### Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/rpwoerle/Text2MdQuiz.git
   cd Text2MdQuiz
   ```
2. **Install dependencies** (Python 3.14+ recommended):

   ```bash
   pip install -r requirements.txt
   ```
3. **Set up your OpenAI API key**:

   ```bash
   cp .env.example .env
   # Edit .env and add your OPENAI_API_KEY
   ```

   Or set it directly in PowerShell/bash:

   ```powershell
   # PowerShell
   $env:OPENAI_API_KEY='sk-your-actual-key-here'
   ```

   ```bash
   # Bash
   export OPENAI_API_KEY='sk-your-actual-key-here'
   ```

### Basic Usage

Generate a multi-choice quiz with default settings:

```bash
python text2mdquiz.py input.txt
```

Generate a Cloze (fill-in-the-blank) quiz:

```bash
python text2mdquiz.py input.txt --type cl
```

Generate a Matching quiz:

```bash
python text2mdquiz.py input.txt --type ma
```

### Examples

See `samples/` directory for example input text and generated quizzes.

```bash
# Multi-choice: 5 questions, 3 correct + 4 incorrect answers each
python text2mdquiz.py samples/example-physics-de.txt --questions 5 --answers 3 4

# Cloze: 2 questions with 6 blanks each
python text2mdquiz.py samples/example-physics-de.txt --type cl --questions 2 --gaps 6

# Matching: 1 question with 8 pairs
python text2mdquiz.py samples/example-physics-de.txt --type ma --pairs 8
```

## Command-Line Options


| Option               | Default                                    | Description                                                              |
| ---------------------- | -------------------------------------------- | -------------------------------------------------------------------------- |
| `--type` / `-t`      | `mc`                                       | Question type:`mc` (Multi-choice), `cl` (Cloze), `ma` (Matching)         |
| `--questions` / `-q` | `4` (Multi-choice/Matching)<br>`1` (Cloze) | Number of questions to generate                                          |
| `--points` / `-p`    | `4`                                        | Points per question (Multi-choice/Matching only; Cloze uses gap weights) |
| `--answers` / `-a`   | `2 3`                                      | Correct and incorrect answer counts (Multi-choice only)                  |
| `--gaps`             | `4`                                        | Number of blanks in Cloze questions                                      |
| `--pairs`            | `4`                                        | Number of pairs in Matching questions                                    |
| `--model`            | `gpt-5`                                    | OpenAI model name                                                        |
| `--output` / `-o`    | `<input>-<type>.md`                        | Output file path or directory                                            |

## Output Format

All quizzes start with a `# Quiz` header. Each question type has its own format:

### Multi-choice

```markdown
# Quiz
## Multi-choice: Was ist Fotosynthese? [4]
- Falsche Antwort
- Richtige Antwort*
- Falsche Antwort
- Richtige Antwort*
- Falsche Antwort
```

**Rules:**

- Points in square brackets: `[4]`
- Correct answers marked with trailing `*`
- Default: 2 correct + 3 incorrect (configurable via `--answers`)
- Blank line between questions

### Cloze (Fill-in-the-Blank)

```markdown
## Cloze: Fülle die Lücken mit den passendsten Begriffen aus.
Energie ist die Fähigkeit durch ihre Umwandlung etwas zu {1:bewirken}. Energie kann von einer Form in eine andere umgewandelt werden, aber sie kann weder geschaffen noch zerstört werden, was als {2:Energieerhaltungsgesetz|Gesetz der Energieerhaltung|Energieerhaltung} bekannt ist.
```

**Rules:**

- Blanks wrapped in `{}` with format `{weight:answer|alternative1|alternative2}`
- Default weight is `1:` (auto-added if not specified)
- Higher weights like `{2:answer}` count for more points
- Total points = sum of all gap weights
- Heading omits `[points]` (derived from gaps)
- Default: 1 question with 4 blanks (configurable via `--questions` and `--gaps`)

### Matching

```markdown
## Matching: Ordne die hauptsächlichen Energieformen den Beispielen zu. [4]
- Mechanische Energie = Ein rollender Ball 
- Chemische Energie = Verbrennung von Holz
- Elektrische Energie = Strom aus der Steckdose
- Strahlungsenergie = Sonnenlicht
```

**Rules:**

- Format: `- Left term = Right term`
- Default: 4 pairs (configurable via `--pairs`)
- Points in square brackets

## Development

### Running Tests

```bash
pytest -q
```

### Code Formatting

```bash
python -m black -l 100 text2mdquiz.py tests/
```

### Project Structure

```
Text2MdQuiz/
├── text2mdquiz.py          # Main CLI script
├── tests/
│   ├── test_quiz_generator.py
│   ├── test_formatter.py
│   └── fixtures/           # Sample test files
├── samples/                # Example input/output files
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
├── README.md
├── CONTRIBUTING.md
└── LICENSE
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Disclaimer

This software is provided "as is" without any guarantees or warranty. Functionality is not guaranteed for any specific purpose or environment. Parts of this project were developed with assistance from GitHub Copilot. Always review code and outputs and verify operation in your context before relying on the results.

## License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0) - see the [LICENSE](LICENSE) file for details.

This is free educational software. You may use, share, and adapt it for non-commercial educational purposes with attribution.

## Troubleshooting

### Model Not Found Error

If you get a "model not found" error with `gpt-5`, your account may not have access. Try:

```bash
python text2mdquiz.py input.txt --model gpt-4o-mini
```

### API Key Issues

- Ensure `.env` file exists with `OPENAI_API_KEY=sk-...`
- Check the key is not placeholder text like `sk-REPLACE-...`
- Verify the key is active in your OpenAI account

### Empty or Invalid Output

- Check your input text is substantial (at least a few sentences)
- Try reducing `--questions` or `--gaps`/`--pairs` counts
- The model may occasionally produce invalid format; retry or adjust prompt
