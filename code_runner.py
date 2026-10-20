# Purpose:
# Run arbitrary code inside of a hardened docker container
#
# Prereqs: Docker installed and running on the host, and these images pulled:
#   docker pull python:3.12-slim
#   docker pull gcc:13
#
# Functions:
# - (TEMPORARY) Uses /code-sandbox as a code editing area
# - At this endpoint, admin users ONLY may run arbitrary code, both C++ and Python
# - stdout and stderr is both displayed, but captured separately

from __future__ import annotations

import subprocess
import uuid

MAX_CODE_CHARS = 20_000
MAX_OUTPUT_CHARS = 10_000
TIMEOUT_SECONDS = 10

BASE_FLAGS = [
    "--rm",
    "-i",                       # keep stdin open so we can pipe the code in
    "--pull", "never",			# ensure docker pull is never run programmatically
    "--network", "none",        # no internet
    "--memory", "128m",			# 128mb mem
    "--memory-swap", "128m",    # no swap
    "--cpus", "0.5",			# half of cpu core
    "--pids-limit", "64",       # blocks fork bombs
    "--read-only",              # container filesystem is immutable...
    "--tmpfs", "/tmp:rw,exec,size=16m",  # ...except a small scratch dir
    "--cap-drop", "ALL",		# remove linux privileges
    "--security-opt", "no-new-privileges",	# ensure privileges cannot be changed at all inside the container
    "--user", "65534:65534",    # "nobody" user, no owned files
]

LANGUAGES = {
    "python": {
        "image": "python:3.12-slim",
        #        read stdin (code) and exec
        "cmd": ["python", "-"],
    },
    "cpp": {
        "image": "gcc:13",
        #					 read stdin (code)      compile the code                       run the code
        "cmd": ["sh", "-c", "cat > /tmp/main.cpp && g++ -O1 -o /tmp/a.out /tmp/main.cpp && /tmp/a.out"],
    },
}

class RunnerError(Exception):
    pass

# enforce max output char limit
def _truncate(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + "\n[output truncated]"
    return text

def runCode(language: str, code: str) -> dict:
    if language not in LANGUAGES:
        raise RunnerError("Unsupported language.")
    if not code.strip():
        raise RunnerError("No code provided.")
    if len(code) > MAX_CODE_CHARS:
        raise RunnerError("Code is too long.")

    spec = LANGUAGES[language]
    name = f"sandbox-{uuid.uuid4().hex[:12]}"
    cmd = ["docker", "run", "--name", name, *BASE_FLAGS, spec["image"], *spec["cmd"]]

    try:
        proc = subprocess.run(
            cmd,
            input=code,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        return {
            "stdout": _truncate(proc.stdout),
            "stderr": _truncate(proc.stderr),
            "exitCode": proc.returncode,
            "timedOut": False,
        }
    except subprocess.TimeoutExpired:
    	# explicitly kill docker container by name
        subprocess.run(["docker", "kill", name], capture_output=True)
        return {"stdout": "", "stderr": "", "exitCode": -1, "timedOut": True}
    except FileNotFoundError:
        raise RunnerError("Docker is not installed or not on PATH.")
