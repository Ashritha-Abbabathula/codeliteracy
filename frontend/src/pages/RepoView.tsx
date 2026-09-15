import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import {
  ApiError,
  DependencyGraph,
  RepoExplanation,
  explainRepo,
  getRepoGraph,
} from "../api/client";
import { GraphViewer } from "../components/GraphViewer";

/** FR3: the dependency graph rendered as a visual flowchart.
 * FR4: plain-language explanations alongside it, per file and for the repo overall. */
export function RepoView() {
  const { repoId } = useParams<{ repoId: string }>();

  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [explanation, setExplanation] = useState<RepoExplanation | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);

  useEffect(() => {
    if (!repoId) return;
    getRepoGraph(repoId)
      .then(setGraph)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load the graph."));
  }, [repoId]);

  async function handleExplain() {
    if (!repoId) return;
    setExplaining(true);
    setError(null);
    try {
      setExplanation(await explainRepo(repoId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to generate explanations.");
    } finally {
      setExplaining(false);
    }
  }

  const selectedExplanation = explanation?.files.find((f) => f.path === selectedId);

  return (
    <section>
      <h2>Repository structure</h2>
      {error && <p className="error">{error}</p>}

      {!graph && !error && <p>Loading graph…</p>}

      {graph && (
        <>
          <GraphViewer graph={graph} selectedId={selectedId} onSelect={setSelectedId} />

          <div className="explain-panel">
            {!explanation && (
              <button onClick={handleExplain} disabled={explaining}>
                {explaining ? "Reading the code…" : "Explain this repo"}
              </button>
            )}

            {explanation && (
              <>
                <h3>Overview</h3>
                <p>{explanation.overview}</p>
                <h3>{selectedId ? "Selected file" : "Click a file in the graph"}</h3>
                {selectedId && (
                  <div className="file-explanation">
                    <code>{selectedId}</code>
                    <p>{selectedExplanation?.explanation ?? "No explanation available for this file."}</p>
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}
