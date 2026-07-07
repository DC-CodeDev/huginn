import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  buildApiUrl,
  fetchCurrentUser,
  loginWithGoogleCode,
  logoutSession,
} from "./api";

describe("api fetch policy", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("preserva rutas same-origin cuando VITE_API_URL no está definida", () => {
    expect(buildApiUrl("/api/boards")).toBe("/api/boards");
  });

  it("incluye credentials para llamadas autenticadas de boards", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));

    await api.listBoards();

    expect(fetchMock).toHaveBeenCalledWith("/api/boards", expect.objectContaining({
      credentials: "include",
    }));
  });

  it("incluye credentials para consultar el usuario actual", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({
      id: "u1",
      email: "user@example.com",
      name: "User",
      avatar_url: "",
    }), { status: 200 }));

    await fetchCurrentUser();

    expect(fetchMock).toHaveBeenCalledWith("/api/auth/me", expect.objectContaining({
      credentials: "include",
    }));
  });

  it("incluye credentials en login OAuth del backend", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({
      id: "u1",
      email: "user@example.com",
      name: "User",
      avatar_url: "",
    }), { status: 200 }));

    await loginWithGoogleCode("oauth-code");

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/login", expect.objectContaining({
      method: "POST",
      credentials: "include",
    }));
    expect(new Headers(options.headers).get("Content-Type")).toBe("application/json");
  });

  it("incluye credentials en logout", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await logoutSession();

    expect(fetchMock).toHaveBeenCalledWith("/api/auth/logout", expect.objectContaining({
      method: "POST",
      credentials: "include",
    }));
  });
});
