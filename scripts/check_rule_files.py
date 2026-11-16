#!/usr/bin/env python3
"""Rule-file guard for AI agent instruction files.

AGENTS.md, CLAUDE.md, .cursorrules and similar files are read by coding agents
and act with the agent's permissions. They are often copied from elsewhere and
rarely reviewed like code. A single hidden line such as "install foo-utils" can
make an agent swap a real dependency for an attacker's package
(arXiv 2610.09264, "Package Hallucination Attacks on Coding Agents through
Prompt Injection in Rule Files").

So these files must not tell the agent to install a package by name, point a
package manager at another registry, or pipe a download into a shell. Installing
what the manifest already lists (`npm install`, `npm ci`,
`pip install -r requirements.txt`, `pip install -e .`) is fine. Dependencies
belong in the manifest and lockfile, where review and Dependabot can see them.

Agents also read README and TODO files, and treat them as trusted. A preprint
(arXiv 2610.38867, "The Trust Region Effect") reports that an instruction placed
in a README or TODO is followed about 2.6 times as often as the same instruction
in a code or data file. So README and TODO files, and the rule files above, are
also checked for instructions a human reviewer would not see or would skim past:
invisible or direction-changing characters, HTML comments addressed to an AI
agent, and "ignore previous instructions"-style overrides. Install commands in a
README are normal setup steps and are not flagged.

A reviewed, intended line can opt out by containing `rule-file-guard: allow`
(for example in an HTML comment at the end of the line).

Usage:
  rule_file_guard.py              check every tracked rule, README and TODO file
  rule_file_guard.py FILE...      check only these files (pre-commit passes them)
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

NAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    ".windsurfrules",
    "copilot-instructions.md",
}
# Files agents read as context and tend to trust: README and TODO, with any
# extension or language suffix (README.md, README.ja.md, TODO, todo.txt).
DOC_STEMS = {"readme", "todo"}
SKIP_DIRS = ("node_modules/", "vendor/", "third_party/")
ALLOW = "rule-file-guard: allow"
# A package-manager install verb. What follows decides whether it names a package.
INSTALL = re.compile(
    r"\b(?:(?:npm|pnpm|yarn|bun)\s+(?:i|install|add)"
    r"|pip3?\s+install|uv\s+(?:add|pip\s+install|tool\s+install)|pipx\s+install"
    r"|(?:gem|cargo|go|brew)\s+install)\b",
    re.IGNORECASE,
)
# Flags whose next argument is a file or directory, not a package name.
FILE_FLAGS = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable", "--prefix", "--target", "-t"}
STOP = re.compile(r"[`;|&)]|\s#")
PATTERNS = [
    ("registry override", re.compile(r"--(extra-)?index-url\b|\bregistry\s*=|\bnpm\s+config\s+set\s+registry\b", re.IGNORECASE)),
    ("download piped to a shell", re.compile(r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b", re.IGNORECASE)),
]


# Characters a reviewer cannot see: zero-width, bidi controls, word joiners,
# the byte-order mark away from the start of a file, and Unicode tag characters
# (which can spell out ASCII text invisibly).
INVISIBLE = re.compile("[\u200b\u200c\u200e\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]")
ZWJ = "\u200d"
AGENT = r"(?:(?:ai|coding)\s+)?(?:ai|agents?|assistants?|llms?|language\s+models?|claude|copilot|codex|cursor|gemini|gpt[\w.-]*|chatgpt)"
OVERRIDE = re.compile(
    r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+)?(?:the\s+|your\s+)?"
    r"(?:previous|prior|above|earlier|preceding|original|system)\s+(?:instructions?|rules|prompts?|messages?)"
    r"|\bdo\s+not\s+(?:tell|inform|mention\s+(?:this|it)\s+to|show\s+(?:this|it)\s+to)\s+the\s+user\b"
    r"|\bnew\s+system\s+prompt\b",
    re.IGNORECASE,
)
# Inside an HTML comment: text that speaks to an agent rather than about one.
ADDRESSED = re.compile(
    r"\b(?:note|message|instructions?|attention|reminder)\s+(?:to|for)\s+(?:the\s+|any\s+)?" + AGENT + r"\b"
    r"|\bif\s+you\s+are\s+(?:an?\s+)?" + AGENT + r"\b"
    r"|^\s*(?:dear\s+|hey\s+)?" + AGENT + r"\s*[:,]\s*\w",
    re.IGNORECASE | re.MULTILINE,
)
COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)


def is_doc(path: str) -> bool:
    return pathlib.PurePosixPath(path).name.split(".")[0].lower() in DOC_STEMS


def wanted(path: str) -> bool:
    return pathlib.PurePosixPath(path).name in NAMES or is_doc(path)


def invisible_chars(text: str) -> list[tuple[int, str]]:
    """(line number, code point) for each character a reviewer would not see."""
    found = []
    for match in INVISIBLE.finditer(text):
        index, char = match.start(), match.group()
        if char == "\ufeff" and index == 0:
            continue  # a byte-order mark at the very start is harmless
        if "\U000e0020" <= char <= "\U000e007f" and _in_flag_sequence(text, index):
            continue  # subdivision flags such as England use tag characters
        found.append((text.count("\n", 0, index) + 1, f"U+{ord(char):04X}"))
    for index in [i for i, c in enumerate(text) if c == ZWJ]:
        before = text[index - 1] if index else ""
        after = text[index + 1] if index + 1 < len(text) else ""
        # A joiner between two pictographs builds one emoji (family, profession).
        if not (_pictograph(before) and _pictograph(after)):
            found.append((text.count("\n", 0, index) + 1, "U+200D"))
    return sorted(found)


def _pictograph(char: str) -> bool:
    if not char:
        return False
    point = ord(char)
    return point >= 0x1F000 or 0x2190 <= point <= 0x2BFF or point == 0xFE0F


def _in_flag_sequence(text: str, index: int) -> bool:
    start = index
    while start > 0 and "\U000e0020" <= text[start - 1] <= "\U000e007f":
        start -= 1
    return start > 0 and text[start - 1] == "\U0001f3f4"


def hidden_instructions(path: str, text: str) -> list[str]:
    found = []
    lines = text.splitlines()

    def allowed(number: int) -> bool:
        return 0 < number <= len(lines) and ALLOW in lines[number - 1]

    for number, point in invisible_chars(text):
        if not allowed(number):
            found.append(f"{path}:{number}: invisible character {point}")
    for match in COMMENT.finditer(text):
        body = match.group(1)
        number = text.count("\n", 0, match.start()) + 1
        if ALLOW in body or allowed(number):
            continue
        if ADDRESSED.search(body):
            found.append(f"{path}:{number}: HTML comment addressed to an AI agent: {' '.join(body.split())[:120]}")
    for number, line in enumerate(lines, 1):
        if ALLOW not in line and OVERRIDE.search(line):
            found.append(f"{path}:{number}: instruction override: {line.strip()[:120]}")
    return found


def names_a_package(line: str) -> bool:
    """True when an install command on this line names a package to fetch."""
    for match in INSTALL.finditer(line):
        rest = STOP.split(line[match.end():], maxsplit=1)[0]
        tokens = rest.split()
        skip_next = False
        for token in tokens:
            if skip_next:
                skip_next = False
                continue
            if token in FILE_FLAGS:
                skip_next = True
                continue
            if token.startswith("-"):
                continue
            if token in {".", ".."} or token.startswith(("./", "../", "/")):
                continue
            if re.match(r"^[@\w]", token):
                return True
    return False


def rule_files() -> list[str]:
    """Every tracked rule, README and TODO file."""
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    paths = [p for p in out.decode("utf-8").split("\0") if p]
    return [p for p in paths if wanted(p) and not any(d in p for d in SKIP_DIRS)]


def findings(paths: list[str]) -> list[str]:
    found = []
    for path in paths:
        try:
            text = pathlib.Path(path).read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        found.extend(hidden_instructions(path, text))
        if pathlib.PurePosixPath(path).name not in NAMES:
            continue  # README and TODO: setup commands are normal there
        for number, line in enumerate(text.splitlines(), 1):
            if ALLOW in line:
                continue
            if names_a_package(line):
                found.append(f"{path}:{number}: package install by name: {line.strip()[:120]}")
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    found.append(f"{path}:{number}: {label}: {line.strip()[:120]}")
    return found


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    paths = [p for p in args if wanted(p)] if args else rule_files()
    found = findings(paths)
    if found:
        print("rule-file guard: AI agent instruction files must not install a package by name,")
        print("change package registries, or pipe downloads into a shell, and no checked file")
        print("(rule files, README, TODO) may hide instructions for an agent.")
        print("\n".join(found))
        print("Move dependencies to the manifest and remove hidden text.")
        print(f"If a line is reviewed and intended, add '{ALLOW}' to it.")
        return 1
    print(f"rule-file guard OK: {len(paths)} file(s) checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
