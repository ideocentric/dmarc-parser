import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useAuth } from "./AuthContext";

interface ClientContextValue {
  currentSlug: string | null;
  setCurrentSlug: (slug: string) => void;
}

const ClientContext = createContext<ClientContextValue | null>(null);

export function ClientProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [currentSlug, setCurrentSlugState] = useState<string | null>(() =>
    localStorage.getItem("current_client")
  );

  useEffect(() => {
    if (!user) return;
    // Auto-select the only client if the user has exactly one
    if (!currentSlug && user.client_slugs.length === 1) {
      setCurrentSlugState(user.client_slugs[0]);
    }
    // Clear selection if user no longer has access
    if (currentSlug && user.client_slugs.length > 0 && !user.client_slugs.includes(currentSlug)) {
      setCurrentSlugState(user.client_slugs[0]);
    }
  }, [user, currentSlug]);

  const setCurrentSlug = (slug: string) => {
    localStorage.setItem("current_client", slug);
    setCurrentSlugState(slug);
  };

  return (
    <ClientContext.Provider value={{ currentSlug, setCurrentSlug }}>
      {children}
    </ClientContext.Provider>
  );
}

export function useClient() {
  const ctx = useContext(ClientContext);
  if (!ctx) throw new Error("useClient must be used inside ClientProvider");
  return ctx;
}