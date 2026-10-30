import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router";
import { getTools, type ToolList } from "./api";
import Footer from "./components/Footer";
import ThemeToggle from "./components/ThemeToggle";
import "./index.css";
import Home from "./pages/Home";
import ToolPage from "./pages/ToolPage";

function App() {
  const [server, setServer] = useState<ToolList | null>(null);
  useEffect(() => {
    getTools().then(setServer).catch(() => setServer({ tools: {}, limits: { file_mb: 0, total_mb: 0, files: 0 } }));
  }, []);

  return (
    <BrowserRouter>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:p-2">Skip to content</a>
      <header className="border-b border-line">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/" className="font-semibold tracking-tight">PDFolio</Link>
          <ThemeToggle />
        </div>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        <Routes>
          <Route path="/" element={<Home server={server} />} />
          <Route path="/:toolId" element={<ToolPage server={server} />} />
        </Routes>
      </main>
      <Footer />
    </BrowserRouter>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
