import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { LogIn, UserPlus, Zap, X } from "lucide-react";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose }) => {
  const { login, register, guestLogin } = useAuth();
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isRegister) {
        await register(username, email, password);
      } else {
        await login(username || email, password);
      }
      onClose();
    } catch (err: any) {
      setError(err?.message || "Authentication failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGuest() {
    setError(null);
    setLoading(true);
    try {
      await guestLogin();
      onClose();
    } catch (err: any) {
      setError(err?.message || "Failed to start guest session.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{isRegister ? "Create Your Account" : "Sign In to CodeLiteracy"}</h3>
          <button
            onClick={onClose}
            className="btn-secondary"
            style={{ padding: "0.3rem", borderRadius: "50%" }}
            title="Close"
          >
            <X size={18} />
          </button>
        </div>

        {error && <div className="quiz-feedback-box incorrect" style={{ marginBottom: "1rem" }}>{error}</div>}

        <form onSubmit={handleSubmit}>
          {isRegister && (
            <div className="form-group">
              <label>Username</label>
              <input
                type="text"
                className="input-text"
                style={{ width: "100%" }}
                required
                placeholder="e.g. devlearner"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
          )}

          <div className="form-group">
            <label>{isRegister ? "Email Address" : "Username or Email"}</label>
            <input
              type={isRegister ? "email" : "text"}
              className="input-text"
              style={{ width: "100%" }}
              required
              placeholder={isRegister ? "you@example.com" : "Username or email"}
              value={isRegister ? email : username}
              onChange={(e) => (isRegister ? setEmail(e.target.value) : setUsername(e.target.value))}
            />
          </div>

          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              className="input-text"
              style={{ width: "100%" }}
              required
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <button
            type="submit"
            className="btn-primary"
            style={{ width: "100%", marginTop: "0.5rem" }}
            disabled={loading}
          >
            {isRegister ? <UserPlus size={16} /> : <LogIn size={16} />}
            {loading ? "Processing..." : isRegister ? "Create Account" : "Sign In"}
          </button>
        </form>

        <div style={{ textAlign: "center", margin: "1.25rem 0", color: "var(--text-muted)", fontSize: "0.8rem" }}>
          ── OR ──
        </div>

        <button
          type="button"
          className="btn-secondary"
          style={{ width: "100%", borderColor: "var(--accent)", color: "#c7d2fe" }}
          onClick={handleGuest}
          disabled={loading}
        >
          <Zap size={16} color="var(--accent)" />
          ⚡ 1-Click Instant Guest Demo
        </button>

        <div style={{ marginTop: "1.25rem", textAlign: "center", fontSize: "0.84rem", color: "var(--text-secondary)" }}>
          {isRegister ? "Already have an account?" : "Don't have an account yet?"}{" "}
          <button
            type="button"
            style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", textDecoration: "underline", padding: 0, fontSize: "0.84rem" }}
            onClick={() => {
              setIsRegister(!isRegister);
              setError(null);
            }}
          >
            {isRegister ? "Sign In" : "Sign Up"}
          </button>
        </div>
      </div>
    </div>
  );
};
