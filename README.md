# Text2MdQuiz

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

Python CLI tool to generate educational quizzes from text files using OpenAI's GPT API. Supports **Multi-choice**, **Cloze** (Lückentext/fill-in-the-blank), and **Matching** questions. The quiz language automatically matches the input text (multi-language support, especially German).

Perfect for K-12 educators creating quizzes from study materials!

## Features

- 🎯 **Three question types**: Multi-choice, Cloze, Matching
- 🌍 **Multi-language support**: Quiz language matches input text
- ⚙️ **Highly configurable**: Control points, answer counts, blanks, pairs
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
python text2mdquiz.py samples/example-physics-de.txt --type cl --questions 2 --blanks 6

# Matching: 1 question with 8 pairs
python text2mdquiz.py samples/example-physics-de.txt --type ma --pairs 8
```

## Command-Line Options


| Option               | Default                                    | Description                                                                 |
| ---------------------- | -------------------------------------------- | ----------------------------------------------------------------------------- |
| `--type` / `-t`      | `mc`                                       | Question type:`mc` (Multi-choice), `cl` (Cloze), `ma` (Matching)            |
| `--questions` / `-q` | `4` (Multi-choice/Matching)<br>`1` (Cloze) | Number of questions to generate                                             |
| `--points` / `-p`    | `4`                                        | Points per question (Multi-choice/Matching only; Cloze uses blank weights)  |
| `--answers` / `-a`   | `2 3`                                      | Correct and incorrect answer counts (Multi-choice only)                     |
| `--blanks`           | `4`                                        | Number of blanks in Cloze questions                                         |
| `--pairs`            | `4`                                        | Number of pairs in Matching questions                                       |
| `--model`            | `gpt-5`                                    | OpenAI model name                                                           |
| `--config` / `-c`    | `text2mdquiz.cfg`                          | Path to custom configuration file                                           |
| `--output` / `-o`    | `<input>-<type>.md`                        | Output file path or directory                                               |

## Configuration and Prompt Files

The tool **requires** a configuration file (`text2mdquiz.cfg`) that defines where prompts are loaded from. Long prompts and examples live in separate text/Markdown files under `prompts/`, which keeps the config readable and avoids multi-line parsing issues.

### Default Location

The config file must exist in the same directory as `text2mdquiz.py`. You can specify a custom config path with `--config`:

```bash
python text2mdquiz.py input.txt --config my-custom-config.cfg
```

If the config file is missing or incomplete, the tool will display an error message indicating what's required.

### Configuration Format

The config file uses INI format with three sections (one per question type). Each section points to external prompt/example files:

```ini
[multi_choice]
system_prompt_file = prompts/mc_system.txt
user_prompt_file = prompts/mc_user.txt
example_file = prompts/mc_example.md

[cloze]
system_prompt_file = prompts/cloze_system.txt
user_prompt_file = prompts/cloze_user.txt
example_file = prompts/cloze_example.md

[matching]
system_prompt_file = prompts/matching_system.txt
user_prompt_file = prompts/matching_user.txt
example_file = prompts/matching_example.md
```

All file paths can be absolute or relative to the directory containing `text2mdquiz.py`.

### Available Placeholders

Templates in the `user_prompt_file` contents (or inline `user_prompt`, if you add one) can use these placeholders (automatically filled from CLI arguments):

**Multi-choice:**
- `{num_questions}` - Number of questions
- `{points_str}` - Points per question (e.g., "[4]")
- `{total_answers}` - Total answers per question (correct + incorrect)
- `{num_correct}` - Number of correct answers
- `{num_incorrect}` - Number of incorrect answers

**Cloze:**
- `{num_questions}` - Number of questions
- `{gaps_spec}` - Description of blanks (e.g., "exactly 4 blanks")

**Matching:**
- `{num_questions}` - Number of questions
- `{points_str}` - Points per question (e.g., "[4]")
- `{pairs_spec}` - Description of pairs (e.g., "exactly 4 pairs")

### Attachment Files (Optional)

You can still provide additional instructions to the OpenAI API via an `attachment` file specified in each question type section:

```ini
[multi_choice]
system_prompt_file = prompts/mc_system.txt
attachment = instructions/multi-choice-guidelines.txt
```

The attachment content is sent as an additional system message, useful for detailed formatting rules, subject-specific terminology, grading rubrics, or pedagogical guidelines.

### Customization Example

To create quizzes with a more formal tone for multi-choice questions:

1. Copy `prompts/mc_system.txt` to `prompts/mc_system_formal.txt` and adapt the wording.
2. Copy `text2mdquiz.cfg` to `formal-tone.cfg`.
3. In `formal-tone.cfg`, point the multi-choice section to the new system prompt file:
   ```ini
   [multi_choice]
   system_prompt_file = prompts/mc_system_formal.txt
   user_prompt_file = prompts/mc_user.txt
   example_file = prompts/mc_example.md
   ```
4. Use the custom config:
   ```bash
   python text2mdquiz.py lecture-notes.txt --config formal-tone.cfg
   ```

### Fallback Behavior

- The configuration file and all required sections (`[multi_choice]`, `[cloze]`, `[matching]`) are **mandatory**.
- Each section must contain either `system_prompt_file` or an inline `system_prompt`, and either `user_prompt_file` or an inline `user_prompt`.
- `example_file` is optional; if present and the file exists, its contents are appended as an example block. If omitted or the file is missing, examples are simply skipped.

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
- Total points = sum of all blank weights
- Heading omits `[points]` (derived from blanks)
- Default: 1 question with 4 blanks (configurable via `--questions` and `--blanks`)

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
- Try reducing `--questions` or `--blanks`/`--pairs` counts
- The model may occasionally produce invalid format; retry or adjust prompt
