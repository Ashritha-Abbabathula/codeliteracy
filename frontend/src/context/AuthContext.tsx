import React, { createContext, useContext, useEffect, useState } from "react";
import {
  getCurrentUser,
  guestLogin as apiGuestLogin,
  loginUser as apiLoginUser,
  logoutUser as apiLogoutUser,
  registerUser as apiRegisterUser,
  UserPublic,
  UserStats,
} from "../api/client";

interface AuthContextType {
  user: UserPublic | null;
  stats: UserStats | null;
  token: string | null;
  loading: boolean;
  login: (loginId: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  guestLogin: () => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [stats, setStats] = useState<UserStats | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("codeliteracy_token"));
  const [loading, setLoading] = useState<boolean>(true);

  async function fetchCurrentUser() {
    try {
      const data = await getCurrentUser();
      setUser(data.user);
      setStats(data.stats);
    } catch {
      localStorage.removeItem("codeliteracy_token");
      setToken(null);
      setUser(null);
      setStats(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (token) {
      fetchCurrentUser();
    } else {
      setLoading(false);
    }
  }, [token]);

  async function login(loginId: string, password: string) {
    const res = await apiLoginUser({ login_id: loginId, password });
    localStorage.setItem("codeliteracy_token", res.token);
    setToken(res.token);
    setUser(res.user);
    await fetchCurrentUser();
  }

  async function register(username: string, email: string, password: string) {
    const res = await apiRegisterUser({ username, email, password });
    localStorage.setItem("codeliteracy_token", res.token);
    setToken(res.token);
    setUser(res.user);
    await fetchCurrentUser();
  }

  async function guestLogin() {
    const res = await apiGuestLogin();
    localStorage.setItem("codeliteracy_token", res.token);
    setToken(res.token);
    setUser(res.user);
    await fetchCurrentUser();
  }

  async function logout() {
    try {
      await apiLogoutUser();
    } catch {
      // ignore
    }
    localStorage.removeItem("codeliteracy_token");
    setToken(null);
    setUser(null);
    setStats(null);
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        stats,
        token,
        loading,
        login,
        register,
        guestLogin,
        logout,
        refreshUser: fetchCurrentUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
