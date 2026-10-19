import React from "react";

/** Inline formatting the AI is allowed to use: **bold** and `code`. Anything else is shown
 * as plain text (never as HTML), so a model's output can't inject markup. */
export function renderInline(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g).map((part, i) => {
    if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) return <code key={i} className="inline-code">{part.slice(1, -1)}</code>;
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

export const InlineText: React.FC<{ text: string }> = ({ text }) => <>{renderInline(text)}</>;

type Block =
  | { kind: "p"; text: string }
  | { kind: "code"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] };

function parseBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "p", text: paragraph.join("\n") });
    paragraph = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim().startsWith("```")) {
      flush();
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) code.push(lines[i++]);
      blocks.push({ kind: "code", text: code.join("\n") });
      continue;
    }
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (bullet || numbered) {
      flush();
      const last = blocks[blocks.length - 1];
      const item = (bullet ?? numbered)![1];
      if (bullet) {
        if (last?.kind === "ul") last.items.push(item);
        else blocks.push({ kind: "ul", items: [item] });
      } else if (last?.kind === "ol") last.items.push(item);
      else blocks.push({ kind: "ol", items: [item] });
      continue;
    }
    if (!line.trim()) {
      flush();
      continue;
    }
    paragraph.push(line.replace(/^#{1,4}\s+/, ""));
  }
  flush();
  return blocks;
}

/** The small subset of Markdown the tutor writes: paragraphs, bullet/numbered lists and
 * fenced code blocks, with **bold** and `code` inline. */
export const RichText: React.FC<{ text: string }> = ({ text }) => (
  <div className="rich-text">
    {parseBlocks(text).map((block, i) => {
      if (block.kind === "code") return <pre key={i} className="rich-code">{block.text}</pre>;
      if (block.kind === "ul") return <ul key={i}>{block.items.map((item, j) => <li key={j}>{renderInline(item)}</li>)}</ul>;
      if (block.kind === "ol") return <ol key={i}>{block.items.map((item, j) => <li key={j}>{renderInline(item)}</li>)}</ol>;
      return <p key={i}>{renderInline(block.text)}</p>;
    })}
  </div>
);
