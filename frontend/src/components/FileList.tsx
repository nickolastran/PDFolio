import { ChevronDown, ChevronUp, Eye, FileText, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { openPdf, renderPage } from "../pdf";
import { moveItem, Sortable, useSortableItem } from "./Sortable";

export type Picked = { id: string; file: File };

export function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function IconButton({ label, children, ...rest }: { label: string; children: React.ReactNode; disabled?: boolean; onClick: () => void; pressed?: boolean }) {
  return (
    <button type="button" aria-label={label} title={label} className="rounded p-1 text-muted hover:bg-subtle hover:text-fg disabled:opacity-30" {...rest}>
      {children}
    </button>
  );
}

export default function FileList({ files, setFiles, onPreview }: { files: Picked[]; setFiles: (f: Picked[]) => void; onPreview: (f: Picked) => void }) {
  const move = (from: number, to: number) => setFiles(moveItem(files, from, to));
  return (
    <Sortable ids={files.map((f) => f.id)} onMove={move}>
      <ol className="mb-4 divide-y divide-line rounded-md border border-line" aria-label="Files, in order">
        {files.map((f, i) => (
          <Row key={f.id} item={f} index={i} count={files.length} move={move} preview={() => onPreview(f)} remove={() => setFiles(files.filter((x) => x.id !== f.id))} />
        ))}
      </ol>
    </Sortable>
  );
}

function Row({ item, index, count, move, preview, remove }: { item: Picked; index: number; count: number; move: (a: number, b: number) => void; preview: () => void; remove: () => void }) {
  const { file } = item;
  const s = useSortableItem(item.id, file.name);
  const thumb = useThumb(file);

  return (
    <li ref={s.ref} style={s.style} className={`flex items-center gap-3 bg-bg px-3 py-2.5 ${s.isDragging ? "relative outline outline-1 outline-fg" : ""}`}>
      {count > 1 && s.handle}
      <span className="w-6 font-mono text-xs text-muted">{index + 1}</span>
      {thumb ? (
        <img src={thumb} alt="" className="h-11 w-9 shrink-0 border border-line bg-white object-contain" />
      ) : (
        <span className="flex h-11 w-9 shrink-0 items-center justify-center"><FileText size={18} aria-hidden /></span>
      )}
      <span className="min-w-0 flex-1 truncate">{file.name}</span>
      <span className="font-mono text-xs text-muted">{formatSize(file.size)}</span>
      {count > 1 && (
        <>
          <IconButton label={`Move ${file.name} up`} disabled={index === 0} onClick={() => move(index, index - 1)}><ChevronUp size={16} /></IconButton>
          <IconButton label={`Move ${file.name} down`} disabled={index === count - 1} onClick={() => move(index, index + 1)}><ChevronDown size={16} /></IconButton>
        </>
      )}
      {thumb && <IconButton label={`Preview ${file.name}`} onClick={preview}><Eye size={16} /></IconButton>}
      <IconButton label={`Remove ${file.name}`} onClick={remove}><X size={16} /></IconButton>
    </li>
  );
}

/** Small picture of an image, or of a PDF's first page. Null for other files or unreadable PDFs. */
function useThumb(file: File) {
  const isImage = file.type.startsWith("image/");
  const imageUrl = useMemo(() => (isImage ? URL.createObjectURL(file) : null), [file, isImage]);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);

  useEffect(() => () => { if (imageUrl) URL.revokeObjectURL(imageUrl); }, [imageUrl]);
  useEffect(() => {
    if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") return;
    let url = "";
    let close = () => {};
    openPdf(file).then(async (r) => {
      close = r.close;
      if (!r.doc) return;
      url = (await renderPage(r.doc, 0, 96)).url;
      setPdfUrl(url);
      close();
    });
    return () => {
      close();
      if (url) URL.revokeObjectURL(url);
    };
  }, [file]);
  return imageUrl ?? pdfUrl;
}
