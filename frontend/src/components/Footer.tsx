import { BriefcaseBusiness, CodeXml, Globe } from "lucide-react";

// Lucide has no brand logos, so these are plain Lucide icons like the rest of the site.
const LINKS = [
  // ponytail: points at the GitHub profile until this project has its own repo.
  { label: "Source on GitHub", href: "https://github.com/nickolastran", icon: CodeXml },
  { label: "LinkedIn", href: "https://www.linkedin.com/in/nickolas-tran/", icon: BriefcaseBusiness },
  { label: "Website", href: "https://nickolastran.vercel.app/", icon: Globe },
];

export default function Footer() {
  return (
    <footer className="mt-16 border-t border-line text-xs text-muted">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-8 gap-y-4 px-4 py-6 sm:px-6">
        <span>© {new Date().getFullYear()} Nickolas Tran · PDFolio</span>
        <nav aria-label="Links" className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {LINKS.map((l) => (
            <a
              key={l.label}
              href={l.href}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded border border-line px-2 py-1 transition-colors hover:border-fg hover:text-fg"
            >
              <l.icon size={13} aria-hidden />
              {l.label}
            </a>
          ))}
        </nav>
      </div>
    </footer>
  );
}
