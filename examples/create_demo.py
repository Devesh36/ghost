"""Create a disposable, intentionally broken repository for trying Ghost."""
from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import sys
import tempfile

from ghost.demo import create_demo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?", type=Path,
                        help="New directory only; defaults to a temporary directory")
    args = parser.parse_args()
    destination = args.destination or Path(tempfile.mkdtemp(prefix="ghost-demo-")) / "pricing"
    try:
        repo = create_demo(destination)
    except FileExistsError:
        parser.error(f"Refusing to overwrite existing directory: {destination}")
    print(f"\nCreated {repo}\nA verified good baseline is committed; pricing.py now contains a bug.\n")
    print(f"cd {shlex.quote(str(repo))}\nghost repl\n")
    print("Inside Ghost, try:")
    print(f"  run {shlex.quote(sys.executable)} -m unittest -v\n"
          "  failures --output\n  debug\n  report\n"
          f"  run {shlex.quote(sys.executable)} -m unittest -v\n  exit")


if __name__ == "__main__":
    main()
