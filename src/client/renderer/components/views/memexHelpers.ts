/** Strip YAML frontmatter from markdown text. */
export function stripFrontmatter(md: string): string {
  if (!md.startsWith("---")) return md;
  const end = md.indexOf("---", 3);
  if (end === -1) return md;
  return md.slice(end + 3).trimStart();
}

/** Parse YAML frontmatter into a simple key-value map. */
export function parseFrontmatter(md: string): Record<string, string> {
  if (!md.startsWith("---")) return {};
  const end = md.indexOf("---", 3);
  if (end === -1) return {};
  const fm: Record<string, string> = {};
  for (const line of md.slice(3, end).trim().split("\n")) {
    const idx = line.indexOf(":");
    if (idx > 0) fm[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  return fm;
}

/** Replace [[wiki-links]] with markdown links using a custom scheme. */
export function processWikiLinks(md: string): string {
  return md.replace(/\[\[([^\]]+)\]\]/g, (_, name: string) => {
    const slug = name
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9\/]/g, "-")
      .replace(/-+/g, "-")
      .replace(/(^-|-$)/g, "");
    return `[${name}](wiki:${slug})`;
  });
}

/** Replace inline [c:0.X] confidence tags with styled HTML spans. */
export function processInlineConfidence(md: string): string {
  return md.replace(/\[c:((?:0\.\d+|1\.0?))\]/g, (_, val: string) => {
    const c = parseFloat(val);
    const color = confidenceColor(c);
    const pct = (c * 100).toFixed(0);
    return `<span class="memex-inline-confidence" style="color:${color};border-color:${color}33;background:${color}12" title="${pct}% — ${confidenceLabel(c)}">${pct}%</span>`;
  });
}

/** Confidence badge color: red → yellow → green. */
export function confidenceColor(c: number): string {
  if (c < 0.3) return "#C9594B";
  if (c < 0.6) return "#D4A843";
  if (c < 0.8) return "#8BB97E";
  return "#5DA34E";
}

export function confidenceLabel(c: number): string {
  if (c < 0.3) return "speculative";
  if (c < 0.6) return "probable";
  if (c < 0.8) return "confident";
  return "certain";
}
