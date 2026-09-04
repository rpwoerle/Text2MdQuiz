
"""Generate quizzes (Multi-choice, Cloze, Matching) from text/PDF files using LLM APIs.

Usage:
    python text2mdquiz.py input.txt|input.pdf [--questions 4] [--points 4] [--answers 2 3] [--type mc|cl|ma] [--output quiz.md] [--provider openai|gemini|claude] [--model MODEL]

The quiz language matches the input text (multi-language, especially German supported).

Disclaimer: provided as is; no guaranteed functionality; developed with assistance from GitHub Copilot; please verify operation.
"""

from __future__ import annotations

import argparse
import base64
import configparser
import glob
import os
import re
import sys
import warnings
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

try:  # Gemini SDK
    from google import genai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    genai = None  # type: ignore

try:  # Anthropic SDK
    from anthropic import Anthropic  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Anthropic = None  # type: ignore


class FormatError(Exception):
    """Raised when the model's output does not match the required quiz format."""


class GenerationFormatError(FormatError):
    """Raised when generation produced content, but it failed quiz format checks."""

    def __init__(self, message: str, raw_response: str, quiz_markdown: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response
        self.quiz_markdown = quiz_markdown if quiz_markdown is not None else (
            raw_response if raw_response.endswith("\n") else raw_response + "\n"
        )

DISCLAIMER = (
    "Provided as is; no guaranteed functionality; developed with assistance from GitHub Copilot; "
    "please verify operation."
)

DEFAULT_MODEL_BY_PROVIDER = {
    "openai": "gpt-5",
    "gemini": "gemini-3.1-flash-lite",
    "claude": "claude-sonnet-4-6",
}


def _get_provider_api_key(provider: str) -> str:
    """Return API key for provider, loading .env as a fallback if needed.

    Supports API_KEY as an alias for OpenAI credentials.
    """

    def _read_key() -> str:
        if provider == "openai":
            return os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("API_KEY", "").strip()
        if provider == "gemini":
            return os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
        return os.getenv("ANTHROPIC_API_KEY", "").strip()

    api_key = _read_key()
    if api_key:
        # Normalize alias usage for SDKs that expect provider-specific names.
        if provider == "openai" and not os.getenv("OPENAI_API_KEY", "").strip():
            os.environ["OPENAI_API_KEY"] = api_key
        return api_key

    if load_dotenv is None:
        return ""

    # Try .env in the current working directory first, then script directory.
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=False)

    api_key = _read_key()
    if provider == "openai" and api_key and not os.getenv("OPENAI_API_KEY", "").strip():
        os.environ["OPENAI_API_KEY"] = api_key
    return api_key


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
    section_map = {"mc": "multi_choice", "cl": "cloze", "ma": "matching", "es": "essay"}
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


def resolve_input_files(inputs: list[str]) -> list[Path]:
    """Resolve explicit paths and glob patterns into existing input files."""
    resolved: list[Path] = []
    seen: set[Path] = set()

    for item in inputs:
        pattern = str(item)
        if any(ch in pattern for ch in "*?[]"):
            matches = sorted(glob.glob(pattern))
            if not matches:
                raise ValueError(f"Input pattern '{pattern}' did not match any files")
            for match in matches:
                p = Path(match).resolve()
                if p not in seen:
                    resolved.append(p)
                    seen.add(p)
            continue

        p = Path(pattern).resolve()
        if not p.exists():
            raise ValueError(f"Input file not found: {pattern}")
        if p not in seen:
            resolved.append(p)
            seen.add(p)

    return resolved


def apply_config_defaults(args: argparse.Namespace, config: configparser.ConfigParser) -> None:
    """Apply config values as defaults unless CLI explicitly provided an option."""
    required_sections = ["defaults", "multi_choice", "cloze", "matching"]
    for section in required_sections:
        if not config.has_section(section):
            raise ValueError(f"Configuration missing required section '{section}'")

    required_options = {
        "defaults": ["provider", "type", "questions", "points"],
        "multi_choice": ["answers"],
        "cloze": ["blanks"],
        "matching": ["pairs"],
    }
    for section, options in required_options.items():
        for option in options:
            if not config.has_option(section, option):
                raise ValueError(f"Configuration section [{section}] is missing required option '{option}'")

    cli_provided = getattr(args, "_cli_provided", set())

    if "provider" not in cli_provided:
        args.provider = config.get("defaults", "provider")
    if "type" not in cli_provided:
        args.type = config.get("defaults", "type")
    if "questions" not in cli_provided:
        args.questions = config.getint("defaults", "questions")
    if "points" not in cli_provided:
        args.points = config.getint("defaults", "points")
    if "answers" not in cli_provided:
        args.answers = [int(x) for x in config.get("multi_choice", "answers").split()]
    if "blanks" not in cli_provided:
        args.blanks = config.getint("cloze", "blanks")
    if "pairs" not in cli_provided:
        args.pairs = config.getint("matching", "pairs")


def build_user_prompt(
    text: str | None,
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

    qtype: 'mc' (Multi-choice), 'cl' (Cloze), 'ma' (Matching), 'es' (Essay)
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
            num_questions=num_questions,
            num_blanks=num_blanks,
        )
        # Keep the question count explicit even for existing custom prompt
        # templates which do not yet use the {num_questions} placeholder.
        spec = (
            f"Generate exactly {num_questions} separate cloze question(s), "
            f"each with exactly {num_blanks} blanks.\n\n{spec}"
        )
        example = example_template if example_template else ""
            
    elif qtype == "ma":
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

    else:  # qtype == "es"
        section = "essay"
        _require_section(config, section)

        essay_points_str = f" [{points}]"

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

        spec = prompt_template.format(num_questions=num_questions, points_str=essay_points_str)
        example = example_template.replace("{points_str}", essay_points_str) if example_template else ""

    if text is None:
        source_block = "\n\nSOURCE MATERIAL:\nUse the provided PDF document as the source text for the quiz.\n\n"
    else:
        source_block = "\n\nTEXT:\n" + text + "\n\n"
    return spec + source_block + example

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
            # Some providers insert a blank line after the heading before answers.
            while i < len(lines) and not lines[i].strip():
                i += 1

            # Collect all answer lines
            while i < len(lines) and ANSWER_RE.match(lines[i]):
                raw = lines[i]
                # Skip rationale/explanation lines that are not answers
                if re.match(r"^-\s*Rationale\s*:", raw):
                    i += 1
                    continue
                # Remove trailing explanation block in double brackets [[ ... ]] if present
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


def _ensure_essay_points(md: str, points: int) -> str:
    """Ensure each essay heading includes the configured points value."""
    heading_re = re.compile(r"^(##\s+Essay:\s+.+?)(?:\s+\[\d+\])?$")
    lines = md.splitlines()
    updated_lines: list[str] = []
    for line in lines:
        match = heading_re.match(line)
        if match:
            updated_lines.append(f"{match.group(1)} [{points}]")
        else:
            updated_lines.append(line)
    result = "\n".join(updated_lines)
    if md.endswith("\n"):
        result += "\n"
    return result


def _ensure_quiz_header(md: str) -> str:
    """Ensure markdown begins with '# Quiz' as the first non-empty line."""
    if not md.strip():
        return "# Quiz\n"

    lines = md.splitlines()
    first_non_empty_idx = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first_non_empty_idx is None:
        return "# Quiz\n"

    first_line = lines[first_non_empty_idx].lstrip("\ufeff").strip()
    if first_line.lower() == "# quiz":
        return md

    had_trailing_newline = md.endswith("\n")
    body = md.lstrip("\ufeff\r\n")
    result = f"# Quiz\n{body}"
    if had_trailing_newline and not result.endswith("\n"):
        result += "\n"
    return result


# ============================================================================
# QUIZ GENERATOR
# ============================================================================

@dataclass
class GenerationResult:
    quiz_markdown: str
    raw_response: str
    raw_native_response_json: str | None = None
    validation_warning: str | None = None


class QuizGenerator:
    def __init__(
        self, 
        model: str | None = None,
        provider: str = "openai",
        timeout: Optional[int] = 180, 
        client: Any | None = None,
        config: configparser.ConfigParser | None = None
    ):
        self.provider = provider
        self.model = model or DEFAULT_MODEL_BY_PROVIDER[provider]
        self.timeout = timeout
        self._client = client
        self.config = config if config is not None else configparser.ConfigParser()

    def _build_messages(self, system_prompt: str, user_prompt: str, attachment_content: str | None) -> list[dict[str, str]]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if attachment_content:
            messages.insert(
                1,
                {
                    "role": "system",
                    "content": f"Additional instructions:\n\n{attachment_content}",
                },
            )
        return messages

    def _call_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        attachment_content: str | None,
        input_pdf_path: Path | None = None,
    ) -> Any:
        client = self._client or (OpenAI() if OpenAI is not None else None)
        if client is None:
            raise RuntimeError("OpenAI SDK not available. Install 'openai' package or inject a client.")

        if input_pdf_path is not None:
            instructions = system_prompt
            if attachment_content:
                instructions += f"\n\nAdditional instructions:\n\n{attachment_content}"

            with input_pdf_path.open("rb") as f:
                uploaded = client.files.create(file=f, purpose="user_data")

            return client.responses.create(
                model=self.model,
                instructions=instructions,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_file", "file_id": uploaded.id},
                            {"type": "input_text", "text": user_prompt},
                        ],
                    }
                ],
            )

        messages = self._build_messages(system_prompt, user_prompt, attachment_content)
        return client.chat.completions.create(
            model=self.model,
            messages=messages,
            timeout=self.timeout,
        )

    def _call_gemini(
        self,
        system_prompt: str,
        user_prompt: str,
        attachment_content: str | None,
        input_pdf_path: Path | None = None,
    ) -> Any:
        if self._client is not None:
            client = self._client
        else:
            if genai is None:
                raise RuntimeError("Gemini SDK not available. Install 'google-genai' package.")
            api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
            client = genai.Client(api_key=api_key)

        combined_system = system_prompt
        if attachment_content:
            combined_system += f"\n\nAdditional instructions:\n\n{attachment_content}"
        if input_pdf_path is not None:
            if genai is None:
                raise RuntimeError("Gemini SDK not available. Install 'google-genai' package.")
            pdf_bytes = input_pdf_path.read_bytes()
            prompt = f"System instructions:\n{combined_system}\n\nUser request:\n{user_prompt}"
            return client.models.generate_content(
                model=self.model,
                contents=[
                    genai.types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    genai.types.Part.from_text(text=prompt),
                ],
            )

        prompt = f"System instructions:\n{combined_system}\n\nUser request:\n{user_prompt}"
        return client.models.generate_content(
            model=self.model,
            contents=prompt,
        )

    def _call_claude(
        self,
        system_prompt: str,
        user_prompt: str,
        attachment_content: str | None,
        input_pdf_path: Path | None = None,
    ) -> Any:
        client = self._client or (Anthropic() if Anthropic is not None else None)
        if client is None:
            raise RuntimeError("Anthropic SDK not available. Install 'anthropic' package or inject a client.")

        message_text = user_prompt
        if attachment_content:
            message_text += f"\n\nAdditional instructions:\n\n{attachment_content}"

        if input_pdf_path is not None:
            pdf_data = base64.standard_b64encode(input_pdf_path.read_bytes()).decode("utf-8")
            return client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_data,
                                },
                            },
                            {"type": "text", "text": message_text},
                        ],
                    }
                ],
            )

        return client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": message_text}],
        )

    def _extract_content(self, response: Any) -> str:
        if self.provider == "openai":
            try:
                output_text = response.get("output_text") if isinstance(response, dict) else getattr(response, "output_text", None)
                if isinstance(output_text, str) and output_text.strip():
                    return output_text
                choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
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

        if self.provider == "gemini":
            text = getattr(response, "text", None)
            if isinstance(text, str) and text.strip():
                return text
            candidates = getattr(response, "candidates", None) or []
            for cand in candidates:
                content = getattr(cand, "content", None)
                parts = getattr(content, "parts", None) or []
                part_texts = [getattr(p, "text", "") for p in parts if getattr(p, "text", "")]
                if part_texts:
                    return "\n".join(part_texts)
            return ""

        # Claude
        blocks = getattr(response, "content", None) or []
        texts = [getattr(block, "text", "") for block in blocks if getattr(block, "text", "")]
        return "\n".join(texts)

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
        input_pdf_path: Path | None = None,
    ) -> GenerationResult:
        if input_pdf_path is None and not text.strip():
            raise ValueError("Input text is empty.")
        if questions <= 0:
            raise ValueError("Number of questions must be positive.")
        if input_pdf_path is not None and not input_pdf_path.exists():
            raise ValueError(f"Input PDF file not found: {input_pdf_path}")

        user_prompt = build_user_prompt(
            text=None if input_pdf_path is not None else text,
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

        # Check for attachment file in question type section
        attachment_content = None
        if self.config.has_option(section, "attachment"):
            attachment_path = Path(self.config.get(section, "attachment"))
            if attachment_path.exists():
                attachment_content = attachment_path.read_text(encoding="utf-8")
                print(f"Loaded additional instructions from: {attachment_path}")

        try:
            print(f"Sending request to {self.provider}, please wait...")
            if self.provider == "openai":
                resp = self._call_openai(system_prompt, user_prompt, attachment_content, input_pdf_path=input_pdf_path)
            elif self.provider == "gemini":
                resp = self._call_gemini(system_prompt, user_prompt, attachment_content, input_pdf_path=input_pdf_path)
            elif self.provider == "claude":
                resp = self._call_claude(system_prompt, user_prompt, attachment_content, input_pdf_path=input_pdf_path)
            else:
                raise RuntimeError(f"Unsupported provider: {self.provider}")
        except Exception as e:
            provider_label = self.provider.capitalize()
            if input_pdf_path is not None:
                raise RuntimeError(
                    f"{provider_label} PDF request failed for '{input_pdf_path.name}'. "
                    f"Verify provider/model PDF support and retry. Details: {e}"
                ) from e
            raise RuntimeError(f"{provider_label} API error for model '{self.model}': {e}") from e

        content = self._extract_content(resp)
        if not content:
            raise RuntimeError("Empty response from model.")

        if qtype == "es":
            essay_md = _ensure_essay_points(content, points)
            essay_md = _ensure_quiz_header(essay_md)
            return GenerationResult(quiz_markdown=essay_md, raw_response=content)

        try:
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
        except FormatError as e:
            # Keep the raw model output so callers can still write an .md file for inspection.
            raise GenerationFormatError(str(e), raw_response=content) from e

        return GenerationResult(quiz_markdown=quiz_md, raw_response=content)


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a multiple-choice quiz from a text file.",
        epilog=DISCLAIMER,
    )
    p.add_argument("input", nargs="+", help="Path(s) or glob pattern(s) to input text/readable PDF file(s)")
    # Default questions: 4 for Multi-choice, 1 for Cloze, 2 for Matching
    p.add_argument("--questions", "-q", type=int, default=4, help="Number of questions (default: 4 for Multi-choice)")
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        required=False,
        help="Output path: file path or directory (default: <input-stem>-<type>-<provider>.md in same folder)",
    )
    p.add_argument(
        "-p","--provider",
        choices=["openai", "gemini", "claude"],
        default="openai",
        help="LLM provider: openai, gemini, or claude (default: openai)",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Model name (default depends on --provider)",
    )
    p.add_argument("--points", type=int, default=4, help="Points per question (default: 4)")
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
        choices=["mc", "cl", "ma", "es"],
        default="mc",
        help="Question type: mc=Multi-choice, cl=Cloze, ma=Matching, es=Essay (default: mc)",
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
    p.add_argument(
        "--debug",
        action="store_true",
        help="Write provider raw native response JSON next to output when available.",
    )

    parsed = p.parse_args(argv)
    provided: set[str] = set()
    option_map = {
        "--provider": "provider",
        "-p": "provider",
        "--type": "type",
        "-t": "type",
        "--questions": "questions",
        "-q": "questions",
        "--points": "points",
        "--answers": "answers",
        "-a": "answers",
        "--blanks": "blanks",
        "--pairs": "pairs",
    }
    for token in argv:
        canonical = option_map.get(token)
        if canonical:
            provided.add(canonical)
    setattr(parsed, "_cli_provided", provided)
    return parsed


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    
    args = parse_args(argv)
    
    # Load configuration
    config = load_config(args.config)
    apply_config_defaults(args, config)

    try:
        input_files = resolve_input_files(args.input)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.output is not None and len(input_files) > 1 and not args.output.is_dir():
        print("Error: --output must be a directory when multiple input files are provided.", file=sys.stderr)
        return 1

    # Override default questions per type if user did not explicitly set --questions / -q
    if "questions" not in getattr(args, "_cli_provided", set()):
        if args.type == "cl":
            args.questions = 1
        elif args.type == "ma":
            args.questions = 2

    # Validate provider API key presence early
    provider = args.provider
    api_key = _get_provider_api_key(provider)
    if provider == "openai":
        if not api_key or api_key.startswith("sk-REPLACE"):
            print("Error: OPENAI_API_KEY is not set. Create a .env file (see .env.example) or set the env var.", file=sys.stderr)
            print("Tip (PowerShell): $env:OPENAI_API_KEY='sk-...'  or create .env with OPENAI_API_KEY=sk-...", file=sys.stderr)
            return 1
    elif provider == "gemini":
        if not api_key:
            print("Error: GEMINI_API_KEY (or GOOGLE_API_KEY) is not set.", file=sys.stderr)
            print("Tip (PowerShell): $env:GEMINI_API_KEY='...'  or create .env with GEMINI_API_KEY=...", file=sys.stderr)
            return 1
    else:  # claude
        if not api_key:
            print("Error: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
            print("Tip (PowerShell): $env:ANTHROPIC_API_KEY='...'  or create .env with ANTHROPIC_API_KEY=...", file=sys.stderr)
            return 1

    def _default_output_name(input_path: Path) -> str:
        type_label_map = {"mc": "multi-choice", "cl": "cloze", "ma": "matching", "es": "essay"}
        type_label = type_label_map.get(args.type, args.type)
        return f"{input_path.stem}-{type_label}-{provider}.md"

    def _warning_output_name(input_path: Path) -> str:
        type_label_map = {"mc": "multi-choice", "cl": "cloze", "ma": "matching", "es": "essay"}
        type_label = type_label_map.get(args.type, args.type)
        return f"{input_path.stem}-{type_label}(error).md"

    def _raw_json_output_name(input_path: Path) -> str:
        type_label_map = {"mc": "multi-choice", "cl": "cloze", "ma": "matching", "es": "essay"}
        type_label = type_label_map.get(args.type, args.type)
        return f"{input_path.stem}-{type_label}-raw-response.json"
    
    gen = QuizGenerator(model=args.model, provider=args.provider, config=config)
    num_correct, num_incorrect = args.answers
    errors: list[tuple[Path, str]] = []
    for input_path in input_files:
        is_pdf_input = input_path.suffix.lower() == ".pdf"
        input_pdf_path: Path | None = input_path if is_pdf_input else None
        text = ""
        if not is_pdf_input:
            try:
                text = input_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"Error: could not read input text file '{input_path}': {e}", file=sys.stderr)
                errors.append((input_path, str(e)))
                continue

        if args.output is None:
            output_path = input_path.with_name(_default_output_name(input_path))
        elif args.output.is_dir():
            output_path = args.output / _default_output_name(input_path)
        else:
            output_path = args.output

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
                input_pdf_path=input_pdf_path,
            )
        except GenerationFormatError as e:
            print(f"Error processing '{input_path}': {e}", file=sys.stderr)
            errors.append((input_path, str(e)))
            continue
        except Exception as e:
            msg = str(e)
            print(f"Error processing '{input_path}': {msg}", file=sys.stderr)
            if "model" in msg.lower() and ("not found" in msg.lower() or "does not exist" in msg.lower()):
                suggested = {
                    "openai": "gpt-4o-mini",
                    "gemini": "gemini-2.5-flash",
                    "claude": "claude-3-5-sonnet-latest",
                }[args.provider]
                print(
                    f"Hint: The selected model may not be available to your account. Try --model {suggested}",
                    file=sys.stderr,
                )
            errors.append((input_path, msg))
            continue

        output_path.write_text(result.quiz_markdown, encoding="utf-8")
        print(f"Wrote quiz to {output_path}")

        if result.validation_warning:
            warnings.warn(f"Quiz validation failed: {result.validation_warning}", UserWarning)
            warning_output = output_path.with_name(_warning_output_name(input_path))
            warning_output.write_text(result.quiz_markdown, encoding="utf-8")

        if args.debug and result.raw_native_response_json:
            raw_json_output = output_path.with_name(_raw_json_output_name(input_path))
            raw_json_output.write_text(result.raw_native_response_json, encoding="utf-8")

    if errors:
        print(
            f"Completed with errors for {len(errors)} of {len(input_files)} input file(s):",
            file=sys.stderr,
        )
        for input_path, message in errors:
            print(f"- {input_path}: {message}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
