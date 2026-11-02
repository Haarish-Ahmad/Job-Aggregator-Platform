import { ApiError, api, apiBase } from "./api";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  window.__APP_CONFIG__ = { apiBase: "/api" };
});
afterEach(() => vi.unstubAllGlobals());

const json = (body: unknown, init: ResponseInit = {}) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" }, ...init });

describe("apiBase", () => {
  it("comes from the runtime config and loses trailing slashes", () => {
    window.__APP_CONFIG__ = { apiBase: "https://api.example.com/v1//" };
    expect(apiBase()).toBe("https://api.example.com/v1");
  });
  it("defaults to /api", () => {
    window.__APP_CONFIG__ = undefined;
    expect(apiBase()).toBe("/api");
  });
});

describe("requests", () => {
  it("send cookies and hit the configured base", async () => {
    fetchMock.mockResolvedValue(json({ id: 1 }));
    await api.me();
    expect(fetchMock).toHaveBeenCalledWith("/api/me", expect.objectContaining({ credentials: "include" }));
  });
  it("send JSON bodies", async () => {
    fetchMock.mockResolvedValue(json({ id: 1 }));
    await api.login("a@b.co", "pw");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/login");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ email: "a@b.co", password: "pw" });
    expect(init.headers["Content-Type"]).toBe("application/json");
  });
});

describe("jobs()", () => {
  it("reads the total from X-Total-Count and sends only the filters that are set", async () => {
    fetchMock.mockResolvedValue(json([{ id: 1 }], { headers: { "Content-Type": "application/json", "X-Total-Count": "57" } }));
    const page = await api.jobs({ q: "python", scope: "india_remote", sort: "newest", limit: 20, offset: 40, job_type: "", hide_expired: false, grad_year: undefined });
    expect(page.total).toBe(57);
    const url = new URL(fetchMock.mock.calls[0][0], "http://x");
    expect(Object.fromEntries(url.searchParams)).toEqual({ q: "python", scope: "india_remote", sort: "newest", limit: "20", offset: "40" });
  });
  it("falls back to the page length without the header", async () => {
    fetchMock.mockResolvedValue(json([{ id: 1 }, { id: 2 }]));
    expect((await api.jobs({})).total).toBe(2);
  });
  it("sends hide_expired only when on", async () => {
    fetchMock.mockResolvedValue(json([]));
    await api.jobs({ hide_expired: true });
    expect(fetchMock.mock.calls[0][0]).toContain("hide_expired=true");
  });
});

describe("errors", () => {
  it("uses FastAPI's detail string", async () => {
    fetchMock.mockResolvedValue(json({ detail: "Invalid user account or password" }, { status: 401 }));
    await expect(api.login("a@b.co", "x")).rejects.toMatchObject({ status: 401, message: "Invalid user account or password" });
  });
  it("flattens validation errors", async () => {
    fetchMock.mockResolvedValue(json({ detail: [{ loc: ["body", "password"], msg: "String should have at least 8 characters" }] }, { status: 422 }));
    await expect(api.register({ name: "A", email: "a@b.co", password: "x", grad_year: 2026, skills: [] })).rejects.toThrow("password: String should have at least 8 characters");
  });
  it("explains a dead server in plain words", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const err = await api.me().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 0 });
    expect(err.message).toMatch(/can't reach the server/i);
  });
  it("handles non-JSON error bodies", async () => {
    fetchMock.mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 }));
    await expect(api.me()).rejects.toMatchObject({ status: 502, message: "The server had a problem. Please try again." });
  });
  it("gives 403 a clear message", async () => {
    fetchMock.mockResolvedValue(json({}, { status: 403 }));
    await expect(api.skillGap()).rejects.toMatchObject({ status: 403, message: "You don't have access to this." });
  });
});
