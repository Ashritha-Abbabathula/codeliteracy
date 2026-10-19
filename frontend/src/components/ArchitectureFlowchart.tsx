import React, { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, ChevronRight, FileCode, Layers, Minus, Plus, RefreshCw } from "lucide-react";
import { ArchitectureFlowchart as FlowchartData, FlowchartNode, Tier } from "../api/client";

interface ArchitectureFlowchartProps {
  flowchart: FlowchartData | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onInspectFile: (filePath: string) => void;
}

interface Geometry {
  id: string;
  d: string;
  labelX: number;
  labelY: number;
  source: string;
  target: string;
  label: string;
}

const MIN_ZOOM = 0.6;
const MAX_ZOOM = 1.4;

export const ArchitectureFlowchart: React.FC<ArchitectureFlowchartProps> = ({
  flowchart,
  loading,
  error,
  onRetry,
  onInspectFile,
}) => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hiddenTiers, setHiddenTiers] = useState<Set<Tier>>(new Set());
  const [zoom, setZoom] = useState(1);
  const [geometry, setGeometry] = useState<Geometry[]>([]);
  const [innerHeight, setInnerHeight] = useState(0);

  const innerRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const visibleNodes = useMemo(
    () => (flowchart ? flowchart.nodes.filter((n) => !hiddenTiers.has(n.tier)) : []),
    [flowchart, hiddenTiers]
  );
  const nodeById = useMemo(() => new Map((flowchart?.nodes ?? []).map((n) => [n.id, n])), [flowchart]);
  const selected = selectedId ? nodeById.get(selectedId) ?? null : null;

  // Measure where each node actually landed and draw arrows between them.
  const measure = useCallback(() => {
    const inner = innerRef.current;
    if (!inner || !flowchart) return;
    const base = inner.getBoundingClientRect();
    setInnerHeight(inner.offsetHeight);

    const box = (id: string) => {
      const el = nodeRefs.current[id];
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {
        left: (r.left - base.left) / zoom,
        right: (r.right - base.left) / zoom,
        top: (r.top - base.top) / zoom,
        bottom: (r.bottom - base.top) / zoom,
      };
    };

    const next: Geometry[] = [];
    for (const edge of flowchart.edges) {
      const a = box(edge.source);
      const b = box(edge.target);
      if (!a || !b) continue;
      let d: string;
      let labelX: number;
      let labelY: number;
      if (Math.abs(b.top - a.top) < 20) {
        // same row: hop over the cards in between with an arc along the top edge
        const x1 = (a.left + a.right) / 2;
        const x2 = (b.left + b.right) / 2;
        const y = a.top;
        const lift = 26 + Math.min(40, Math.abs(x2 - x1) / 8);
        d = `M ${x1} ${y} C ${x1} ${y - lift}, ${x2} ${y - lift}, ${x2} ${y}`;
        labelX = (x1 + x2) / 2;
        labelY = y - lift * 0.75;
      } else {
        const downward = b.top > a.top;
        const x1 = (a.left + a.right) / 2;
        const y1 = downward ? a.bottom : a.top;
        const x2 = (b.left + b.right) / 2;
        const y2 = downward ? b.top : b.bottom;
        const dy = Math.max(30, Math.abs(y2 - y1) / 2);
        const sign = downward ? 1 : -1;
        d = `M ${x1} ${y1} C ${x1} ${y1 + sign * dy}, ${x2} ${y2 - sign * dy}, ${x2} ${y2}`;
        labelX = (x1 + x2) / 2;
        labelY = (y1 + y2) / 2;
      }
      next.push({ id: edge.id, d, labelX, labelY, source: edge.source, target: edge.target, label: edge.label });
    }
    setGeometry(next);
  }, [flowchart, zoom]);

  useLayoutEffect(() => {
    measure();
    const inner = innerRef.current;
    if (!inner || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measure());
    observer.observe(inner);
    return () => observer.disconnect();
  }, [measure, visibleNodes]);

  if (loading) {
    return (
      <div className="flowchart-container" style={{ textAlign: "center", padding: "3rem" }}>
        <Layers size={36} color="var(--accent)" style={{ animation: "pulse 1.5s infinite", margin: "0 auto 1rem" }} />
        <h3>Building the architecture flowchart…</h3>
        <p style={{ color: "var(--text-secondary)", marginTop: "0.5rem" }}>
          Grouping modules into layers and tracing how they import each other.
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flowchart-container" style={{ textAlign: "center", padding: "2rem" }}>
        <AlertTriangle size={30} color="var(--warning)" style={{ margin: "0 auto 0.75rem" }} />
        <p className="error-text">{error}</p>
        <button onClick={onRetry} className="btn-primary" style={{ marginTop: "1rem" }}>
          <RefreshCw size={15} />
          <span>Try again</span>
        </button>
      </div>
    );
  }

  if (!flowchart || !flowchart.nodes.length) {
    return (
      <div className="flowchart-container" style={{ textAlign: "center", padding: "2rem" }}>
        <p>No architecture could be drawn for this repository.</p>
      </div>
    );
  }

  function handleNodeClick(node: FlowchartNode) {
    if (selectedId === node.id) {
      if (node.file_path) onInspectFile(node.file_path); // second click opens the code
    } else {
      setSelectedId(node.id);
    }
  }

  function toggleTier(tier: Tier) {
    setHiddenTiers((prev) => {
      const next = new Set(prev);
      if (next.has(tier)) next.delete(tier);
      else next.add(tier);
      return next;
    });
  }

  const nodesByTier: Record<string, FlowchartNode[]> = {};
  for (const n of visibleNodes) (nodesByTier[n.tier] ??= []).push(n);

  const outgoing = selected ? flowchart.edges.filter((e) => e.source === selected.id) : [];
  const incoming = selected ? flowchart.edges.filter((e) => e.target === selected.id) : [];
  const isTouching = (g: Geometry) => !!selected && (g.source === selected.id || g.target === selected.id);

  return (
    <div className="flowchart-container">
      <div className="flowchart-header">
        <div>
          <h3>System architecture</h3>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>
            Arrows follow real imports, top to bottom. Click a module to see its role and connections; click it again to open its code.
            {flowchart.shown_modules !== undefined && flowchart.total_modules !== undefined && (
              <> Showing the {flowchart.shown_modules} most connected of {flowchart.total_modules} modules.</>
            )}
          </p>
        </div>

        {selected?.file_path && (
          <button onClick={() => onInspectFile(selected.file_path)} className="btn-primary" style={{ fontSize: "0.85rem" }}>
            <FileCode size={16} />
            <span>Inspect {selected.label}</span>
            <ChevronRight size={16} />
          </button>
        )}
      </div>

      {flowchart.notice && (
        <div className="notice-banner">
          <AlertTriangle size={16} />
          <span>{flowchart.notice}</span>
          <button onClick={onRetry} className="btn-secondary" style={{ marginLeft: "auto", fontSize: "0.78rem", padding: "0.25rem 0.6rem" }}>
            <RefreshCw size={13} /> Retry
          </button>
        </div>
      )}

      <div className="flowchart-toolbar">
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Layers:</span>
          {flowchart.tiers.map((t) => (
            <button
              key={t.id}
              className={`layer-chip ${hiddenTiers.has(t.id) ? "off" : ""}`}
              onClick={() => toggleTier(t.id)}
              aria-pressed={!hiddenTiers.has(t.id)}
              title={t.description}
            >
              {t.title.replace(/^\d+\.\s*/, "")}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: "0.3rem", alignItems: "center" }}>
          <button className="btn-secondary" style={{ padding: "0.25rem 0.5rem" }} onClick={() => setZoom((z) => Math.max(MIN_ZOOM, +(z - 0.1).toFixed(2)))} disabled={zoom <= MIN_ZOOM} title="Zoom out">
            <Minus size={14} />
          </button>
          <button className="btn-secondary" style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem", minWidth: "3.2rem" }} onClick={() => setZoom(1)} title="Reset zoom">
            {Math.round(zoom * 100)}%
          </button>
          <button className="btn-secondary" style={{ padding: "0.25rem 0.5rem" }} onClick={() => setZoom((z) => Math.min(MAX_ZOOM, +(z + 0.1).toFixed(2)))} disabled={zoom >= MAX_ZOOM} title="Zoom in">
            <Plus size={14} />
          </button>
        </div>
      </div>

      {selected && (
        <div className="node-detail-card">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
              <span className="node-badge-chip" style={{ background: selected.badge_color, margin: 0 }}>{selected.tier_label}</span>
              <strong style={{ fontSize: "1.1rem" }}>{selected.label}</strong>
              {selected.file_path && <code style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{selected.file_path}</code>}
            </div>
            {!selected.file_path && <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>External library / service</span>}
          </div>

          <p style={{ marginTop: "0.6rem", fontSize: "0.9rem" }}>{selected.summary}</p>

          {selected.key_functions.length > 0 && (
            <div className="chip-row">
              <span className="chip-label">Defines:</span>
              {selected.key_functions.map((fn) => <span key={fn} className="file-micro-chip">{fn}</span>)}
            </div>
          )}

          {(outgoing.length > 0 || incoming.length > 0) && (
            <div className="connection-list">
              {outgoing.map((e) => (
                <div key={e.id}>
                  <ArrowRight size={12} /> <strong>{nodeById.get(e.target)?.label}</strong> <span>— {e.label}</span>
                </div>
              ))}
              {incoming.map((e) => (
                <div key={e.id}>
                  <ArrowRight size={12} style={{ transform: "rotate(180deg)" }} /> used by <strong>{nodeById.get(e.source)?.label}</strong> <span>— {e.label}</span>
                </div>
              ))}
            </div>
          )}

          {selected.file_path && (
            <button onClick={() => onInspectFile(selected.file_path)} className="btn-outline-accent" style={{ marginTop: "0.75rem", fontSize: "0.82rem", padding: "0.4rem 0.8rem" }}>
              <span>Open the line-by-line code inspector</span>
              <ChevronRight size={14} />
            </button>
          )}
        </div>
      )}

      <div className="flowchart-viewport" style={{ height: innerHeight ? innerHeight * zoom : undefined }}>
        <div
          ref={innerRef}
          className="flowchart-tiers-grid"
          style={{ transform: `scale(${zoom})`, transformOrigin: "0 0", width: `${100 / zoom}%` }}
        >
          <svg className="flowchart-edges" width="100%" height={innerHeight || "100%"} aria-hidden="true">
            <defs>
              <marker id="fc-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
              </marker>
            </defs>
            {geometry.map((g) => {
              const hot = isTouching(g);
              const dim = !!selected && !hot;
              return (
                <g key={g.id} className={`fc-edge ${hot ? "hot" : ""} ${dim ? "dim" : ""}`}>
                  <path d={g.d} fill="none" markerEnd="url(#fc-arrow)" />
                  {hot && (
                    <text x={g.labelX} y={g.labelY} textAnchor="middle" className="fc-edge-label">
                      {g.label}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>

          {flowchart.tiers.map((tier) => {
            const nodes = nodesByTier[tier.id] ?? [];
            if (!nodes.length) return null;
            return (
              <div key={tier.id} className="tier-lane">
                <div className="tier-title-row">
                  <h4>{tier.title}</h4>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{tier.description}</span>
                </div>
                <div className="nodes-row">
                  {nodes.map((node) => {
                    const isSelected = selectedId === node.id;
                    return (
                      <div
                        key={node.id}
                        ref={(el) => { nodeRefs.current[node.id] = el; }}
                        className={`flowchart-node-card ${isSelected ? "selected" : ""}`}
                        onClick={() => handleNodeClick(node)}
                        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), handleNodeClick(node))}
                        role="button"
                        tabIndex={0}
                        aria-pressed={isSelected}
                      >
                        <span className="node-badge-chip" style={{ background: node.badge_color }}>{node.tier_label}</span>
                        <strong>{node.label}</strong>
                        <p>{node.summary}</p>
                        <div className="node-actions">
                          <span>{isSelected ? (node.file_path ? "Click again to open code" : "Selected") : "Click to explain"}</span>
                          <ChevronRight size={14} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
