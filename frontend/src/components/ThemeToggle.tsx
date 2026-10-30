import { Moon, Sun } from "lucide-react";
import { useState } from "react";

type Theme = "light" | "dark";

function stored(): Theme | null {
  try {
    const t = localStorage.getItem("theme");
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

const initial = stored();
if (initial) document.documentElement.dataset.theme = initial;

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(
    () => initial ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
  );
  const next: Theme = theme === "dark" ? "light" : "dark";

  function toggle() {
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* private mode: the choice just won't persist */
    }
    setTheme(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${next === "dark" ? "black" : "white"} theme`}
      className="flex h-9 items-center gap-2 rounded border border-line px-3 text-sm hover:bg-subtle"
    >
      {theme === "dark" ? <Sun size={16} aria-hidden /> : <Moon size={16} aria-hidden />}
      {next === "dark" ? "Black" : "White"}
    </button>
  );
}
