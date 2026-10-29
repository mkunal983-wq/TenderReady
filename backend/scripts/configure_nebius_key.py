"""Enter the Nebius key privately in a local terminal; never print the value."""
import getpass
import json
import os
from pathlib import Path
import re
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[2]


def main():
    if not sys.stdin.isatty():
        raise SystemExit('Run this command in your own local terminal for hidden key entry.')
    target = PROJECT / '.env'
    override = PROJECT / 'backend' / '.env'
    if override.exists() and re.search(r'^\s*NEBIUS_API_KEY\s*=', override.read_text(), re.M):
        target = override
    if target.is_symlink():
        raise SystemExit('Refusing to write through a .env symlink.')
    value = getpass.getpass('Paste Nebius Token Factory API key (hidden): ').strip()
    if not value or any(c.isspace() for c in value):
        raise SystemExit('Key must be nonempty and contain no whitespace. Nothing saved.')
    current = target.read_text() if target.exists() else ''
    line = 'NEBIUS_API_KEY=' + json.dumps(value)
    if re.search(r'^\s*NEBIUS_API_KEY\s*=', current, re.M):
        updated = re.sub(r'^\s*NEBIUS_API_KEY\s*=.*$', lambda _: line, current, flags=re.M)
    else:
        updated = current.rstrip('\n') + '\n' + line + '\n'
    fd, name = tempfile.mkstemp(prefix='.nebius-key-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w') as file:
            file.write(updated)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(name, 0o600)
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print('Key saved privately to server configuration (permissions 0600).')
    print('Restart the backend before running model discovery or PDF analysis.')
    if os.environ.get('NEBIUS_API_KEY'):
        print('This shell has NEBIUS_API_KEY exported; it overrides .env. Unset it if outdated.')


if __name__ == '__main__':
    main()
