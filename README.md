# PDFolio

Self-hosted PDF and document tools: merge, split, convert, edit, protect. Files are processed in a
sandbox and deleted after an hour. No accounts, no analytics, no third-party requests.

## Setup (Ubuntu 24.04 / WSL2)

```sh
npm run setup   # once: apt packages (needs sudo), Python venv, npm packages, test browser
npm run dev     # open http://localhost:5173 (backend on :8000, both reload on changes)
```

Other commands:

```sh
npm start       # production-style: builds the frontend, serves everything at http://localhost:8000
npm test        # backend tests (pytest) + end-to-end tests (Playwright)
npm run audit   # pip-audit + npm audit
```

## Configuration

Every limit is an environment variable. See [.env.example](.env.example) for the full list with
defaults: file sizes and counts, page limits, job timeouts and memory, rate limits, and allowed origins.

## Tools

| Category | Tools |
|---|---|
| Organize | Merge, Split, Remove pages, Extract pages, Organize (reorder, rotate, duplicate, blank pages), Rotate, Scan to PDF |
| Optimize | Compress, Repair, OCR |
| Convert | Any of DOCX, ODT, RTF, TXT, Markdown, HTML (or a zipped site), EPUB, PDF, JPG, PNG, PPTX, XLSX to any reachable format; PDF to JPG/Word/PowerPoint/Excel/PDF-A/Markdown |
| Edit | Page numbers, Watermark (text or image), Crop, Annotate, Fill form |
| Security | Protect (AES-256), Unlock (with the password you know), Sign, Redact (verified), Compare |
| Intelligence | Summarize, Translate, Markdown with AI (optional, see below) |

Every tool page shows your files with a first-page thumbnail and a full preview, and when a job
finishes you can preview the result and rename it before downloading. Previews are rendered in your
browser with pdf.js, so they never leave your computer.

## How it works

```
browser ─► FastAPI (backend/app/main.py)
             ├─ checks file types by content, sizes, session ownership
             ├─ stores uploads as random names in backend/data/<job id>/in/
             ├─ runs each job in bubblewrap (backend/app/sandbox.py):
             │  no network, sees only its own job folder, memory/CPU/time limits
             └─ deletes the uploads as soon as the job ends; the result is deleted
                after download (if chosen) or after 1 hour
```

- `backend/app/tools.py` lists every tool and its options.
- `backend/app/ops/` holds the code for each tool.
- `frontend/src/tools.ts` holds the matching names and icons for the UI.

## Optional AI tools

Set `AI_ENABLED=true` and `ANTHROPIC_API_KEY=...` to turn on Summarize, Translate and Markdown
with AI. These send the PDF's text to Anthropic's API, and users must agree to that each time.
They use `claude-opus-5-5` by default (`AI_MODEL` to change it).

## Optional: newer pandoc

Ubuntu 24.04 ships pandoc 3.1.3. To use the official release instead (newer, and able to write
DOCX/ODT/EPUB under `--sandbox`), download a release `.deb` from
https://github.com/jgm/pandoc/releases, check its SHA-256 against the release page, and install
it with `sudo apt install ./pandoc-<version>-1-amd64.deb`.

## Putting it online

When you host this publicly, put [Caddy](https://caddyserver.com) in front of it. Caddy fetches and
renews the HTTPS certificate on its own. A `Caddyfile` with:

```
your-domain.com {
    reverse_proxy 127.0.0.1:8000
}
```

Then start the app with `ALLOWED_ORIGINS=https://your-domain.com` and run uvicorn with
`--proxy-headers --forwarded-allow-ips 127.0.0.1` so rate limiting sees real client IPs.
HSTS is sent automatically once requests arrive over HTTPS.

**License note:** PyMuPDF is AGPL-licensed. If you run this as a public service, the AGPL
requires you to offer the source code of your version to its users.

## Author

Made by Nickolas Tran: [GitHub](https://github.com/nickolastran) ·
[LinkedIn](https://www.linkedin.com/in/nickolas-tran/) · [Website](https://nickolastran.vercel.app/)
