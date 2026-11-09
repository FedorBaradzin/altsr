// Минимальный безопасный markdown → HTML (заголовки, списки, ссылки, жирный, абзацы).
function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function mdToHtml(md: string): string {
  const lines = md.replace(/\r/g, "").split("\n");
  const out: string[] = [];
  let inList = false;
  const closeList = () => { if (inList) { out.push("</ul>"); inList = false; } };

  const inline = (t: string) =>
    esc(t)
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, txt, url) =>
        `<a href="${encodeURI(url)}" target="_blank" rel="noopener nofollow">${txt}</a>`)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/_([^_]+)_/g, "<em>$1</em>");

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) { closeList(); continue; }
    if (line.startsWith("## ")) { closeList(); out.push(`<h2>${inline(line.slice(3))}</h2>`); }
    else if (line.startsWith("# ")) { closeList(); out.push(`<h1>${inline(line.slice(2))}</h1>`); }
    else if (line.startsWith("- ")) {
      if (!inList) { out.push("<ul>"); inList = true; }
      out.push(`<li>${inline(line.slice(2))}</li>`);
    } else { closeList(); out.push(`<p>${inline(line)}</p>`); }
  }
  closeList();
  return out.join("\n");
}
