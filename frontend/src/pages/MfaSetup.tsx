import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, ShieldOff } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { authApi } from "@/api/auth";
import { useAuth } from "@/contexts/AuthContext";

// ── Enrolment flow ────────────────────────────────────────────────────────────

function MfaEnrol() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { user, refreshUser } = useAuth();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");

  const isMandatory = user?.mfa_setup_required === true;

  const { data: setup, isLoading } = useQuery({
    queryKey: ["mfa-setup"],
    queryFn: () => authApi.mfaSetup(),
    staleTime: Infinity,  // don't re-fetch — each call regenerates the secret
  });

  const confirmMutation = useMutation({
    mutationFn: (code: string) => authApi.mfaConfirm(code),
    onSuccess: async (data) => {
      // Evict the QR code / otpauth_uri from cache — the secret should not linger
      qc.removeQueries({ queryKey: ["mfa-setup"] });
      // /mfa/confirm now returns a fresh access token with msr=False so the
      // middleware stops blocking. Store it before calling refreshUser().
      if (data?.access_token) {
        localStorage.setItem("access_token", data.access_token);
      }
      await refreshUser();
      navigate("/dashboard");
    },
    onError: () => {
      setError("Invalid code — check your authenticator app and try again.");
      setCode("");
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError("");
    confirmMutation.mutate(code);
  };

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <Card className="w-full max-w-md">
        <CardHeader className="items-center text-center">
          <ShieldCheck className="mb-2 h-10 w-10 text-primary" />
          <CardTitle className="text-xl">Set up two-factor authentication</CardTitle>
          <p className="text-sm text-muted-foreground">
            {isMandatory
              ? "Two-factor authentication is required for this platform. Scan the QR code to continue."
              : "Scan the QR code with Microsoft Authenticator, Authy, or Google Authenticator."}
          </p>
        </CardHeader>
        <CardContent className="space-y-6">
          {setup && (
            <div className="flex justify-center">
              <img
                src={setup.qr_data_uri}
                alt="MFA QR code"
                className="h-48 w-48 rounded border"
              />
            </div>
          )}

          <div className="rounded-md bg-muted px-4 py-3 text-xs text-muted-foreground">
            <p className="font-medium mb-1">Can't scan the code?</p>
            <p className="break-all font-mono">{setup?.otpauth_uri}</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="code">Confirm with a code from your app</Label>
              <Input
                id="code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="000000"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                required
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="flex gap-2">
              <Button
                type="submit"
                className="flex-1"
                disabled={confirmMutation.isPending || code.length !== 6}
              >
                {confirmMutation.isPending ? "Verifying…" : "Enable MFA"}
              </Button>
              {/* Cancel is hidden when MFA is mandatory */}
              {!isMandatory && (
                <Button type="button" variant="outline" onClick={() => navigate(-1)}>
                  Cancel
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Disable flow ──────────────────────────────────────────────────────────────

function MfaDisable() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { user, refreshUser } = useAuth();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");

  // If MFA is platform-enforced, users cannot disable — show an informational screen
  if (user?.mfa_required) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center">
        <Card className="w-full max-w-sm">
          <CardHeader className="items-center text-center">
            <ShieldCheck className="mb-2 h-10 w-10 text-green-600" />
            <CardTitle className="text-xl">MFA is enforced</CardTitle>
            <p className="text-sm text-muted-foreground">
              Two-factor authentication is required by your administrator and cannot be
              disabled. If you have lost access to your authenticator app, contact a
              super admin to reset your MFA device.
            </p>
          </CardHeader>
          <CardContent>
            <Button variant="outline" className="w-full" onClick={() => navigate(-1)}>
              Back
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const disableMutation = useMutation({
    mutationFn: (code: string) => authApi.mfaDisable(code),
    onSuccess: async () => {
      await refreshUser();
      await qc.invalidateQueries({ queryKey: ["me"] });
      navigate("/dashboard");
    },
    onError: () => {
      setError("Invalid code — MFA was not disabled.");
      setCode("");
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError("");
    disableMutation.mutate(code);
  };

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <ShieldOff className="mb-2 h-10 w-10 text-destructive" />
          <CardTitle className="text-xl">Disable two-factor authentication</CardTitle>
          <p className="text-sm text-muted-foreground">
            Enter a current code from your authenticator app to confirm.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="code">Authenticator code</Label>
              <Input
                id="code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="000000"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                autoFocus
                required
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="flex gap-2">
              <Button
                type="submit"
                variant="destructive"
                className="flex-1"
                disabled={disableMutation.isPending || code.length !== 6}
              >
                {disableMutation.isPending ? "Disabling…" : "Disable MFA"}
              </Button>
              <Button type="button" variant="outline" onClick={() => navigate(-1)}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Page router ───────────────────────────────────────────────────────────────

export function MfaSetup() {
  const { user } = useAuth();
  return user?.mfa_enabled ? <MfaDisable /> : <MfaEnrol />;
}