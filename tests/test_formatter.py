from __future__ import annotations

import pytest
import sys
from pathlib import Path

# Add parent directory to path to import text2mdquiz
sys.path.insert(0, str(Path(__file__).parent.parent))

from text2mdquiz import parse_quiz, validate_quiz, normalize_quiz, FormatError


def test_parse_and_validate_happy_path():
    md = (
        "# Quiz\n"
        "## Multi-choice: Frage 1\n"
        "- A\n"
        "- B*\n"
        "- C\n"
        "- D*\n\n"
        "## Multi-choice: Frage 2 [2]\n"
        "- A*\n"
        "- B\n"
        "- C*\n"
        "- D\n"
    )
    validate_quiz(md, expected_questions=2)
    q = parse_quiz(md)
    assert len(q) == 2
    assert sum(a.is_correct for a in q[0].answers) == 2
    assert q[0].question_type == "Multi-choice"
    assert q[0].points == 1
    assert q[1].points == 2


def test_missing_correct_answers():
    md = (
        "# Quiz\n"
        "## Multi-choice: Frage 1\n"
        "- A\n"
        "- B\n"
        "- C\n"
        "- D\n"
    )
    with pytest.raises(FormatError):
        validate_quiz(md)


def test_normalize_trims_and_spacing():
    md = (
        "## Multi-choice: Q\n"
        "- A*  \n"
        "- B\n"
        "- C\n"
        "- D*\n\n\n"
    )
    norm = normalize_quiz(md)
    assert norm.startswith("# Quiz\n")
    assert norm.endswith("\n")
    assert "\n\n\n" not in norm


def test_parse_validate_cloze():
    md = (
        "# Quiz\n"
        "## Cloze: Titel\n"
        "Dies ist ein {Test|Beispiel}.\n"
    )
    validate_quiz(md, expected_questions=1)
    q = parse_quiz(md)
    assert q[0].question_type == "Cloze"
    assert q[0].body and "{" in q[0].body


def test_parse_validate_matching():
    md = (
        "# Quiz\n"
        "## Matching: Ordne zu. [2]\n"
        "- A = A1\n"
        "- B = B1\n"
    )
    validate_quiz(md, expected_questions=1)
    q = parse_quiz(md)
    assert q[0].question_type == "Matching"
    assert q[0].pairs and len(q[0].pairs) == 2


def test_cloze_adds_default_weight_prefix():
    md = (
        "# Quiz\n"
        "## Cloze: Titel\n"
        "Dies ist ein {Test|Beispiel} und {2:Gewichtetes|Beispiel}.\n"
    )
    norm = normalize_quiz(md)
    # Expect first blank to be prefixed with 1:, second remains 2:
    assert "{1:Test|Beispiel}" in norm
    assert "{2:Gewichtetes|Beispiel}" in norm
