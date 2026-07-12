import { StrictMode, useState, useCallback, useMemo, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import NodeBoard from "./NodeBoard";
import { Home } from "./components/Home";
import { StudioView } from "./components/StudioView";
import { FolderView } from "./components/FolderView";
import { NavBar } from "./components/NavBar";
import { PwaNoticeCenter } from "./components/PwaNoticeCenter";
import { SettingsModal } from "./components/SettingsModal";
import { ProfileMenu } from "./components/ProfileMenu";
import { Login, AuthLoader } from "./components/Login";
import { AuthProvider, useAuth } from "./lib/auth-context";
import { PwaProvider } from "./lib/pwa";
import { THEMES } from "./lib/theme";
import { ThemeContext } from "./lib/theme-context";
import type { ThemeCtx } from "./lib/theme-context";
import "bylgja/variants/pressable.css";
import "bylgja/variants/fadeScale.css";
import "bylgja/variants/modalBackdrop.css";
import "bylgja/variants/modalPanel.css";
import "bylgja/variants/tooltip.css";
import "./styles.css";

type View =
  | { kind: "home" }
  | { kind: "studio"; studioId: string }
  | { kind: "folder"; folderId: string; studioId: string }
  | { kind: "board"; boardId: string; backView: Exclude<View, { kind: "board" }> };

/*
 * CallbackHandler gestiona el retorno de Google OAuth.
 *
 * Cuando Google redirige al usuario de vuelta a /auth/callback?code=...,
 * este componente extrae el code del query string, lo envía al backend
 * via POST /api/auth/login, y una vez obtenido el usuario, limpia la URL
 * para que el ruteo condicional muestre Home automáticamente.
 */
function CallbackHandler({ onLogin }: { onLogin: (code: string) => Promise<void> }) {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    if (!code) return;
    // Reemplazar la URL sin recargar para ocultar el code y evitar
    // que un refresh manual re-envie el mismo code al backend.
    window.history.replaceState({}, "", "/");
    onLogin(code).catch((err) => {
      console.error(err);
    });
  }, [onLogin]);
  return <AuthLoader />;
}

function AppInner() {
  const { user, loading, login, logout } = useAuth();
  const [view, setView] = useState<View>({ kind: "home" });
  const [theme, setTheme] = useState("dark");
  const T = THEMES[theme] || THEMES.dark;
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const themeTransitionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const toggleTheme = useCallback(() => {
    if (themeTransitionTimerRef.current !== null) clearTimeout(themeTransitionTimerRef.current);
    document.documentElement.classList.add("theme-transitioning");
    setTheme((t) => (t === "dark" ? "light" : "dark"));
    themeTransitionTimerRef.current = setTimeout(() => {
      document.documentElement.classList.remove("theme-transitioning");
      themeTransitionTimerRef.current = null;
    }, 250);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const ctx = useMemo<ThemeCtx>(() => ({ theme, T, toggleTheme }), [theme, T, toggleTheme]);

  const navigateHome = useCallback(() => setView({ kind: "home" }), []);
  const navigateStudio = useCallback(
    (studioId: string) => { setView({ kind: "studio", studioId }); setSettingsOpen(false); setProfileOpen(false); },
    [],
  );
  const navigateFolder = useCallback(
    (folderId: string, studioId: string) => {
      setView({ kind: "folder", folderId, studioId });
      setSettingsOpen(false);
      setProfileOpen(false);
    },
    [],
  );
  const navigateBoard = useCallback(
    (boardId: string, backView: Exclude<View, { kind: "board" }>) =>
      setView({ kind: "board", boardId, backView }),
    [],
  );

  const closeProfile = useCallback(() => {
    setProfileOpen(false);
    setView({ kind: "home" });
  }, []);

  const navBar = user && view.kind !== "board" ? (
    <NavBar
      user={user}
      theme={theme}
      onHomeClick={navigateHome}
      onToggleTheme={toggleTheme}
      onSettingsClick={() => { setSettingsOpen(true); setProfileOpen(false); }}
      onProfileClick={() => { setProfileOpen((v) => !v); setSettingsOpen(false); }}
    />
  ) : null;

  const sharedModals = user ? (
    <>
      <SettingsModal
        show={settingsOpen}
        T={T} theme={theme} mode="app"
        onToggleTheme={toggleTheme}
        onClose={() => setSettingsOpen(false)}
      />
      <ProfileMenu show={profileOpen} T={T} theme={theme} user={user} menuRight="calc(60px + var(--safe-right))" onLogout={logout} onCloseProfile={closeProfile} onClose={() => setProfileOpen(false)} />
    </>
  ) : null;

  // ── Auth: determinar pantalla ─────────────────────────────────

  const renderView = () => {
    // 1. Mientras se resuelve la sesión inicial
    if (loading) {
      return <AuthLoader />;
    }

    // 2. Callback de Google OAuth: detectar ?code= en la URL
    const isCallback = window.location.pathname === "/auth/callback" &&
      new URLSearchParams(window.location.search).has("code");

    if (isCallback) {
      return <CallbackHandler onLogin={login} />;
    }

    // 3. Sin sesión → Login
    if (!user) {
      return <Login />;
    }

    // 4. Con sesión: render normal
    switch (view.kind) {
    case "home":
      return (
        <>
          {navBar}
          <Home onStudioClick={navigateStudio} />
          {sharedModals}
        </>
      );
    case "studio":
      return (
        <>
          {navBar}
          <StudioView
            studioId={view.studioId}
            onBack={navigateHome}
            onFolderClick={(folderId) => navigateFolder(folderId, view.studioId)}
            onBoardClick={(boardId) => navigateBoard(boardId, view)}
          />
          {sharedModals}
        </>
      );
    case "folder":
      return (
        <>
          {navBar}
          <FolderView
            folderId={view.folderId}
            studioId={view.studioId}
            onBack={() => navigateStudio(view.studioId)}
            onBoardClick={(boardId) => navigateBoard(boardId, view)}
          />
          {sharedModals}
        </>
      );
    case "board":
      return (
        <NodeBoard
          boardId={view.boardId}
          theme={theme}
          onToggleTheme={toggleTheme}
          onBack={() => {
            const back = view.backView;
            if (back.kind === "home") navigateHome();
            else if (back.kind === "studio") navigateStudio(back.studioId);
            else if (back.kind === "folder") navigateFolder(back.folderId, back.studioId);
            else navigateHome();
          }}
        />
      );
    }
  };

  return (
    <ThemeContext.Provider value={ctx}>
      {renderView()}
      <PwaNoticeCenter />
    </ThemeContext.Provider>
  );
}

function App() {
  return (
    <PwaProvider>
      <AuthProvider>
        <AppInner />
      </AuthProvider>
    </PwaProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
