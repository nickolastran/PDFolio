import { expect, test } from "@playwright/test";

// A tiny PDF with one page per text; MuPDF and pdf.js tolerate the missing xref table.
const pdf = (...texts: string[]) => {
  const kids = texts.map((_, i) => `${3 + i * 2} 0 R`).join(" ");
  const pages = texts.map((t, i) => {
    const content = `BT /F1 12 Tf 20 100 Td (${t}) Tj ET`;
    return `${3 + i * 2} 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 300]/Contents ${4 + i * 2} 0 R>>endobj\n` +
      `${4 + i * 2} 0 obj<</Length ${content.length}>>stream\n${content}\nendstream endobj\n`;
  });
  return Buffer.from(`%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[${kids}]/Count ${texts.length}>>endobj\n` +
    pages.join("") + "trailer<</Root 1 0 R>>\n%%EOF");
};

async function runAndDownload(page: import("@playwright/test").Page, button: string) {
  await page.getByRole("button", { name: button, exact: true }).click();
  await expect(page.getByText("Ready")).toBeVisible({ timeout: 30_000 });
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download" }).click();
  return (await download).suggestedFilename();
}

test("merge flow: upload, reorder with keyboard buttons, merge, download", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /Merge PDF/ }).click();
  await expect(page.getByRole("heading", { name: "Merge PDF" })).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles([
    { name: "alpha.pdf", mimeType: "application/pdf", buffer: pdf("Alpha") },
    { name: "beta.pdf", mimeType: "application/pdf", buffer: pdf("Beta") },
  ]);
  await page.getByRole("button", { name: "Move beta.pdf up" }).click();
  await expect(page.getByRole("list", { name: "Files, in order" }).getByRole("listitem").first()).toContainText("beta.pdf");

  // Preview an input before merging.
  await page.getByRole("button", { name: "Preview alpha.pdf" }).click();
  const viewer = page.getByRole("dialog", { name: "Preview of alpha.pdf" });
  await expect(viewer.getByRole("img", { name: "Page 1" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(viewer).toBeHidden();

  await page.getByRole("button", { name: "Merge PDF", exact: true }).click();
  await expect(page.getByText("Ready")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByLabel("File name")).toHaveValue("beta-merge"); // first file after reorder names the output

  // Preview the merged result: both pages, in the new order.
  await page.getByRole("button", { name: "Preview", exact: true }).click();
  const result = page.getByRole("dialog");
  await expect(result.getByText("1 / 2")).toBeVisible();
  await expect(result.getByRole("img", { name: "Page 2" })).toBeVisible();
  await result.getByRole("button", { name: "Close preview" }).click();

  await page.getByLabel("File name").fill("Combined report");
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download" }).click();
  expect((await download).suggestedFilename()).toBe("Combined report.pdf");
  await expect(page.getByText("Files deleted from the server")).toBeVisible();
});

test("theme toggle switches and persists", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await page.getByRole("button", { name: "Switch to black theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("button", { name: "Switch to white theme" })).toBeVisible();
});

test("footer links open in a new tab", async ({ page }) => {
  await page.goto("/");
  const footer = page.getByRole("contentinfo");
  await expect(footer).toContainText(`© ${new Date().getFullYear()} Nickolas Tran`);
  for (const [name, href] of [["Source on GitHub", "https://github.com/nickolastran"], ["LinkedIn", "https://www.linkedin.com/in/nickolas-tran/"], ["Website", "https://nickolastran.vercel.app/"]]) {
    const link = footer.getByRole("link", { name });
    await expect(link).toHaveAttribute("href", href);
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noreferrer");
  }
});

test("no requests leave the site", async ({ page }) => {
  const external: string[] = [];
  page.on("request", (r) => {
    if (!r.url().startsWith("http://localhost:8000")) external.push(r.url());
  });
  await page.goto("/");
  await page.goto("/merge");
  expect(external).toEqual([]);
});

test("organize: thumbnails render, rotate and delete a page with buttons", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/organize");
  await page.locator('input[type="file"]').setInputFiles({ name: "doc.pdf", mimeType: "application/pdf", buffer: pdf("One", "Two", "Three") });
  const pages = page.getByRole("list", { name: "Pages" }).getByRole("listitem");
  await expect(pages).toHaveCount(3);
  await expect(pages.locator("img")).toHaveCount(3);   // rendered in the browser by pdf.js

  await page.getByRole("button", { name: "Rotate page 1 right" }).click();
  await expect(pages.first()).toContainText("90°");
  await page.getByRole("button", { name: "Delete page 2" }).click();
  await expect(pages).toHaveCount(2);

  // Keyboard reordering: focus the handle, Space to lift, arrow to move, Space to drop.
  await page.getByRole("button", { name: "Drag page 2" }).focus();
  for (const key of ["Space", "ArrowLeft", "Space"]) {
    await page.keyboard.press(key);
    await page.waitForTimeout(150); // dnd-kit measures positions between steps
  }
  await expect(pages.first()).not.toContainText("90°");

  expect(await runAndDownload(page, "Organize PDF")).toBe("doc-organize.pdf");
  expect(errors).toEqual([]);
});

test("remove pages: select in the grid", async ({ page }) => {
  await page.goto("/remove");
  await page.locator('input[type="file"]').setInputFiles({ name: "doc.pdf", mimeType: "application/pdf", buffer: pdf("One", "Two") });
  const run = page.getByRole("button", { name: "Remove pages", exact: true });
  await expect(run).toBeDisabled();
  await page.getByRole("button", { name: "Page 2" }).click();
  await expect(page.getByText("1 of 2 selected")).toBeVisible();
  expect(await runAndDownload(page, "Remove pages")).toBe("doc-remove.pdf");
});

test("split: options panel", async ({ page }) => {
  await page.goto("/split");
  await page.locator('input[type="file"]').setInputFiles({ name: "doc.pdf", mimeType: "application/pdf", buffer: pdf("1", "2", "3") });
  await page.getByLabel("Page ranges").fill("1, 2-end");
  expect(await runAndDownload(page, "Split PDF")).toBe("doc-split.zip");
});

test("convert: impossible targets are disabled", async ({ page }) => {
  await page.goto("/convert");
  await expect(page.getByLabel("Convert to")).toBeDisabled();
  await page.locator('input[type="file"]').setInputFiles({ name: "notes.md", mimeType: "text/markdown", buffer: Buffer.from("# Notes\n\nHello") });
  const target = page.getByLabel("Convert to");
  await expect(target.locator('option[value="xlsx"]')).toBeDisabled();
  await expect(target.locator('option[value="md"]')).toBeDisabled();
  await expect(target.locator('option[value="pdfa"]')).toBeEnabled();
  await expect(page.getByRole("button", { name: "Convert document", exact: true })).toBeDisabled();
  await target.selectOption("pdf");
  expect(await runAndDownload(page, "Convert document")).toBe("notes.pdf");
});

const onePage = { name: "doc.pdf", mimeType: "application/pdf", buffer: pdf("Hello") };

test("sign: typed signature, placed with the keyboard-friendly button", async ({ page }) => {
  await page.goto("/sign");
  await page.locator('input[type="file"]').first().setInputFiles(onePage);
  await page.getByRole("tab", { name: "Type" }).click();
  await page.getByLabel("Type your name").fill("Ada Lovelace");
  await page.getByRole("button", { name: "Add signature" }).click();
  const box = page.getByRole("button", { name: /^Signature 1, page 1/ });
  await box.focus();
  await page.keyboard.press("ArrowDown");
  expect(await runAndDownload(page, "Sign PDF")).toBe("doc-sign.pdf");
});

test("annotate: drag a box with the mouse and write a note", async ({ page }) => {
  await page.goto("/annotate");
  await page.locator('input[type="file"]').setInputFiles(onePage);
  const img = page.getByRole("img", { name: "Page 1" });
  const r = (await img.boundingBox())!;
  await page.mouse.move(r.x + 40, r.y + 40);
  await page.mouse.down();
  await page.mouse.move(r.x + 200, r.y + 90, { steps: 5 });
  await page.mouse.up();
  const run = page.getByRole("button", { name: "Annotate PDF", exact: true });
  await expect(run).toBeDisabled(); // note text still empty
  await page.getByLabel("Note 1, page 1", { exact: true }).fill("Looks good");
  expect(await runAndDownload(page, "Annotate PDF")).toBe("doc-annotate.pdf");
});

test("redact: words to remove", async ({ page }) => {
  await page.goto("/redact");
  await page.locator('input[type="file"]').setInputFiles(onePage);
  await page.getByLabel("Words to remove everywhere").fill("Hello");
  expect(await runAndDownload(page, "Redact PDF")).toBe("doc-redact.pdf");
});

test("protect: passwords must match", async ({ page }) => {
  await page.goto("/protect");
  await page.locator('input[type="file"]').setInputFiles(onePage);
  await page.getByLabel("Password (6 characters or more)").fill("correct horse");
  await page.getByLabel("Repeat password").fill("correct hose");
  await expect(page.getByText("Passwords don't match.")).toBeVisible();
  await page.getByLabel("Repeat password").fill("correct horse");
  expect(await runAndDownload(page, "Protect PDF")).toBe("doc-protect.pdf");
});
