"""Sandbox entry point: python -m app.worker /job

Reads /job/job.json, runs the tool, writes /job/result.json. Never runs outside bwrap.
"""
import importlib
import json
import sys
import traceback
from pathlib import Path

from app import config, safety
from app.tools import AI_TOOLS, TOOLS, UserError


def main(job: Path) -> dict:
    spec = json.loads((job / "job.json").read_text())
    tool = {**TOOLS, **AI_TOOLS}[spec["tool"]]   # the API decides which tools are on
    opts = tool.options.model_validate(spec["options"])
    inputs = [(job / "in" / f["id"], f["kind"]) for f in spec["inputs"]]
    out = job / "out"
    out.mkdir()
    safety.harden()
    for path, kind in inputs:
        safety.check_input(path, kind, tool.encrypted_ok)
    mod, fn = tool.run.split(".")
    result: Path = getattr(importlib.import_module(f"app.ops.{mod}"), fn)(inputs, opts, out)
    if result.suffix == ".pdf" and tool.sanitize:
        safety.sanitize_pdf(result)
    return {"output": result.name}


if __name__ == "__main__":
    job = Path(sys.argv[1])
    try:
        res = main(job)
    except UserError as e:
        res = {"error": str(e)}
    except MemoryError:
        res = {"error": "File needs too much memory to process"}
    except Exception:
        if config.DEBUG_JOBS:
            traceback.print_exc()
        res = {"error": "Processing failed"}
    (job / "result.json").write_text(json.dumps(res))
