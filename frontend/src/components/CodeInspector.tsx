import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  Code2,
  FileCode,
  FolderTree,
  Info,
  MessageSquare,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import {
  ChatMessageContext,
  errorMessage,
  explainLines,
  FileDetailsResponse,
  LearningStep,
  LinesExplanation,
  LineSection,
  MAX_EXPLAIN_LINES,
  RepoFile,
} from "../api/client";
import { InteractiveQuiz } from "./InteractiveQuiz";
import { InlineText } from "./RichText";

interface CodeInspectorProps {
  repoId: string;
  files: RepoFile[];
  learningPath: LearningStep[];
  activePath: string | null;
  fileDetails: FileDetailsResponse | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onOpenFile: (path: string) => void;
  onBackToFlowchart: () => void;
  onOpenDiscussion: (context: ChatMessageContext) => void;
  onProgress: () => void;
}

// --- tiny Python highlighter (no dependency); tracks triple-quoted strings across lines ---

const KEYWORDS =
  "def|class|import|from|as|return|if|elif|else|for|while|try|except|finally|with|raise|yield|lambda|pass|break|continue|in|is|not|and|or|None|True|False|async|await|global|nonlocal|assert|del";
const TOKEN = new RegExp(
  `(#.*$)|("""|''')|("(?:[^"\\\\]|\\\\.)*"|'(?:[^'\\\\]|\\\\.)*')|(\\b\\d+(?:\\.\\d+)?\\b)|(\\b(?:${KEYWORDS})\\b)|(@\\w+(?:\\.\\w+)*)`,
  "g"
);

function highlight(lines: string[], python: boolean): React.ReactNode[][] {
  if (!python) return lines.map((line) => [line]);
  let openTriple: string | null = null;
  return lines.map((line) => {
    const out: React.ReactNode[] = [];
    let pos = 0;
    const push = (text: string, cls?: string) => {
      if (!text) return;
      out.push(cls ? <span key={out.length} className={cls}>{text}</span> : <React.Fragment key={out.length}>{text}</React.Fragment>);
    };

    if (openTriple) {
      const close = line.indexOf(openTriple);
      if (close === -1) {
        push(line, "tok-string");
        return out;
      }
      push(line.slice(0, close + 3), "tok-string");
      pos = close + 3;
      openTriple = null;
    }

    TOKEN.lastIndex = pos;
    let m: RegExpExecArray | null;
    while ((m = TOKEN.exec(line)) !== null) {
      push(line.slice(pos, m.index));
      pos = m.index + m[0].length;
      if (m[1]) push(m[1], "tok-comment");
      else if (m[2]) {
        const close = line.indexOf(m[2], pos);
        if (close === -1) {
          push(line.slice(m.index), "tok-string");
          openTriple = m[2];
          return out;
        }
        push(line.slice(m.index, close + 3), "tok-string");
        pos = close + 3;
        TOKEN.lastIndex = pos;
      } else if (m[3]) push(m[3], "tok-string");
      else if (m[4]) push(m[4], "tok-number");
      else if (m[5]) push(m[5], "tok-keyword");
      else if (m[6]) push(m[6], "tok-decorator");
    }
    push(line.slice(pos));
    return out;
  });
}

// --- file browser -------------------------------------------------------------------------

const FileBrowser: React.FC<{
  files: RepoFile[];
  activePath: string | null;
  onOpenFile: (path: string) => void;
}> = ({ files, activePath, onOpenFile }) => {
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);

  const hasOther = files.some((f) => f.kind !== "python");
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const visible = files.filter((f) => (showAll || q || f.kind === "python" || f.path === activePath) && (!q || f.path.toLowerCase().includes(q)));
    const byFolder = new Map<string, RepoFile[]>();
    for (const f of visible) {
      const cut = f.path.lastIndexOf("/");
      const folder = cut === -1 ? "" : f.path.slice(0, cut);
      if (!byFolder.has(folder)) byFolder.set(folder, []);
      byFolder.get(folder)!.push(f);
    }
    return [...byFolder.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [files, query, showAll, activePath]);

  return (
    <aside className="file-browser" aria-label="Repository files">
      <div className="file-browser-head">
        <FolderTree size={15} color="var(--accent)" />
        <strong>Files</strong>
        <span className="muted-count">{files.filter((f) => f.kind === "python").length} Python</span>
      </div>
      <div className="file-search">
        <Search size={13} />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a file…" aria-label="Find a file" />
        {query && (
          <button onClick={() => setQuery("")} aria-label="Clear search"><X size={12} /></button>
        )}
      </div>
      <div className="file-list">
        {groups.length === 0 && <p className="file-empty">No files match.</p>}
        {groups.map(([folder, entries]) => (
          <div key={folder || "."}>
            <div className="file-folder" title={folder || "(repository root)"}>{folder || "(root)"}</div>
            {entries.map((f) => {
              const name = f.path.slice(f.path.lastIndexOf("/") + 1);
              const mastered = f.questions > 0 && f.solved === f.questions;
              return (
                <button
                  key={f.path}
                  className={`file-row ${f.path === activePath ? "active" : ""}`}
                  onClick={() => onOpenFile(f.path)}
                  title={`${f.path} · ${f.lines} lines${f.questions ? ` · ${f.solved}/${f.questions} questions solved` : ""}`}
                >
                  <span className={`file-dot ${mastered ? "mastered" : f.explored ? "explored" : ""}`}>
                    {mastered && <Check size={10} strokeWidth={3} />}
                  </span>
                  <span className="file-name">{name}</span>
                  {f.questions > 0 && !mastered && <span className="file-score">{f.solved}/{f.questions}</span>}
                </button>
              );
            })}
          </div>
        ))}
      </div>
      <div className="file-legend">
        <span><span className="file-dot explored" /> opened</span>
        <span><span className="file-dot mastered"><Check size={10} strokeWidth={3} /></span> quiz solved</span>
        {hasOther && (
          <button className="link-btn" onClick={() => setShowAll((v) => !v)}>
            {showAll ? "Python only" : "Show all files"}
          </button>
        )}
      </div>
    </aside>
  );
};

// --- the inspector ------------------------------------------------------------------------

interface Selection {
  start: number;
  end: number;
}

export const CodeInspector: React.FC<CodeInspectorProps> = ({
  repoId,
  files,
  learningPath,
  activePath,
  fileDetails,
  loading,
  error,
  onRetry,
  onOpenFile,
  onBackToFlowchart,
  onOpenDiscussion,
  onProgress,
}) => {
  const [activeIndex, setActiveIndex] = useState(0);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [explained, setExplained] = useState<LinesExplanation | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);
  const [anchor, setAnchor] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const explainedRef = useRef<HTMLDivElement>(null);
  const explainRequest = useRef(0);

  const lines = useMemo(() => (fileDetails ? fileDetails.content.split("\n") : []), [fileDetails]);
  const isPython = !!fileDetails && fileDetails.file_path.endsWith(".py");
  const highlighted = useMemo(() => highlight(lines, isPython), [lines, isPython]);
  const sections = fileDetails?.line_sections ?? [];
  const active: LineSection | undefined = sections[activeIndex];

  useEffect(() => {
    setActiveIndex(0);
    setSelection(null);
    setExplained(null);
    setExplainError(null);
    setAnchor(null);
    explainRequest.current += 1;
  }, [fileDetails?.file_path]);

  const scrollToLine = useCallback((line: number) => {
    const box = scrollRef.current;
    const row = box?.querySelector<HTMLElement>(`[data-line="${line}"]`);
    if (box && row) box.scrollTo({ top: row.offsetTop - box.clientHeight / 3, behavior: "smooth" });
  }, []);

  // Scroll only the code panel to the active range (scrollIntoView would also scroll the page).
  useEffect(() => {
    if (active) scrollToLine(active.start_line);
  }, [active, scrollToLine]);

  /** Line range covered by the browser's text selection inside the code panel, if any. */
  function selectionFromDom(): Selection | null {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !scrollRef.current) return null;
    const lineOf = (node: Node | null) => {
      const el = node instanceof Element ? node : node?.parentElement;
      const row = el?.closest<HTMLElement>("[data-line]");
      return row && scrollRef.current!.contains(row) ? Number(row.dataset.line) : null;
    };
    const a = lineOf(sel.anchorNode);
    const b = lineOf(sel.focusNode);
    if (a === null || b === null) return null;
    return { start: Math.min(a, b), end: Math.max(a, b) };
  }

  function handleMouseUp() {
    const picked = selectionFromDom();
    if (picked) {
      setSelection(picked);
      setAnchor(picked.start);
    }
  }

  function handleGutterClick(n: number, shift: boolean) {
    window.getSelection()?.removeAllRanges();
    if (shift && anchor !== null) {
      setSelection({ start: Math.min(anchor, n), end: Math.max(anchor, n) });
    } else {
      setAnchor(n);
      setSelection({ start: n, end: n });
    }
  }

  async function explain(range: Selection) {
    if (!fileDetails) return;
    const end = Math.min(range.end, range.start + MAX_EXPLAIN_LINES - 1);
    const req = ++explainRequest.current;
    setExplaining(true);
    setExplainError(null);
    try {
      const result = await explainLines(repoId, fileDetails.file_path, range.start, end);
      if (req !== explainRequest.current) return;
      setExplained(result);
      requestAnimationFrame(() => explainedRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
    } catch (err) {
      if (req === explainRequest.current) setExplainError(errorMessage(err, "Couldn't explain those lines. Please try again."));
    } finally {
      if (req === explainRequest.current) setExplaining(false);
    }
  }

  function askAbout(range: Selection, title?: string) {
    onOpenDiscussion({
      context_type: "file_explainer",
      file_path: fileDetails!.file_path,
      selection: `lines ${range.start}-${range.end}${title ? `: ${title}` : ""}`,
      start_line: range.start,
      end_line: range.end,
    });
  }

  const browser = <FileBrowser files={files} activePath={activePath} onOpenFile={onOpenFile} />;

  let body: React.ReactNode;
  if (loading) {
    body = (
      <div className="flowchart-container center-state">
        <Code2 size={36} color="var(--accent)" style={{ animation: "pulse 1.5s infinite", margin: "0 auto 1rem" }} />
        <h3>Reading {activePath ?? "the code"} and writing your walkthrough…</h3>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.5rem" }}>
          Breaking the file into sections and preparing questions. This usually takes 5–20 seconds; the next time you open this file it&apos;s instant.
        </p>
      </div>
    );
  } else if (error) {
    body = (
      <div className="flowchart-container center-state">
        <AlertTriangle size={30} color="var(--warning)" style={{ margin: "0 auto 0.75rem" }} />
        <p className="error-text">{error}</p>
        <div style={{ display: "flex", gap: "0.6rem", justifyContent: "center", marginTop: "1rem" }}>
          <button onClick={onRetry} className="btn-primary"><RefreshCw size={15} /><span>Try again</span></button>
        </div>
      </div>
    );
  } else if (!fileDetails) {
    body = (
      <div className="flowchart-container">
        <h3 style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <BookOpen size={20} color="var(--accent)" />
          Pick a file to walk through
        </h3>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", margin: "0.35rem 0 1rem" }}>
          Choose any file from the list on the left. You&apos;ll get a section-by-section explanation next to the code, you can
          select any lines to have them explained, and a short quiz at the end checks it stuck.
        </p>
        {learningPath.length > 0 && (
          <>
            <h4 className="rail-heading">Suggested reading order</h4>
            <ol className="path-list">
              {learningPath.map((step, i) => (
                <li key={step.file_path}>
                  <button className="path-step" onClick={() => onOpenFile(step.file_path)}>
                    <span className="path-number">{i + 1}</span>
                    <span>
                      <strong>{step.title}</strong> <code className="inline-code">{step.file_path}</code>
                      <span className="path-why"><InlineText text={step.why} /></span>
                    </span>
                    <ChevronRight size={16} />
                  </button>
                </li>
              ))}
            </ol>
          </>
        )}
        <button onClick={onBackToFlowchart} className="btn-secondary" style={{ marginTop: "1rem" }}>
          <ArrowLeft size={15} />
          <span>Or pick a module from the flowchart</span>
        </button>
      </div>
    );
  } else {
    const sectionForLine = (n: number) => sections.findIndex((s) => n >= s.start_line && n <= s.end_line);
    const last = sections.length - 1;
    const selCount = selection ? selection.end - selection.start + 1 : 0;
    const pathIndex = learningPath.findIndex((s) => s.file_path === fileDetails.file_path);
    const nextStep = pathIndex >= 0 ? learningPath[pathIndex + 1] : undefined;
    const neighbours = [...(fileDetails.imports ?? []).map((p) => ({ p, rel: "imports" })), ...(fileDetails.imported_by ?? []).map((p) => ({ p, rel: "used by" }))];

    body = (
      <div style={{ minWidth: 0 }}>
        {fileDetails.notice && (
          <div className="notice-banner">
            <AlertTriangle size={16} />
            <span>{fileDetails.notice}</span>
            {fileDetails.degraded && (
              <button onClick={onRetry} className="btn-secondary" style={{ marginLeft: "auto", fontSize: "0.78rem", padding: "0.25rem 0.6rem" }}>
                <RefreshCw size={13} /> Retry
              </button>
            )}
          </div>
        )}

        <div className="code-inspector-layout">
          <div className="code-viewer-panel">
            <div className="code-viewer-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
                <FileCode size={16} color="var(--accent)" />
                <span className="ellipsis">{fileDetails.file_path}</span>
              </div>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                {fileDetails.total_lines} lines{fileDetails.truncated ? " (truncated)" : ""}
              </span>
            </div>

            {selection ? (
              <div className="selection-bar">
                <span>
                  {selCount === 1 ? `Line ${selection.start}` : `Lines ${selection.start}–${selection.end}`} selected
                  {selCount > MAX_EXPLAIN_LINES && ` (the first ${MAX_EXPLAIN_LINES} will be explained)`}
                </span>
                <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                  <button className="btn-primary" onClick={() => explain(selection)} disabled={explaining}>
                    <Sparkles size={13} />
                    <span>{explaining ? "Explaining…" : selCount === 1 ? "Explain this line" : "Explain selected lines"}</span>
                  </button>
                  <button className="btn-secondary" onClick={() => askAbout(selection)}>
                    <MessageSquare size={13} />
                    <span>Ask the tutor</span>
                  </button>
                  <button className="btn-secondary" onClick={() => { setSelection(null); window.getSelection()?.removeAllRanges(); }} aria-label="Clear selection">
                    <X size={13} />
                  </button>
                </div>
              </div>
            ) : (
              <div className="selection-bar idle">
                Tip: select any code with the mouse (or click a line number, then Shift-click another) to have exactly those lines explained.
              </div>
            )}

            <div className="code-scroll-area" ref={scrollRef} onMouseUp={handleMouseUp}>
              {highlighted.map((tokens, idx) => {
                const n = idx + 1;
                const inSection = !!active && n >= active.start_line && n <= active.end_line;
                const inSelection = !!selection && n >= selection.start && n <= selection.end;
                return (
                  <div
                    key={idx}
                    data-line={n}
                    className={`code-line-row ${inSection ? "highlighted" : ""} ${inSelection ? "selected" : ""}`}
                    onClick={() => {
                      if (window.getSelection()?.isCollapsed === false) return; // a drag-selection, not a click
                      const s = sectionForLine(n);
                      if (s >= 0) setActiveIndex(s);
                    }}
                  >
                    <span
                      className="line-number"
                      role="button"
                      title="Click to select this line; Shift-click to select a range"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleGutterClick(n, e.shiftKey);
                      }}
                    >
                      {n}
                    </span>
                    <span className="line-content">{tokens.length ? tokens : " "}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="explanations-rail">
            <div className="section-explain-card overview-card">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.4rem" }}>
                <Info size={16} color="var(--accent)" />
                <strong style={{ fontSize: "0.95rem" }}>What this file is for</strong>
              </div>
              <p style={{ fontSize: "0.86rem", color: "var(--text-primary)" }}><InlineText text={fileDetails.overview} /></p>
              {neighbours.length > 0 && (
                <div className="chip-row" style={{ marginTop: "0.6rem" }}>
                  {neighbours.slice(0, 8).map(({ p, rel }) => (
                    <button key={rel + p} className="file-micro-chip as-button" onClick={() => onOpenFile(p)} title={`Open ${p}`}>
                      <span style={{ opacity: 0.65 }}>{rel}</span> {p.slice(p.lastIndexOf("/") + 1)}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {(fileDetails.key_concepts ?? []).length > 0 && (
              <div className="section-explain-card glossary-card">
                <strong style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>Ideas you&apos;ll meet in this file</strong>
                <dl>
                  {fileDetails.key_concepts!.map((c) => (
                    <div key={c.term}>
                      <dt>{c.term}</dt>
                      <dd><InlineText text={c.meaning} /></dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}

            {(explained || explaining || explainError) && (
              <div className="section-explain-card explained-card" ref={explainedRef}>
                <div className="section-header-row">
                  <h5 style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <Sparkles size={14} color="var(--accent)" />
                    {explained ? `Lines ${explained.start_line}–${explained.end_line}, line by line` : "Explaining your selection…"}
                  </h5>
                  <button className="btn-secondary" style={{ padding: "0.15rem 0.35rem" }} onClick={() => { setExplained(null); setExplainError(null); }} aria-label="Close explanation">
                    <X size={12} />
                  </button>
                </div>
                {explaining && !explained && <p className="hint-text">Reading those lines…</p>}
                {explainError && <p className="error-text" style={{ fontSize: "0.84rem" }}>{explainError}</p>}
                {explained && (
                  <>
                    <p style={{ color: "var(--text-primary)" }}><InlineText text={explained.summary} /></p>
                    <ul className="line-notes">
                      {explained.notes.map((note, i) => (
                        <li key={i}>
                          <button
                            className="line-range-pill as-button"
                            onClick={() => {
                              setSelection({ start: note.start_line, end: note.end_line });
                              scrollToLine(note.start_line);
                            }}
                          >
                            {note.start_line === note.end_line ? `L${note.start_line}` : `L${note.start_line}–${note.end_line}`}
                          </button>
                          <span><InlineText text={note.explanation} /></span>
                        </li>
                      ))}
                    </ul>
                    {explained.concepts.length > 0 && (
                      <dl className="mini-glossary">
                        {explained.concepts.map((c) => (
                          <div key={c.term}>
                            <dt>{c.term}</dt>
                            <dd><InlineText text={c.meaning} /></dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    <button className="link-btn" style={{ marginTop: "0.5rem" }} onClick={() => askAbout({ start: explained.start_line, end: explained.end_line })}>
                      <MessageSquare size={13} /> Still unclear? Ask the tutor about these lines
                    </button>
                  </>
                )}
              </div>
            )}

            <div className="rail-heading-row">
              <h4 className="rail-heading">Walkthrough</h4>
              {sections.length > 0 && (
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                    {activeIndex + 1} / {sections.length}
                  </span>
                  <button onClick={() => setActiveIndex((i) => Math.max(0, i - 1))} disabled={activeIndex === 0} className="btn-secondary" style={{ padding: "0.2rem 0.4rem" }} title="Previous section">
                    <ChevronLeft size={15} />
                  </button>
                  <button onClick={() => setActiveIndex((i) => Math.min(last, i + 1))} disabled={activeIndex === last} className="btn-secondary" style={{ padding: "0.2rem 0.4rem" }} title="Next section">
                    <ChevronRight size={15} />
                  </button>
                </div>
              )}
            </div>

            {sections.map((section, idx) => {
              const isActive = idx === activeIndex;
              const range = { start: section.start_line, end: section.end_line };
              return (
                <div key={idx} className={`section-explain-card ${isActive ? "active" : ""}`} onClick={() => setActiveIndex(idx)}>
                  <div className="section-header-row">
                    <h5><InlineText text={section.title} /></h5>
                    <span className="line-range-pill">Lines {section.start_line}–{section.end_line}</span>
                  </div>
                  <p><InlineText text={section.explanation} /></p>
                  {section.needs_explanation && (
                    <p className="hint-text" style={{ marginTop: "0.35rem" }}>From the file&apos;s own structure. Not yet explained by the AI.</p>
                  )}
                  {isActive && (
                    <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginTop: "0.6rem" }}>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelection(range);
                          void explain(range);
                        }}
                        className="btn-secondary small"
                        disabled={explaining}
                      >
                        <Sparkles size={13} />
                        <span>Go line by line</span>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          askAbout(range, section.title);
                        }}
                        className="btn-secondary small"
                      >
                        <MessageSquare size={13} />
                        <span>Ask the tutor</span>
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {fileDetails.quizzes.length > 0 ? (
          <InteractiveQuiz
            key={fileDetails.file_path + fileDetails.quizzes.map((q) => q.id).join(",")}
            quizzes={fileDetails.quizzes}
            filePath={fileDetails.file_path}
            onOpenDiscussion={onOpenDiscussion}
            onProgress={onProgress}
          />
        ) : (
          <div className="quiz-section-container" style={{ textAlign: "center" }}>
            <p style={{ color: "var(--text-secondary)" }}>
              {fileDetails.degraded ? "Quiz questions need the AI. Use Retry above once it's available." : "No quiz questions for this file yet."}
            </p>
          </div>
        )}

        {nextStep && (
          <div className="transition-banner" style={{ marginTop: "1.25rem" }}>
            <div>
              <p>Next in your reading order: <code className="inline-code">{nextStep.file_path}</code></p>
              <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}><InlineText text={nextStep.why} /></span>
            </div>
            <button onClick={() => onOpenFile(nextStep.file_path)} className="btn-primary">
              <span>Open it</span>
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="inspector-shell">
      {browser}
      {body}
    </div>
  );
};
