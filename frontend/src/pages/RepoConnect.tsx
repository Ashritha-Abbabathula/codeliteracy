import { FormEvent, useState } from "react";

import { ApiError, connectRepo, RepoConnectResponse } from "../api/client";

/** FR1 + FR2 + (temporary) FR3 stand-in: connect a repo and see its parsed
 * dependency graph. Sprint 2 replaces the raw JSON dump below with an actual
 * flowchart viewer and plain-language explanations. */
export function RepoConnect() {
  const [source, setSource] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RepoConnectResponse | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!source.trim()) return;

    setLoading(true);
    setError(null);
    try {
      setResult(await connectRepo(source.trim()));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong connecting the repo.");
      setResult(null);
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

      {result && (
        <div className="result">
          <h3>
            {result.name} — {result.node_count} modules, {result.edge_count} dependencies
          </h3>
          <pre>{JSON.stringify(result.graph, null, 2)}</pre>
        </div>
      )}
    </section>
  );
}
