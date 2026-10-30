import { ArrowLeft, Download, Eye } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { createJob, deleteJob, downloadUrl, fetchResult, getFormats, getJob, type JobStatus, type ToolList } from "../api";
import Dropzone from "../components/Dropzone";
import FileList, { type Picked } from "../components/FileList";
import OptionFields, { defaults, visible, type Values } from "../components/OptionFields";
import FormFiller from "../components/FormFiller";
import PageEditor, { type PageRef } from "../components/PageEditor";
import Placer, { type Extra } from "../components/Placer";
import Viewer, { canView, type Viewable } from "../components/Viewer";
import { kindOf, TOOLS, type Tool } from "../tools";

type Phase =
  | { kind: "pick" }
  | { kind: "working"; id: string; status: JobStatus["status"] }
  | { kind: "done"; id: string; ext: string }
  | { kind: "error"; message: string };

let nextId = 0;

const countLabel = (max: number, min: number) =>
  max === 1 ? "One file" : min === max ? `${max} files` : min > 1 ? `${min}–${max} files` : `Up to ${max} files`;

export default function ToolPage({ server }: { server: ToolList | null }) {
  const { toolId } = useParams();
  const tool = TOOLS.find((t) => t.id === toolId);
  if (!tool) return <p>Tool not found. <Link to="/" className="underline">All tools</Link></p>;
  return <ToolView key={tool.id} tool={tool} server={server} />;
}

function ToolView({ tool, server }: { tool: Tool; server: ToolList | null }) {
  const spec = server?.tools[tool.id];
  const [files, setFiles] = useState<Picked[]>([]);
  const [values, setValues] = useState<Values>(() => defaults(tool.fields));
  // Options and extra files produced by a page editor, placer or form filler (null: not ready).
  const [extra, setExtra] = useState<Extra>(null);
  const onPlan = useCallback((p: PageRef[] | null) => setExtra(p && { options: { pages: p } }), []);
  const [phase, setPhase] = useState<Phase>({ kind: "pick" });
  const [deleteAfter, setDeleteAfter] = useState(true);
  const [downloaded, setDownloaded] = useState(false);
  const [formats, setFormats] = useState<Record<string, string[]> | null>(null);
  const [aiConsent, setAiConsent] = useState(false);
  const [name, setName] = useState("");
  const [viewing, setViewing] = useState<Viewable | null>(null);
  const [result, setResult] = useState<Blob | null>(null);
  const hasTarget = tool.fields?.some((f) => f.type === "target");

  useEffect(() => {
    if (hasTarget) getFormats().then(setFormats).catch(() => setFormats({}));
  }, [hasTarget]);
  const reachable = files.length && formats ? formats[kindOf(files[0].file.name)] ?? [] : null;
  const targetOk = !hasTarget || (reachable ?? []).includes(String(values.to));

  useEffect(() => {
    if (phase.kind !== "working") return;
    const timer = setInterval(async () => {
      try {
        const s = await getJob(phase.id);
        if (s.status === "done") {
          setName(s.name ?? "");
          setPhase({ kind: "done", id: phase.id, ext: s.ext ?? "" });
        }
        else if (s.status === "failed") setPhase({ kind: "error", message: s.error ?? "Processing failed" });
        else if (s.status !== phase.status) setPhase({ ...phase, status: s.status });
      } catch (e) {
        setPhase({ kind: "error", message: (e as Error).message });
      }
    }, 700);
    return () => clearInterval(timer);
  }, [phase]);

  const limits = server?.limits;
  const tooBig = limits && files.some((f) => f.file.size > limits.file_mb * 1024 * 1024);
  const total = files.length + (extra?.files?.length ?? 0); // a signature image counts as a file
  const countOk = spec && total >= spec.min_files && total <= spec.max_files;
  const needsExtra = Boolean(tool.pages || tool.place || tool.form);
  const matchOk = (tool.fields ?? []).every((f) => !f.matches || values[f.key] === values[f.matches]);
  const filled = (tool.fields ?? []).every((f) => f.type !== "text" || f.showIf || String(values[f.key]).trim());
  const canStart = countOk && !tooBig && targetOk && matchOk && filled && (!tool.ai || aiConsent) && (!needsExtra || extra);

  function add(picked: File[]) {
    if (!spec) return;
    const items = picked.map((file) => ({ id: String(++nextId), file }));
    setFiles((cur) => (spec.max_files === 1 ? items.slice(0, 1) : [...cur, ...items].slice(0, spec.max_files)));
  }
  async function start() {
    const options = Object.fromEntries(visible(tool.fields, values).filter((f) => !f.local).map((f) => [f.key, values[f.key]]));
    try {
      const { id } = await createJob(tool.id, [...files.map((f) => f.file), ...(extra?.files ?? [])], { ...options, ...extra?.options });
      setPhase({ kind: "working", id, status: "queued" });
    } catch (e) {
      setPhase({ kind: "error", message: (e as Error).message });
    }
  }
  function reset() {
    if (phase.kind === "done" && !(downloaded && deleteAfter)) deleteJob(phase.id);
    setFiles([]);
    setDownloaded(false);
    setResult(null);
    setPhase({ kind: "pick" });
  }

  return (
    <>
      <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={16} aria-hidden /> All tools
      </Link>
      <h1 className="mt-4 text-[28px] font-semibold leading-tight tracking-tight">{tool.name}</h1>
      <p className="mt-2 text-muted">{tool.description}</p>

      {server && !spec ? (
        <p className="mt-10 border-t border-line pt-6">This tool isn't available yet.</p>
      ) : (
        <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_300px]">
          <div className="min-w-0">
            {phase.kind === "pick" && (
              <>
                {files.length > 0 && <FileList files={files} setFiles={setFiles} onPreview={(f) => setViewing({ blob: f.file, name: f.file.name })} />}
                {files.length > 0 && needsExtra && (
                  <div className="mb-8">
                    {tool.pages && <PageEditor files={files} mode={tool.pages} onPlan={onPlan} />}
                    {tool.place && <Placer key={files[0].id} file={files[0].file} mode={tool.place} onChange={setExtra} />}
                    {tool.form && <FormFiller key={files[0].id} file={files[0].file} onChange={setExtra} />}
                  </div>
                )}
                {(!spec || files.length < spec.max_files - (tool.place === "sign" ? 1 : 0)) && (
                  <Dropzone accept={tool.accept} multiple={!spec || spec.max_files > 1} onFiles={add} compact={files.length > 0} />
                )}
              </>
            )}
            {phase.kind === "working" && (
              <div role="status" className="rounded-md border border-line p-6">
                <p>{phase.status === "queued" ? "Waiting to start" : "Processing"}</p>
                <div className="mt-3 h-1 overflow-hidden rounded bg-subtle" aria-hidden>
                  <div className="progress-indeterminate h-full w-2/5 bg-fg" />
                </div>
              </div>
            )}
            {phase.kind === "done" && (
              <div role="status" className="rounded-md border border-line p-6">
                <p className="font-medium">{downloaded && deleteAfter ? "Downloaded. Files deleted from the server." : "Ready"}</p>
                {!(downloaded && deleteAfter) && (
                  <>
                    <label htmlFor="out-name" className="mt-5 block text-sm font-medium">File name</label>
                    <div className="mt-1.5 flex max-w-md items-center rounded border border-line focus-within:border-fg">
                      <input id="out-name" value={name} onChange={(e) => setName(e.target.value)} spellCheck={false}
                        className="h-9 min-w-0 flex-1 bg-transparent px-2.5 text-sm outline-none" />
                      <span className="pr-2.5 font-mono text-xs text-muted">{phase.ext}</span>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {canView(phase.ext) && (
                        <button
                          type="button"
                          onClick={async () => {
                            try {
                              const blob = result ?? (await fetchResult(phase.id));
                              setResult(blob);
                              setViewing({ blob, name: `${name || "result"}${phase.ext}` });
                            } catch (e) {
                              setPhase({ kind: "error", message: (e as Error).message });
                            }
                          }}
                          className="inline-flex items-center gap-2 rounded border border-line px-4 py-2 hover:bg-subtle"
                        >
                          <Eye size={16} aria-hidden /> Preview
                        </button>
                      )}
                      <a
                        href={downloadUrl(phase.id, deleteAfter, name.trim())}
                        download
                        onClick={() => setDownloaded(true)}
                        className="inline-flex items-center gap-2 rounded bg-fg px-4 py-2 text-bg hover:opacity-85"
                      >
                        <Download size={16} aria-hidden /> Download
                      </a>
                    </div>
                  </>
                )}
              </div>
            )}
            {phase.kind === "error" && (
              <div role="alert" className="rounded-md border border-fg p-6">
                <p className="font-medium">{phase.message}</p>
                <button type="button" onClick={() => setPhase({ kind: "pick" })} className="mt-4 rounded border border-line px-3 py-1.5 text-sm hover:bg-subtle">
                  Try again
                </button>
              </div>
            )}
          </div>

          <aside className="self-start rounded-md border border-line p-5 lg:sticky lg:top-6">
            {phase.kind === "pick" ? (
              <>
                {tool.fields && (
                  <div className="mb-5">
                    <OptionFields fields={tool.fields} values={values} onChange={setValues} reachable={reachable} />
                  </div>
                )}
                {spec && (
                  <p className="text-sm text-muted">
                    {countLabel(spec.max_files - (tool.place === "sign" ? 1 : 0), spec.min_files)},
                    up to <span className="font-mono">{limits?.file_mb} MB</span>{spec.max_files > 1 && " each"}.
                  </p>
                )}
                {tooBig && <p className="mt-3 text-sm" role="alert">A file is larger than {limits?.file_mb} MB.</p>}
                {!matchOk && <p className="mt-3 text-sm" role="alert">Passwords don't match.</p>}
                {tool.ai && (
                  <div className="mt-5 rounded border border-fg p-3 text-sm">
                    <p>This tool sends the text of your PDF to Anthropic's API, a third-party service. Anthropic's data policies apply to it there.</p>
                    <label className="mt-3 flex items-start gap-2">
                      <input type="checkbox" checked={aiConsent} onChange={(e) => setAiConsent(e.target.checked)} className="mt-0.5 accent-current" />
                      Send the text to Anthropic
                    </label>
                  </div>
                )}
                <button
                  type="button"
                  disabled={!canStart}
                  onClick={start}
                  className="mt-5 w-full rounded bg-fg px-4 py-2.5 font-medium text-bg hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-30"
                >
                  {tool.name}
                </button>
              </>
            ) : (
              <>
                {phase.kind === "done" && !downloaded && (
                  <label className="mb-4 flex items-start gap-2 text-sm">
                    <input type="checkbox" checked={deleteAfter} onChange={(e) => setDeleteAfter(e.target.checked)} className="mt-0.5 accent-current" />
                    Delete files from the server after download
                  </label>
                )}
                <button type="button" onClick={reset} className="w-full rounded border border-line px-4 py-2 text-sm hover:bg-subtle">
                  Start over
                </button>
              </>
            )}
            <p className="mt-5 border-t border-line pt-4 text-xs text-muted">Files are processed privately and deleted automatically after 1 hour.</p>
          </aside>
        </div>
      )}
      {viewing && <Viewer file={viewing} onClose={() => setViewing(null)} />}
    </>
  );
}
