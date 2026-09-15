import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, connectRepo } from "../api/client";

/** FR1 + FR2: connect a repo (clone a GitHub URL, or link a local path) and parse its
 * dependency graph. On success, hands off to RepoView for the flowchart + explanations. */
export function RepoConnect() {
  const [source, setSource] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!source.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const result = await connectRepo(source.trim());
      navigate(`/repo/${result.repo_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong connecting the repo.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <h2>Connect a repository</h2>
      <p className="hint">
        Paste a GitHub URL (e.g. <code>https://github.com/owner/repo</code>) or a local folder path.
        Initial version supports Python repositories only.
      </p>
      <form onSubmit={handleSubmit} className="connect-form">
        <input
          type="text"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="https://github.com/owner/repo"
        />
        <button type="submit" disabled={loading}>
          {loading ? "Connecting…" : "Connect"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}
    </section>
  );
}
