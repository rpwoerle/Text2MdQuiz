from __future__ import annotations

import configparser
import sys
from pathlib import Path

import pytest

# Add parent directory to path to import text2mdquiz
sys.path.insert(0, str(Path(__file__).parent.parent))

from text2mdquiz import QuizGenerator


def _minimal_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read_dict(
        {
            "multi_choice": {
                "system_prompt": "You are a quiz generator.",
                "user_prompt": "Create {num_questions} questions with {total_answers} answers.{points_str}",
            },
            "cloze": {
                "system_prompt": "You are a quiz generator.",
                "user_prompt": "Create a cloze with {num_blanks} blanks.",
            },
            "matching": {
                "system_prompt": "You are a quiz generator.",
                "user_prompt": "Create {num_questions} matching questions.{pairs_spec}{points_str}",
            },
        }
    )
    return cfg


def test_generate_pdf_path_skips_text_empty_validation(monkeypatch, tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    cfg = _minimal_config()
    gen = QuizGenerator(provider="openai", model="gpt-5", config=cfg)

    def fake_call(*args, **kwargs):
        class Resp:
            choices = [type("Choice", (), {"message": type("Msg", (), {"content": "## Multi-choice: Frage\n- A*\n- B\n"})()})]

        return Resp()

    monkeypatch.setattr(gen, "_call_openai", fake_call)

    result = gen.generate(text="", questions=1, qtype="mc", input_pdf_path=pdf_path)

    assert "# Quiz" in result.quiz_markdown


def test_generate_pdf_provider_error_is_graceful(monkeypatch, tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    cfg = _minimal_config()
    gen = QuizGenerator(provider="openai", model="gpt-5", config=cfg)

    def fail_call(*args, **kwargs):
        raise RuntimeError("upstream provider failure")

    monkeypatch.setattr(gen, "_call_openai", fail_call)

    with pytest.raises(RuntimeError, match="PDF request failed"):
        gen.generate(text="", questions=1, qtype="mc", input_pdf_path=pdf_path)
