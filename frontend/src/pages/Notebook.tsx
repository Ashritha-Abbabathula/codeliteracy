import React, { useCallback, useEffect, useState } from "react";
import { BookOpen, Calendar, Download, FileCode, Folder, PenLine, Plus, Search, Star, Trash2 } from "lucide-react";
import {
  createNote,
  deleteNotebookEntry,
  errorMessage,
  getNotebook,
  NotebookEntry,
  toggleNotebookFavorite,
  updateNotebookNotes,
} from "../api/client";
import { useAuth } from "../context/AuthContext";
import { InlineText } from "../components/RichText";

type Filter = "all" | "file_walkthrough" | "change" | "note" | "favorites";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "file_walkthrough", label: "File quizzes" },
  { id: "change", label: "Bug fixes" },
  { id: "note", label: "My notes" },
  { id: "favorites", label: "★ Favorites" },
];

const CATEGORY_STYLE: Record<string, { label: string; bg: string; color: string }> = {
  file_walkthrough: { label: "File mastery", bg: "rgba(16, 185, 129, 0.2)", color: "#86efac" },
  change: { label: "Bug fix / feature", bg: "rgba(99, 102, 241, 0.2)", color: "#c7d2fe" },
  note: { label: "My note", bg: "rgba(245, 158, 11, 0.2)", color: "#fcd34d" },
};

export const Notebook: React.FC = () => {
  const { user, loading: authLoading, refreshUser } = useAuth();
  const [entries, setEntries] = useState<NotebookEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [composing, setComposing] = useState(false);
  const [noteTitle, setNoteTitle] = useState("");
  const [noteBody, setNoteBody] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    return getNotebook({
      q: query || undefined,
      category: filter === "all" || filter === "favorites" ? undefined : filter,
      favorites: filter === "favorites",
    })
      .then((rows) => {
        setEntries(rows);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Couldn't load your notebook.")))
      .finally(() => setLoading(false));
  }, [query, filter]);

  // Search as you type (debounced); reload when sign-in changes, since a notebook belongs to a user.
  useEffect(() => {
    if (authLoading) return;
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load, user?.id, authLoading]);

  function replace(updated: NotebookEntry) {
    setEntries((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
  }

  async function run(action: () => Promise<void>, failure: string) {
    try {
      await action();
      setError(null);
    } catch (err) {
      setError(errorMessage(err, failure));
    }
  }

  const saveNotes = (id: string) =>
    run(async () => {
      replace(await updateNotebookNotes(id, draft));
      setEditingId(null);
    }, "Couldn't save your note.");

  const toggleFavorite = (id: string) =>
    run(async () => {
      const updated = await toggleNotebookFavorite(id);
      if (filter === "favorites" && !updated.is_favorite) setEntries((prev) => prev.filter((e) => e.id !== id));
      else replace(updated);
    }, "Couldn't update that favorite.");

  const remove = (id: string) =>
    run(async () => {
      if (!window.confirm("Remove this entry from your notebook?")) return;
      await deleteNotebookEntry(id);
      setEntries((prev) => prev.filter((e) => e.id !== id));
      if (user) void refreshUser();
    }, "Couldn't delete that entry.");

  const addNote = () =>
    run(async () => {
      if (!noteTitle.trim() || !noteBody.trim()) return;
      await createNote({ concept: noteTitle, summary: noteBody });
      setNoteTitle("");
      setNoteBody("");
      setComposing(false);
      if (filter === "file_walkthrough" || filter === "change") setFilter("all");
      else await load();
      if (user) void refreshUser();
    }, "Couldn't save your note.");

  function exportMarkdown() {
    if (!entries.length) return;
    let md = `# CodeLiteracy Learning Notebook\n\nGenerated for: ${user?.username ?? "Developer"}\nDate: ${new Date().toLocaleDateString()}\n\n`;
    for (const e of entries) {
      md += `## ${e.is_favorite ? "★ " : ""}${e.concept}\n`;
      md += `- **Repository:** ${e.repo_name}\n`;
      if (e.file_path) md += `- **File:** ${e.file_path}\n`;
      md += `- **Date:** ${new Date(e.created_at).toLocaleDateString()}\n\n`;
      md += `### Summary\n${e.summary}\n\n`;
      if (e.question) md += `### Quiz question\n> ${e.question}\n\n`;
      if (e.user_notes) md += `### My notes\n${e.user_notes}\n\n`;
      md += `---\n\n`;
    }
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `codeliteracy-notebook-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="notebook-container">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h2 style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <BookOpen size={24} color="var(--accent)" />
            <span>My Learning Notebook</span>
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.25rem" }}>
            {user
              ? "Concepts you've mastered, code breakdowns, and your own notes across every repository."
              : "You're not signed in, so this notebook is shared by anonymous sessions on this machine. Sign in to keep your own."}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button onClick={() => setComposing((c) => !c)} className="btn-primary" style={{ fontSize: "0.85rem" }}>
            <Plus size={15} />
            <span>New note</span>
          </button>
          {entries.length > 0 && (
            <button onClick={exportMarkdown} className="btn-secondary" style={{ fontSize: "0.85rem" }}>
              <Download size={15} />
              <span>Export to Markdown</span>
            </button>
          )}
        </div>
      </div>

      {composing && (
        <div className="notebook-card" style={{ borderColor: "var(--accent)" }}>
          <input className="input-text" style={{ width: "100%", marginBottom: "0.6rem" }} placeholder="Title (e.g. What I learned about dependency injection)" value={noteTitle} onChange={(e) => setNoteTitle(e.target.value)} maxLength={200} />
          <textarea className="notes-input-area" rows={4} placeholder="Write down what you learned…" value={noteBody} onChange={(e) => setNoteBody(e.target.value)} style={{ marginTop: 0 }} />
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.6rem" }}>
            <button onClick={addNote} className="btn-primary" style={{ fontSize: "0.82rem" }} disabled={!noteTitle.trim() || !noteBody.trim()}>Save note</button>
            <button onClick={() => setComposing(false)} className="btn-secondary" style={{ fontSize: "0.82rem" }}>Cancel</button>
          </div>
        </div>
      )}

      <div className="notebook-search-row">
        <div style={{ position: "relative", flex: 1 }}>
          <Search size={16} color="var(--text-muted)" style={{ position: "absolute", left: "1rem", top: "50%", transform: "translateY(-50%)" }} />
          <input type="text" className="input-text" style={{ width: "100%", paddingLeft: "2.5rem" }} placeholder="Search concepts, files, questions or your notes…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search notebook" />
        </div>
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
          {FILTERS.map((f) => (
            <button key={f.id} className={`btn-secondary ${filter === f.id ? "active" : ""}`} style={{ fontSize: "0.82rem", padding: "0.45rem 0.8rem" }} onClick={() => setFilter(f.id)} aria-pressed={filter === f.id}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="quiz-feedback-box incorrect" style={{ marginBottom: "1rem" }}>{error}</div>}
      {loading && !entries.length && <p style={{ color: "var(--text-muted)" }}>Loading your learning records…</p>}

      {!loading && !error && entries.length === 0 && (
        <div style={{ textAlign: "center", padding: "3rem", background: "var(--bg-secondary)", borderRadius: "var(--radius-lg)" }}>
          <BookOpen size={36} color="var(--text-muted)" style={{ margin: "0 auto 1rem" }} />
          <h4>{query || filter !== "all" ? "Nothing matches that" : "No notebook entries yet"}</h4>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem", marginTop: "0.35rem" }}>
            {query || filter !== "all"
              ? "Try a different search or filter."
              : "Connect a repository and answer a code quiz correctly to start building your learning record."}
          </p>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {entries.map((entry) => {
          const style = CATEGORY_STYLE[entry.category] ?? { label: "Concept", bg: "rgba(99, 102, 241, 0.2)", color: "#c7d2fe" };
          const isEditing = editingId === entry.id;
          return (
            <div key={entry.id} className="notebook-card">
              <div className="notebook-card-header">
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                  <span className="tech-tag" style={{ background: style.bg, color: style.color }}>{style.label}</span>
                  <strong>{entry.concept}</strong>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                    <Calendar size={12} />
                    {new Date(entry.created_at).toLocaleDateString()}
                  </span>
                  <button onClick={() => toggleFavorite(entry.id)} className="btn-secondary" style={{ padding: "0.25rem 0.45rem", color: entry.is_favorite ? "#fbbf24" : undefined }} title={entry.is_favorite ? "Remove from favorites" : "Add to favorites"} aria-pressed={entry.is_favorite}>
                    <Star size={13} fill={entry.is_favorite ? "currentColor" : "none"} />
                  </button>
                  <button onClick={() => remove(entry.id)} className="btn-secondary" style={{ padding: "0.25rem 0.45rem", color: "#f87171" }} title="Remove entry">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>

              <div style={{ display: "flex", gap: "0.8rem", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.6rem", flexWrap: "wrap" }}>
                <span style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}><Folder size={13} />{entry.repo_name}</span>
                {entry.file_path && <span style={{ display: "flex", alignItems: "center", gap: "0.25rem", fontFamily: "monospace" }}><FileCode size={13} />{entry.file_path}</span>}
              </div>

              <p style={{ fontSize: "0.9rem", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{entry.category === "note" ? entry.summary : <InlineText text={entry.summary} />}</p>

              {entry.question && (
                <div style={{ margin: "0.75rem 0", padding: "0.65rem 0.9rem", background: "rgba(0, 0, 0, 0.2)", borderRadius: "var(--radius-sm)", fontSize: "0.84rem", borderLeft: "2px solid var(--accent)" }}>
                  <span style={{ color: "var(--text-muted)", fontSize: "0.75rem", display: "block" }}>Quiz question mastered:</span>
                  <InlineText text={entry.question} />
                </div>
              )}

              <div style={{ marginTop: "0.75rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "0.75rem" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                    <PenLine size={13} />
                    <span>My notes &amp; reflections</span>
                  </span>
                  {!isEditing && (
                    <button onClick={() => { setEditingId(entry.id); setDraft(entry.user_notes ?? ""); }} className="btn-secondary" style={{ fontSize: "0.74rem", padding: "0.2rem 0.5rem" }}>
                      {entry.user_notes ? "Edit note" : "+ Add note"}
                    </button>
                  )}
                </div>

                {isEditing ? (
                  <div style={{ marginTop: "0.5rem" }}>
                    <textarea className="notes-input-area" rows={3} placeholder="Write your own takeaways here…" value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
                    <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.4rem" }}>
                      <button onClick={() => saveNotes(entry.id)} className="btn-primary" style={{ fontSize: "0.78rem", padding: "0.3rem 0.7rem" }}>Save note</button>
                      <button onClick={() => setEditingId(null)} className="btn-secondary" style={{ fontSize: "0.78rem", padding: "0.3rem 0.7rem" }}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  entry.user_notes && <p style={{ fontSize: "0.84rem", color: "#c7d2fe", fontStyle: "italic", marginTop: "0.3rem", whiteSpace: "pre-wrap" }}>“{entry.user_notes}”</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
