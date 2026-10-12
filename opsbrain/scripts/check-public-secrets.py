"""Heuristic release scan. Print paths/rules only, never matching credentials.

This detects common credential shapes; it is not proof of secret absence.
"""

import re
import sys
from pathlib import Path

PATTERNS = {
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'supabase-secret': re.compile(r'\bsb_secret_[A-Za-z0-9_-]{8,}'),
    'jwt-token': re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'),
    'provider-key': re.compile(r'\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,})'),
    'aws-access-key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'database-password': re.compile(r'postgres(?:ql)?://[^\s:/]+:[^\s@]+@'),
    'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})'),
}


def scan(root):
    findings = []
    for path in sorted(root.rglob('*')):
        if path.is_file():
            content = path.read_bytes().decode('utf-8', errors='replace')
            for rule, pattern in PATTERNS.items():
                if pattern.search(content):
                    findings.append((str(path.relative_to(root)), rule))
    return findings


if __name__ == '__main__':
    root = Path(sys.argv[1]) if len(sys.argv) == 2 else None
    if root is None or not root.is_dir() or not any(root.iterdir()):
        print('Public scan requires a nonempty build directory', file=sys.stderr)
        sys.exit(2)
    findings = scan(root)
    for path, rule in findings:
        print(f'{path}: credential pattern ({rule})', file=sys.stderr)
    print(f'Public credential-pattern scan: {len(findings)} findings')
    sys.exit(bool(findings))
