
"""Generate quizzes (Multi-choice, Cloze, Matching) from text files using OpenAI's GPT API.

Usage:
    python text2mdquiz.py input.txt [--questions 4] [--points 4] [--answers 2 3] [--type mc|cl|ma] [--output quiz.md] [--model gpt-5]

The quiz language matches the input text (multi-language, especially German supported).

Disclaimer: provided as is; no guaranteed functionality; developed with assistance from GitHub Copilot; please verify operation.
"""

from __future__ import annotations

import argparse
import configparser
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

DISCLAIMER = (
    "Provided as is; no guaranteed functionality; developed with assistance from GitHub Copilot; "
    "please verify operation."
)


def load_config(config_path: Path | None = None) -> configparser.ConfigParser:
    """Load configuration from file.
    
    Raises:
        FileNotFoundError: If config file not found at specified or default location.
    """
    config = configparser.ConfigParser()
    
    if config_path is None:
        # Try default location: text2mdquiz.cfg in script directory
        config_path = Path(__file__).parent / "text2mdquiz.cfg"
    
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Please create text2mdquiz.cfg or specify path with --config"
        )
    
    config.read(config_path, encoding="utf-8")
    return config


def get_section_name(qtype: str) -> str:
    """Get config section name for question type."""
    section_map = {"mc": "multi_choice", "cl": "cloze", "ma": "matching"}
    return section_map.get(qtype, qtype)


def _require_section(config: configparser.ConfigParser, section: str) -> None:
    if not config.has_section(section):
        raise ValueError(
            f"Configuration file missing [{section}] section. "
            f"Please ensure text2mdquiz.cfg has a [{section}] section."
        )


def get_system_prompt_from_section(config: configparser.ConfigParser, section: str) -> str:
    """Get system prompt from section, supporting system_prompt_file or system_prompt.
    
    Raises:
        ValueError: If neither system_prompt_file nor system_prompt is present.
    """
    _require_section(config, section)

    # Prefer external file
    if config.has_option(section, "system_prompt_file"):
        path = Path(config.get(section, "system_prompt_file")).expanduser()
        if not path.is_absolute():
            path = (Path(__file__).parent / path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"System prompt file not found: {path}")
        return path.read_text(encoding="utf-8").strip()

    # Fallback to inline system_prompt
    if config.has_option(section, "system_prompt"):
        return config.get(section, "system_prompt").strip()

    raise ValueError(
        f"Configuration for section [{section}] must define either system_prompt_file or system_prompt."
    )


def build_user_prompt(
    text: str,
    num_questions: int = 4,
    points: int = 4,
    num_correct: int = 2,
    num_incorrect: int = 3,
    qtype: str = "mc",
    blanks: int | None = None,
    pairs: int | None = None,
    config: configparser.ConfigParser | None = None,
) -> str:
    """Build user prompt with explicit formatting and language rules for the selected type.

    qtype: 'mc' (Multi-choice), 'cl' (Cloze), 'ma' (Matching)
    """
    if config is None:
        config = configparser.ConfigParser()
    
    points_str = f" [{points}]" if points > 1 else ""
    
    if qtype == "mc":
        total_answers = num_correct + num_incorrect
        section = "multi_choice"
        _require_section(config, section)

        # Prefer external user_prompt_file
        if config.has_option(section, "user_prompt_file"):
            path = Path(config.get(section, "user_prompt_file")).expanduser()
            if not path.is_absolute():
                path = (Path(__file__).parent / path).resolve()
            if not path.exists():
                raise FileNotFoundError(f"User prompt file not found: {path}")
            prompt_template = path.read_text(encoding="utf-8")
        elif config.has_option(section, "user_prompt"):
            prompt_template = config.get(section, "user_prompt")
        else:
            raise ValueError(
                f"Configuration for section [{section}] must define either user_prompt_file or user_prompt."
            )

        # Optional example: load from example_file if present; otherwise skip
        example_template = ""
        if config.has_option(section, "example_file"):
            ex_path = Path(config.get(section, "example_file")).expanduser()
            if not ex_path.is_absolute():
                ex_path = (Path(__file__).parent / ex_path).resolve()
            if ex_path.exists():
                example_template = ex_path.read_text(encoding="utf-8")
        
        spec = prompt_template.format(
            num_questions=num_questions,
            points_str=points_str,
            total_answers=total_answers,
            num_correct=num_correct,
            num_incorrect=num_incorrect
        )
        example = example_template.format(points_str=points_str) if example_template else ""
            
    elif qtype == "cl":
        section = "cloze"
        _require_section(config, section)

        if config.has_option(section, "user_prompt_file"):
            path = Path(config.get(section, "user_prompt_file")).expanduser()
            if not path.is_absolute():
                path = (Path(__file__).parent / path).resolve()
            if not path.exists():
                raise FileNotFoundError(f"User prompt file not found: {path}")
            prompt_template = path.read_text(encoding="utf-8")
        elif config.has_option(section, "user_prompt"):
            prompt_template = config.get(section, "user_prompt")
        else:
            raise ValueError(
                f"Configuration for section [{section}] must define either user_prompt_file or user_prompt."
            )
        example_template = ""
        if config.has_option(section, "example_file"):
            ex_path = Path(config.get(section, "example_file")).expanduser()
            if not ex_path.is_absolute():
                ex_path = (Path(__file__).parent / ex_path).resolve()
            if ex_path.exists():
                example_template = ex_path.read_text(encoding="utf-8")
        
        # For cloze, number of blanks comes from `blanks` if provided,
        # otherwise fall back to the number of questions.
        num_blanks = blanks if blanks is not None and blanks > 0 else num_questions
        spec = prompt_template.format(
            num_blanks=num_blanks,
        )
        example = example_template if example_template else ""
            
    else:  # qtype == "ma"
        section = "matching"
        _require_section(config, section)

        if config.has_option(section, "user_prompt_file"):
            path = Path(config.get(section, "user_prompt_file")).expanduser()
            if not path.is_absolute():
                path = (Path(__file__).parent / path).resolve()
            if not path.exists():
                raise FileNotFoundError(f"User prompt file not found: {path}")
            prompt_template = path.read_text(encoding="utf-8")
        elif config.has_option(section, "user_prompt"):
            prompt_template = config.get(section, "user_prompt")
        else:
            raise ValueError(
                f"Configuration for section [{section}] must define either user_prompt_file or user_prompt."
            )
        example_template = ""
        if config.has_option(section, "example_file"):
            ex_path = Path(config.get(section, "example_file")).expanduser()
            if not ex_path.is_absolute():
                ex_path = (Path(__file__).parent / ex_path).resolve()
            if ex_path.exists():
                example_template = ex_path.read_text(encoding="utf-8")
        
        # For matching, requested pairs per question come from `pairs` if provided,
        # otherwise we leave the model free (no explicit constraint).
        pairs_spec = ""
        if pairs is not None and pairs > 0:
            pairs_spec = f"- Include exactly {pairs} pairs per question."

        spec = prompt_template.format(
            num_questions=num_questions,
            points_str=points_str,
            pairs_spec=("\n" + pairs_spec) if pairs_spec else "",
        )
        example = example_template.format(points_str=points_str) if example_template else ""

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
                # Skip rationale/explanation lines that are not answers
                if re.match(r"^-\s*Rationale\s*:", raw):
                    i += 1
                    continue
                # Remove trailing explanation block in double brackets [[ ... ]] if present
                cleaned = re.sub(r"\s*\[\[[^\]]*\]\]\s*$", "", raw)
                is_correct = cleaned.endswith("*")
                text = cleaned[2:].rstrip("*").strip()
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
            blank_count = len(re.findall(r"\{[^}]+\}", q.body))
            if blank_count > 0:
                computed_points = blank_count
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
    def __init__(
        self, 
        model: str = "gpt-5", 
        timeout: Optional[int] = 180, 
        client: Any | None = None,
        config: configparser.ConfigParser | None = None
    ):
        self.model = model
        self.timeout = timeout
        self._client = client
        self.config = config if config is not None else configparser.ConfigParser()

    def generate(
        self,
        text: str,
        questions: int,
        points: int = 4,
        num_correct: int = 2,
        num_incorrect: int = 3,
        qtype: str = "mc",
        blanks: int | None = None,
        pairs: int | None = None,
    ) -> GenerationResult:
        if not text.strip():
            raise ValueError("Input text is empty.")
        if questions <= 0:
            raise ValueError("Number of questions must be positive.")

        user_prompt = build_user_prompt(
            text=text,
            num_questions=questions,
            points=points,
            num_correct=num_correct,
            num_incorrect=num_incorrect,
            qtype=qtype,
            blanks=blanks,
            pairs=pairs,
            config=self.config,
        )
        
        # Get section name and load section-specific system prompt and attachment
        section = get_section_name(qtype)
        system_prompt = get_system_prompt_from_section(self.config, section)

        try:
            client = self._client or (OpenAI() if OpenAI is not None else None)
            if client is None:
                raise RuntimeError("OpenAI SDK not available. Install 'openai' package or inject a client.")
            
            # Check for attachment file in question type section
            attachment_content = None
            if self.config.has_option(section, "attachment"):
                attachment_path = Path(self.config.get(section, "attachment"))
                if attachment_path.exists():
                    attachment_content = attachment_path.read_text(encoding="utf-8")
                    print(f"Loaded additional instructions from: {attachment_path}")
            
            try:
                print("Sending request to OpenAI, please wait...")
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                
                # If attachment exists, add it as an additional user message
                if attachment_content:
                    messages.insert(1, {
                        "role": "system", 
                        "content": f"Additional instructions:\n\n{attachment_content}"
                    })
                
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
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

        # Early parse to enforce blank/pair counts before normalization alters output
        try:
            preliminary = parse_quiz(content)
        except FormatError:
            # Will be handled again in validate after normalization
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
        validate_quiz(quiz_md, expected_questions=questions)

        return GenerationResult(quiz_markdown=quiz_md, raw_response=content)


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a multiple-choice quiz from a text file.",
        epilog=DISCLAIMER,
    )
    p.add_argument("input", type=Path, help="Path to input text file")
    # Default questions: 4 for Multi-choice, 1 for Cloze, 2 for Matching
    p.add_argument("--questions", "-q", type=int, default=4, help="Number of questions (default: 4 for Multi-choice)")
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
        "--blanks",
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
    p.add_argument(
        "--config",
        "-c",
        type=Path,
        required=False,
        help="Path to configuration file (default: text2mdquiz.cfg in script directory)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    
    if load_dotenv is not None:
        load_dotenv()
    
    args = parse_args(argv)
    
    # Load configuration
    config = load_config(args.config)

    # Override default questions per type if user did not explicitly set --questions / -q
    if not any(a in argv for a in ("--questions", "-q")):
        if args.type == "cl":
            args.questions = 1
        elif args.type == "ma":
            args.questions = 2

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
    
    gen = QuizGenerator(model=args.model, config=config)
    num_correct, num_incorrect = args.answers
    try:
        result = gen.generate(
            text=text,
            questions=args.questions,
            points=args.points,
            num_correct=num_correct,
            num_incorrect=num_incorrect,
            qtype=args.type,
            blanks=args.blanks if args.type == "cl" else None,
            pairs=args.pairs if args.type == "ma" else None,
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
