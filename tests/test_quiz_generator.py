from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path to import text2mdquiz
sys.path.insert(0, str(Path(__file__).parent.parent))

from text2mdquiz import QuizGenerator


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
    gen = QuizGenerator(model="gpt-5", client=client)
    res = gen.generate(text=text, questions=1, points=4, num_correct=2, num_incorrect=3)
    assert "# Quiz" in res.quiz_markdown
    assert "Multi-choice: Was ist Fotosynthese?" in res.quiz_markdown


def test_generate_quiz_empty_text_error():
    gen = QuizGenerator(model="gpt-5")
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
    gen = QuizGenerator(model="gpt-5", client=client)
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
    gen = QuizGenerator(model="gpt-5", client=client)
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
    gen = QuizGenerator(model="gpt-5", client=client)
    res = gen.generate(text=text, questions=1, qtype="ma", pairs=3)
    # Expect only 3 pairs in normalized output
    lines = [l for l in res.quiz_markdown.splitlines() if l.startswith("- ")]
    assert len(lines) == 3
