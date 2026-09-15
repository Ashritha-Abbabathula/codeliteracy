import { useEffect, useState } from "react";

import { ApiError, NotebookEntry, getNotebook } from "../api/client";

/** FR11 + FR12: everything the user has answered correctly, kept across repos and
 * sessions so they can look back over what they've actually learned. */
export function Notebook() {
  const [query, setQuery] = useState("");
  const [entries, setEntries] = useState<NotebookEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const timeout = setTimeout(() => {
      getNotebook(query || undefined)
        .then((result) => {
          setEntries(result);
          setError(null);
        })
        .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load the notebook."))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(timeout);
  }, [query]);

  return (
    <section>
      <h2>My notebook</h2>
      <p className="hint">Concepts you've answered correctly, across every repo you've worked in.</p>

      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search concepts, repos, or summaries…"
        className="notebook-search"
      />

      {error && <p className="error">{error}</p>}
      {!error && loading && <p className="hint">Loading…</p>}
      {!error && !loading && entries.length === 0 && (
        <p className="hint">
          {query ? "No matching entries." : "Nothing here yet - answer a quiz correctly to start building this up."}
        </p>
      )}

      <ul className="notebook-list">
        {entries.map((entry) => (
          <li key={entry.id} className="notebook-entry">
            <div className="notebook-entry-header">
              <strong>{entry.concept}</strong>
              <span className="meta">
                {entry.repo_name} · {new Date(entry.created_at).toLocaleDateString()}
              </span>
            </div>
            <p>{entry.summary}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
