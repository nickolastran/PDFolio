import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import type { ToolList } from "../api";
import { CATEGORIES, TOOLS } from "../tools";

export default function Home({ server }: { server: ToolList | null }) {
  const [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        input.current?.focus();
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);

  const q = query.trim().toLowerCase();
  const match = (t: (typeof TOOLS)[number]) =>
    !q || t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q);

  return (
    <>
      <div className="mb-10 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-[28px] font-semibold leading-tight tracking-tight">PDF tools</h1>
          <p className="mt-2 text-muted">Files are processed privately and deleted automatically after 1 hour.</p>
        </div>
        <label className="flex h-10 w-full items-center gap-2 rounded border border-line px-3 sm:w-72 focus-within:border-fg">
          <Search size={16} aria-hidden className="text-muted" />
          <span className="sr-only">Find a tool</span>
          <input
            ref={input}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find a tool"
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted"
          />
          <kbd className="hidden font-mono text-xs text-muted sm:inline" aria-hidden>/</kbd>
        </label>
      </div>

      {CATEGORIES.map((cat) => {
        const tools = TOOLS.filter((t) => t.category === cat && match(t));
        if (!tools.length) return null;
        return (
          <section key={cat} aria-labelledby={`cat-${cat}`} className="grid gap-3 border-t border-line py-6 md:grid-cols-[180px_1fr]">
            <h2 id={`cat-${cat}`} className="pt-2 text-sm font-medium text-muted">{cat}</h2>
            <ul className="grid gap-x-6 sm:grid-cols-2 lg:grid-cols-3">
              {tools.map((t) => {
                const ready = !server || t.id in server.tools;
                return (
                  <li key={t.id}>
                    <Link
                      to={`/${t.id}`}
                      className={`-mx-2 flex gap-3 rounded px-2 py-2 hover:bg-subtle ${ready ? "" : "text-muted"}`}
                    >
                      <t.icon size={20} aria-hidden className="mt-0.5 shrink-0" />
                      <span>
                        <span className="block font-medium">{t.name}</span>
                        <span className="block text-sm text-muted">{ready ? t.description : t.ai ? "Off on this server" : "Not available yet"}</span>
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
      {!TOOLS.some(match) && <p className="border-t border-line py-6 text-muted">No tool matches “{query}”.</p>}
    </>
  );
}
