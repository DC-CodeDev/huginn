import { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { registerUnauthorizedHandler } from "../api";

export interface User {
  id: string;
  email: string;
  name: string;
  avatar_url: string;
}

export interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (code: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const checkDone = useRef(false);

  useEffect(() => {
    if (checkDone.current) return;
    checkDone.current = true;
    fetch("/api/auth/me", { credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error("No autenticado");
        return res.json() as Promise<User>;
      })
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (code: string) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ code }),
    });
    if (!res.ok) throw new Error("Error al iniciar sesión");
    const userData = (await res.json()) as User;
    setUser(userData);
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    } catch {
      // ignorar errores de red en logout
    }
    setUser(null);
  }, []);

  // Registrar logout como handler global de 401 para que sesiones
  // expiradas cierren sesión automáticamente sin recargar la página.
  useEffect(() => {
    registerUnauthorizedHandler(logout);
    return () => registerUnauthorizedHandler(null);
  }, [logout]);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
