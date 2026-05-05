import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, UserCircle, KeyRound, Pencil, ShieldOff } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { usersApi, type ClientRoleEntry } from "@/api/users";
import { clientsApi } from "@/api/clients";
import { useAuth } from "@/contexts/AuthContext";

const GLOBAL_ROLES = ["super_admin", "user"];
const CLIENT_ROLES = ["admin", "viewer"] as const;

function RoleBadge({ role }: { role: string }) {
  const variant =
    role === "super_admin" ? "destructive" : role === "admin" ? "default" : "secondary";
  return <Badge variant={variant}>{role}</Badge>;
}

interface ResetPasswordModalProps {
  userId: number;
  email: string;
  onClose: () => void;
}

function ResetPasswordModal({ userId, email, onClose }: ResetPasswordModalProps) {
  const [newPassword, setNewPassword] = useState("");
  const [temporary, setTemporary] = useState(true);
  const [error, setError] = useState("");
  const qc = useQueryClient();

  const reset = useMutation({
    mutationFn: () => usersApi.resetPassword(userId, { new_password: newPassword, temporary }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
    onError: () => setError("Failed to reset password."),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-base">Reset Password — {email}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <Label>New Password</Label>
            <Input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoFocus
            />
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={temporary}
              onChange={(e) => setTemporary(e.target.checked)}
              className="rounded"
            />
            Temporary — require change on next login
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex gap-2">
            <Button
              onClick={() => reset.mutate()}
              disabled={!newPassword || reset.isPending}
            >
              Reset Password
            </Button>
            <Button variant="outline" onClick={onClose}>Cancel</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

interface ResetMfaModalProps {
  userId: number;
  email: string;
  onClose: () => void;
}

function ResetMfaModal({ userId, email, onClose }: ResetMfaModalProps) {
  const [error, setError] = useState("");
  const qc = useQueryClient();

  const resetMfa = useMutation({
    mutationFn: () => usersApi.resetMfa(userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
    onError: () => setError("Failed to reset MFA."),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-base">Reset MFA — {email}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            This will clear the user's MFA enrolment. They will be prompted to set up a new
            authenticator device on their next login.
          </p>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex gap-2">
            <Button
              variant="destructive"
              onClick={() => resetMfa.mutate()}
              disabled={resetMfa.isPending}
            >
              {resetMfa.isPending ? "Resetting…" : "Reset MFA"}
            </Button>
            <Button variant="outline" onClick={onClose}>Cancel</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

interface EditRoleModalProps {
  userId: number;
  email: string;
  currentRole: string;
  currentClientRoles: ClientRoleEntry[];
  onClose: () => void;
}

function EditRoleModal({ userId, email, currentRole, currentClientRoles, onClose }: EditRoleModalProps) {
  const [globalRole, setGlobalRole] = useState(currentRole);
  const [clientRoles, setClientRoles] = useState<ClientRoleEntry[]>(currentClientRoles);
  const [error, setError] = useState("");
  const qc = useQueryClient();
  const { data: allClients } = useQuery({ queryKey: ["clients"], queryFn: clientsApi.list });

  const update = useMutation({
    mutationFn: () =>
      usersApi.update(userId, { role: globalRole, client_roles: clientRoles }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
    onError: () => setError("Failed to update user."),
  });

  const setClientRole = (slug: string, role: "admin" | "viewer") => {
    setClientRoles((prev) =>
      prev.map((cr) => (cr.slug === slug ? { ...cr, role } : cr))
    );
  };

  const addClient = (slug: string) => {
    if (!slug || clientRoles.some((cr) => cr.slug === slug)) return;
    setClientRoles((prev) => [...prev, { slug, role: "viewer" }]);
  };

  const removeClient = (slug: string) => {
    setClientRoles((prev) => prev.filter((cr) => cr.slug !== slug));
  };

  const unassigned = allClients?.filter((c) => !clientRoles.some((cr) => cr.slug === c.slug)) ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-base">Edit User — {email}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label>Global Role</Label>
            <select
              value={globalRole}
              onChange={(e) => setGlobalRole(e.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {GLOBAL_ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label>Client Access</Label>
            {clientRoles.length === 0 && (
              <p className="text-xs text-muted-foreground">No clients assigned.</p>
            )}
            {clientRoles.map((cr) => (
              <div key={cr.slug} className="flex items-center gap-2">
                <span className="flex-1 text-sm font-mono">{cr.slug}</span>
                <select
                  value={cr.role}
                  onChange={(e) => setClientRole(cr.slug, e.target.value as "admin" | "viewer")}
                  className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                >
                  {CLIENT_ROLES.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2 text-destructive hover:text-destructive"
                  onClick={() => removeClient(cr.slug)}
                >
                  ✕
                </Button>
              </div>
            ))}

            {unassigned.length > 0 && (
              <select
                defaultValue=""
                onChange={(e) => { addClient(e.target.value); e.target.value = ""; }}
                className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
              >
                <option value="" disabled>Add client…</option>
                {unassigned.map((c) => (
                  <option key={c.slug} value={c.slug}>{c.slug}</option>
                ))}
              </select>
            )}
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex gap-2">
            <Button onClick={() => update.mutate()} disabled={update.isPending}>
              Save
            </Button>
            <Button variant="outline" onClick={onClose}>Cancel</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function UserList() {
  const { user: me } = useAuth();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [clientRoles, setClientRoles] = useState<ClientRoleEntry[]>([]);
  const [resetTarget, setResetTarget] = useState<{ id: number; email: string } | null>(null);
  const [resetMfaTarget, setResetMfaTarget] = useState<{ id: number; email: string } | null>(null);
  const [editTarget, setEditTarget] = useState<{
    id: number; email: string; role: string; clientRoles: ClientRoleEntry[];
  } | null>(null);

  const { data: users } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  const { data: clients } = useQuery({ queryKey: ["clients"], queryFn: clientsApi.list });

  const createUser = useMutation({
    mutationFn: () => usersApi.create({ email, password, role, client_roles: clientRoles }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setShowForm(false);
      setEmail(""); setPassword(""); setRole("user"); setClientRoles([]);
    },
  });

  const deactivate = useMutation({
    mutationFn: (id: number) => usersApi.deactivate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  const addClientRole = (slug: string) => {
    if (!slug || clientRoles.some((cr) => cr.slug === slug)) return;
    setClientRoles((prev) => [...prev, { slug, role: "viewer" }]);
  };

  const updateClientRole = (slug: string, newRole: "admin" | "viewer") => {
    setClientRoles((prev) => prev.map((cr) => (cr.slug === slug ? { ...cr, role: newRole } : cr)));
  };

  const removeClientRole = (slug: string) => {
    setClientRoles((prev) => prev.filter((cr) => cr.slug !== slug));
  };

  const isSuperAdmin = me?.role === "super_admin";

  return (
    <div className="space-y-4">
      {resetTarget && (
        <ResetPasswordModal
          userId={resetTarget.id}
          email={resetTarget.email}
          onClose={() => setResetTarget(null)}
        />
      )}
      {editTarget && (
        <EditRoleModal
          userId={editTarget.id}
          email={editTarget.email}
          currentRole={editTarget.role}
          currentClientRoles={editTarget.clientRoles}
          onClose={() => setEditTarget(null)}
        />
      )}
      {resetMfaTarget && (
        <ResetMfaModal
          userId={resetMfaTarget.id}
          email={resetMfaTarget.email}
          onClose={() => setResetMfaTarget(null)}
        />
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Users</h1>
        {isSuperAdmin && (
          <Button size="sm" onClick={() => setShowForm((v) => !v)}>
            <Plus className="mr-2 h-4 w-4" /> New User
          </Button>
        )}
      </div>

      {showForm && (
        <Card>
          <CardHeader><CardTitle className="text-base">Create User</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Email</Label>
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>Password</Label>
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>Global Role</Label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {GLOBAL_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Client Access</Label>
              {clientRoles.map((cr) => (
                <div key={cr.slug} className="flex items-center gap-2">
                  <span className="flex-1 text-sm font-mono">{cr.slug}</span>
                  <select
                    value={cr.role}
                    onChange={(e) => updateClientRole(cr.slug, e.target.value as "admin" | "viewer")}
                    className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                  >
                    {CLIENT_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 px-2 text-destructive hover:text-destructive"
                    onClick={() => removeClientRole(cr.slug)}
                  >
                    ✕
                  </Button>
                </div>
              ))}
              <select
                defaultValue=""
                onChange={(e) => { addClientRole(e.target.value); e.target.value = ""; }}
                className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
              >
                <option value="" disabled>Add client…</option>
                {clients
                  ?.filter((c) => !clientRoles.some((cr) => cr.slug === c.slug))
                  .map((c) => <option key={c.slug} value={c.slug}>{c.slug}</option>)}
              </select>
            </div>

            <div className="flex gap-2">
              <Button onClick={() => createUser.mutate()} disabled={!email || !password || createUser.isPending}>
                Create
              </Button>
              <Button variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
            </div>
            {createUser.isError && (
              <p className="text-sm text-destructive">Failed to create user. Check for duplicate email.</p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Email</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Global Role</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Client Access</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="w-36 px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {users?.map((u) => (
                <tr key={u.id} className="border-b hover:bg-muted/20">
                  <td className="px-4 py-2 flex items-center gap-2">
                    <UserCircle className="h-4 w-4 text-muted-foreground" />
                    <span>
                      {u.email}
                      {u.must_change_password && (
                        <span className="ml-2 text-xs text-amber-600 font-medium">
                          (must change password)
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <RoleBadge role={u.role} />
                  </td>
                  <td className="px-4 py-2 text-muted-foreground text-xs space-y-1">
                    {u.client_roles.length === 0
                      ? "—"
                      : u.client_roles.map((cr) => (
                          <div key={cr.slug}>
                            <span className="font-mono">{cr.slug}</span>{" "}
                            <Badge variant={cr.role === "admin" ? "default" : "secondary"} className="text-xs">
                              {cr.role}
                            </Badge>
                          </div>
                        ))}
                  </td>
                  <td className="px-4 py-2">
                    <Badge variant={u.is_active ? "default" : "secondary"}>
                      {u.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-right space-x-1">
                    {isSuperAdmin && (
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Edit role & access"
                        onClick={() =>
                          setEditTarget({
                            id: u.id,
                            email: u.email,
                            role: u.role,
                            clientRoles: u.client_roles,
                          })
                        }
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                    )}
                    {isSuperAdmin && u.mfa_enabled && u.id !== me?.id && (
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Reset MFA"
                        className="text-amber-600 hover:text-amber-700"
                        onClick={() => setResetMfaTarget({ id: u.id, email: u.email })}
                      >
                        <ShieldOff className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      title="Reset password"
                      onClick={() => setResetTarget({ id: u.id, email: u.email })}
                    >
                      <KeyRound className="h-4 w-4" />
                    </Button>
                    {u.is_active && isSuperAdmin && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => deactivate.mutate(u.id)}
                      >
                        Deactivate
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}