import { Check, Copy, FilePlus, RotateCcw, RotateCw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { loadPdf, MAX_THUMBS, type PdfPages } from "../pdf";
import type { PageMode } from "../tools";
import { IconButton, type Picked } from "./FileList";
import { moveItem, Sortable, useSortableItem } from "./Sortable";

type Item = { key: string; fileId: string; page: number; rotate: number; blank: boolean; selected: boolean };
export type PageRef = { file: number; page: number; rotate: number; blank: boolean };

const HINT: Record<PageMode, string> = {
  organize: "Drag pages to reorder. With a keyboard, focus a handle, press Space, then use the arrow keys.",
  remove: "Select the pages to remove.",
  extract: "Select the pages to keep.",
  rotate: "Select pages to rotate, or rotate all of them.",
};

let blankCount = 0;

export default function PageEditor({ files, mode, onPlan }: { files: Picked[]; mode: PageMode; onPlan: (p: PageRef[] | null) => void }) {
  const [pdfs, setPdfs] = useState<Record<string, PdfPages>>({});
  const [items, setItems] = useState<Item[]>([]);
  const started = useRef(new Map<string, AbortController>());

  useEffect(() => {
    for (const f of files) {
      if (started.current.has(f.id)) continue;
      const ctl = new AbortController();
      started.current.set(f.id, ctl);
      let first = true;
      loadPdf(f.file, (p) => {
        if (ctl.signal.aborted) return;
        setPdfs((cur) => ({ ...cur, [f.id]: p }));
        if (first && p.count) {
          first = false;
          const added = Array.from({ length: p.count }, (_, i) => ({ key: `${f.id}-${i}`, fileId: f.id, page: i, rotate: 0, blank: false, selected: false }));
          setItems((cur) => [...cur, ...added]);
        }
      }, ctl.signal);
    }
    const ids = new Set(files.map((f) => f.id));
    for (const [id, ctl] of started.current) {
      if (!ids.has(id)) {
        ctl.abort();
        started.current.delete(id);
      }
    }
    setItems((cur) => cur.filter((it) => it.blank || ids.has(it.fileId)));
  }, [files]);

  useEffect(() => () => {
    started.current.forEach((c) => c.abort());
    started.current.clear();
  }, []);

  const error = files.map((f) => pdfs[f.id]?.error).find(Boolean);
  const loaded = files.every((f) => pdfs[f.id]?.count);

  useEffect(() => {
    if (!loaded || error) return onPlan(null);
    const index = new Map(files.map((f, i) => [f.id, i]));
    const keep = mode === "remove" ? items.filter((i) => !i.selected) : mode === "extract" ? items.filter((i) => i.selected) : items;
    const nothingPicked = (mode === "remove" || mode === "extract") && !items.some((i) => i.selected);
    onPlan(keep.length && !nothingPicked
      ? keep.map((i) => ({ file: i.blank ? 0 : index.get(i.fileId)!, page: i.page, rotate: i.rotate, blank: i.blank }))
      : null);
  }, [items, loaded, error, files, mode, onPlan]);

  const update = (key: string, patch: Partial<Item>) => setItems((cur) => cur.map((i) => (i.key === key ? { ...i, ...patch } : i)));
  const rotate = (it: Item, by: number) => update(it.key, { rotate: (it.rotate + by + 360) % 360 });
  const selectedCount = items.filter((i) => i.selected).length;
  function rotateMany(by: number) {
    setItems((cur) => cur.map((i) => (selectedCount === 0 || i.selected ? { ...i, rotate: (i.rotate + by + 360) % 360 } : i)));
  }
  function insertAfter(idx: number, it: Item) {
    const copy = { ...it, key: `${it.key}-${++blankCount}`, selected: false };
    setItems((cur) => [...cur.slice(0, idx + 1), copy, ...cur.slice(idx + 1)]);
  }
  const setAll = (selected: boolean) => setItems((cur) => cur.map((i) => ({ ...i, selected })));

  if (error) return <p role="alert" className="rounded-md border border-fg p-6">{error}</p>;
  if (!loaded) return <p role="status" className="rounded-md border border-line p-6 text-muted">Reading pages</p>;

  const fileName = (id: string) => files.find((f) => f.id === id)?.file.name ?? "";
  const grid = (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(136px,1fr))] gap-4" aria-label="Pages">
      {items.map((it, idx) => (
        <PageCard
          key={it.key}
          item={it}
          position={idx + 1}
          thumb={it.blank ? null : pdfs[it.fileId]?.thumbs[it.page] ?? null}
          source={files.length > 1 && !it.blank ? `${fileName(it.fileId)}, p. ${it.page + 1}` : null}
          mode={mode}
          toggle={() => update(it.key, { selected: !it.selected })}
          actions={mode === "organize" && (
            <>
              <IconButton label={`Rotate page ${idx + 1} left`} onClick={() => rotate(it, -90)}><RotateCcw size={16} /></IconButton>
              <IconButton label={`Rotate page ${idx + 1} right`} onClick={() => rotate(it, 90)}><RotateCw size={16} /></IconButton>
              <IconButton label={`Duplicate page ${idx + 1}`} onClick={() => insertAfter(idx, it)}><Copy size={16} /></IconButton>
              <IconButton label={`Insert blank page after page ${idx + 1}`} onClick={() => insertAfter(idx, { ...it, blank: true, rotate: 0, key: "blank" })}><FilePlus size={16} /></IconButton>
              <IconButton label={`Delete page ${idx + 1}`} disabled={items.length === 1} onClick={() => setItems(items.filter((x) => x.key !== it.key))}><X size={16} /></IconButton>
            </>
          )}
        />
      ))}
    </ul>
  );

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <p className="mr-auto text-muted">{HINT[mode]}</p>
        {mode !== "organize" && (
          <>
            <span className="font-mono text-xs text-muted" aria-live="polite">{selectedCount} of {items.length} selected</span>
            <button type="button" className="underline-offset-2 hover:underline" onClick={() => setAll(true)}>Select all</button>
            <button type="button" className="underline-offset-2 hover:underline" onClick={() => setAll(false)}>Clear</button>
          </>
        )}
        {mode === "rotate" && (
          <>
            <button type="button" onClick={() => rotateMany(-90)} className="inline-flex items-center gap-1.5 rounded border border-line px-2.5 py-1 hover:bg-subtle">
              <RotateCcw size={16} aria-hidden /> Left
            </button>
            <button type="button" onClick={() => rotateMany(90)} className="inline-flex items-center gap-1.5 rounded border border-line px-2.5 py-1 hover:bg-subtle">
              <RotateCw size={16} aria-hidden /> Right
            </button>
          </>
        )}
      </div>
      {items.length > MAX_THUMBS && <p className="mb-4 text-sm text-muted">Previews are shown for the first {MAX_THUMBS} pages.</p>}
      <Sortable grid ids={items.map((i) => i.key)} onMove={(a, b) => setItems(moveItem(items, a, b))}>{grid}</Sortable>
    </div>
  );
}

function PageCard({ item, position, thumb, source, mode, toggle, actions }: {
  item: Item; position: number; thumb: string | null; source: string | null; mode: PageMode; toggle: () => void; actions: React.ReactNode;
}) {
  const sortable = useSortableItem(item.key, `page ${position}`, mode !== "organize");
  const selectable = mode !== "organize";
  const removing = mode === "remove" && item.selected;
  const label = item.blank ? "Blank page" : `Page ${position}`;

  const preview = (
    <span className={`relative flex aspect-square items-center justify-center overflow-hidden rounded border bg-subtle p-2 ${item.selected ? "border-fg outline outline-1 outline-fg" : "border-line"}`}>
      {thumb ? (
        <img src={thumb} alt="" style={{ transform: `rotate(${item.rotate}deg)` }} className={`max-h-full max-w-full border border-line transition-transform duration-150 ${removing ? "opacity-30" : ""}`} />
      ) : (
        <span className="flex aspect-[1/1.414] h-full items-center justify-center bg-bg font-mono text-xs text-muted" style={{ transform: `rotate(${item.rotate}deg)` }}>
          {item.blank ? "Blank" : position}
        </span>
      )}
      {item.selected && (
        <span className="absolute right-1.5 top-1.5 rounded-sm bg-fg p-0.5 text-bg">
          {removing ? <X size={14} aria-hidden /> : <Check size={14} aria-hidden />}
        </span>
      )}
    </span>
  );

  return (
    <li ref={sortable.ref} style={sortable.style} className="bg-bg">
      {selectable ? (
        <button type="button" aria-pressed={item.selected} aria-label={label} onClick={toggle} className="block w-full rounded">
          {preview}
        </button>
      ) : preview}
      <div className="mt-1.5 flex items-center gap-1">
        {mode === "organize" && sortable.handle}
        <span className="font-mono text-xs">{position}</span>
        {item.rotate !== 0 && <span className="font-mono text-xs text-muted">{item.rotate}°</span>}
      </div>
      {source && <p className="truncate text-xs text-muted">{source}</p>}
      {actions && <div className="-ml-1 mt-1 flex flex-wrap">{actions}</div>}
    </li>
  );
}
