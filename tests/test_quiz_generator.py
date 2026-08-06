from __future__ import annotations

import configparser
import sys
from pathlib import Path

import pytest

# Add parent directory to path to import text2mdquiz
sys.path.insert(0, str(Path(__file__).parent.parent))

from quizvalidation import main as validation_main
from text2mdquiz import (
    GenerationResult,
    QuizGenerator,
    apply_config_defaults,
    load_config,
    main,
    parse_args,
    resolve_input_files,
)


# Load the actual config file once for all tests
TEST_CONFIG = load_config(Path(__file__).parent.parent / "text2mdquiz.cfg")


class FakeChoice:
    def __init__(self, content: str):
        self.message = type("Msg", (), {"content": content})()


class FakeCompletions:
    def __init__(self, content: str):
        self._content = content

    def create(self, **kwargs):
        class Resp:
            def __init__(self, content: str):
                self.choices = [FakeChoice(content)]

        return Resp(self._content)


class FakeClient:
    def __init__(self, content: str):
        self.chat = type("Chat", (), {"completions": FakeCompletions(content)})()


class FakeGeminiResponse:
    def __init__(self, text: str):
        self.text = text


class FakeGeminiModels:
    def __init__(self, text: str):
        self._text = text

    def generate_content(self, **kwargs):
        return FakeGeminiResponse(self._text)


class FakeGeminiClient:
    def __init__(self, text: str):
        self.models = FakeGeminiModels(text)


class FakeClaudeBlock:
    def __init__(self, text: str):
        self.text = text


class FakeClaudeResponse:
    def __init__(self, text: str):
        self.content = [FakeClaudeBlock(text)]


class FakeClaudeMessages:
    def __init__(self, text: str):
        self._text = text

    def create(self, **kwargs):
        return FakeClaudeResponse(self._text)


class FakeClaudeClient:
    def __init__(self, text: str):
        self.messages = FakeClaudeMessages(text)


def test_generate_quiz_success(tmp_path):
    text = "Fotosynthese nutzt Lichtenergie."
    output_md = (
        "## Multi-choice: Was ist Fotosynthese? [4]\n"
        "- Atmen von Tieren\n"
        "- Umwandlung von Licht in Energie*\n"
        "- Verdunstung von Wasser\n"
        "- Prozess in Pflanzen*\n"
        "- Noch eine falsche Antwort\n"
    )
    client = FakeClient(output_md)
    gen = QuizGenerator(model="gpt-5", client=client, config=TEST_CONFIG)
    res = gen.generate(text=text, questions=1, points=4, num_correct=2, num_incorrect=3)
    assert "# Quiz" in res.quiz_markdown
    assert "Multi-choice: Was ist Fotosynthese?" in res.quiz_markdown


def test_generate_quiz_empty_text_error():
    gen = QuizGenerator(model="gpt-5", config=TEST_CONFIG)
    try:
        gen.generate(text="   ", questions=1)
    except ValueError as e:
        assert "empty" in str(e)


def test_generate_cloze_success():
    text = "Energie und Bewegung"
    output_md = (
        "## Cloze: Fülle die Lücken mit den passendsten Begriffen aus.\n"
        "Energie ist die Fähigkeit etwas zu {bewirken}. Dies wird im {2:Energieerhaltungsgesetz|Gesetz der Energieerhaltung} beschrieben.\n"
    )
    client = FakeClient(output_md)
    gen = QuizGenerator(model="gpt-5", client=client, config=TEST_CONFIG)
    res = gen.generate(text=text, questions=1, qtype="cl")
    assert "# Quiz" in res.quiz_markdown
    assert "## Cloze:" in res.quiz_markdown
    assert "{" in res.quiz_markdown and "}" in res.quiz_markdown


def test_generate_matching_success():
    text = "Energieformen Zuordnung"
    output_md = (
        "## Matching: Ordne die hauptsächlichen Energieformen den Beispielen zu. [3]\n"
        "- Mechanische Energie = Ein rollender Ball\n"
        "- Chemische Energie = Verbrennung von Holz\n"
        "- Elektrische Energie = Strom aus der Steckdose\n"
        "- Strahlungsenergie = Sonnenlicht\n"
        "- Thermische Energie = Erwärmtes Wasser\n"
    )
    client = FakeClient(output_md)
    gen = QuizGenerator(model="gpt-5", client=client, config=TEST_CONFIG)
    res = gen.generate(text=text, questions=1, qtype="ma", pairs=5)
    assert "# Quiz" in res.quiz_markdown
    assert "## Matching:" in res.quiz_markdown
    assert " = " in res.quiz_markdown


def test_matching_pairs_trim():
    text = "Energieformen Zuordnung"
    output_md = (
        "## Matching: Ordne die hauptsächlichen Energieformen den Beispielen zu.\n"
        "- Mechanische Energie = Ein rollender Ball\n"
        "- Chemische Energie = Verbrennung von Holz\n"
        "- Elektrische Energie = Strom aus der Steckdose\n"
        "- Strahlungsenergie = Sonnenlicht\n"
        "- Thermische Energie = Erwärmtes Wasser\n"
    )
    client = FakeClient(output_md)
    gen = QuizGenerator(model="gpt-5", client=client, config=TEST_CONFIG)
    res = gen.generate(text=text, questions=1, qtype="ma", pairs=4)
    # Explicitly trim to 4 pairs.
    lines = [l for l in res.quiz_markdown.splitlines() if l.startswith("- ")]
    assert len(lines) == 4


def test_generate_quiz_with_gemini_provider():
    text = "Fotosynthese nutzt Lichtenergie."
    output_md = (
        "## Multi-choice: Was ist Fotosynthese? [4]\n"
        "- Atmen von Tieren\n"
        "- Umwandlung von Licht in Energie*\n"
        "- Verdunstung von Wasser\n"
        "- Prozess in Pflanzen*\n"
        "- Noch eine falsche Antwort\n"
    )
    client = FakeGeminiClient(output_md)
    gen = QuizGenerator(provider="gemini", model="gemini-2.5-flash", client=client, config=TEST_CONFIG)
    res = gen.generate(text=text, questions=1, points=4, num_correct=2, num_incorrect=3)
    assert "# Quiz" in res.quiz_markdown
    assert "Multi-choice: Was ist Fotosynthese?" in res.quiz_markdown


def test_generate_quiz_with_claude_provider():
    text = "Fotosynthese nutzt Lichtenergie."
    output_md = (
        "## Multi-choice: Was ist Fotosynthese? [4]\n"
        "- Atmen von Tieren\n"
        "- Umwandlung von Licht in Energie*\n"
        "- Verdunstung von Wasser\n"
        "- Prozess in Pflanzen*\n"
        "- Noch eine falsche Antwort\n"
    )
    client = FakeClaudeClient(output_md)
    gen = QuizGenerator(provider="claude", model="claude-3-5-sonnet-latest", client=client, config=TEST_CONFIG)
    res = gen.generate(text=text, questions=1, points=4, num_correct=2, num_incorrect=3)
    assert "# Quiz" in res.quiz_markdown
    assert "Multi-choice: Was ist Fotosynthese?" in res.quiz_markdown


def test_generate_essay_returns_raw_response_without_validation():
    text = "Fotosynthese nutzt Lichtenergie."
    raw_output = "## Essay: Erkläre die Fotosynthese.\nSchreibe deine Antwort frei.\n"
    client = FakeClient(raw_output)
    gen = QuizGenerator(model="gpt-5", client=client, config=TEST_CONFIG)
    res = gen.generate(text=text, questions=2, qtype="es", num_correct=99, num_incorrect=99)
    assert res.quiz_markdown.startswith("# Quiz\n")
    assert "## Essay: Erkläre die Fotosynthese. [4]" in res.quiz_markdown
    assert res.raw_response == raw_output


def test_generate_essay_with_claude_provider_includes_quiz_header():
    text = "Fotosynthese nutzt Lichtenergie."
    raw_output = "## Essay: Beschreibe die Bedeutung der Fotosynthese.\nAntwort frei formulieren.\n"
    client = FakeClaudeClient(raw_output)
    gen = QuizGenerator(provider="claude", model="claude-3-5-sonnet-latest", client=client, config=TEST_CONFIG)
    res = gen.generate(text=text, questions=1, qtype="es")
    assert res.quiz_markdown.startswith("# Quiz\n")
    assert "## Essay: Beschreibe die Bedeutung der Fotosynthese. [4]" in res.quiz_markdown


def test_provider_defaults_in_cli_args():
    args = parse_args(["input.txt", "--provider", "claude"])
    assert args.provider == "claude"
    assert args.model is None


def test_parse_args_accepts_multiple_inputs():
    args = parse_args(["a.txt", "b.txt"])
    assert args.input == ["a.txt", "b.txt"]


def test_resolve_input_files_supports_globs(tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("A", encoding="utf-8")
    file_b.write_text("B", encoding="utf-8")

    resolved = resolve_input_files([str(tmp_path / "*.txt")])
    assert file_a.resolve() in resolved
    assert file_b.resolve() in resolved


def test_resolve_input_files_raises_on_unmatched_glob(tmp_path):
    with pytest.raises(ValueError, match="did not match any files"):
        resolve_input_files([str(tmp_path / "*.doesnotexist")])


def test_apply_config_defaults_from_cfg_for_mc():
    args = parse_args(["input.txt"])
    cfg = configparser.ConfigParser()
    cfg.read_dict(
        {
            "defaults": {"provider": "openai", "type": "mc", "questions": "4", "points": "4"},
            "multi_choice": {"answers": "2 3"},
            "cloze": {"blanks": "4"},
            "matching": {"pairs": "4"},
        }
    )

    apply_config_defaults(args, cfg)
    assert args.provider == "openai"
    assert args.type == "mc"
    assert args.questions == 4
    assert args.points == 4
    assert args.answers == [2, 3]


def test_apply_config_defaults_cli_overrides_cfg():
    args = parse_args(
        [
            "input.txt",
            "--provider",
            "gemini",
            "--type",
            "cl",
            "--questions",
            "3",
            "--blanks",
            "6",
        ]
    )
    cfg = configparser.ConfigParser()
    cfg.read_dict(
        {
            "defaults": {"provider": "openai", "type": "mc", "questions": "4", "points": "4"},
            "multi_choice": {"answers": "2 3"},
            "cloze": {"blanks": "4"},
            "matching": {"pairs": "4"},
        }
    )

    apply_config_defaults(args, cfg)
    assert args.provider == "gemini"
    assert args.type == "cl"
    assert args.questions == 3
    assert args.points == 4
    assert args.blanks == 6


def test_apply_config_defaults_missing_required_option_raises():
    args = parse_args(["input.txt"])
    cfg = configparser.ConfigParser()
    cfg.read_dict(
        {
            "defaults": {"provider": "openai", "type": "mc", "questions": "4", "points": "4"},
            # Missing multi_choice.answers on purpose.
            "multi_choice": {},
            "cloze": {"blanks": "4"},
            "matching": {"pairs": "4"},
        }
    )

    with pytest.raises(ValueError, match="missing required option 'answers'"):
        apply_config_defaults(args, cfg)


def test_apply_config_defaults_missing_points_raises():
    args = parse_args(["input.txt"])
    cfg = configparser.ConfigParser()
    cfg.read_dict(
        {
            "defaults": {"provider": "openai", "type": "mc", "questions": "4"},
            "multi_choice": {"answers": "2 3"},
            "cloze": {"blanks": "4"},
            "matching": {"pairs": "4"},
        }
    )

    with pytest.raises(ValueError, match="missing required option 'points'"):
        apply_config_defaults(args, cfg)


def test_main_writes_invalid_quiz_with_error_suffix(tmp_path, monkeypatch):
    input_path = tmp_path / "lesson.txt"
    input_path.write_text("Fotosynthese nutzt Lichtenergie.", encoding="utf-8")

    def fake_generate(self, **kwargs):
        return GenerationResult(
            quiz_markdown="# Quiz\n## Multi-choice: Frage\n- A\n- B\n",
            raw_response="## Multi-choice: Frage\n- A\n- B\n",
            validation_warning="Multi-choice must have at least 1 correct answer.",
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(QuizGenerator, "generate", fake_generate)

    with pytest.warns(UserWarning, match="Quiz validation failed"):
        exit_code = main([str(input_path)])

    assert exit_code == 0
    error_output_candidates = [
        tmp_path / "lesson-multi-choice(error).md",
        tmp_path / "lesson-multi-choice-(error).md",
    ]
    error_output = next((p for p in error_output_candidates if p.exists()), None)
    assert error_output is not None
    assert "# Quiz" in error_output.read_text(encoding="utf-8")


def test_main_debug_writes_raw_native_response_json(tmp_path, monkeypatch):
    input_path = tmp_path / "lesson.txt"
    input_path.write_text("Fotosynthese nutzt Lichtenergie.", encoding="utf-8")

    def fake_generate(self, **kwargs):
        return GenerationResult(
            quiz_markdown="# Quiz\n## Multi-choice: Frage\n- A*\n- B\n",
            raw_response="## Multi-choice: Frage\n- A*\n- B\n",
            raw_native_response_json='{"provider":"claude","response":{"content":[{"text":"## Multi-choice: Frage\\n- A*\\n- B"}]}}',
            validation_warning=None,
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(QuizGenerator, "generate", fake_generate)

    exit_code = main([str(input_path), "--debug"])
    assert exit_code == 0

    raw_output = tmp_path / "lesson-multi-choice-raw-response.json"
    assert raw_output.exists()
    assert '"provider":"claude"' in raw_output.read_text(encoding="utf-8")


def test_main_multiple_inputs_writes_one_output_per_input(tmp_path, monkeypatch):
    input_a = tmp_path / "lesson-a.txt"
    input_b = tmp_path / "lesson-b.txt"
    input_a.write_text("Text A", encoding="utf-8")
    input_b.write_text("Text B", encoding="utf-8")

    def fake_generate(self, **kwargs):
        return GenerationResult(
            quiz_markdown="# Quiz\n## Multi-choice: Frage\n- A*\n- B\n",
            raw_response="## Multi-choice: Frage\n- A*\n- B\n",
            validation_warning=None,
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(QuizGenerator, "generate", fake_generate)

    exit_code = main([str(input_a), str(input_b)])
    assert exit_code == 0

    output_a = tmp_path / "lesson-a-multi-choice-openai.md"
    output_b = tmp_path / "lesson-b-multi-choice-openai.md"
    assert output_a.exists()
    assert output_b.exists()


def test_quizvalidation_cli_from_raw_response_file(tmp_path):
    raw_path = tmp_path / "raw.json"
    raw_payload = (
        '{'
        '"provider":"claude",'
        '"response":{' 
        '"content":[{"text":"## Multi-choice: Frage 1\\n- Richtig*\\n- Falsch\\n"}]'
        '}'
        '}'
    )
    raw_path.write_text(raw_payload, encoding="utf-8")

    exit_code = validation_main([
        str(raw_path),
        "--provider",
        "claude",
        "--type",
        "mc",
        "--questions",
        "1",
    ])
    assert exit_code == 0
    output = tmp_path / "raw-validated.md"
    assert output.exists()
    assert "# Quiz" in output.read_text(encoding="utf-8")