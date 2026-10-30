"""Run a command inside a bubblewrap sandbox scoped to one job directory.

Inside: no network, no view of other jobs or the home directory, read-only /usr,
fresh /tmp, cleared environment, and hard memory/CPU/file-size/wall-clock limits.
"""
import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

from app import config

VENV = Path(sys.prefix)
APP_DIR = config.BACKEND / "app"
# Only the host paths the converters need (fonts, LibreOffice registry, linker cache, gs font maps).
ETC = ("/etc/fonts", "/etc/libreoffice", "/etc/alternatives", "/etc/ld.so.cache",
       "/etc/ghostscript", "/etc/mime.types", "/var/lib/ghostscript")
WORKER = [str(VENV / "bin" / "python"), "-P", "-s", "-m", "app.worker", "/job"]


def argv(job_dir: Path, cmd: list[str]) -> list[str]:
    a = ["prlimit", f"--as={config.JOB_MEMORY_BYTES}", f"--cpu={config.JOB_TIMEOUT_SECONDS}",
         f"--fsize={config.JOB_MAX_OUTPUT_BYTES}", "--",
         "bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--hostname", "sandbox",
         "--ro-bind", "/usr", "/usr",
         "--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
         "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
         "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/dev/shm",
         "--size", str(512 * config.MB), "--tmpfs", "/tmp",
         "--ro-bind", str(VENV), str(VENV),
         "--ro-bind", str(APP_DIR), "/srv/app",
         "--bind", str(job_dir), "/job", "--chdir", "/job",
         "--clearenv", "--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/tmp",
         "--setenv", "LANG", "C.UTF-8", "--setenv", "PYTHONPATH", "/srv",
         # One thread each: numeric libraries reserve big per-thread arenas that blow the memory limit.
         "--setenv", "OMP_NUM_THREADS", "1", "--setenv", "OPENBLAS_NUM_THREADS", "1",
         "--setenv", "OMP_THREAD_LIMIT", "1"]
    for p in ETC:
        a += ["--ro-bind-try", p, p]
    for k in config.SANDBOX_ENV:
        if k in os.environ:
            a += ["--setenv", k, os.environ[k]]
    return a + ["--", *cmd]


async def run(job_dir: Path, cmd: list[str] = WORKER, timeout: float | None = None) -> int | None:
    """Returns the exit code, or None if the wall-clock timeout killed it."""
    out = None if config.DEBUG_JOBS else subprocess.DEVNULL
    proc = await asyncio.create_subprocess_exec(
        *argv(job_dir, cmd), stdin=subprocess.DEVNULL, stdout=out, stderr=out,
        start_new_session=True)
    try:
        return await asyncio.wait_for(proc.wait(), timeout or config.JOB_TIMEOUT_SECONDS)
    except TimeoutError:
        os.killpg(proc.pid, signal.SIGKILL)
        await proc.wait()
        return None
