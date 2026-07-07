import { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import {
  fetchCurrentUser,
  loginWithGoogleCode,
  logoutSession,
  registerUnauthorizedHandler,
  type AuthUser as User,
} from "../api";

export type { User };

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
    fetchCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (code: string) => {
    const userData = await loginWithGoogleCode(code);
    setUser(userData);
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutSession();
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
