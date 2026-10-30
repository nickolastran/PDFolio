import {
  Archive, Code, Combine, Crop, EyeOff, FileMinus, FileOutput, FileSpreadsheet, FileText, FileType,
  GitCompare, Hash, Image, Images, Languages, LayoutGrid, ListCollapse, ListOrdered, Lock, LockOpen,
  MessageSquareText, Minimize2, Presentation, RotateCw, ScanLine, ScanText, Signature, Split, Stamp,
  Table, TextCursorInput, Wrench, type LucideIcon,
} from "lucide-react";

// local: shown but not sent (e.g. "confirm password"); matches: must equal another field.
type FieldBase = { key: string; label: string; showIf?: [string, string]; local?: boolean; matches?: string };
export type Field = FieldBase & (
  | { type: "select"; choices: [string, string][]; default: string }
  | { type: "number"; min: number; max: number; default: number }
  | { type: "text" | "password"; placeholder?: string; default: string }
  | { type: "checkbox"; default: boolean }
  | { type: "target"; default: string } // conversion target, limited to what the file can become
);

// files: a list of files; pages: a thumbnail grid of every page.
export type PageMode = "organize" | "remove" | "extract" | "rotate";

export type Tool = {
  id: string;
  name: string;
  description: string;
  category: Category;
  icon: LucideIcon;
  accept: string; // hint for the file picker only; the server checks file contents
  pages?: PageMode;
  place?: "sign" | "annotate" | "redact"; // draw areas on pages
  form?: boolean; // fill the PDF's own form fields
  ai?: boolean; // sends the PDF's text to a third-party AI API
  fields?: Field[];
};

const pageSize = (d: string): Field[] => [
  { key: "page_size", label: "Page size", type: "select", default: d, choices: [["fit", "Same as image"], ["a4", "A4"], ["letter", "US Letter"]] },
  { key: "margin", label: "Margin", type: "select", default: "none", choices: [["none", "None"], ["small", "Small"], ["large", "Large"]] },
];

export const CATEGORIES = [
  "Organize", "Optimize", "Convert to PDF", "Convert from PDF", "Edit", "Security", "Intelligence",
] as const;
export type Category = (typeof CATEGORIES)[number];

const PDF = ".pdf,application/pdf";
const IMG = ".jpg,.jpeg,.png,image/jpeg,image/png";

export const TOOLS: Tool[] = [
  { id: "merge", name: "Merge PDF", description: "Combine PDFs in the order you set.", category: "Organize", icon: Combine, accept: PDF },
  { id: "split", name: "Split PDF", description: "By page ranges, every N pages, or one file per page.", category: "Organize", icon: Split, accept: PDF,
    fields: [
      { key: "mode", label: "Split", type: "select", default: "ranges", choices: [["ranges", "By page ranges"], ["every", "Every N pages"], ["each", "One file per page"]] },
      { key: "ranges", label: "Page ranges", type: "text", default: "", placeholder: "1-3, 4-7, 8-end", showIf: ["mode", "ranges"] },
      { key: "every", label: "Pages per file", type: "number", default: 2, min: 1, max: 2000, showIf: ["mode", "every"] },
    ] },
  { id: "remove", name: "Remove pages", description: "Pick pages to delete.", category: "Organize", icon: FileMinus, accept: PDF, pages: "remove" },
  { id: "extract", name: "Extract pages", description: "Pick pages to keep as a new PDF.", category: "Organize", icon: FileOutput, accept: PDF, pages: "extract" },
  { id: "organize", name: "Organize PDF", description: "Reorder, rotate, duplicate and insert blank pages.", category: "Organize", icon: LayoutGrid, accept: PDF, pages: "organize" },
  { id: "rotate", name: "Rotate PDF", description: "Rotate all or selected pages.", category: "Organize", icon: RotateCw, accept: PDF, pages: "rotate",
    fields: [{ key: "orientation", label: "Page orientation", type: "select", default: "keep", choices: [["keep", "Keep"], ["portrait", "Portrait"], ["landscape", "Landscape"]] }] },
  { id: "scan", name: "Scan to PDF", description: "Combine photos of pages into one PDF.", category: "Organize", icon: ScanLine, accept: IMG, fields: pageSize("a4") },

  { id: "compress", name: "Compress PDF", description: "Make the file smaller.", category: "Optimize", icon: Minimize2, accept: PDF,
    fields: [{ key: "level", label: "Compression", type: "select", default: "medium", choices: [["low", "Low, best quality"], ["medium", "Medium"], ["high", "High, smallest file"]] }] },
  { id: "repair", name: "Repair PDF", description: "Fix a damaged PDF.", category: "Optimize", icon: Wrench, accept: PDF },
  { id: "ocr", name: "OCR PDF", description: "Make scanned text searchable.", category: "Optimize", icon: ScanText, accept: PDF,
    fields: [{ key: "redo", label: "Redo pages that already have text", type: "checkbox", default: false }] },

  { id: "jpg-to-pdf", name: "JPG to PDF", description: "Images to a PDF.", category: "Convert to PDF", icon: Image, accept: IMG, fields: pageSize("fit") },
  { id: "word-to-pdf", name: "Word to PDF", description: "DOCX, ODT or RTF to PDF.", category: "Convert to PDF", icon: FileText, accept: ".docx,.odt,.rtf" },
  { id: "pptx-to-pdf", name: "PowerPoint to PDF", description: "PPTX slides to PDF.", category: "Convert to PDF", icon: Presentation, accept: ".pptx" },
  { id: "xlsx-to-pdf", name: "Excel to PDF", description: "XLSX sheets to PDF.", category: "Convert to PDF", icon: FileSpreadsheet, accept: ".xlsx" },
  { id: "html-to-pdf", name: "HTML to PDF", description: "An HTML file or zipped site to PDF.", category: "Convert to PDF", icon: Code, accept: ".html,.htm,.zip" },
  { id: "convert", name: "Convert document", description: "Between DOCX, ODT, RTF, TXT, MD, HTML, EPUB and PDF.", category: "Convert to PDF", icon: FileType, accept: ".docx,.odt,.rtf,.txt,.md,.html,.htm,.zip,.epub,.pdf,.pptx,.xlsx,.jpg,.jpeg,.png",
    fields: [{ key: "to", label: "Convert to", type: "target", default: "" }] },

  { id: "pdf-to-jpg", name: "PDF to JPG", description: "Each page as an image.", category: "Convert from PDF", icon: Images, accept: PDF,
    fields: [{ key: "dpi", label: "Image quality", type: "select", default: "150", choices: [["72", "Screen (72 dpi)"], ["150", "Standard (150 dpi)"], ["300", "Print (300 dpi)"]] }] },
  { id: "pdf-to-word", name: "PDF to Word", description: "Editable DOCX.", category: "Convert from PDF", icon: FileText, accept: PDF },
  { id: "pdf-to-pptx", name: "PDF to PowerPoint", description: "One slide per page.", category: "Convert from PDF", icon: Presentation, accept: PDF },
  { id: "pdf-to-xlsx", name: "PDF to Excel", description: "Tables to spreadsheet sheets.", category: "Convert from PDF", icon: Table, accept: PDF },
  { id: "pdf-to-pdfa", name: "PDF to PDF/A", description: "Archival format.", category: "Convert from PDF", icon: Archive, accept: PDF },
  { id: "pdf-to-md", name: "PDF to Markdown", description: "Text and headings as Markdown.", category: "Convert from PDF", icon: Hash, accept: PDF },

  { id: "page-numbers", name: "Page numbers", description: "Position, format and start number.", category: "Edit", icon: ListOrdered, accept: PDF,
    fields: [
      { key: "position", label: "Position", type: "select", default: "bottom-center", choices: [["bottom-center", "Bottom center"], ["bottom-left", "Bottom left"], ["bottom-right", "Bottom right"], ["top-center", "Top center"], ["top-left", "Top left"], ["top-right", "Top right"]] },
      { key: "format", label: "Format", type: "select", default: "n", choices: [["n", "1"], ["page_n", "Page 1"], ["n_of_total", "1 of 9"], ["page_n_of_total", "Page 1 of 9"]] },
      { key: "start", label: "First number", type: "number", default: 1, min: 0, max: 100000 },
      { key: "size", label: "Text size", type: "number", default: 10, min: 6, max: 36 },
    ] },
  { id: "watermark", name: "Watermark", description: "Text or image, with opacity and rotation.", category: "Edit", icon: Stamp, accept: `${PDF},${IMG}`,
    fields: [
      { key: "mode", label: "Watermark", type: "select", default: "text", choices: [["text", "Text"], ["image", "Image (add it as a second file)"]] },
      { key: "text", label: "Text", type: "text", default: "CONFIDENTIAL", showIf: ["mode", "text"] },
      { key: "opacity", label: "Opacity (%)", type: "number", default: 30, min: 5, max: 100 },
      { key: "rotation", label: "Rotation (degrees)", type: "number", default: 45, min: -180, max: 180 },
      { key: "size", label: "Size (% of page)", type: "number", default: 50, min: 5, max: 100 },
    ] },
  { id: "crop", name: "Crop PDF", description: "Trim page margins.", category: "Edit", icon: Crop, accept: PDF,
    fields: [{ key: "top", label: "Top (mm)", type: "number", default: 10, min: 0, max: 500 }, { key: "right", label: "Right (mm)", type: "number", default: 10, min: 0, max: 500 }, { key: "bottom", label: "Bottom (mm)", type: "number", default: 10, min: 0, max: 500 }, { key: "left", label: "Left (mm)", type: "number", default: 10, min: 0, max: 500 }] },
  { id: "annotate", name: "Annotate PDF", description: "Add text or images to pages.", category: "Edit", icon: MessageSquareText, accept: PDF, place: "annotate" },
  { id: "fill-form", name: "Fill form", description: "Fill in an existing PDF form.", category: "Edit", icon: TextCursorInput, accept: PDF, form: true },

  { id: "protect", name: "Protect PDF", description: "Add a password (AES-256).", category: "Security", icon: Lock, accept: PDF,
    fields: [
      { key: "password", label: "Password (6 characters or more)", type: "password", default: "" },
      { key: "confirm", label: "Repeat password", type: "password", default: "", local: true, matches: "password" },
    ] },
  { id: "unlock", name: "Unlock PDF", description: "Remove a password you know.", category: "Security", icon: LockOpen, accept: PDF,
    fields: [{ key: "password", label: "Password", type: "password", default: "" }] },
  { id: "sign", name: "Sign PDF", description: "Draw, type or upload a signature.", category: "Security", icon: Signature, accept: PDF, place: "sign" },
  { id: "redact", name: "Redact PDF", description: "Permanently remove text.", category: "Security", icon: EyeOff, accept: PDF, place: "redact" },
  { id: "compare", name: "Compare PDF", description: "Show differences between two PDFs.", category: "Security", icon: GitCompare, accept: PDF },

  { id: "summarize", name: "Summarize", description: "Short summary of a PDF.", category: "Intelligence", icon: ListCollapse, accept: PDF, ai: true,
    fields: [{ key: "length", label: "Length", type: "select", default: "medium", choices: [["short", "Short (bullet points)"], ["medium", "Medium"], ["long", "Long, with headings"]] }] },
  { id: "translate", name: "Translate", description: "Translate the text of a PDF.", category: "Intelligence", icon: Languages, accept: PDF, ai: true,
    fields: [{ key: "language", label: "Translate to", type: "text", default: "", placeholder: "e.g. Spanish" }] },
  { id: "ai-markdown", name: "Markdown with AI", description: "Cleaner Markdown than the standard converter.", category: "Intelligence", icon: Hash, accept: PDF, ai: true },
];

export const FORMAT_NAMES: Record<string, string> = {
  pdf: "PDF", pdfa: "PDF/A", docx: "Word (DOCX)", odt: "OpenDocument (ODT)", rtf: "Rich Text (RTF)",
  txt: "Plain text", md: "Markdown", html: "HTML", epub: "EPUB", jpg: "JPG", png: "PNG",
  pptx: "PowerPoint (PPTX)", xlsx: "Excel (XLSX)",
};

const KIND_BY_EXT: Record<string, string> = {
  docx: "docx", odt: "odt", rtf: "rtf", txt: "txt", md: "md", markdown: "md", html: "html", htm: "html",
  zip: "htmlzip", epub: "epub", pdf: "pdf", jpg: "jpg", jpeg: "jpg", png: "png", pptx: "pptx", xlsx: "xlsx",
};

/** Best guess from the name, for the UI only. The server decides from the file's contents. */
export const kindOf = (name: string) => KIND_BY_EXT[name.split(".").pop()?.toLowerCase() ?? ""];
