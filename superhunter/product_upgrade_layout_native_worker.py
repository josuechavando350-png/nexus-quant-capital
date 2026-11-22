"""Bound the isolated native upgrade compiler process before importing packages."""
import os
from pathlib import Path
import resource

resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
work = Path.cwd()
os.execve(work/'node', ['node', '--max-old-space-size=512', str(work/'worker.mjs')], os.environ)
