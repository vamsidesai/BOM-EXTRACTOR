import sys

from .cli import main

if __name__ == "__main__":  # guard needed for multiprocessing on Windows
    sys.exit(main())
