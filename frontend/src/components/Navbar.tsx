import React, { useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen, Code2, LogIn, LogOut, User as UserIcon } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { AuthModal } from "./AuthModal";

export const Navbar: React.FC = () => {
  const { user, stats, logout } = useAuth();
  const [authModalOpen, setAuthModalOpen] = useState(false);

  return (
    <>
      <header className="navbar">
        <div className="navbar-inner">
          <Link to="/" className="navbar-brand">
            <div className="logo-badge">
              <Code2 size={20} />
            </div>
            <div className="brand-text">
              <h1>CodeLiteracy</h1>
              <span className="brand-tag">Adaptive Codebase Learning Platform</span>
            </div>
          </Link>

          <div className="navbar-actions">
            <Link to="/notebook" className="nav-link-btn">
              <BookOpen size={16} color="var(--accent)" />
              <span>My Notebook</span>
              {stats && stats.notebook_count > 0 && (
                <span className="counter-badge">{stats.notebook_count}</span>
              )}
            </Link>

            {user ? (
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <div className="user-badge">
                  <UserIcon size={14} />
                  <span>{user.username}</span>
                  {user.is_guest && <span style={{ fontSize: "0.68rem", opacity: 0.8 }}>(Guest)</span>}
                </div>
                <button
                  onClick={() => logout()}
                  className="btn-secondary"
                  style={{ padding: "0.45rem 0.75rem", fontSize: "0.82rem" }}
                  title="Sign Out"
                >
                  <LogOut size={14} />
                  <span>Logout</span>
                </button>
              </div>
            ) : (
              <button
                onClick={() => setAuthModalOpen(true)}
                className="btn-primary"
                style={{ padding: "0.45rem 0.9rem", fontSize: "0.85rem" }}
              >
                <LogIn size={15} />
                <span>Sign In / Demo</span>
              </button>
            )}
          </div>
        </div>
      </header>

      <AuthModal isOpen={authModalOpen} onClose={() => setAuthModalOpen(false)} />
    </>
  );
};
