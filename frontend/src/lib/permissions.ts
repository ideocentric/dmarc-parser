import type { UserMe } from "@/api/auth";

/** super_admin, or a user assigned to more than one client */
export function canAccessClients(user: UserMe | null): boolean {
  if (!user) return false;
  if (user.role === "super_admin") return true;
  return user.client_slugs.length > 1;
}

/** super_admin, or a user who is an admin on at least one client */
export function canAccessUsers(user: UserMe | null): boolean {
  if (!user) return false;
  if (user.role === "super_admin") return true;
  return user.client_roles.some((cr) => cr.role === "admin");
}