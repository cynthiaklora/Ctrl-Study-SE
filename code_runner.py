# Purpose:
# Run arbitrary code inside of a hardened docker container
#
# Prereqs: Docker running on the host (when containerized, the host's socket is mounted in),
#   the docker SDK (pip install docker), and these images pulled:
#   docker pull python:3.12-slim
#   docker pull gcc:13
#
# Functions:
# - (TEMPORARY) Uses /code-sandbox as a code editing area
# - At this endpoint, admin users ONLY may run arbitrary code, both C++ and Python
# - stdout and stderr is both displayed, but captured separately
# - At most MAX_CONCURRENT_RUNS sandboxes may run at the same time

from __future__ import annotations

import socket
import threading
import uuid

import docker
import requests

MAX_CODE_CHARS = 20_000
MAX_OUTPUT_CHARS = 10_000
TIMEOUT_SECONDS = 10
MAX_CONCURRENT_RUNS = 4		# sandboxes allowed to run at once
SLOT_WAIT_SECONDS = 10		# how long a request waits for a free slot before giving up

# talks to the docker daemon through /var/run/docker.sock
client = docker.from_env()

# one slot per running sandbox
slots = threading.BoundedSemaphore(MAX_CONCURRENT_RUNS)

# same restrictions as the old docker run flags
BASE_OPTS = dict(
    stdin_open=True,                        # -i, keep stdin open so we can pipe the code in
    network_mode="none",                    # no internet
    mem_limit="128m",                       # 128mb mem
    memswap_limit="128m",                   # no swap
    nano_cpus=500_000_000,                  # half of cpu core
    pids_limit=64,                          # blocks fork bombs
    read_only=True,                         # container filesystem is immutable...
    tmpfs={"/tmp": "rw,exec,size=16m"},     # ...except a small scratch dir
    cap_drop=["ALL"],                       # remove linux privileges
    security_opt=["no-new-privileges"],     # ensure privileges cannot be changed at all inside the container
    user="65534:65534",                     # "nobody" user, no owned files
    # caps the log file so a runaway print loop can't fill memory/disk
    log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}),
)

LANGUAGES = {
    "python": {
        "image": "python:3.12-slim",
        #        read stdin (code) and exec
        "cmd": ["python", "-"],
    },
    "cpp": {
        "image": "gcc:13",
        #                    read stdin (code)      compile the code                       run the code
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

    # wait for a free slot
    if not slots.acquire(timeout=SLOT_WAIT_SECONDS):
        raise RunnerError("Server is busy, try again shortly.")

    container = None
    try:
        # create (not run) so stdin can be attached before the container starts
        container = client.containers.create(spec["image"], spec["cmd"], name=name, **BASE_OPTS)
        sock = container.attach_socket(params={"stdin": 1, "stream": 1})
        container.start()

        # pipe the code in, then half-close so the program sees EOF on stdin
        try:
            sock._sock.sendall(code.encode())
            sock._sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass    # container already exited, its output will explain why
        finally:
            sock.close()

        try:
            result = container.wait(timeout=TIMEOUT_SECONDS)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            # explicitly kill docker container
            try:
                container.kill()
            except docker.errors.APIError:
                pass
            return {"stdout": "", "stderr": "", "exitCode": -1, "timedOut": True}

        # stdout and stderr fetched separately
        stdout = container.logs(stdout=True, stderr=False).decode(errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode(errors="replace")
        return {
            "stdout": _truncate(stdout),
            "stderr": _truncate(stderr),
            "exitCode": result["StatusCode"],
            "timedOut": False,
        }
    except docker.errors.ImageNotFound:
        raise RunnerError("Sandbox image is not pulled on this host.")
    except (docker.errors.DockerException, requests.exceptions.ConnectionError):
        raise RunnerError("Docker is not available.")
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except docker.errors.APIError:
                pass
        slots.release()
