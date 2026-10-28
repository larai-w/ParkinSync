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

A reviewed, intended line can opt out by containing `rule-file-guard: allow`
(for example in an HTML comment at the end of the line).
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
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    paths = [p for p in out.decode("utf-8").split("\0") if p]
    return [p for p in paths if pathlib.PurePosixPath(p).name in NAMES and "node_modules/" not in p]


def findings(paths: list[str]) -> list[str]:
    found = []
    for path in paths:
        try:
            text = pathlib.Path(path).read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if ALLOW in line:
                continue
            if names_a_package(line):
                found.append(f"{path}:{number}: package install by name: {line.strip()[:120]}")
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    found.append(f"{path}:{number}: {label}: {line.strip()[:120]}")
    return found


def main() -> int:
    paths = rule_files()
    found = findings(paths)
    if found:
        print("rule-file guard: AI agent instruction files must not install a package by name,")
        print("change package registries, or pipe downloads into a shell.")
        print("\n".join(found))
        print(f"Move dependencies to the manifest. If a line is reviewed and intended, add '{ALLOW}' to it.")
        return 1
    print(f"rule-file guard OK: {len(paths)} file(s) checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
