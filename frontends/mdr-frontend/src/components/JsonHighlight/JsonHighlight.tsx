import { useMemo } from "react";
import "./JsonHighlight.css";

// Dependency-free JSON syntax highlighting. The export payload is untrusted, so
// HTML is escaped first, then tokens are wrapped in themed spans. Avoids a
// syntax-highlighter dependency and keeps the (CSP-strict) bundle self-contained.
function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

const TOKEN = /("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(?:\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

function highlight(json: string): string {
  return escapeHtml(json).replace(TOKEN, (match) => {
    let cls = "tok-num";
    if (match.startsWith('"')) {
      cls = match.trimEnd().endsWith(":") ? "tok-key" : "tok-str";
    } else if (match === "true" || match === "false") {
      cls = "tok-bool";
    } else if (match === "null") {
      cls = "tok-null";
    }
    return `<span class="${cls}">${match}</span>`;
  });
}

/** Pretty-print + colorize a value as JSON. */
export default function JsonHighlight({ value }: { value: unknown }) {
  const html = useMemo(() => highlight(JSON.stringify(value, null, 2)), [value]);
  return (
    <pre className="json-highlight">
      <code dangerouslySetInnerHTML={{ __html: html }} />
    </pre>
  );
}
