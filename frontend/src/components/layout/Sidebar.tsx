import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, FileText, Flag, Building2, Users, BarChart3, ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { canAccessClients, canAccessUsers } from "@/lib/permissions";
import type { UserMe } from "@/api/auth";

type NavItem = {
  to: string;
  label: string;
  icon: React.ElementType;
  allowed: (user: UserMe) => boolean;
};

const navItems: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, allowed: () => true },
  { to: "/reports",   label: "Reports",   icon: FileText,        allowed: () => true },
  { to: "/flags",     label: "Flags",     icon: Flag,            allowed: () => true },
  { to: "/analytics", label: "Analytics", icon: BarChart3,       allowed: () => true },
  { to: "/clients",   label: "Clients",   icon: Building2,       allowed: canAccessClients },
  { to: "/users",     label: "Users",     icon: Users,           allowed: canAccessUsers },
];

export function Sidebar() {
  const { user } = useAuth();

  return (
    <aside className="flex h-screen w-56 flex-col border-r bg-background">
      <div className="flex h-16 items-center gap-2 border-b px-4">
        <ShieldCheck className="h-6 w-6 text-primary" />
        <span className="font-semibold text-sm">DMARC Intelligence</span>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {user && navItems
          .filter((item) => item.allowed(user))
          .map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }: { isActive: boolean }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </NavLink>
          ))}
      </nav>
    </aside>
  );
}