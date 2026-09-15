import { FormEvent, useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError, AssistantResponse, askAssistant } from "../api/client";
import { QuizPanel } from "../components/QuizPanel";

interface Exchange {
  id: number;
  request: string;
  loading: boolean;
  response: AssistantResponse | null;
  error: string | null;
}

/** FR5 + FR6 + FR7: chat-style interface for requesting a fix/feature and watching the
 * assistant explain, step by step, what it did and why. */
export function AssistantChat() {
  const { repoId } = useParams<{ repoId: string }>();
  const [message, setMessage] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!repoId || !message.trim()) return;

    const id = Date.now();
    const request = message.trim();
    setMessage("");
    setExchanges((prev) => [...prev, { id, request, loading: true, response: null, error: null }]);

    try {
      const response = await askAssistant(repoId, request);
      setExchanges((prev) => prev.map((e) => (e.id === id ? { ...e, loading: false, response } : e)));
    } catch (err) {
      const errorMessage = err instanceof ApiError ? err.message : "Something went wrong.";
      setExchanges((prev) => prev.map((e) => (e.id === id ? { ...e, loading: false, error: errorMessage } : e)));
    }
  }

  return (
    <section>
      <h2>Ask for a fix or feature</h2>
      <p className="hint">
        Describe what you want changed. The assistant will explore the repo, make the change, and
        explain each step - it won't just apply a silent diff.
      </p>

      <div className="chat-log">
        {exchanges.map((exchange) => (
          <div key={exchange.id} className="exchange">
            <div className="bubble user">{exchange.request}</div>

            {exchange.loading && <div className="bubble assistant">Working on it…</div>}

            {exchange.error && <div className="bubble assistant error">{exchange.error}</div>}

            {exchange.response && (
              <div className="bubble assistant">
                <p>{exchange.response.summary}</p>
                <ol className="steps">
                  {exchange.response.steps.map((step, i) => (
                    <li key={i}>
                      <strong>{step.action}</strong>
                      <p>{step.explanation}</p>
                    </li>
                  ))}
                </ol>
                <p className="meta">
                  Files changed: {exchange.response.files_changed.join(", ") || "none"}
                  {exchange.response.commit_sha && ` · commit ${exchange.response.commit_sha.slice(0, 7)}`}
                </p>
              </div>
            )}

            {exchange.response && <QuizPanel changeId={exchange.response.change_id} />}
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="connect-form">
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="e.g. Add input validation to the connect_repository function"
        />
        <button type="submit" disabled={!message.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}
