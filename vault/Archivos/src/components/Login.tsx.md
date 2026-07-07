import { Loader2 } from "lucide-react";

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

function buildGoogleUrl() {
  const redirectUri = `${window.location.origin}/auth/callback`;
  const params = new URLSearchParams({
    client_id: GOOGLE_CLIENT_ID,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: "openid email profile",
    access_type: "offline",
  });
  return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

export function Login() {
  if (!GOOGLE_CLIENT_ID) {
    return (
      <div
        className="w-full app-dvh app-safe-page flex items-center justify-center"
        style={{ background: "var(--bg)" }}
      >
        <div style={{ textAlign: "center", maxWidth: 400, fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" }}>
          <p style={{ color: "var(--sub)", fontSize: 13, lineHeight: 1.6, marginBottom: 6 }}>
            Falta <code style={{ background: "var(--card)", padding: "1px 6px", borderRadius: 4, fontSize: 12 }}>VITE_GOOGLE_CLIENT_ID</code> en las variables de entorno.
          </p>
          <p style={{ color: "var(--sub)", fontSize: 13, lineHeight: 1.6 }}>
            Creá un archivo <code style={{ background: "var(--card)", padding: "1px 6px", borderRadius: 4, fontSize: 12 }}>.env</code> en la raíz con ese valor.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="w-full app-dvh app-safe-page flex items-center justify-center"
      style={{ background: "var(--bg)" }}
    >
      <div
        style={{
          background: "var(--card)",
          border: "1px solid var(--card-border)",
          borderRadius: 16,
          padding: "44px 40px 40px",
          maxWidth: 360,
          width: "100%",
          textAlign: "center",
          fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
        }}
      >
        <div
          style={{
            width: 52,
            height: 52,
            borderRadius: 14,
            background: "var(--card)",
            border: "1px solid var(--card-border)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: 20,
            color: "var(--accent)",
          }}
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
          >
            <circle cx="12" cy="4.5" r="2.5" />
            <path d="m10.2 6.3-3.9 3.9" />
            <circle cx="4.5" cy="12" r="2.5" />
            <path d="M7 12h10" />
            <circle cx="19.5" cy="12" r="2.5" />
            <path d="m13.8 17.7 3.9-3.9" />
            <circle cx="12" cy="19.5" r="2.5" />
          </svg>
        </div>

        <h1
          style={{
            margin: 0,
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: "-0.02em",
            color: "var(--text)",
          }}
        >
          Huginn
        </h1>
        <p
          style={{
            margin: "8px 0 28px",
            fontSize: 13.5,
            lineHeight: 1.6,
            color: "var(--sub)",
          }}
        >
          Iniciá sesión para acceder a tus pizarras y estudios.
        </p>

        <a
          href={buildGoogleUrl()}
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            width: "100%",
            padding: "12px 20px",
            fontSize: 14,
            fontWeight: 600,
            color: "var(--text)",
            background: "var(--field)",
            border: "1px solid var(--card-border)",
            borderRadius: 10,
            cursor: "pointer",
            textDecoration: "none",
            transition: "background 0.15s",
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--btn-overlay, rgba(255,255,255,0.06))"; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--field)"; }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
          </svg>
          <span>Sign in with Google</span>
        </a>
      </div>
    </div>
  );
}

export function AuthLoader() {
  return (
    <div
      className="w-full app-dvh app-safe-page flex items-center justify-center"
      style={{ background: "var(--bg)" }}
    >
      <Loader2 className="animate-spin" size={28} style={{ color: "var(--sub)" }} />
    </div>
  );
}
