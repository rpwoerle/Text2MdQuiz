from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional


class FormatError(Exception):
    """Raised when the model output does not match the required quiz format."""


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


def append_error_suffix(path: Path) -> Path:
    """Append '(error)' to the filename stem before the extension."""
    return path.with_name(f"{path.stem}(error){path.suffix}")


def parse_quiz(md: str) -> List[Question]:
    """Parse a quiz markdown string into structured questions."""
    lines = [l.rstrip() for l in md.strip().splitlines()]
    i = 0
    questions: List[Question] = []

    # Skip "# Quiz" header if present
    if i < len(lines) and lines[i].startswith("# Quiz"):
        i += 1
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
            # Some providers insert a blank line after the heading before answers.
            while i < len(lines) and not lines[i].strip():
                i += 1

            while i < len(lines) and ANSWER_RE.match(lines[i]):
                raw = lines[i]
                if re.match(r"^-\s*Rationale\s*:", raw):
                    i += 1
                    continue
                cleaned = re.sub(r"\s*\[\[[^\]]*\]\]\s*$", "", raw).rstrip()
                is_correct = cleaned.endswith("*")
                text = cleaned[2:].strip()
                if is_correct:
                    text = text[:-1].rstrip()
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
            body_lines: List[str] = []
            while i < len(lines):
                if QUESTION_RE.match(lines[i]):
                    break
                body_lines.append(lines[i])
                i += 1

            while body_lines and body_lines[-1].strip() == "":
                body_lines.pop()
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
    pairs: int | None = None,
) -> str:
    """Normalize quiz markdown to the canonical format."""
    questions = parse_quiz(md)
    out_lines: List[str] = ["# Quiz"]
    for idx, q in enumerate(questions):
        computed_points = q.points
        if q.question_type == "Cloze" and q.body:
            blank_count = len(re.findall(r"\{[^}]+\}", q.body))
            if blank_count > 0:
                computed_points = blank_count

        if q.question_type == "Cloze":
            points_str = ""
        else:
            points_str = f" [{computed_points}]" if computed_points > 1 else ""
        out_lines.append(f"## {q.question_type}: {q.prompt}{points_str}")

        if q.question_type == "Multi-choice":
            correct = [a for a in q.answers if a.is_correct]
            incorrect = [a for a in q.answers if not a.is_correct]
            selected_answers = correct[:num_correct] + incorrect[:num_incorrect]
            for a in selected_answers:
                suffix = "*" if a.is_correct else ""
                out_lines.append(f"- {a.text}{suffix}")
        elif q.question_type == "Cloze":
            if q.body:

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
    """Validate quiz and raise FormatError on violations."""
    questions = parse_quiz(md)
    if expected_questions is not None and len(questions) != expected_questions:
        raise FormatError(f"Expected {expected_questions} questions, got {len(questions)}.")

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


def extract_content_from_native_response(native_payload: dict[str, Any], provider: str) -> str:
    """Extract markdown text from a provider-native response payload encoded as JSON."""
    response = native_payload.get("response", native_payload)

    if provider == "openai":
        choices = response.get("choices") if isinstance(response, dict) else None
        if not choices:
            return ""
        c0 = choices[0]
        msg = c0.get("message", {}) if isinstance(c0, dict) else {}
        content = msg.get("content") if isinstance(msg, dict) else ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
            return "\n".join(parts)
        return ""

    if provider == "gemini":
        text = response.get("text") if isinstance(response, dict) else None
        if isinstance(text, str) and text.strip():
            return text
        candidates = response.get("candidates", []) if isinstance(response, dict) else []
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            content = cand.get("content", {})
            parts = content.get("parts", []) if isinstance(content, dict) else []
            part_texts = [
                p.get("text", "")
                for p in parts
                if isinstance(p, dict) and isinstance(p.get("text"), str) and p.get("text", "").strip()
            ]
            if part_texts:
                return "\n".join(part_texts)
        return ""

    # Claude
    blocks = response.get("content", []) if isinstance(response, dict) else []
    texts = [
        b.get("text", "")
        for b in blocks
        if isinstance(b, dict) and isinstance(b.get("text"), str) and b.get("text", "").strip()
    ]
    return "\n".join(texts)


def validate_ai_response(
    content: str,
    *,
    qtype: str,
    questions: int,
    num_correct: int,
    num_incorrect: int,
    blanks: int | None,
    pairs: int | None,
) -> tuple[str, str | None]:
    """Validate and normalize AI response text into canonical quiz markdown."""
    try:
        preliminary = parse_quiz(content)
    except FormatError:
        preliminary = []

    if preliminary:
        if qtype == "cl" and blanks is not None and blanks > 0:
            for q in preliminary:
                if q.question_type == "Cloze":
                    blank_count = len(re.findall(r"\{[^}]+\}", q.body or ""))
                    if blank_count != blanks:
                        raise FormatError(
                            f"Cloze question has {blank_count} blanks but --blanks {blanks} was requested."
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
        num_correct=num_correct,
        num_incorrect=num_incorrect,
        pairs=pairs if qtype == "ma" else None,
    )

    validation_warning: str | None = None
    try:
        validate_quiz(quiz_md, expected_questions=questions)
    except FormatError as exc:
        validation_warning = str(exc)

    return quiz_md, validation_warning


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate and normalize quiz markdown from a raw provider response JSON file.")
    p.add_argument(
        "raw", 
        type=Path, 
        help="Path to raw response JSON file"
    )
    p.add_argument(
        "--provider",
        "-p",
        choices=["openai", "gemini", "claude"],
        required=True,
        help="Provider used to generate the raw response",
    )
    p.add_argument(
        "--type",
        "-t",
        choices=["mc", "cl", "ma"],
        default="mc",
        help="Question type: mc=Multi-choice, cl=Cloze, ma=Matching (default: mc)",
    )
    p.add_argument("--questions", 
        "-q", 
        type=int, 
        default=4, 
        help="Expected number of questions"
    )
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
        "--blanks", 
        type=int, 
        default=4, 
        help="Exact number of blanks for Cloze"
    )
    p.add_argument(
        "--pairs", 
        type=int, 
        default=4, 
        help="Exact number of pairs for Matching"
    )
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        required=False,
        help="Output path for normalized markdown (default: <raw-stem>-validated-<type>.md)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    args = parse_args(argv)

    if not args.raw.exists():
        print(f"Error: Raw response file not found: {args.raw}", file=sys.stderr)
        return 1

    try:
        native_payload = json.loads(args.raw.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error: Could not parse JSON from {args.raw}: {exc}", file=sys.stderr)
        return 1

    content = extract_content_from_native_response(native_payload, args.provider)
    if not content.strip():
        print("Error: No response content could be extracted from raw JSON.", file=sys.stderr)
        return 1

    num_correct, num_incorrect = args.answers
    try:
        quiz_md, validation_warning = validate_ai_response(
            content,
            qtype=args.type,
            questions=args.questions,
            num_correct=num_correct,
            num_incorrect=num_incorrect,
            blanks=args.blanks if args.type == "cl" else None,
            pairs=args.pairs if args.type == "ma" else None,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.output is None:
        # type_label_map = {"mc": "multi-choice", "cl": "cloze", "ma": "matching"}
        # type_label = type_label_map.get(args.type, args.type)
        output_path = args.raw.with_name(f"{args.raw.stem}-validated.md")
    else:
        output_path = args.output

    if validation_warning:
        output_path = append_error_suffix(output_path)
        warnings.warn(
            f"Quiz validation failed: {validation_warning}. Writing quiz to {output_path}",
            UserWarning,
            stacklevel=1,
        )

    output_path.write_text(quiz_md, encoding="utf-8")
    print(f"Wrote quiz to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
