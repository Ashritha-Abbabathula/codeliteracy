import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, GitBranch, History, Sparkles } from "lucide-react";
import {
  connectRepo,
  errorMessage,
  getSampleRepositories,
  getUserRepositories,
  RepoInfo,
  SampleRepo,
} from "../api/client";
import { useAuth } from "../context/AuthContext";

export const RepoConnect: React.FC = () => {
  const { user, loading: authLoading } = useAuth();
  const [source, setSource] = useState("");
  const [connecting, setConnecting] = useState<string | null>(null); // the source being connected
  const [error, setError] = useState<string | null>(null);
  const [samples, setSamples] = useState<SampleRepo[]>([]);
  const [recentRepos, setRecentRepos] = useState<RepoInfo[]>([]);

  const navigate = useNavigate();

  useEffect(() => {
    getSampleRepositories().then(setSamples).catch(() => {});
  }, []);

  // Recent repositories belong to whoever is signed in, so reload when that changes.
  useEffect(() => {
    if (authLoading) return;
    getUserRepositories().then(setRecentRepos).catch(() => setRecentRepos([]));
  }, [user?.id, authLoading]);

  async function handleConnect(target?: string) {
    const src = (target ?? source).trim();
    if (!src || connecting) return;

    setConnecting(src);
    setError(null);
    try {
      const result = await connectRepo(src);
      navigate(`/repo/${result.repo_id}`);
    } catch (err) {
      setError(errorMessage(err, "Something went wrong connecting the repository."));
      setConnecting(null);
    }
  }

  const busy = connecting !== null;
  const isUrl = /^(https?:\/\/|git@)/.test(connecting ?? "");

  return (
    <div className="connect-hero">
      <div className="hero-pill">
        <Sparkles size={14} />
        <span>Adaptive AI Codebase Literacy Platform</span>
      </div>

      <h2>
        Understand Any Codebase. <br />
        <span className="gradient-text">Actually Learn How It Works.</span>
      </h2>

      <p className="hero-sub">
        Connect a repository to get an instant AI-tutor walkthrough, a clean architecture flowchart, line-by-line code
        explanations, and interactive quizzes that make the knowledge stick.
      </p>

      <div className="connect-card">
        <strong style={{ fontSize: "1.05rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <GitBranch size={20} color="var(--accent)" />
          <span>Connect a GitHub or local repository</span>
        </strong>
        <p style={{ fontSize: "0.86rem", color: "var(--text-secondary)", marginTop: "0.35rem" }}>
          Paste a public GitHub URL (e.g. <code>https://github.com/owner/repo</code>) or a local folder path. Python projects only, for now.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleConnect();
          }}
          className="input-group"
        >
          <input
            type="text"
            className="input-text"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder="https://github.com/owner/repo  or  C:\path\to\project"
            disabled={busy}
            aria-label="Repository URL or folder path"
          />
          <button type="submit" className="btn-primary" disabled={busy || !source.trim()}>
            <span>{busy ? (isUrl ? "Cloning & analyzing…" : "Analyzing…") : "Connect & Learn"}</span>
            <ArrowRight size={16} />
          </button>
        </form>

        {busy && isUrl && (
          <p className="hint-text">Cloning from GitHub. Large repositories can take a little while.</p>
        )}
        {error && <div className="quiz-feedback-box incorrect" style={{ marginTop: "1rem" }}>{error}</div>}

        {samples.length > 0 && (
          <div className="sample-repos-section">
            <h3>⚡ Or try a one-click sample project</h3>
            <div className="sample-grid">
              {samples.map((s) => (
                <div
                  key={s.id}
                  className="sample-card"
                  role="button"
                  tabIndex={0}
                  aria-disabled={busy}
                  onClick={() => void handleConnect(s.source)}
                  onKeyDown={(e) => e.key === "Enter" && void handleConnect(s.source)}
                  style={busy ? { opacity: 0.6, pointerEvents: "none" } : undefined}
                >
                  <div>
                    <strong>{s.name}</strong>
                    <p>{s.description}</p>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "0.5rem" }}>
                    <span className="tech-tag">{s.tech}</span>
                    <span style={{ fontSize: "0.78rem", color: "var(--accent)", fontWeight: 500 }}>
                      {connecting === s.source ? "Opening…" : "Explore →"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {recentRepos.length > 0 && (
          <div style={{ marginTop: "1.75rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "1rem" }}>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.6rem" }}>
              <History size={14} />
              <span>Recently connected</span>
            </span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
              {recentRepos.map((r) => (
                <button key={r.repo_id} onClick={() => navigate(`/repo/${r.repo_id}`)} className="btn-secondary" style={{ fontSize: "0.82rem", padding: "0.35rem 0.75rem" }} title={r.source}>
                  📁 {r.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
