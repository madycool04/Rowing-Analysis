import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { athletesApi, authApi, getStoredToken, setStoredToken } from "../api/client";
import type { Athlete, User } from "../types";

interface AuthContextValue {
  user: User | null;
  athlete: Athlete | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  /** Lets pages that mutate the athlete profile (e.g. settings) refresh context state. */
  setAthlete: (athlete: Athlete) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [athlete, setAthleteState] = useState<Athlete | null>(null);
  // Starts true: on first mount we don't yet know whether a stored token is valid.
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setIsLoading(false);
      return;
    }
    // Persistent login (spec section 5): a stored token re-authenticates
    // the user automatically on app reload without requiring re-login.
    authApi
      .me()
      .then((me) => {
        setUser(me);
        // /auth/me doesn't return the athlete profile, so once we know the
        // token is valid we still need the athlete separately.
        return athletesApi.list();
      })
      .then((athletes) => {
        if (athletes.length > 0) setAthleteState(athletes[0]);
      })
      .catch(() => {
        setStoredToken(null);
        setUser(null);
        setAthleteState(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login(email, password);
    setStoredToken(res.access_token);
    setUser(res.user);
    setAthleteState(res.athlete);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const res = await authApi.register(email, password);
    setStoredToken(res.access_token);
    setUser(res.user);
    setAthleteState(res.athlete);
  }, []);

  const logout = useCallback(() => {
    setStoredToken(null);
    setUser(null);
    setAthleteState(null);
  }, []);

  const setAthlete = useCallback((updated: Athlete) => {
    setAthleteState(updated);
  }, []);

  const value: AuthContextValue = {
    user,
    athlete,
    isAuthenticated: user !== null,
    isLoading,
    login,
    register,
    logout,
    setAthlete,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
