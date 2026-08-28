#!/usr/bin/env python3
import runpy
import sys
from pathlib import Path

sys.argv.insert(1, "host_connect")
runpy.run_path(str(Path(__file__).resolve().parents[1] / "python_server.py"), run_name="__main__")
