import { useEffect, useState } from "react";
import { openPdf } from "../pdf";
import type { Extra } from "./Placer";

type PdfField = { name: string; type: string; value: unknown; exportValues?: string; items?: { exportValue: string; displayValue: string }[] };
type Field = { name: string; type: "text" | "checkbox" | "radio" | "choice"; options: [string, string][] };
type Value = string | boolean;

const input = "mt-1.5 h-9 w-full rounded border border-line bg-bg px-2.5 text-sm focus:border-fg focus:outline-none";

/** Reads the PDF's form fields in the browser and collects values for them. */
export default function FormFiller({ file, onChange }: { file: File; onChange: (e: Extra) => void }) {
  const [fields, setFields] = useState<Field[] | null>(null);
  const [values, setValues] = useState<Record<string, Value>>({});
  const [error, setError] = useState<string>();

  useEffect(() => {
    let close = () => {};
    (async () => {
      const r = await openPdf(file);
      close = r.close;
      if (!r.doc) return setError(r.error);
      const objs = ((await r.doc.getFieldObjects()) ?? {}) as Record<string, PdfField[]>;
      const found: Field[] = [];
      const initial: Record<string, Value> = {};
      for (const [name, widgets] of Object.entries(objs)) {
        const w = widgets[0];
        if (w.type === "text") found.push({ name, type: "text", options: [] });
        else if (w.type === "checkbox") found.push({ name, type: "checkbox", options: [] });
        else if (w.type === "radiobutton") found.push({ name, type: "radio", options: widgets.map((x) => [x.exportValues ?? "", x.exportValues ?? ""]) });
        else if (w.type === "combobox" || w.type === "listbox") found.push({ name, type: "choice", options: (w.items ?? []).map((i) => [i.exportValue, i.displayValue]) });
        else continue;
        initial[name] = w.type === "checkbox" ? w.value !== "Off" && Boolean(w.value) : String(w.value ?? "");
      }
      setFields(found);
      setValues(initial);
    })();
    return () => close();
  }, [file]);

  useEffect(() => {
    onChange(fields?.length ? { options: { values } } : null);
  }, [values, fields]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <p role="alert" className="rounded-md border border-fg p-6">{error}</p>;
  if (!fields) return <p role="status" className="rounded-md border border-line p-6 text-muted">Reading form</p>;
  if (!fields.length) return <p className="rounded-md border border-line p-6">This PDF has no form fields.</p>;

  const set = (k: string, v: Value) => setValues({ ...values, [k]: v });
  return (
    <div className="grid gap-4 rounded-md border border-line p-5 sm:grid-cols-2">
      {fields.map((f, i) => {
        const id = `field-${i}`;
        if (f.type === "checkbox") {
          return (
            <label key={f.name} className="flex items-center gap-2 self-end text-sm">
              <input id={id} type="checkbox" checked={Boolean(values[f.name])} onChange={(e) => set(f.name, e.target.checked)} className="accent-current" />
              {f.name}
            </label>
          );
        }
        return (
          <div key={f.name}>
            <label htmlFor={id} className="text-sm font-medium">{f.name}</label>
            {f.type === "text" ? (
              <input id={id} value={String(values[f.name])} onChange={(e) => set(f.name, e.target.value)} className={input} />
            ) : (
              <select id={id} value={String(values[f.name])} onChange={(e) => set(f.name, e.target.value)} className={input}>
                <option value="">None</option>
                {f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            )}
          </div>
        );
      })}
    </div>
  );
}
