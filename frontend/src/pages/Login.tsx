import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, Smartphone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import { authApi } from "@/api/auth";

type Step = "credentials" | "mfa";

export function Login() {
  const { login, verifyMfa } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState<Step>("credentials");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleCredentials = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await login(email, password);
      if (result.status === "mfa_required") {
        setMfaToken(result.mfa_token);
        setStep("mfa");
      } else {
        navigate("/dashboard");
      }
    } catch {
      setError("Invalid email or password.");
    } finally {
      setLoading(false);
    }
  };

  const handleMfa = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await verifyMfa(mfaToken, code);
      navigate("/dashboard");
    } catch {
      setError("Invalid code. Check your authenticator app and try again.");
      setCode("");
    } finally {
      setLoading(false);
    }
  };

  const handleAzureLogin = async () => {
    try {
      const { auth_url } = await authApi.azureLoginUrl();
      window.location.href = auth_url;
    } catch {
      setError("Azure SSO is not configured.");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30">
      <Card className="w-full max-w-sm">
        {step === "credentials" ? (
          <>
            <CardHeader className="items-center text-center">
              <ShieldCheck className="mb-2 h-10 w-10 text-primary" />
              <CardTitle className="text-xl">DMARC Intelligence</CardTitle>
              <p className="text-sm text-muted-foreground">Sign in to your account</p>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={handleCredentials} className="space-y-4">
                <div className="space-y-1">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? "Signing in…" : "Sign in"}
                </Button>
              </form>

              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-background px-2 text-muted-foreground">or</span>
                </div>
              </div>

              <Button variant="outline" className="w-full" onClick={handleAzureLogin}>
                Sign in with Microsoft
              </Button>
            </CardContent>
          </>
        ) : (
          <>
            <CardHeader className="items-center text-center">
              <Smartphone className="mb-2 h-10 w-10 text-primary" />
              <CardTitle className="text-xl">Two-factor authentication</CardTitle>
              <p className="text-sm text-muted-foreground">
                Enter the 6-digit code from your authenticator app.
              </p>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleMfa} className="space-y-4">
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
                <Button type="submit" className="w-full" disabled={loading || code.length !== 6}>
                  {loading ? "Verifying…" : "Verify"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full"
                  onClick={() => { setStep("credentials"); setError(""); setCode(""); }}
                >
                  Back to sign in
                </Button>
              </form>
            </CardContent>
          </>
        )}
      </Card>
    </div>
  );
}