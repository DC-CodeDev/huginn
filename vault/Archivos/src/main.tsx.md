import { StrictMode, useState, useCallback, useMemo, useEffect } from "react";
import { createRoot } from "react-dom/client";
import NodeBoard from "./NodeBoard";
import { Home } from "./components/Home";
import { StudioView } from "./components/StudioView";
import { FolderView } from "./components/FolderView";
import { AppBar } from "./components/AppBar";
import { SettingsModal } from "./components/SettingsModal";
import { ProfileMenu } from "./components/ProfileMenu";
import { THEMES } from "./lib/theme";
import { ThemeContext } from "./lib/theme-context";
import type { ThemeCtx } from "./lib/theme-context";
import "./styles.css";

type View =
  | { kind: "home" }
  | { kind: "studio"; studioId: string }
  | { kind: "folder"; folderId: string; studioId: string }
  | { kind: "board"; boardId: string; backView: Exclude<View, { kind: "board" }> };

function App() {
  const [view, setView] = useState<View>({ kind: "home" });
  const [theme, setTheme] = useState("dark");
  const T = THEMES[theme] || THEMES.dark;
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
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

  const showBar = view.kind !== "board";

  const closeProfile = useCallback(() => {
    setProfileOpen(false);
    setView({ kind: "home" });
  }, []);

  const renderView = () => {
    switch (view.kind) {
    case "home":
      return (
        <>
          {showBar && <AppBar T={T} theme={theme} onToggleTheme={toggleTheme} onSettingsClick={() => { setSettingsOpen(true); setProfileOpen(false); }} onProfileClick={() => { setProfileOpen((v) => !v); setSettingsOpen(false); }} />}
          <Home onStudioClick={navigateStudio} />
          {settingsOpen && (
            <SettingsModal
              T={T} theme={theme} mode="app"
              onToggleTheme={toggleTheme}
              onClose={() => setSettingsOpen(false)}
            />
          )}
          {profileOpen && (
            <ProfileMenu T={T} theme={theme} onCloseProfile={closeProfile} onClose={() => setProfileOpen(false)} />
          )}
        </>
      );
    case "studio":
      return (
        <>
          {showBar && <AppBar T={T} theme={theme} onToggleTheme={toggleTheme} onSettingsClick={() => { setSettingsOpen(true); setProfileOpen(false); }} onProfileClick={() => { setProfileOpen((v) => !v); setSettingsOpen(false); }} />}
          <StudioView
            studioId={view.studioId}
            onBack={navigateHome}
            onFolderClick={(folderId) => navigateFolder(folderId, view.studioId)}
            onBoardClick={(boardId) => navigateBoard(boardId, view)}
          />
          {settingsOpen && (
            <SettingsModal
              T={T} theme={theme} mode="app"
              onToggleTheme={toggleTheme}
              onClose={() => setSettingsOpen(false)}
            />
          )}
          {profileOpen && (
            <ProfileMenu T={T} theme={theme} onCloseProfile={closeProfile} onClose={() => setProfileOpen(false)} />
          )}
        </>
      );
    case "folder":
      return (
        <>
          {showBar && <AppBar T={T} theme={theme} onToggleTheme={toggleTheme} onSettingsClick={() => { setSettingsOpen(true); setProfileOpen(false); }} onProfileClick={() => { setProfileOpen((v) => !v); setSettingsOpen(false); }} />}
          <FolderView
            folderId={view.folderId}
            studioId={view.studioId}
            onBack={() => navigateStudio(view.studioId)}
            onBoardClick={(boardId) => navigateBoard(boardId, view)}
          />
          {settingsOpen && (
            <SettingsModal
              T={T} theme={theme} mode="app"
              onToggleTheme={toggleTheme}
              onClose={() => setSettingsOpen(false)}
            />
          )}
          {profileOpen && (
            <ProfileMenu T={T} theme={theme} onCloseProfile={closeProfile} onClose={() => setProfileOpen(false)} />
          )}
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
    </ThemeContext.Provider>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
