import { ChevronLeft, ChevronRight, Plus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { openPdf, renderPage } from "../pdf";
import { IconButton } from "./FileList";
import SignaturePad, { type Signature } from "./SignaturePad";

export type PlaceMode = "sign" | "annotate" | "redact";
export type Extra = { options: object; files?: File[] } | null;
type Box = { id: number; page: number; x: number; y: number; w: number; h: number; text: string };

const ADD_LABEL: Record<PlaceMode, string> = { sign: "Add signature", annotate: "Add note", redact: "Add area" };
const HINT: Record<PlaceMode, string> = {
  sign: "Click or drag on the page to place your signature.",
  annotate: "Drag on the page to add a note.",
  redact: "Drag over anything you want removed, or list words to remove from every page.",
};
const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
let nextId = 0;

export default function Placer({ file, mode, onChange }: { file: File; mode: PlaceMode; onChange: (e: Extra) => void }) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string>();
  const [page, setPage] = useState(0);
  const [image, setImage] = useState<{ url: string; width: number; height: number } | null>(null);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [draft, setDraft] = useState<Box | null>(null);
  const [terms, setTerms] = useState("");
  const [sig, setSig] = useState<Signature | null>(null);
  const area = useRef<HTMLDivElement>(null);
  const start = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    let close = () => {};
    openPdf(file).then((r) => {
      close = r.close;
      if (r.doc) setDoc(r.doc);
      else setError(r.error);
    });
    return () => close();
  }, [file]);

  useEffect(() => {
    if (!doc) return;
    let url = "";
    renderPage(doc, page, 900).then((img) => {
      url = img.url;
      setImage(img);
    });
    return () => URL.revokeObjectURL(url);
  }, [doc, page]);

  const termList = terms.split(/[\n,]/).map((t) => t.trim()).filter(Boolean);
  useEffect(() => {
    const strip = boxes.map(({ page, x, y, w, h }) => ({ page, x, y, w, h }));
    if (mode === "sign") onChange(sig && boxes.length ? { options: { places: strip }, files: [sig.file] } : null);
    else if (mode === "annotate")
      onChange(boxes.length && boxes.every((b) => b.text.trim()) ? { options: { notes: boxes.map((b, i) => ({ ...strip[i], text: b.text })) } } : null);
    else onChange(boxes.length || termList.length ? { options: { areas: strip, terms: termList } } : null);
  }, [boxes, sig, terms, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <p role="alert" className="rounded-md border border-fg p-6">{error}</p>;
  if (!doc || !image) return <p role="status" className="rounded-md border border-line p-6 text-muted">Reading pages</p>;

  const aspect = image.width / image.height;
  function defaultBox(cx = 0.5, cy = 0.5): Box {
    let w = 0.4, h = mode === "annotate" ? 0.08 : 0.05;
    if (mode === "sign") {
      w = 0.25;
      h = (w * aspect) / (sig?.aspect ?? 3);
    }
    return { id: ++nextId, page, x: clamp(cx - w / 2, 0, 1 - w), y: clamp(cy - h / 2, 0, 1 - h), w, h, text: "" };
  }
  const point = (e: React.PointerEvent) => {
    const r = area.current!.getBoundingClientRect();
    return { x: clamp((e.clientX - r.left) / r.width), y: clamp((e.clientY - r.top) / r.height) };
  };
  function down(e: React.PointerEvent) {
    if (e.target !== e.currentTarget && !(e.target as HTMLElement).dataset.page) return;
    start.current = point(e);
    area.current!.setPointerCapture(e.pointerId);
  }
  function move(e: React.PointerEvent) {
    if (!start.current) return;
    const p = point(e), s = start.current;
    setDraft({ id: 0, page, x: Math.min(s.x, p.x), y: Math.min(s.y, p.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y), text: "" });
  }
  function up(e: React.PointerEvent) {
    const s = start.current;
    start.current = null;
    setDraft(null);
    if (!s) return;
    const p = point(e);
    const dragged = Math.abs(p.x - s.x) > 0.01 && Math.abs(p.y - s.y) > 0.01;
    if (dragged) add({ id: ++nextId, page, x: Math.min(s.x, p.x), y: Math.min(s.y, p.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y), text: "" });
    else if (mode === "sign") add(defaultBox(p.x, p.y));
  }
  const add = (b: Box) => setBoxes((cur) => [...cur, b]);
  const update = (id: number, patch: Partial<Box>) => setBoxes((cur) => cur.map((b) => (b.id === id ? { ...b, ...patch } : b)));
  const remove = (id: number) => setBoxes((cur) => cur.filter((b) => b.id !== id));

  function key(e: React.KeyboardEvent, b: Box) {
    const step = 0.01;
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (e.key === "Delete" || e.key === "Backspace") return remove(b.id);
    if (!d) return;
    e.preventDefault();
    if (e.shiftKey) update(b.id, { w: clamp(b.w + d[0], 0.02, 1 - b.x), h: clamp(b.h + d[1], 0.01, 1 - b.y) });
    else update(b.id, { x: clamp(b.x + d[0], 0, 1 - b.w), y: clamp(b.y + d[1], 0, 1 - b.h) });
  }

  const label = (b: Box, i: number) => `${mode === "sign" ? "Signature" : mode === "annotate" ? "Note" : "Area"} ${i + 1}, page ${b.page + 1}`;
  const style = (b: Box) => ({ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` });
  const look = mode === "redact" ? "bg-black/85 border border-black" : mode === "sign" ? "border border-dashed border-fg" : "border border-fg bg-bg/70";

  return (
    <div className="space-y-6">
      {mode === "sign" && <SignaturePad onChange={setSig} />}
      {mode === "redact" && (
        <div>
          <label htmlFor="terms" className="text-sm font-medium">Words to remove everywhere</label>
          <textarea id="terms" rows={2} value={terms} onChange={(e) => setTerms(e.target.value)} placeholder="One per line, or separated by commas"
            className="mt-1.5 w-full rounded border border-line bg-bg px-2.5 py-2 text-sm focus:border-fg focus:outline-none" />
        </div>
      )}

      <div>
        <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
          <p className="mr-auto text-muted">{HINT[mode]}</p>
          <button type="button" disabled={mode === "sign" && !sig} onClick={() => add(defaultBox())}
            className="inline-flex items-center gap-1.5 rounded border border-line px-2.5 py-1 hover:bg-subtle disabled:opacity-30">
            <Plus size={16} aria-hidden /> {ADD_LABEL[mode]}
          </button>
          <span className="inline-flex items-center gap-1">
            <IconButton label="Previous page" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft size={16} /></IconButton>
            <span className="font-mono text-xs" aria-live="polite">Page {page + 1} of {doc.numPages}</span>
            <IconButton label="Next page" disabled={page === doc.numPages - 1} onClick={() => setPage(page + 1)}><ChevronRight size={16} /></IconButton>
          </span>
        </div>

        <div className="flex justify-center rounded-md border border-line bg-subtle p-4">
          <div ref={area} data-page="1" onPointerDown={down} onPointerMove={move} onPointerUp={up}
            className={`relative touch-none select-none ${mode === "sign" && !sig ? "" : "cursor-crosshair"}`} style={{ aspectRatio: `${aspect}`, width: "100%", maxWidth: 680 }}>
            <img src={image.url} alt={`Page ${page + 1}`} data-page="1" draggable={false} className="h-full w-full border border-line bg-white" />
            {boxes.map((b, i) => b.page === page && (
              <div key={b.id} tabIndex={0} role="button" style={style(b)} onKeyDown={(e) => key(e, b)}
                aria-label={`${label(b, i)}. Arrow keys move it, Shift and arrows resize, Delete removes it.`}
                className={`group absolute ${look}`}>
                {mode === "sign" && sig && <img src={sig.url} alt="" className="h-full w-full object-contain" />}
                {mode === "annotate" && <span className="block overflow-hidden p-1 text-xs text-black">{b.text}</span>}
                <button type="button" aria-label={`Remove ${label(b, i)}`} onClick={() => remove(b.id)}
                  className="absolute -right-2.5 -top-2.5 hidden rounded-sm border border-line bg-bg p-0.5 group-focus-within:block group-hover:block">
                  <X size={12} aria-hidden />
                </button>
              </div>
            ))}
            {draft && <div className={`absolute ${look} opacity-60`} style={style(draft)} />}
          </div>
        </div>
      </div>

      {mode === "annotate" && boxes.length > 0 && (
        <ol className="space-y-3">
          {boxes.map((b, i) => (
            <li key={b.id}>
              <label htmlFor={`note-${b.id}`} className="text-sm font-medium">{label(b, i)}</label>
              <textarea id={`note-${b.id}`} rows={2} value={b.text} onChange={(e) => update(b.id, { text: e.target.value })}
                className="mt-1.5 w-full rounded border border-line bg-bg px-2.5 py-2 text-sm focus:border-fg focus:outline-none" />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
