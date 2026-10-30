import { useEffect, useRef, useState } from "react";

export type Signature = { file: File; url: string; aspect: number };
type Tab = "draw" | "type" | "upload";
const W = 600, H = 200;

async function toSignature(canvas: HTMLCanvasElement): Promise<Signature | null> {
  const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/png"));
  if (!blob) return null;
  return { file: new File([blob], "signature.png", { type: "image/png" }), url: URL.createObjectURL(blob), aspect: W / H };
}

/** Draw, type or upload a signature; reports it as a PNG file. */
export default function SignaturePad({ onChange }: { onChange: (s: Signature | null) => void }) {
  const [tab, setTab] = useState<Tab>("draw");
  const [name, setName] = useState("");
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const inked = useRef(false);

  const ctx = () => canvas.current!.getContext("2d")!;
  function clear() {
    canvas.current?.getContext("2d")?.clearRect(0, 0, W, H);
    inked.current = false;
    onChange(null);
  }
  useEffect(clear, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (tab !== "type") return;
    const font = 'italic 64px "IBM Plex Sans"';
    document.fonts.load(font).then(async () => {
      const c = ctx();
      c.clearRect(0, 0, W, H);
      if (!name.trim()) return onChange(null);
      c.font = font;
      c.fillStyle = "#000";
      c.textAlign = "center";
      c.textBaseline = "middle";
      c.fillText(name, W / 2, H / 2, W - 40);
      onChange(await toSignature(canvas.current!));
    });
  }, [name, tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const pos = (e: React.PointerEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * W, ((e.clientY - r.top) / r.height) * H] as const;
  };

  async function upload(f?: File) {
    if (!f) return onChange(null);
    const img = new Image();
    img.src = URL.createObjectURL(f);
    await img.decode();
    onChange({ file: f, url: img.src, aspect: img.width / img.height });
  }

  const tabs: [Tab, string][] = [["draw", "Draw"], ["type", "Type"], ["upload", "Upload"]];
  return (
    <fieldset>
      <legend className="text-sm font-medium">Signature</legend>
      <div role="tablist" className="mt-1.5 inline-flex rounded border border-line p-0.5 text-sm">
        {tabs.map(([t, l]) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`rounded-sm px-3 py-1 ${tab === t ? "bg-fg text-bg" : "hover:bg-subtle"}`}>{l}</button>
        ))}
      </div>

      {tab === "upload" ? (
        <input type="file" accept=".png,.jpg,.jpeg,image/png,image/jpeg" aria-label="Signature image" onChange={(e) => upload(e.target.files?.[0])}
          className="mt-3 block text-sm file:mr-3 file:rounded file:border file:border-line file:bg-bg file:px-3 file:py-1.5 file:text-fg" />
      ) : (
        <div className="mt-3">
          {tab === "type" && (
            <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Type your name" placeholder="Your name"
              className="mb-3 h-9 w-full max-w-sm rounded border border-line bg-bg px-2.5 text-sm focus:border-fg focus:outline-none" />
          )}
          <div className="relative max-w-xl rounded border border-line bg-white">
            <canvas ref={canvas} width={W} height={H} aria-label={tab === "draw" ? "Signature drawing area" : "Signature preview"}
              className={`block w-full ${tab === "draw" ? "cursor-crosshair touch-none" : ""}`}
              onPointerDown={(e) => {
                if (tab !== "draw") return;
                drawing.current = true;
                canvas.current!.setPointerCapture(e.pointerId);
                const c = ctx();
                c.lineWidth = 3;
                c.lineCap = c.lineJoin = "round";
                c.strokeStyle = "#000";
                c.beginPath();
                c.moveTo(...pos(e));
              }}
              onPointerMove={(e) => {
                if (!drawing.current) return;
                ctx().lineTo(...pos(e));
                ctx().stroke();
                inked.current = true;
              }}
              onPointerUp={async () => {
                if (!drawing.current) return;
                drawing.current = false;
                if (inked.current) onChange(await toSignature(canvas.current!));
              }}
            />
            {tab === "draw" && (
              <button type="button" onClick={clear} className="absolute right-2 top-2 rounded border border-line bg-white px-2 py-0.5 text-xs text-black hover:bg-neutral-100">
                Clear
              </button>
            )}
          </div>
          {tab === "draw" && <p className="mt-1.5 text-xs text-muted">Using a keyboard? Choose Type instead.</p>}
        </div>
      )}
    </fieldset>
  );
}
