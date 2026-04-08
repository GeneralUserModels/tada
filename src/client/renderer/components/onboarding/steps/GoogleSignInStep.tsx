import React from "react";

type Props = {
  googleUser: { name: string; email: string } | null;
  googleLoading: boolean;
  googleError: string;
  onBack: () => void;
  onContinue: () => void;
  onGoogleLogin: () => void;
};

export function GoogleSignInStep({
  googleUser,
  googleLoading,
  googleError,
  onBack,
  onContinue,
  onGoogleLogin,
}: Props) {
  return (
    <div className="page active">
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm0 2.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM8 13c-1.7 0-3.2-.9-4-2.2.02-1.3 2.7-2 4-2s3.98.7 4 2c-.8 1.3-2.3 2.2-4 2.2Z" fill="currentColor"/></svg>
      </div>
      <div className="page-title">Sign In</div>
      <p className="page-desc">Sign in with your Google account so we know who you are.</p>
      <div className="glass-card" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
        {!googleUser && (
          <button
            className="btn"
            style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 24px", background: "#fff", border: "1px solid #dadce0", borderRadius: 4, fontSize: 14, fontWeight: 500, color: "#3c4043" }}
            onClick={onGoogleLogin}
            disabled={googleLoading}
          >
            <svg width="18" height="18" viewBox="0 0 18 18"><path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615Z" fill="#4285F4"/><path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.26c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18Z" fill="#34A853"/><path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332Z" fill="#FBBC05"/><path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 2.58 9 2.58Z" fill="#EA4335"/></svg>
            {googleLoading ? "Signing in..." : "Sign in with Google"}
          </button>
        )}
        <div style={{ fontSize: 12.5, color: googleUser ? "var(--active-green)" : googleError ? "var(--danger)" : "var(--text-secondary)", textAlign: "center", minHeight: 20 }}>
          {googleUser
            ? <><strong>Signed in as {googleUser.name}</strong><br/>{googleUser.email}</>
            : googleError || ""}
        </div>
      </div>
      <div className="btn-row">
        <button className="btn btn-ghost" onClick={onBack}>Back</button>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button className="btn btn-primary" disabled={!googleUser} onClick={onContinue}>Continue</button>
        </div>
      </div>
    </div>
  );
}
