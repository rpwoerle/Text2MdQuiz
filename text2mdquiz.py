#!/usr/bin/env python3
"""Generate quizzes (Multi-choice, Cloze, Matching) from text files using OpenAI's GPT API.

Usage:
    python text2mdquiz.py input.txt [--questions 4] [--points 4] [--answers 2 3] [--type mc|cl|ma] [--output quiz.md] [--model gpt-5]

The quiz language matches the input text (multi-language, especially German supported).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore

try:  # OpenAI SDK v1
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore


class FormatError(Exception):
    """Raised when the model's output does not match the required quiz format."""


SYSTEM_PROMPT = "You are an experienced K-12 teacher creating educational quizzes for students."

def build_user_prompt(
    text: str,
    num_questions: int,
    points: int = 4,
    num_correct: int = 2,
    num_incorrect: int = 3,
    qtype: str = "mc",
    gaps: int | None = None,
    pairs: int | None = None,
) -> str:
    """Build user prompt with explicit formatting and language rules for the selected type.

    qtype: 'mc' (Multi-choice), 'cl' (Cloze), 'ma' (Matching)
    """
    points_str = f" [{points}]" if points > 1 else ""
    if qtype == "mc":
        total_answers = num_correct + num_incorrect
        spec = f"""
Generate exactly {num_questions} multiple-choice questions in the SAME language as the provided text.

Formatting requirements (strict):
- Each question must be a level-2 Markdown heading starting with: ## Multi-choice: <question>{points_str}
- Provide exactly {total_answers} answer choices for each question.
- Start every answer with a hyphen and a space: - <answer>
- Mark correct answers by adding a trailing asterisk: - <answer>*
- Provide exactly {num_correct} correct answers per question solely from the provided text.
- Include exactly {num_incorrect} incorrect answers as plausible distractors.
- You may invent these incorrect answers, but they must be plausible within the context of the question and the subject matter and do not simply reverse any correct answer to generate an incorrect option.
- Put a single blank line between questions.

Only output the quiz in Markdown. Do not include explanations or any text outside the quiz.
"""

        example = f"""
Example (format only; content will differ):
## Multi-choice: Beispielfrage?{points_str}
- Falsche Antwort
- Richtige Antwort*
- Falsche Antwort
- Richtige Antwort*
""".strip()
    elif qtype == "cl":
        spec = f"""
Generate exactly {num_questions} Cloze questions (Lückentexte) in the SAME language as the provided text.
restrictions:
- Use only single words as gaps. The words should be nouns, verbs or specialist terms relevant to the subject matter.
- Do not use the gap words in the surrounding text or as part of other words. 

Formatting requirements (strict):
- Each question must be a level-2 Markdown heading starting with: ## Cloze: <short instruction or title>
- Immediately after the heading, include the cloze text paragraph(s) using curly braces for blanks.
- Use braces with the correct answer and optional alternatives separated by pipes, e.g., {{Photosynthese|Assimilation}}.
- You may optionally include a leading integer weight, e.g., {{2:Energieerhaltungsgesetz|Gesetz der Energieerhaltung|Energieerhaltung}}.
- Put a single blank line between questions.

Defaults and counts:
- Assign 1 point per blank; total points for the question equals the number of blanks.
- If no explicit weight is provided for a blank, prefix the blank with `1:` (e.g., `{{1:Antwort|Alt1}}`).
"""

        if gaps is not None and gaps > 0:
            spec += f"\n- Include exactly {gaps} blanks (curly-brace fields).\n"
        spec += "\nOnly output the quiz in Markdown. Do not include explanations or any text outside the quiz.\n"

        example = (
            "## Cloze: Fülle die Lücken mit den passendsten Begriffen aus.\n"
            "Energie ist die Fähigkeit durch ihre Umwandlung etwas zu {1:bewirken}. Energie kann von einer Form in eine andere umgewandelt werden, aber sie kann weder geschaffen noch zerstört werden, was als {2:Energieerhaltungsgesetz|Gesetz der Energieerhaltung|Energieerhaltung} bekannt ist. Beispiel: Bei einem Skater in der Halfpipe wird die {1:potenzielle Energie|Lageenergie|Höhenenergie} am höchsten Punkt in {1:kinetische Energie} umgewandelt, wenn er nach unten fährt. Auf der anderen Seite erreicht er nicht mehr die gleiche Höhe, weil ein Teil der Energie durch {1:Reibung} in {1:Wärmeenergie|thermische Energie} umgewandelt wird."
        )
    else:  # qtype == "ma"
        spec = f"""
Generate exactly {num_questions} Matching questions in the SAME language as the provided text.

Formatting requirements (strict):
- Each question must be a level-2 Markdown heading starting with: ## Matching: <instruction>{points_str}
- Provide pairs on separate lines after the heading.
- Each pair must be formatted with a hyphen, a space, the left term, an equals sign, and the right term: - <Left> = <Right>
- Do not add trailing asterisks here.
- Put a single blank line between questions.

Only output the quiz in Markdown. Do not include explanations or any text outside the quiz.
"""

        if pairs is not None and pairs > 0:
            spec += f"\n- Include exactly {pairs} pairs.\n"

        example = (
            "## Matching: Ordne die hauptsächlichen Energieformen den Beispielen zu.\n"
            "- Mechanische Energie = Ein rollender Ball\n"
            "- Chemische Energie = Verbrennung von Holz\n"
            "- Elektrische Energie = Strom aus der Steckdose\n"
            "- Strahlungsenergie = Sonnenlicht\n"
            "- Thermische Energie = Erwärmtes Wasser"
        )

    return spec + "\n\nTEXT:\n" + text + "\n\n" + example

QUESTION_RE = re.compile(r"^##\s+(Multi-choice|Cloze|Matching):\s+.+")
ANSWER_RE = re.compile(r"^-\s+.+")
@dataclass
class Answer:
    text: str
    is_correct: bool


@dataclass
class Question:
    prompt: str
    answers: List[Answer]
    question_type: str = "Multi-choice"
    points: int = 1
    body: Optional[str] = None  # For Cloze
    pairs: Optional[List[tuple[str, str]]] = None  # For Matching

def parse_quiz(md: str) -> List[Question]:
    """Parse a quiz markdown string into structured questions."""
    lines = [l.rstrip() for l in md.strip().splitlines()]
    i = 0
    questions: List[Question] = []
    
    # Skip "# Quiz" header if present
    if i < len(lines) and lines[i].startswith("# Quiz"):
        i += 1
        # Skip blank line after header
        if i < len(lines) and not lines[i].strip():
            i += 1

    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue
        if not QUESTION_RE.match(line):
            raise FormatError(
                f"Expected question heading starting with '## (Multi-choice|Cloze|Matching): ' at line {i+1}: {line!r}"
            )
        
        # Parse: "## Multi-choice: Question text [2]"
        match = re.match(r"^##\s+(Multi-choice|Cloze|Matching):\s+(.+?)(?:\s+\[(\d+)\])?$", line)
        if not match:
            raise FormatError(f"Invalid question format at line {i+1}: {line!r}")
        
        question_type = match.group(1)
        prompt = match.group(2).strip()
        points = int(match.group(3)) if match.group(3) else 1
        i += 1

        answers: List[Answer] = []
        body: Optional[str] = None
        pairs: Optional[List[tuple[str, str]]] = None

        if question_type == "Multi-choice":
            # Collect all answer lines
            while i < len(lines) and ANSWER_RE.match(lines[i]):
                raw = lines[i]
                is_correct = raw.endswith("*")
                text = raw[2:].rstrip("*").strip()
                if not text:
                    raise FormatError(f"Empty answer at line {i+1}")
                answers.append(Answer(text=text, is_correct=is_correct))
                i += 1

            if i < len(lines) and lines[i].strip() == "":
                i += 1

            if len(answers) < 2:
                raise FormatError(
                    f"Each Multi-choice question must have at least 2 answers (got {len(answers)} for '{prompt}')."
                )
            correct_count = sum(a.is_correct for a in answers)
            if correct_count < 1:
                raise FormatError(
                    f"Each Multi-choice question must have at least 1 correct answer marked with '*' (got {correct_count} for '{prompt}')."
                )
        elif question_type == "Cloze":
            # Collect paragraphs until next question header or EOF
            body_lines: List[str] = []
            while i < len(lines):
                if QUESTION_RE.match(lines[i]):
                    break
                body_lines.append(lines[i])
                i += 1
            # Trim trailing blank lines
            while body_lines and body_lines[-1].strip() == "":
                body_lines.pop()
            # Skip single blank line between questions
            if i < len(lines) and lines[i].strip() == "":
                i += 1
            body = "\n".join(body_lines).strip()
            if not body:
                raise FormatError(f"Cloze question body is empty for '{prompt}'.")
        else:  # Matching
            pairs = []
            pair_re = re.compile(r"^-\s+(.+?)\s*=\s*(.+)$")
            while i < len(lines) and pair_re.match(lines[i]):
                m = pair_re.match(lines[i])
                assert m
                left = m.group(1).strip()
                right = m.group(2).strip()
                pairs.append((left, right))
                i += 1
            if i < len(lines) and lines[i].strip() == "":
                i += 1
            if len(pairs) < 2:
                raise FormatError(f"Matching question must have at least 2 pairs for '{prompt}'.")

        questions.append(
            Question(
                prompt=prompt,
                answers=answers,
                question_type=question_type,
                points=points,
                body=body,
                pairs=pairs,
            )
        )

    if not questions:
        raise FormatError("No questions found in quiz output.")

    return questions


def normalize_quiz(
    md: str,
    num_correct: int = 2,
    num_incorrect: int = 3,
    *,
    qtype: str | None = None,
    gaps: int | None = None,
    pairs: int | None = None,
) -> str:
    """Normalize quiz markdown to the canonical format.
    
    Ensures the specified number of correct and incorrect answers per question.
    """
    questions = parse_quiz(md)
    out_lines: List[str] = ["# Quiz"]
    for idx, q in enumerate(questions):
        # Compute points for Cloze based on blanks (1 point per blank by default)
        computed_points = q.points
        if q.question_type == "Cloze" and q.body:
            gap_count = len(re.findall(r"\{[^}]+\}", q.body))
            if gap_count > 0:
                computed_points = gap_count
        # For Cloze, omit points in the heading entirely
        if q.question_type == "Cloze":
            points_str = ""
        else:
            points_str = f" [{computed_points}]" if computed_points > 1 else ""
        out_lines.append(f"## {q.question_type}: {q.prompt}{points_str}")

        if q.question_type == "Multi-choice":
            # Separate correct and incorrect answers
            correct = [a for a in q.answers if a.is_correct]
            incorrect = [a for a in q.answers if not a.is_correct]
            selected_answers = correct[:num_correct] + incorrect[:num_incorrect]
            for a in selected_answers:
                suffix = "*" if a.is_correct else ""
                out_lines.append(f"- {a.text}{suffix}")
        elif q.question_type == "Cloze":
            if q.body:
                # Add default '1:' weight to blanks that lack explicit weight
                def _add_weight(m: re.Match[str]) -> str:
                    inner = m.group(1).strip()
                    if re.match(r"^\d+\s*:", inner):
                        return "{" + inner + "}"
                    return "{1:" + inner + "}"

                body_weighted = re.sub(r"\{([^}]*)\}", _add_weight, q.body)
                out_lines.append(body_weighted)
        else:  # Matching
            if q.pairs:
                use_pairs = q.pairs
                if pairs is not None and pairs > 0:
                    use_pairs = use_pairs[:pairs]
                for left, right in use_pairs:
                    out_lines.append(f"- {left} = {right}")
        if idx < len(questions) - 1:
            out_lines.append("")
    return "\n".join(out_lines) + "\n"


def validate_quiz(md: str, expected_questions: int | None = None) -> None:
    """Validate quiz raises FormatError on violations."""
    questions = parse_quiz(md)
    if expected_questions is not None and len(questions) != expected_questions:
        raise FormatError(f"Expected {expected_questions} questions, got {len(questions)}.")

    # Per-type validations
    for q in questions:
        if q.question_type == "Multi-choice":
            if len(q.answers) < 2:
                raise FormatError("Multi-choice must have at least 2 answers.")
            if sum(a.is_correct for a in q.answers) < 1:
                raise FormatError("Multi-choice must have at least 1 correct answer.")
        elif q.question_type == "Cloze":
            if not q.body or not re.search(r"\{[^}]+\}", q.body):
                raise FormatError("Cloze must contain at least one {...} blank.")
        elif q.question_type == "Matching":
            if not q.pairs or len(q.pairs) < 2:
                raise FormatError("Matching must have at least 2 pairs.")


# ============================================================================
# QUIZ GENERATOR
# ============================================================================

@dataclass
class GenerationResult:
    quiz_markdown: str
    raw_response: str


class QuizGenerator:
    def __init__(self, model: str = "gpt-5", timeout: Optional[int] = 60, client: Any | None = None):
        self.model = model
        self.timeout = timeout
        self._client = client

    def generate(
        self,
        text: str,
        questions: int,
        points: int = 4,
        num_correct: int = 2,
        num_incorrect: int = 3,
        qtype: str = "mc",
        gaps: int | None = None,
        pairs: int | None = None,
    ) -> GenerationResult:
        if not text.strip():
            raise ValueError("Input text is empty.")
        if questions <= 0:
            raise ValueError("Number of questions must be positive.")

        user_prompt = build_user_prompt(
            text,
            questions,
            points,
            num_correct,
            num_incorrect,
            qtype,
            gaps=gaps,
            pairs=pairs,
        )

        try:
            client = self._client or (OpenAI() if OpenAI is not None else None)
            if client is None:
                raise RuntimeError("OpenAI SDK not available. Install 'openai' package or inject a client.")
            
            try:
                print("Sending request to OpenAI, please wait...")
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    timeout=self.timeout,
                )
            except Exception as inner:
                raise RuntimeError(f"OpenAI API error for model '{self.model}': {inner}") from inner
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}") from e

        def _get_content(r) -> str:
            try:
                choices = r.get("choices") if isinstance(r, dict) else getattr(r, "choices", None)
                if not choices:
                    return ""
                c0 = choices[0]
                if isinstance(c0, dict):
                    msg = c0.get("message")
                    if isinstance(msg, dict):
                        return msg.get("content", "")
                    return getattr(msg, "content", "")
                msg = getattr(c0, "message", None)
                if msg is None:
                    return getattr(c0, "message", "") or getattr(c0, "content", "")
                if isinstance(msg, dict):
                    return msg.get("content", "")
                return getattr(msg, "content", "")
            except Exception:
                return ""

        content = _get_content(resp)
        if not content:
            raise RuntimeError("Empty response from model.")

        # Early parse to enforce gap/pair counts before normalization alters output
        try:
            preliminary = parse_quiz(content)
        except FormatError:
            # Will be handled again in validate after normalization
            preliminary = []
        if preliminary:
            if qtype == "cl" and gaps is not None and gaps > 0:
                for q in preliminary:
                    if q.question_type == "Cloze":
                        gap_count = len(re.findall(r"\{[^}]+\}", q.body or ""))
                        if gap_count != gaps:
                            raise FormatError(
                                f"Cloze question has {gap_count} blanks but --gaps {gaps} was requested."
                            )
            if qtype == "ma" and pairs is not None and pairs > 0:
                for q in preliminary:
                    if q.question_type == "Matching":
                        pair_count = len(q.pairs or [])
                        if pair_count < pairs:
                            raise FormatError(
                                f"Matching question has {pair_count} pairs but at least {pairs} were requested."
                            )

        quiz_md = normalize_quiz(
            content,
            num_correct,
            num_incorrect,
            qtype=qtype,
            gaps=gaps,
            pairs=pairs,
        )
        validate_quiz(quiz_md, expected_questions=questions)

        return GenerationResult(quiz_markdown=quiz_md, raw_response=content)


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate a multiple-choice quiz from a text file.")
    p.add_argument("input", type=Path, help="Path to input text file")
    p.add_argument("--questions", "-q", type=int, default=4, help="Number of questions (default: 4)")
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        required=False,
        help="Output path: file path or directory (default: <input-stem>-questions.md in same folder)",
    )
    p.add_argument("--model", default="gpt-5", help="OpenAI model name (default: gpt-5)")
    p.add_argument("--points", "-p", type=int, default=4, help="Points per question (default: 4)")
    p.add_argument(
        "--answers",
        "-a",
        type=int,
        nargs=2,
        default=[2, 3],
        metavar=("CORRECT", "INCORRECT"),
        help="Number of correct and incorrect answers (default: 2 3)",
    )
    p.add_argument(
        "--type",
        "-t",
        choices=["mc", "cl", "ma"],
        default="mc",
        help="Question type: mc=Multi-choice, cl=Cloze, ma=Matching (default: mc)",
    )
    p.add_argument(
        "--gaps",
        type=int,
        default=4,
        help="Exact number of blanks for Cloze questions (default: 4).",
    )
    p.add_argument(
        "--pairs",
        type=int,
        default=4,
        help="Exact number of pairs for Matching questions (default: 4).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    
    if load_dotenv is not None:
        load_dotenv()
    
    args = parse_args(argv)
    # Override default questions for Cloze if user did not explicitly set --questions / -q
    if args.type == "cl" and not any(a in argv for a in ("--questions", "-q")):
        args.questions = 1

    # Validate API key presence early
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key.startswith("sk-REPLACE"):
        print("Error: OPENAI_API_KEY is not set. Create a .env file (see .env.example) or set the env var.", file=sys.stderr)
        print("Tip (PowerShell): $env:OPENAI_API_KEY='sk-...'  or create .env with OPENAI_API_KEY=sk-...", file=sys.stderr)
        return 1

    text = args.input.read_text(encoding="utf-8")
    
    # Determine default output path if not provided
    type_label_map = {"mc": "multi-choice", "cl": "cloze", "ma": "matching"}
    type_label = type_label_map.get(args.type, args.type)
    if args.output is None:
        default_name = f"{args.input.stem}-{type_label}.md"
        output_path = args.input.with_name(default_name)
    else:
        # If output is a directory, use default filename in that directory
        if args.output.is_dir():
            default_name = f"{args.input.stem}-{type_label}.md"
            output_path = args.output / default_name
        else:
            output_path = args.output
    
    gen = QuizGenerator(model=args.model)
    num_correct, num_incorrect = args.answers
    try:
        result = gen.generate(
            text=text,
            questions=args.questions,
            points=args.points,
            num_correct=num_correct,
            num_incorrect=num_incorrect,
            qtype=args.type,
            gaps=args.gaps,
            pairs=args.pairs,
        )
    except Exception as e:
        msg = str(e)
        print(f"Error: {msg}", file=sys.stderr)
        if "model" in msg.lower() and ("not found" in msg.lower() or "does not exist" in msg.lower()):
            print("Hint: The default model 'gpt-5' may not be available to your account. Try --model gpt-4o-mini", file=sys.stderr)
        return 1

    output_path.write_text(result.quiz_markdown, encoding="utf-8")
    print(f"Wrote quiz to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
