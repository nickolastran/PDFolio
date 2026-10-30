import { FORMAT_NAMES, type Field } from "../tools";

export type Values = Record<string, string | number | boolean>;

export const defaults = (fields: Field[] = []): Values => Object.fromEntries(fields.map((f) => [f.key, f.default]));

export const visible = (fields: Field[] = [], values: Values) =>
  fields.filter((f) => !f.showIf || values[f.showIf[0]] === f.showIf[1]);

const input = "mt-1.5 h-9 w-full rounded border border-line bg-bg px-2.5 text-sm focus:border-fg focus:outline-none";

/** reachable: for "target" fields, the formats the current file can become (null: no file yet). */
export default function OptionFields({ fields, values, onChange, reachable }: { fields: Field[]; values: Values; onChange: (v: Values) => void; reachable?: string[] | null }) {
  const set = (k: string, v: string | number | boolean) => onChange({ ...values, [k]: v });
  return (
    <div className="space-y-4">
      {visible(fields, values).map((f) => {
        const id = `opt-${f.key}`;
        if (f.type === "checkbox") {
          return (
            <label key={f.key} className="flex items-center gap-2 text-sm">
              <input id={id} type="checkbox" checked={Boolean(values[f.key])} onChange={(e) => set(f.key, e.target.checked)} className="accent-current" />
              {f.label}
            </label>
          );
        }
        return (
          <div key={f.key}>
            <label htmlFor={id} className="text-sm font-medium">{f.label}</label>
            {f.type === "target" ? (
              <select id={id} value={String(values[f.key])} onChange={(e) => set(f.key, e.target.value)} className={input} disabled={!reachable}>
                <option value="">{reachable ? "Choose a format" : "Add a file first"}</option>
                {Object.entries(FORMAT_NAMES).map(([v, l]) => (
                  <option key={v} value={v} disabled={!reachable?.includes(v)}>{l}</option>
                ))}
              </select>
            ) : f.type === "select" ? (
              <select id={id} value={String(values[f.key])} onChange={(e) => set(f.key, e.target.value)} className={input}>
                {f.choices.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            ) : f.type === "number" ? (
              <input id={id} type="number" min={f.min} max={f.max} value={Number(values[f.key])} onChange={(e) => set(f.key, Number(e.target.value))} className={`${input} font-mono`} />
            ) : (
              <input id={id} type={f.type} value={String(values[f.key])} placeholder={f.placeholder} onChange={(e) => set(f.key, e.target.value)} autoComplete={f.type === "password" ? "off" : undefined} className={input} />
            )}
          </div>
        );
      })}
    </div>
  );
}
