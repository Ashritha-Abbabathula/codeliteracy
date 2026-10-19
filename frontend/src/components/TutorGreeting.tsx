import React from "react";
import {
  CheckCircle2,
  FolderGit2,
  Layers,
  Sparkles,
  ArrowRight,
  HelpCircle,
  AlertCircle,
  AlertTriangle,
  RefreshCw,
  Route,
} from "lucide-react";
import { RepoOnboarding } from "../api/client";
import { InlineText } from "./RichText";

interface TutorGreetingProps {
  onboarding: RepoOnboarding | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onViewFlowchart: () => void;
  onOpenFile: (path: string) => void;
  /** files the learner has already opened, to tick them off the reading order */
  exploredPaths: Set<string>;
}

export const TutorGreeting: React.FC<TutorGreetingProps> = ({
  onboarding,
  loading,
  error,
  onRetry,
  onViewFlowchart,
  onOpenFile,
  exploredPaths,
}) => {
  if (loading) {
    return (
      <div className="tutor-greeting-card" style={{ textAlign: "center", padding: "3rem" }}>
        <div className="tutor-avatar" style={{ margin: "0 auto 1rem", animation: "pulse 1.5s infinite" }}>
          🤖
        </div>
        <h3>Analyzing Repository Structure...</h3>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.5rem" }}>
          Reading codebase files, dependencies, and architecture to build your personalized onboarding guide.
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="tutor-greeting-card" style={{ textAlign: "center", padding: "2.5rem" }}>
        <AlertTriangle size={32} color="var(--warning)" style={{ margin: "0 auto 0.75rem" }} />
        <p className="error-text">{error}</p>
        <button onClick={onRetry} className="btn-primary" style={{ marginTop: "1rem" }}>
          <RefreshCw size={15} />
          <span>Try again</span>
        </button>
      </div>
    );
  }

  if (!onboarding) return null;

  const { easy, hard } = onboarding.learning_curve;
  const hasCurve = easy.length > 0 || hard.length > 0;
  const path = onboarding.learning_path ?? [];
  const nextIndex = path.findIndex((s) => !exploredPaths.has(s.file_path));

  return (
    <div className="tutor-greeting-card">
      <div className="tutor-header">
        <div className="tutor-avatar">🤖</div>
        <div className="tutor-title">
          <h3>AI Code Tutor</h3>
          <p>{onboarding.greeting}</p>
        </div>
      </div>

      {onboarding.degraded && (
        <div className="notice-banner">
          <AlertTriangle size={16} />
          <span>{onboarding.notice ?? "The AI summary is unavailable right now."}</span>
          <button onClick={onRetry} className="btn-secondary" style={{ marginLeft: "auto", fontSize: "0.78rem", padding: "0.25rem 0.6rem" }}>
            <RefreshCw size={13} /> Retry
          </button>
        </div>
      )}

      <div className="onboarding-grid">
        {/* Main Idea */}
        <div className="onboarding-box" style={{ gridColumn: "1 / -1" }}>
          <h4>
            <Sparkles size={18} color="var(--accent)" />
            Main Idea & Project Purpose
          </h4>
          <p style={{ fontSize: "1rem", color: "var(--text-primary)" }}><InlineText text={onboarding.main_idea} /></p>
        </div>

        {/* Tech Stack */}
        <div className="onboarding-box">
          <h4>
            <Layers size={18} color="#38bdf8" />
            Technologies & Frameworks
          </h4>
          <p style={{ marginBottom: "0.75rem" }}>
            The core building blocks powering this codebase:
          </p>
          {onboarding.tech_stack.length === 0 && (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>No recognizable frameworks found in the dependency files.</p>
          )}
          <div className="tech-badges-list">
            {onboarding.tech_stack.map((t, i) => (
              <div key={i} className="tech-chip" title={t.purpose}>
                <strong>{t.name}</strong>
                <span className="category-badge">({t.category})</span>
                {t.purpose && <span className="tech-purpose">{t.purpose}</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Learning Curve: Easy vs Hard */}
        {hasCurve && (
        <div className="onboarding-box">
          <h4>
            <HelpCircle size={18} color="#f59e0b" />
            Learning Curve Breakdown
          </h4>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div>
              <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "#34d399", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                🟢 Easier to Understand
              </span>
              <ul className="concept-list" style={{ marginTop: "0.3rem" }}>
                {easy.map((c, i) => (
                  <li key={i} className="concept-item easy">
                    <CheckCircle2 size={14} style={{ flexShrink: 0, marginTop: "2px" }} />
                    <span><InlineText text={c} /></span>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "#f87171", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                🔴 Harder / Advanced Concepts
              </span>
              <ul className="concept-list" style={{ marginTop: "0.3rem" }}>
                {hard.map((c, i) => (
                  <li key={i} className="concept-item hard">
                    <AlertCircle size={14} style={{ flexShrink: 0, marginTop: "2px" }} />
                    <span><InlineText text={c} /></span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
        )}

        {/* Reading order */}
        {path.length > 0 && (
        <div className="onboarding-box" style={{ gridColumn: "1 / -1" }}>
          <h4>
            <Route size={18} color="#34d399" />
            Where to start: a reading order for this repo
          </h4>
          <p style={{ marginBottom: "0.75rem" }}>
            Read these files in this order. Each one opens with a section-by-section walkthrough and a short quiz.
          </p>
          <ol className="path-list">
            {path.map((step, i) => {
              const done = exploredPaths.has(step.file_path);
              return (
                <li key={step.file_path}>
                  <button className={`path-step ${done ? "done" : ""} ${i === nextIndex ? "next" : ""}`} onClick={() => onOpenFile(step.file_path)}>
                    <span className="path-number">{done ? <CheckCircle2 size={15} /> : i + 1}</span>
                    <span>
                      <strong>{step.title}</strong> <code className="inline-code">{step.file_path}</code>
                      <span className="path-why"><InlineText text={step.why} /></span>
                    </span>
                    <span className="path-cta">{i === nextIndex ? (i === 0 ? "Start here" : "Up next") : done ? "Opened" : ""} <ArrowRight size={14} /></span>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
        )}

        {/* Folder Guide */}
        {onboarding.folder_guide.length > 0 && (
        <div className="onboarding-box" style={{ gridColumn: "1 / -1" }}>
          <h4>
            <FolderGit2 size={18} color="#ec4899" />
            What Each Folder Does in this Repo
          </h4>
          <div className="folder-accordion">
            {onboarding.folder_guide.map((f, i) => (
              <div key={i} className="folder-card">
                <div className="folder-card-header">
                  <strong>📁 {f.folder}</strong>
                  <span style={{ fontSize: "0.75rem", color: "var(--accent)" }}>{f.title}</span>
                </div>
                <p><InlineText text={f.purpose} /></p>
                {f.key_files && f.key_files.length > 0 && (
                  <div className="folder-key-files">
                    {f.key_files.map((file, j) => (
                      <span key={j} className="file-micro-chip">
                        📄 {file}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
        )}
      </div>

      {/* Transition to Flowchart */}
      <div className="transition-banner">
        <div>
          <p>✨ {onboarding.transition_message || "Creating the architectural flowchart for you..."}</p>
          <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
            See how the modules depend on each other, then click any of them to open its code.
          </span>
        </div>
        <button onClick={onViewFlowchart} className="btn-primary">
          <span>View Architecture Flowchart</span>
          <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
};
