import { createContext, useContext, useEffect, useMemo, useState } from "react";

const TOKEN_KEY = "interviewinsight_token";
const REFRESH_TOKEN_KEY = "interviewinsight_refresh_token";
const USER_KEY = "interviewinsight_user";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const AuthContext = createContext(null);

function loadInitialAuth() {
  try {
    const token = window.localStorage.getItem(TOKEN_KEY) || "";
    const refreshToken = window.localStorage.getItem(REFRESH_TOKEN_KEY) || "";
    const rawUser = window.localStorage.getItem(USER_KEY);
    const user = rawUser ? JSON.parse(rawUser) : null;
    return { token, refreshToken, user };
  } catch {
    return { token: "", refreshToken: "", user: null };
  }
}

export function AuthProvider({ children }) {
  const initial = loadInitialAuth();
  const [token, setToken] = useState(initial.token);
  const [refreshToken, setRefreshToken] = useState(initial.refreshToken);
  const [user, setUser] = useState(initial.user);
  const [authReady, setAuthReady] = useState(false);

  function setAuthSession(nextToken, nextUser, nextRefreshToken = "") {
    setToken(nextToken || "");
    setRefreshToken(nextRefreshToken || "");
    setUser(nextUser || null);
    if (nextToken) {
      window.localStorage.setItem(TOKEN_KEY, nextToken);
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
    }
    if (nextRefreshToken) {
      window.localStorage.setItem(REFRESH_TOKEN_KEY, nextRefreshToken);
    } else {
      window.localStorage.removeItem(REFRESH_TOKEN_KEY);
    }
    if (nextUser) {
      window.localStorage.setItem(USER_KEY, JSON.stringify(nextUser));
    } else {
      window.localStorage.removeItem(USER_KEY);
    }
  }

  async function refreshAccessToken() {
    if (!refreshToken) {
      setAuthSession("", null, "");
      return false;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refreshToken }),
      });
      if (!response.ok) {
        setAuthSession("", null, "");
        return false;
      }
      const payload = await response.json();
      setAuthSession(payload.accessToken || payload.token, payload.user, payload.refreshToken || refreshToken);
      return true;
    } catch {
      return false;
    }
  }

  async function logout() {
    const outgoingRefreshToken = refreshToken;
    setAuthSession("", null, "");
    if (!outgoingRefreshToken) {
      return;
    }
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refreshToken: outgoingRefreshToken }),
      });
    } catch {
      // ignore logout network failures
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function validateSession() {
      if (!token || !user?.userId) {
        if (!cancelled) {
          setAuthReady(true);
        }
        return;
      }

      try {
        const response = await fetch(`${API_BASE_URL}/auth/me`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (!response.ok) {
          if (response.status === 401) {
            const refreshed = await refreshAccessToken();
            if (!refreshed) {
              if (!cancelled) {
                setAuthSession("", null, "");
              }
              return;
            }
          } else {
            if (!cancelled) {
              setAuthSession("", null, "");
            }
            return;
          }
        }
        const retryResponse = response.ok
          ? response
          : await fetch(`${API_BASE_URL}/auth/me`, {
              headers: {
                Authorization: `Bearer ${window.localStorage.getItem(TOKEN_KEY) || ""}`,
              },
            });
        if (!retryResponse.ok) {
          if (!cancelled) {
            setAuthSession("", null, "");
          }
          return;
        }
        const payload = await retryResponse.json();
        if (!cancelled && payload?.userId) {
          const effectiveToken = window.localStorage.getItem(TOKEN_KEY) || token;
          const effectiveRefresh = window.localStorage.getItem(REFRESH_TOKEN_KEY) || refreshToken;
          setAuthSession(effectiveToken, payload, effectiveRefresh);
        }
      } catch {
        // Ignore transient network issues and keep current auth session.
      } finally {
        if (!cancelled) {
          setAuthReady(true);
        }
      }
    }

    validateSession();
    return () => {
      cancelled = true;
    };
  }, [token, refreshToken, user?.userId]);

  const value = useMemo(
    () => ({
      token,
      refreshToken,
      user,
      authReady,
      isAuthenticated: Boolean(token && user?.userId),
      setAuthSession,
      refreshAccessToken,
      logout,
    }),
    [token, refreshToken, user, authReady]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
