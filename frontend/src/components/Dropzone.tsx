import { Upload } from "lucide-react";
import { useRef, useState } from "react";

type Props = { accept: string; multiple: boolean; onFiles: (files: File[]) => void; compact?: boolean };

export default function Dropzone({ accept, multiple, onFiles, compact }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        onFiles([...e.dataTransfer.files]);
      }}
      className={`flex flex-col items-center justify-center gap-3 rounded-md border border-dashed text-center transition-colors ${
        over ? "border-fg bg-subtle" : "border-strong"
      } ${compact ? "py-6" : "py-16"}`}
    >
      <Upload size={compact ? 20 : 28} aria-hidden className="text-muted" />
      <p className={compact ? "text-sm" : ""}>Drop files here</p>
      <button
        type="button"
        onClick={() => input.current?.click()}
        className="rounded border border-line px-3 py-1.5 text-sm hover:bg-subtle"
      >
        {multiple ? "Choose files" : "Choose file"}
      </button>
      <input
        ref={input}
        type="file"
        accept={accept}
        multiple={multiple}
        hidden
        onChange={(e) => {
          onFiles([...(e.target.files ?? [])]);
          e.target.value = "";
        }}
      />
    </div>
  );
}
