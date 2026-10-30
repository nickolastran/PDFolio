import { X } from "lucide-react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { useEffect, useMemo, useRef, useState } from "react";
import { openPdf, renderPage } from "../pdf";

export type Viewable = { blob: Blob; name: string };

const kindOf = (name: string, type = "") =>
  type === "application/pdf" || /\.pdf$/i.test(name) ? "pdf"
    : type.startsWith("image/") || /\.(jpe?g|png)$/i.test(name) ? "image"
    : /\.(md|txt)$/i.test(name) ? "text" : null;

/** Whether a file with this name can be previewed. */
export const canView = (name: string) => kindOf(name) !== null;

/** Full-screen preview of a PDF, image or text file, rendered in the browser. */
export default function Viewer({ file, onClose }: { file: Viewable; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const kind = kindOf(file.name, file.blob.type);
  const [scroller, setScroller] = useState<HTMLDivElement | null>(null);
  useEffect(() => dialog.current?.showModal(), []);

  return (
    <dialog ref={dialog} onClose={onClose} aria-label={`Preview of ${file.name}`}
      className="m-auto h-[92vh] w-[min(960px,94vw)] max-w-none rounded-md border border-line bg-bg p-0 text-fg backdrop:bg-black/60">
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <p className="min-w-0 flex-1 truncate font-medium">{file.name}</p>
          <button type="button" autoFocus onClick={() => dialog.current?.close()} aria-label="Close preview"
            className="rounded p-1 text-muted hover:bg-subtle hover:text-fg">
            <X size={18} aria-hidden />
          </button>
        </div>
        <div ref={setScroller} className="flex-1 overflow-auto bg-subtle p-4">
          {kind === "pdf" && scroller && <PdfPages blob={file.blob} root={scroller} />}
          {kind === "image" && <ImagePreview blob={file.blob} />}
          {kind === "text" && <TextPreview blob={file.blob} />}
        </div>
      </div>
    </dialog>
  );
}

function PdfPages({ blob, root }: { blob: Blob; root: HTMLElement }) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [aspect, setAspect] = useState(1 / 1.414);
  const [error, setError] = useState<string>();

  useEffect(() => {
    let close = () => {};
    openPdf(blob).then(async (r) => {
      close = r.close;
      if (!r.doc) return setError(r.error);
      const vp = (await r.doc.getPage(1)).getViewport({ scale: 1 });
      setAspect(vp.width / vp.height);
      setDoc(r.doc);
    });
    return () => close();
  }, [blob]);

  if (error) return <p role="alert">{error}</p>;
  if (!doc) return <p role="status" className="text-muted">Loading</p>;
  return (
    <ol className="mx-auto max-w-3xl space-y-4">
      {Array.from({ length: doc.numPages }, (_, i) => (
        <li key={i}>
          <LazyPage doc={doc} index={i} aspect={aspect} root={root} />
          <p className="mt-1 text-center font-mono text-xs text-muted">{i + 1} / {doc.numPages}</p>
        </li>
      ))}
    </ol>
  );
}

/** Renders a page only once it scrolls near the viewport, so long PDFs open instantly. */
function LazyPage({ doc, index, aspect, root }: { doc: PDFDocumentProxy; index: number; aspect: number; root: HTMLElement }) {
  const box = useRef<HTMLDivElement>(null);
  const [img, setImg] = useState<{ url: string; width: number; height: number } | null>(null);

  useEffect(() => {
    let url = "";
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      renderPage(doc, index, 1400).then((r) => {
        url = r.url;
        setImg(r);
      });
    }, { root, rootMargin: "800px" }); // root: the dialog scrolls, not the window
    io.observe(box.current!);
    return () => {
      io.disconnect();
      if (url) URL.revokeObjectURL(url);
    };
  }, [doc, index, root]);

  return (
    <div ref={box} className="border border-line bg-white" style={{ aspectRatio: img ? `${img.width / img.height}` : `${aspect}` }}>
      {img && <img src={img.url} alt={`Page ${index + 1}`} className="h-full w-full" />}
    </div>
  );
}

function ImagePreview({ blob }: { blob: Blob }) {
  const url = useMemo(() => URL.createObjectURL(blob), [blob]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  return <img src={url} alt="" className="mx-auto max-h-full max-w-full border border-line" />;
}

function TextPreview({ blob }: { blob: Blob }) {
  const [text, setText] = useState("");
  useEffect(() => { blob.text().then(setText); }, [blob]);
  return <pre className="mx-auto max-w-3xl whitespace-pre-wrap rounded border border-line bg-bg p-5 font-mono text-sm leading-relaxed">{text}</pre>;
}
