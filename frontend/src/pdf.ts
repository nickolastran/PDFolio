// Pages are rendered here in the browser, so previews never leave the user's computer.
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

GlobalWorkerOptions.workerSrc = workerUrl;

export const MAX_THUMBS = 300;
const THUMB = 160;

export type PdfPages = { count: number; thumbs: (string | null)[]; error?: string };

export async function openPdf(file: Blob): Promise<{ doc?: PDFDocumentProxy; close: () => void; error?: string }> {
  const task = getDocument({ data: new Uint8Array(await file.arrayBuffer()), enableXfa: false });
  try {
    return { doc: await task.promise, close: () => task.destroy() };
  } catch (e) {
    task.destroy();
    const locked = (e as Error).name === "PasswordException";
    return { close: () => {}, error: locked ? "This PDF has a password. Unlock it first." : "This PDF could not be read." };
  }
}

/** Render page i (0-based) so its longer side is `size` px. Returns a blob: URL. */
export async function renderPage(doc: PDFDocumentProxy, i: number, size: number) {
  const page = await doc.getPage(i + 1);
  const base = page.getViewport({ scale: 1 });
  const viewport = page.getViewport({ scale: size / Math.max(base.width, base.height) });
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  await page.render({ canvas, viewport }).promise;
  const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r));
  return { url: blob ? URL.createObjectURL(blob) : "", width: canvas.width, height: canvas.height };
}

/** Calls onUpdate as thumbnails render. Pages past MAX_THUMBS get no image (just a number). */
export async function loadPdf(file: File, onUpdate: (p: PdfPages) => void, signal: AbortSignal) {
  const { doc, close, error } = await openPdf(file);
  if (!doc) return onUpdate({ count: 0, thumbs: [], error });
  const thumbs: (string | null)[] = Array(doc.numPages).fill(null);
  onUpdate({ count: doc.numPages, thumbs: [...thumbs] });
  for (let i = 0; i < Math.min(doc.numPages, MAX_THUMBS) && !signal.aborted; i++) {
    thumbs[i] = (await renderPage(doc, i, THUMB)).url;
    onUpdate({ count: doc.numPages, thumbs: [...thumbs] });
  }
  close();
}
