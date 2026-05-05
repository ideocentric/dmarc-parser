import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Building2, Globe, Mail, CheckCircle, XCircle, RefreshCw, ShieldCheck, Download, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { clientsApi, type Client } from "@/api/clients";
import { imapApi, type ImapConfig } from "@/api/imap";
import { useAuth } from "@/contexts/AuthContext";

// ---------------------------------------------------------------------------
// Security tab — MFA policy (client_admin) + name/status (super_admin)
// ---------------------------------------------------------------------------
interface SecurityPanelProps {
  client: Client;
  isSuperAdmin: boolean;
}

function SecurityPanel({ client, isSuperAdmin }: SecurityPanelProps) {
  const qc = useQueryClient();

  const [name, setName] = useState(client.name);
  const [isActive, setIsActive] = useState(client.is_active);
  const [mfaAdmins, setMfaAdmins] = useState(client.mfa_required_admins);
  const [mfaViewers, setMfaViewers] = useState(client.mfa_required_viewers);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const save = useMutation({
    mutationFn: async () => {
      const calls: Promise<unknown>[] = [];
      if (isSuperAdmin && (name !== client.name || isActive !== client.is_active)) {
        calls.push(clientsApi.update(client.slug, { name, is_active: isActive }));
      }
      if (mfaAdmins !== client.mfa_required_admins || mfaViewers !== client.mfa_required_viewers) {
        calls.push(clientsApi.updateMfaPolicy(client.slug, {
          mfa_required_admins: mfaAdmins,
          mfa_required_viewers: mfaViewers,
        }));
      }
      await Promise.all(calls);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clients"] });
      setError("");
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
    onError: () => setError("Failed to save changes."),
  });

  return (
    <div className="space-y-5">
      {isSuperAdmin && (
        <div className="space-y-3">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Client Settings</p>
          <div className="space-y-1">
            <Label className="text-xs">Display Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="max-w-sm" />
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="rounded"
            />
            Active
          </label>
        </div>
      )}

      <div className="space-y-3">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">MFA Requirements</p>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={mfaAdmins}
            onChange={(e) => setMfaAdmins(e.target.checked)}
            className="rounded"
          />
          Require MFA for client admins
        </label>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={mfaViewers}
            onChange={(e) => setMfaViewers(e.target.checked)}
            className="rounded"
          />
          Require MFA for viewers
        </label>
        <p className="text-xs text-muted-foreground">
          Users with access to any client requiring MFA for their role must enrol before using the platform.
          Changes take effect on the user's next login.
        </p>
      </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
      {saved && <p className="text-sm text-green-600">Saved.</p>}
      <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
        {save.isPending ? "Saving…" : "Save"}
      </Button>

      {/* Danger Zone — super_admin only */}
      {isSuperAdmin && <DangerZone client={client} qc={qc} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Danger Zone — export and purge (super_admin only)
// ---------------------------------------------------------------------------
function DangerZone({ client, qc }: { client: Client; qc: ReturnType<typeof useQueryClient> }) {
  const [purgeSlug, setPurgeSlug] = useState("");
  const [purgeError, setPurgeError] = useState("");
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const blob = await clientsApi.exportClient(client.slug);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${client.slug}-export-${new Date().toISOString().split("T")[0]}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setPurgeError("Export failed — check server logs.");
    } finally {
      setExporting(false);
    }
  };

  const purge = useMutation({
    mutationFn: () => clientsApi.purgeClient(client.slug, purgeSlug),
    onSuccess: (summary) => {
      qc.invalidateQueries({ queryKey: ["clients"] });
      const deactivated = summary.deactivated_users.length
        ? ` Deactivated: ${summary.deactivated_users.join(", ")}.`
        : "";
      // Client card will disappear from the list; log summary to console for reference
      console.info("Purge summary:", summary);
      alert(`Client '${summary.slug}' purged.${deactivated}`);
    },
    onError: () => setPurgeError("Purge failed — check server logs."),
  });

  return (
    <div className="rounded-md border border-destructive/40 p-4 space-y-4">
      <p className="text-xs font-medium text-destructive uppercase tracking-wide">Danger Zone</p>

      {/* Export */}
      <div className="space-y-1">
        <p className="text-sm font-medium">Export client data</p>
        <p className="text-xs text-muted-foreground">
          Download a ZIP of all reports, records, flags, and configuration in JSON/CSV format.
          Passwords and secrets are not included.
        </p>
        <Button
          size="sm"
          variant="outline"
          onClick={handleExport}
          disabled={exporting}
          className="mt-1"
        >
          <Download className="mr-2 h-3 w-3" />
          {exporting ? "Preparing…" : "Export Data"}
        </Button>
      </div>

      <div className="border-t" />

      {/* Purge */}
      <div className="space-y-2">
        <p className="text-sm font-medium">Purge client</p>
        <p className="text-xs text-muted-foreground">
          Permanently deletes <strong>all</strong> data for this client. Users with no other
          client access will be deactivated. This cannot be undone.
        </p>
        <div className="flex gap-2 items-center">
          <input
            type="text"
            placeholder={`Type "${client.slug}" to confirm`}
            value={purgeSlug}
            onChange={(e) => { setPurgeSlug(e.target.value); setPurgeError(""); }}
            className="h-8 rounded-md border border-input bg-background px-3 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button
            size="sm"
            variant="destructive"
            disabled={purgeSlug !== client.slug || purge.isPending}
            onClick={() => purge.mutate()}
          >
            <Trash2 className="mr-2 h-3 w-3" />
            {purge.isPending ? "Purging…" : "Purge Client"}
          </Button>
        </div>
        {purgeError && <p className="text-xs text-destructive">{purgeError}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mail ingestion configuration panel
// ---------------------------------------------------------------------------
const COMMON_DEFAULTS = { inbox_folder: "INBOX", processed_folder: "DMARC-Processed", poll_interval_minutes: 15 };
const IMAP_DEFAULTS   = { auth_type: "imap" as const, host: "", port: 993, use_ssl: true, username: "", password: "" };
const O365_DEFAULTS   = { auth_type: "office365" as const, username: "", oauth2_tenant_id: "", oauth2_client_id: "", oauth2_client_secret: "" };

function ImapPanel({ slug }: { slug: string }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [authType, setAuthType] = useState<"imap" | "office365">("imap");
  const [imapForm, setImapForm]   = useState({ ...IMAP_DEFAULTS, ...COMMON_DEFAULTS });
  const [o365Form, setO365Form]   = useState({ ...O365_DEFAULTS, ...COMMON_DEFAULTS });
  const [testResult, setTestResult] = useState<string | null>(null);

  const { data: config, isLoading } = useQuery<ImapConfig | null>({
    queryKey: ["imap", slug],
    queryFn: () => imapApi.get(slug).catch((e) => e.response?.status === 404 ? null : Promise.reject(e)),
  });

  const startEditing = () => {
    if (config) {
      setAuthType(config.auth_type);
      if (config.auth_type === "office365") {
        setO365Form({
          auth_type: "office365",
          username: config.username,
          oauth2_tenant_id: config.oauth2_tenant_id ?? "",
          oauth2_client_id: config.oauth2_client_id ?? "",
          oauth2_client_secret: "",
          inbox_folder: config.inbox_folder,
          processed_folder: config.processed_folder ?? "",
          poll_interval_minutes: config.poll_interval_minutes,
        });
      } else {
        setImapForm({
          auth_type: "imap",
          host: config.host,
          port: config.port,
          use_ssl: config.use_ssl,
          username: config.username,
          password: "",
          inbox_folder: config.inbox_folder,
          processed_folder: config.processed_folder ?? "",
          poll_interval_minutes: config.poll_interval_minutes,
        });
      }
    }
    setEditing(true);
  };

  const save = useMutation({
    mutationFn: () => {
      const common = {
        inbox_folder: authType === "imap" ? imapForm.inbox_folder : o365Form.inbox_folder,
        processed_folder: authType === "imap" ? imapForm.processed_folder || null : o365Form.processed_folder || null,
        poll_interval_minutes: authType === "imap" ? imapForm.poll_interval_minutes : o365Form.poll_interval_minutes,
      };
      if (config) {
        const patch = authType === "imap"
          ? { ...common, host: imapForm.host, port: imapForm.port, use_ssl: imapForm.use_ssl, username: imapForm.username, ...(imapForm.password ? { password: imapForm.password } : {}) }
          : { ...common, username: o365Form.username, oauth2_tenant_id: o365Form.oauth2_tenant_id, oauth2_client_id: o365Form.oauth2_client_id, ...(o365Form.oauth2_client_secret ? { oauth2_client_secret: o365Form.oauth2_client_secret } : {}) };
        return imapApi.update(slug, patch);
      }
      if (authType === "office365") {
        return imapApi.create(slug, { auth_type: "office365", username: o365Form.username, oauth2_tenant_id: o365Form.oauth2_tenant_id, oauth2_client_id: o365Form.oauth2_client_id, oauth2_client_secret: o365Form.oauth2_client_secret, ...common });
      }
      return imapApi.create(slug, { auth_type: "imap", host: imapForm.host, port: imapForm.port, use_ssl: imapForm.use_ssl, username: imapForm.username, password: imapForm.password, ...common });
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["imap", slug] }); setEditing(false); setTestResult(null); },
  });

  const remove   = useMutation({ mutationFn: () => imapApi.delete(slug), onSuccess: () => qc.invalidateQueries({ queryKey: ["imap", slug] }) });
  const testConn = useMutation({ mutationFn: () => imapApi.test(slug), onSuccess: (r) => setTestResult(`${r.status === "ok" ? "✓" : "✗"} ${r.message}`) });
  const poll     = useMutation({ mutationFn: () => imapApi.poll(slug), onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["imap", slug] }); setTestResult(r.message); } });

  if (isLoading) return <p className="text-xs text-muted-foreground">Loading config…</p>;

  // ── Summary view ─────────────────────────────────────────────────────────
  if (config && !editing) {
    const typeLabel = config.auth_type === "office365" ? "Microsoft 365 (OAuth2)" : "IMAP";
    const summary = config.auth_type === "office365"
      ? `${config.username} · App: ${config.oauth2_client_id?.slice(0, 8)}…`
      : `${config.username}@${config.host}:${config.port}`;

    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm space-y-0.5">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs">{typeLabel}</Badge>
              <p className="font-medium">{summary}</p>
            </div>
            <p className="text-xs text-muted-foreground">
              Polls every {config.poll_interval_minutes} min ·{" "}
              {config.last_polled_at ? `Last polled ${new Date(config.last_polled_at).toLocaleString()}` : "Never polled"}
            </p>
            {config.last_poll_status && (
              <div className="flex items-center gap-1 text-xs">
                {config.last_poll_status === "ok"
                  ? <CheckCircle className="h-3 w-3 text-green-600" />
                  : <XCircle className="h-3 w-3 text-red-600" />}
                <span className="text-muted-foreground">{config.last_poll_message}</span>
              </div>
            )}
          </div>
          <Badge variant={config.is_active ? "default" : "secondary"}>
            {config.is_active ? "Active" : "Paused"}
          </Badge>
        </div>
        {testResult && <p className="text-xs font-mono bg-muted rounded p-2">{testResult}</p>}
        <div className="flex gap-2 flex-wrap">
          <Button size="sm" variant="outline" onClick={startEditing}>Edit</Button>
          <Button size="sm" variant="outline" onClick={() => testConn.mutate()} disabled={testConn.isPending}>Test Connection</Button>
          <Button size="sm" variant="outline" onClick={() => poll.mutate()} disabled={poll.isPending}>
            <RefreshCw className="mr-1 h-3 w-3" /> Poll Now
          </Button>
          <Button size="sm" variant="outline" onClick={() => imapApi.update(slug, { is_active: !config.is_active }).then(() => qc.invalidateQueries({ queryKey: ["imap", slug] }))}>
            {config.is_active ? "Pause" : "Resume"}
          </Button>
          <Button size="sm" variant="ghost" className="text-destructive" onClick={() => remove.mutate()}>Remove</Button>
        </div>
      </div>
    );
  }

  // ── Edit / create form ────────────────────────────────────────────────────
  const f = authType === "imap" ? imapForm : o365Form;
  const setF = authType === "imap"
    ? (v: Partial<typeof imapForm>) => setImapForm((p) => ({ ...p, ...v }))
    : (v: Partial<typeof o365Form>) => setO365Form((p) => ({ ...p, ...v }));

  return (
    <div className="space-y-4">
      {!config && !editing && (
        <Button size="sm" variant="outline" onClick={startEditing}>
          <Mail className="mr-2 h-3 w-3" /> Configure Mail Ingestion
        </Button>
      )}
      {editing && (
        <>
          {/* Auth type selector */}
          {!config && (
            <div className="flex gap-2">
              {(["imap", "office365"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setAuthType(t)}
                  className={`flex-1 rounded-md border px-3 py-2 text-xs font-medium transition-colors ${
                    authType === t
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input text-muted-foreground hover:bg-accent"
                  }`}
                >
                  {t === "imap" ? "Standard IMAP" : "Microsoft 365 (OAuth2)"}
                </button>
              ))}
            </div>
          )}

          {/* Office 365 hint */}
          {authType === "office365" && (
            <p className="text-xs text-muted-foreground bg-muted rounded p-2 leading-relaxed">
              Requires an Azure AD app registration with <strong>IMAP.AccessAsApp</strong> application
              permission (admin consent granted) and Exchange Online mailbox permission granted to the
              service principal. Host is fixed to <code>outlook.office365.com:993</code>.
            </p>
          )}

          <div className="grid grid-cols-2 gap-3">
            {/* Mailbox address — both types */}
            <div className="col-span-2 space-y-1">
              <Label className="text-xs">{authType === "office365" ? "Shared Mailbox Address" : "Username"}</Label>
              <Input
                placeholder={authType === "office365" ? "dmarc@yourfirm.com" : "user@example.com"}
                value={f.username}
                onChange={(e) => setF({ username: e.target.value } as any)}
              />
            </div>

            {/* Standard IMAP fields */}
            {authType === "imap" && (
              <>
                <div className="space-y-1">
                  <Label className="text-xs">Host</Label>
                  <Input placeholder="imap.gmail.com" value={(f as typeof imapForm).host} onChange={(e) => setF({ host: e.target.value } as any)} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Port</Label>
                  <Input type="number" value={(f as typeof imapForm).port} onChange={(e) => setF({ port: Number(e.target.value) } as any)} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Password</Label>
                  <Input type="password" placeholder={config ? "Leave blank to keep current" : ""} value={(f as typeof imapForm).password} onChange={(e) => setF({ password: e.target.value } as any)} />
                </div>
                <div className="flex items-center gap-2 pt-5">
                  <input type="checkbox" id={`ssl-${slug}`} checked={(f as typeof imapForm).use_ssl} onChange={(e) => setF({ use_ssl: e.target.checked } as any)} />
                  <Label htmlFor={`ssl-${slug}`} className="text-xs">Use SSL/TLS</Label>
                </div>
              </>
            )}

            {/* Office 365 OAuth2 fields */}
            {authType === "office365" && (
              <>
                <div className="col-span-2 space-y-1">
                  <Label className="text-xs">Tenant ID</Label>
                  <Input placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" value={(f as typeof o365Form).oauth2_tenant_id} onChange={(e) => setF({ oauth2_tenant_id: e.target.value } as any)} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Client ID (App Registration)</Label>
                  <Input placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" value={(f as typeof o365Form).oauth2_client_id} onChange={(e) => setF({ oauth2_client_id: e.target.value } as any)} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Client Secret</Label>
                  <Input type="password" placeholder={config ? "Leave blank to keep current" : ""} value={(f as typeof o365Form).oauth2_client_secret} onChange={(e) => setF({ oauth2_client_secret: e.target.value } as any)} />
                </div>
              </>
            )}

            {/* Common fields — both types */}
            <div className="space-y-1">
              <Label className="text-xs">Inbox Folder</Label>
              <Input value={f.inbox_folder} onChange={(e) => setF({ inbox_folder: e.target.value } as any)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Processed Folder (blank = mark read)</Label>
              <Input value={f.processed_folder ?? ""} onChange={(e) => setF({ processed_folder: e.target.value } as any)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Poll interval (minutes)</Label>
              <Input type="number" min={5} value={f.poll_interval_minutes} onChange={(e) => setF({ poll_interval_minutes: Number(e.target.value) } as any)} />
            </div>
          </div>

          <div className="flex gap-2">
            <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>Save</Button>
            <Button size="sm" variant="outline" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
          {save.isError && <p className="text-xs text-destructive">Failed to save — check all required fields.</p>}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main client list page
// ---------------------------------------------------------------------------
type TabId = "domains" | "imap" | "security";

export function ClientList() {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === "super_admin";
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [domainInput, setDomainInput] = useState<Record<number, string>>({});
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<Record<number, TabId>>({});

  const { data: clients } = useQuery({ queryKey: ["clients"], queryFn: clientsApi.list });

  const { data: domains } = useQuery({
    queryKey: ["domains", expandedId],
    queryFn: () => {
      const c = clients?.find((c) => c.id === expandedId);
      return c ? clientsApi.listDomains(c.slug) : null;
    },
    enabled: !!expandedId,
  });

  const createClient = useMutation({
    mutationFn: () => clientsApi.create(slug, name),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["clients"] }); setShowForm(false); setSlug(""); setName(""); },
  });

  const addDomain = useMutation({
    mutationFn: ({ clientSlug, domain }: { clientSlug: string; domain: string }) =>
      clientsApi.addDomain(clientSlug, domain),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["domains", expandedId] }),
  });

  const tab = (id: number): TabId => activeTab[id] ?? "domains";

  const canEditClient = (clientSlug: string) =>
    isSuperAdmin || user?.client_roles.some((cr) => cr.slug === clientSlug && cr.role === "admin");

  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: "domains",  label: "Domains",       icon: <Globe className="h-3 w-3" /> },
    { id: "imap",     label: "Mail Ingestion", icon: <Mail className="h-3 w-3" /> },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Clients</h1>
        {isSuperAdmin && (
          <Button size="sm" onClick={() => setShowForm((v) => !v)}>
            <Plus className="mr-2 h-4 w-4" /> New Client
          </Button>
        )}
      </div>

      {showForm && (
        <Card>
          <CardHeader><CardTitle className="text-base">Create Client</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Slug (URL-safe ID)</Label>
                <Input placeholder="acme-corp" value={slug} onChange={(e) => setSlug(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>Display Name</Label>
                <Input placeholder="Acme Corporation" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={() => createClient.mutate()} disabled={!slug || !name || createClient.isPending}>Create</Button>
              <Button variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {clients?.map((client) => {
          const canEdit = canEditClient(client.slug);

          return (
            <Card key={client.id}>
              <CardContent className="p-4">
                {/* Header row */}
                <div
                  className="flex cursor-pointer items-center justify-between"
                  onClick={() => setExpandedId(expandedId === client.id ? null : client.id)}
                >
                  <div className="flex items-center gap-3">
                    <Building2 className="h-5 w-5 text-muted-foreground" />
                    <div>
                      <p className="font-medium">{client.name}</p>
                      <p className="text-xs text-muted-foreground font-mono">{client.slug}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {(client.mfa_required_admins || client.mfa_required_viewers) && (
                      <span title="MFA enforcement active">
                        <ShieldCheck className="h-4 w-4 text-primary" />
                      </span>
                    )}
                    <Badge variant={client.is_active ? "default" : "secondary"}>
                      {client.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </div>
                </div>

                {/* Expanded panel */}
                {expandedId === client.id && (
                  <div className="mt-4 border-t pt-4 space-y-4">
                    {/* Tab bar */}
                    <div className="flex gap-1 border-b">
                      {tabs.map((t) => (
                        <button
                          key={t.id}
                          onClick={() => setActiveTab((p) => ({ ...p, [client.id]: t.id }))}
                          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border-b-2 -mb-px transition-colors ${
                            tab(client.id) === t.id
                              ? "border-primary text-primary"
                              : "border-transparent text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          {t.icon}
                          {t.label}
                        </button>
                      ))}
                      {canEdit && (
                        <button
                          onClick={() => setActiveTab((p) => ({ ...p, [client.id]: "security" }))}
                          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border-b-2 -mb-px transition-colors ${
                            tab(client.id) === "security"
                              ? "border-primary text-primary"
                              : "border-transparent text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          <ShieldCheck className="h-3 w-3" />
                          Security
                        </button>
                      )}
                    </div>

                    {/* Domains tab */}
                    {tab(client.id) === "domains" && (
                      <div className="space-y-3">
                        <ul className="space-y-1">
                          {domains?.map((d) => (
                            <li key={d.id} className="flex items-center gap-2 text-sm">
                              <Globe className="h-3 w-3 text-muted-foreground" />
                              {d.domain}
                            </li>
                          ))}
                          {domains?.length === 0 && <li className="text-sm text-muted-foreground">No domains yet.</li>}
                        </ul>
                        <div className="flex gap-2">
                          <Input
                            placeholder="example.com"
                            value={domainInput[client.id] ?? ""}
                            onChange={(e) => setDomainInput((p) => ({ ...p, [client.id]: e.target.value }))}
                            className="w-64"
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && domainInput[client.id]) {
                                addDomain.mutate({ clientSlug: client.slug, domain: domainInput[client.id] });
                                setDomainInput((p) => ({ ...p, [client.id]: "" }));
                              }
                            }}
                          />
                          <Button size="sm" variant="outline" onClick={() => {
                            if (domainInput[client.id]) {
                              addDomain.mutate({ clientSlug: client.slug, domain: domainInput[client.id] });
                              setDomainInput((p) => ({ ...p, [client.id]: "" }));
                            }
                          }}>Add Domain</Button>
                        </div>
                      </div>
                    )}

                    {/* Mail Ingestion tab */}
                    {tab(client.id) === "imap" && <ImapPanel slug={client.slug} />}

                    {/* Security tab */}
                    {tab(client.id) === "security" && canEdit && (
                      <SecurityPanel client={client} isSuperAdmin={isSuperAdmin} />
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}