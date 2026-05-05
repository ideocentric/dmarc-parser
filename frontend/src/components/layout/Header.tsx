import { useState, useRef, useEffect } from "react";
import { LogOut, ChevronDown, KeyRound, UserCircle, ShieldCheck, ShieldOff } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/contexts/AuthContext";
import { useClient } from "@/contexts/ClientContext";
import { clientsApi } from "@/api/clients";

export function Header() {
  const { user, logout } = useAuth();
  const { currentSlug, setCurrentSlug } = useClient();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close the menu when clicking outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  // Super-admins are not in the user_clients junction table so their
  // user.client_slugs is always empty. Fetch the full client list instead.
  const { data: allClients } = useQuery({
    queryKey: ["clients"],
    queryFn: clientsApi.list,
    enabled: user?.role === "super_admin",
  });

  const handleLogout = () => {
    setMenuOpen(false);
    logout();
    navigate("/login");
  };

  const handleChangePassword = () => {
    setMenuOpen(false);
    navigate("/change-password");
  };

  const handleMfa = () => {
    setMenuOpen(false);
    navigate("/mfa-setup");
  };

  const clientOptions =
    user?.role === "super_admin"
      ? (allClients ?? []).map((c) => ({ slug: c.slug, label: c.name }))
      : user?.client_slugs.map((s) => ({ slug: s, label: s })) ?? [];

  const showSelector =
    user?.role === "super_admin" || (user?.client_slugs.length ?? 0) > 1;

  return (
    <header className="flex h-16 items-center justify-between border-b bg-background px-6">
      <div className="flex items-center gap-3">
        {user && showSelector && (
          <div className="flex items-center gap-2">
            <select
              value={currentSlug ?? ""}
              onChange={(e) => setCurrentSlug(e.target.value)}
              className="h-8 rounded-md border border-input bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {user.role === "super_admin" && (
                <option value="">— Select a client —</option>
              )}
              {clientOptions.map(({ slug, label }) => (
                <option key={slug} value={slug}>
                  {label}
                </option>
              ))}
            </select>
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          </div>
        )}
        {user?.role === "user" && !showSelector && currentSlug && (
          <span className="text-sm font-medium">{currentSlug}</span>
        )}
      </div>

      <div className="relative flex items-center" ref={menuRef}>
        <button
          onClick={() => setMenuOpen((v) => !v)}
          className="flex items-center gap-2 rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <UserCircle className="h-4 w-4" />
          <span>{user?.email}</span>
          <ChevronDown className={`h-3 w-3 transition-transform ${menuOpen ? "rotate-180" : ""}`} />
        </button>

        {menuOpen && (
          <div className="absolute right-0 top-full mt-1 w-52 rounded-md border bg-background shadow-lg z-50">
            <div className="border-b px-3 py-2">
              <p className="text-xs font-medium text-muted-foreground">Signed in as</p>
              <p className="truncate text-sm font-medium">{user?.email}</p>
            </div>
            {/* Only shown for local (password-based) accounts, not SSO-only */}
            {user?.has_password && (
              <button
                onClick={handleChangePassword}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                <KeyRound className="h-4 w-4" />
                Change Password
              </button>
            )}
            {user?.has_password && (
              user.mfa_required && user.mfa_enabled ? (
                // MFA is enforced and active — show a non-interactive badge
                <div className="flex w-full items-center gap-2 px-3 py-2 text-sm text-muted-foreground cursor-default select-none">
                  <ShieldCheck className="h-4 w-4 text-green-600" />
                  MFA active (enforced)
                </div>
              ) : (
                // MFA is optional, or not yet set up — show Set up / Disable
                !user.mfa_required && (
                  <button
                    onClick={handleMfa}
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
                  >
                    {user.mfa_enabled
                      ? <ShieldOff className="h-4 w-4 text-destructive" />
                      : <ShieldCheck className="h-4 w-4" />}
                    {user.mfa_enabled ? "Disable MFA" : "Set up MFA"}
                  </button>
                )
              )
            )}
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-accent transition-colors"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}