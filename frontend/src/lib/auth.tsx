import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, api } from "./api";
import type { ProfileUpdate, RegisterInput, Student } from "./types";

interface AuthValue {
  user: Student | null;
  /** True until the first "who am I?" answer arrives. */
  checking: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (update: ProfileUpdate) => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Student | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let live = true;
    api.me().then(
      (u) => live && (setUser(u), setChecking(false)),
      (e) => {
        // 401 just means "not signed in". Anything else (server down) also leaves us signed out; the login page shows the error.
        if (!(e instanceof ApiError) || e.status !== 401) console.warn("could not check session:", e);
        if (live) setChecking(false);
      },
    );
    return () => {
      live = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => setUser(await api.login(email, password)), []);
  const register = useCallback(
    async (input: RegisterInput) => {
      await api.register(input);
      await login(input.email, input.password);
    },
    [login],
  );
  const logout = useCallback(async () => {
    await api.logout();
    setUser(null);
  }, []);
  const updateProfile = useCallback(async (update: ProfileUpdate) => setUser(await api.updateProfile(update)), []);

  const value = useMemo(() => ({ user, checking, login, register, logout, updateProfile }), [user, checking, login, register, logout, updateProfile]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
