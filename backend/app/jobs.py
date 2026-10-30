"""Job store, runner and cleanup."""
import asyncio
import json
import re
import secrets
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from app import ai, config, sandbox
from app.tools import TOOLS, UserError


@dataclass
class Job:
    owner: str
    dir: Path
    stem: str
    tool: str
    created: float = field(default_factory=time.monotonic)
    options: dict = field(default_factory=dict)   # kept only for AI tools, which need them after the sandbox
    status: str = "queued"     # queued | running | done | failed
    error: str | None = None
    output: Path | None = None


# ponytail: in-memory store, so run a single API process. Move to Redis if you need several.
JOBS: dict[str, Job] = {}
_slots = asyncio.Semaphore(config.MAX_CONCURRENT_JOBS)
_tasks: set[asyncio.Task] = set()


def new_job(owner: str, tool: str) -> tuple[str, Job]:
    job_id = secrets.token_urlsafe(24)  # 192 bits
    d = config.DATA_DIR / job_id
    (d / "in").mkdir(parents=True, mode=0o700)
    job = JOBS[job_id] = Job(owner=owner, dir=d, stem="file", tool=tool)
    return job_id, job


def active_count() -> int:
    return sum(j.status in ("queued", "running") for j in JOBS.values())


def get_owned(job_id: str, owner: str) -> Job | None:
    job = JOBS.get(job_id)
    if job and secrets.compare_digest(job.owner, owner):
        return job
    return None


def start(job_id: str, spec: dict) -> None:
    job = JOBS[job_id]
    if TOOLS[job.tool].ai:
        job.options = spec["options"]
    (job.dir / "job.json").write_text(json.dumps(spec))
    task = asyncio.create_task(_run(job_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _result(job: Job) -> tuple[Path | None, str | None]:
    try:
        res = json.loads((job.dir / "result.json").read_text())
    except (OSError, ValueError):
        return None, None
    if not isinstance(res, dict):
        return None, None
    if "error" in res:
        return None, str(res["error"])[:200]
    # The sandbox controls this file, so make sure the output is a regular file
    # inside this job's out/ directory and not a symlink pointing elsewhere.
    out_dir = (job.dir / "out").resolve()
    out = job.dir / "out" / Path(str(res.get("output", ""))).name
    if out.is_symlink() or not out.is_file() or out.resolve().parent != out_dir:
        return None, None
    return out, None


async def _run(job_id: str) -> None:
    async with _slots:
        job = JOBS.get(job_id)
        if job is None:      # deleted while queued
            return
        job.status = "running"
        code = await sandbox.run(job.dir)
        # Inputs and the job spec (which may hold a password) aren't needed any more; only the output stays.
        for d in ("in", "work"):
            shutil.rmtree(job.dir / d, ignore_errors=True)
        (job.dir / "job.json").unlink(missing_ok=True)
        out, err = _result(job) if code is not None else (None, "Took too long to process")
        if out and TOOLS[job.tool].ai:
            out, err = await _ai(job, out)
        if out:
            job.status, job.output = "done", out
        else:
            job.status, job.error = "failed", err or "Processing failed"


async def _ai(job: Job, text_file: Path) -> tuple[Path | None, str | None]:
    tool = TOOLS[job.tool]
    opts = tool.options.model_validate(job.options)
    try:
        result = await ai.complete(job.tool, opts, text_file.read_text())
    except UserError as e:
        return None, str(e)
    finally:
        text_file.unlink(missing_ok=True)
    dest = text_file.with_name("result.md")
    dest.write_text(result)
    return dest, None


def delete(job_id: str) -> None:
    job = JOBS.pop(job_id, None)
    if job:
        shutil.rmtree(job.dir, ignore_errors=True)


def sweep(now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    for job_id, job in list(JOBS.items()):
        if now - job.created > config.JOB_TTL_SECONDS:
            delete(job_id)


async def cleanup_loop() -> None:
    while True:
        await asyncio.sleep(60)
        sweep()


def wipe_data_dir() -> None:
    """On startup the in-memory store is empty, so any job folders on disk are orphans.

    Only job-shaped names are removed, in case DATA_DIR is ever pointed somewhere wrong.
    """
    config.DATA_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
    for d in config.DATA_DIR.iterdir():
        if d.is_dir() and not d.is_symlink() and re.fullmatch(r"[A-Za-z0-9_-]{32}", d.name):
            shutil.rmtree(d, ignore_errors=True)
