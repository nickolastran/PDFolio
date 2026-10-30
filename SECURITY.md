# Security

The goal: nobody can see anyone else's files, and a booby-trapped upload can't change that.

## Threat model

| Threat | Mitigation | Where |
|---|---|---|
| Guessing or enumerating someone else's job | 192-bit random job IDs, tied to a per-browser random session cookie; every status/download/delete checks ownership and answers "Not found" either way | `jobs.py`, `main.py` |
| Malicious file exploits a parser (MuPDF, LibreOffice, Ghostscript…) | Every job runs in bubblewrap: all namespaces unshared (no network), read-only `/usr`, only its own job folder mounted, empty `/tmp`, cleared environment | `sandbox.py` |
| Runaway job (CPU, memory, disk, time) | `prlimit` address-space, CPU-time and file-size limits; wall-clock timeout kills the whole process group | `sandbox.py` |
| Compromised sandbox points its output at a host file | The API only serves a regular, non-symlink file whose resolved path is inside that job's `out/` | `jobs._result` |
| Wrong file type / disguised file | Type is detected from content with libmagic; the extension only picks between text flavours (txt/md/html) | `uploads.py` |
| Path traversal via filename | Files are stored as random UUIDs; the original name is only used, reduced to `[A-Za-z0-9._ -]`, in the download name | `uploads.py` |
| Huge uploads | `Content-Length` checked before parsing; per-file, per-request and file-count limits while streaming | `main.py`, `uploads.py` |
| Zip bombs, zip slip, symlinks in archives | Entry count, total unpacked size and per-entry ratio caps; absolute/`..` paths and symlinks rejected; reads capped at the declared size | `safety.py` |
| XXE / billion laughs in docx/odt/epub | Every XML entry parsed with `defusedxml` first; any entity or external reference rejects the file | `safety.py` |
| Decompression-bomb images | Pillow `MAX_IMAGE_PIXELS`, with the warning band also treated as an error | `safety.py` |
| PDF bombs | Page-count cap; rendering capped by DPI, pixels per page and page count | `safety.py`, `ops/convert.py` |
| SSRF from HTML/EPUB/Markdown | WeasyPrint uses a fetcher that allows only `data:` URIs and files inside the uploaded zip (no http, no `file://` outside it, so no localhost, internal IPs or 169.254.169.254); the sandbox has no network anyway | `ops/convert.py` |
| Pandoc reading local files | `--sandbox` on every call, and no `--embed-resources` (in pandoc 3.1 it reads local files even under `--sandbox`; a test proves this stays fixed) | `ops/convert.py` |
| LibreOffice macros | Fresh profile per job with macro security "very high" and macro execution disabled | `ops/convert.py` |
| Ghostscript | Always `-dSAFER` | `ops/optimize.py` |
| Spreadsheet formula injection | Cells written from PDF tables are forced to text, so `=HYPERLINK(...)` never runs | `ops/convert.py` |
| Redaction that only hides text | PyMuPDF `apply_redactions` removes text, image pixels and drawings under each area; notes mentioning a term or overlapping an area are deleted; metadata, attachments, JavaScript and hidden text are scrubbed; the saved file is reopened and checked, and the job fails rather than returning an unverified file | `ops/secure.py` |
| Password cracking | Unlock makes exactly one attempt with the password the user typed; rate limits apply | `ops/secure.py` |
| Passwords and inputs left on disk | The job spec (which can hold a password) and all inputs are deleted as soon as the sandbox exits; only the output stays | `jobs.py` |
| Active content in output PDFs | JavaScript, OpenAction/AA, Launch/GoToR/GoToE/ImportData/SubmitForm actions, embedded files, file-attachment annotations and XFA are removed from every PDF we return | `safety.sanitize_pdf` |
| Uploaded HTML running in our origin | Downloads use `Content-Disposition: attachment`, the right Content-Type, `nosniff` and `CSP: sandbox` | `main.py` |
| CSRF | Session cookie is `SameSite=Strict`, and every non-GET request must carry an allowed `Origin` | `main.py` |
| XSS / clickjacking | Strict CSP (`'self'` only, no inline script), `X-Frame-Options: DENY`, `frame-ancestors 'none'` | `main.py` |
| Abuse | Per-IP rate limit on job creation; global cap on queued jobs | `main.py` |
| Data left behind | Files deleted after 1 hour (checked every minute), right after download if chosen, and all job folders wiped on restart | `jobs.py` |
| Leaks via logs or third parties | Access logs off; no filenames or contents logged; fonts self-hosted; no analytics; an E2E test asserts no off-site requests | `package.json`, `e2e/` |

## AI tools (optional, off by default)

Summarize, Translate and Markdown with AI send the PDF's **text** to Anthropic's API. They are
only offered when `AI_ENABLED=true` and `ANTHROPIC_API_KEY` are set, and the user must tick a
"Send the text to Anthropic" box first. The sandbox extracts the text (no network there); the API
process, which never parses files, sends it on. The API key is never passed into the sandbox. The
system prompt tells the model to treat the document as data, not instructions, and the result is
only ever returned as a downloaded Markdown file.

## Known trade-offs

- **Single process.** The job store is in memory, so the app runs as one process. Restarting it
  forgets jobs and deletes their files.
- **Sandbox needs user namespaces.** bubblewrap needs unprivileged user namespaces (on by default
  on WSL2; on stock Ubuntu 24.04 servers AppArmor may restrict them, see the CI workflow).
- **No process-count limit inside a job.** `RLIMIT_NPROC` counts all of the user's processes, not
  just the job's. The memory and time limits still bound a fork bomb, which also needs code
  execution in the first place.
- **System packages track Ubuntu security updates** rather than exact pinned versions. Run
  `apt upgrade` regularly. Python and npm packages are pinned exactly and audited in CI.
- **Ubuntu's pandoc (3.1.3) can't write DOCX/ODT/EPUB under `--sandbox`** (its data files live on
  disk), so those formats are written by LibreOffice instead. The official pandoc release embeds
  them; installing it (see README) would allow pandoc for those too.
- **HTTPS is not set up on localhost.** When hosting publicly, put Caddy in front (see README).
