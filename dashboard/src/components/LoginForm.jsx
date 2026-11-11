/**
 * LoginForm — Glassmorphic HUD Auth Component
 * Matches the dark glass design system of the Smart Panel HUD.
 * Tabs: Register (new user) | Sign In (existing user)
 */
import { useState } from "react";
import { Activity, UserCheck, LogIn, Eye, EyeOff, ShieldCheck, Zap } from "lucide-react";
import { api, setToken } from "../api/client.js";

export default function LoginForm({ onSuccess }) {
  const [tab, setTab] = useState("login"); // "login" | "register"

  // Shared fields
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [role, setRole] = useState("operator");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  function resetForm() {
    setEmail("");
    setPassword("");
    setConfirmPassword("");
    setError("");
    setSuccess("");
    setShowPass(false);
  }

  function switchTab(t) {
    setTab(t);
    resetForm();
  }

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await api.login(email, password);
      setToken(data.access_token);
      onSuccess(data.access_token);
    } catch (err) {
      setError(err.message || "Login failed. Check your email and password.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setLoading(true);
    try {
      const data = await api.register(email, password, role);
      setToken(data.access_token);
      setSuccess("Account created! Logging you in...");
      setTimeout(() => onSuccess(data.access_token), 800);
    } catch (err) {
      setError(err.message || "Registration failed. Email may already be in use.");
    } finally {
      setLoading(false);
    }
  }

  const inputStyle = {
    width: "100%",
    padding: "12px 16px",
    background: "rgba(255, 255, 255, 0.05)",
    border: "1px solid rgba(255, 255, 255, 0.12)",
    borderRadius: "10px",
    color: "#f4f6f9",
    fontSize: "14px",
    fontFamily: "inherit",
    outline: "none",
    transition: "border-color 0.2s ease",
  };

  const labelStyle = {
    display: "block",
    fontSize: "11px",
    fontWeight: "600",
    letterSpacing: "0.08em",
    color: "#8b95a5",
    marginBottom: "7px",
    textTransform: "uppercase",
  };

  const fieldWrap = { display: "flex", flexDirection: "column", gap: "14px" };

  return (
    <div style={{
      minHeight: "100vh",
      width: "100%",
      background: "#000000",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      position: "relative",
      overflow: "hidden",
    }}>

      {/* Ambient blobs */}
      <div style={{
        position: "fixed", top: "-10%", left: "15%", width: 480, height: 480,
        background: "rgba(10, 132, 255, 0.06)", filter: "blur(100px)", borderRadius: "50%", pointerEvents: "none",
      }} />
      <div style={{
        position: "fixed", bottom: "-5%", right: "10%", width: 540, height: 400,
        background: "rgba(10, 132, 255, 0.04)", filter: "blur(110px)", borderRadius: "50%", pointerEvents: "none",
      }} />

      {/* Auth Card */}
      <div style={{
        width: "100%",
        maxWidth: 460,
        margin: "24px",
        background: "rgba(22, 28, 36, 0.80)",
        backdropFilter: "blur(32px) saturate(180%)",
        WebkitBackdropFilter: "blur(32px) saturate(180%)",
        border: "1px solid rgba(255, 255, 255, 0.09)",
        borderRadius: "20px",
        boxShadow: "0 24px 64px rgba(0,0,0,0.65), inset 0 1px 0 rgba(255,255,255,0.1)",
        overflow: "hidden",
        position: "relative",
        zIndex: 10,
      }}>

        {/* Header Brand Bar */}
        <div style={{
          padding: "22px 28px 18px",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: "rgba(10, 132, 255, 0.18)",
            border: "1px solid rgba(10, 132, 255, 0.4)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <Activity size={18} color="#70b6ff" />
          </div>
          <div>
            <div style={{ fontSize: "13px", fontWeight: 700, color: "#e1e6eb", letterSpacing: "0.04em" }}>
              SMART PANEL HUD
            </div>
            <div style={{ fontSize: "11px", color: "#8b95a5", marginTop: 1 }}>
              Dual-Channel Load Protection System
            </div>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{
              width: 7, height: 7, borderRadius: "50%",
              background: "#30d158",
              boxShadow: "0 0 6px rgba(48, 209, 88, 0.6)",
              display: "inline-block",
            }} />
            <span style={{ fontSize: "11px", color: "#30d158" }}>SYSTEM ONLINE</span>
          </div>
        </div>

        {/* Tab Switcher */}
        <div style={{
          display: "flex",
          margin: "20px 28px 0",
          background: "rgba(255,255,255,0.04)",
          borderRadius: "12px",
          border: "1px solid rgba(255,255,255,0.07)",
          padding: "4px",
          gap: "4px",
        }}>
          {[
            { id: "login", label: "Sign In", Icon: LogIn },
            { id: "register", label: "Register", Icon: UserCheck },
          ].map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => switchTab(id)}
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 7,
                padding: "10px 16px",
                borderRadius: "9px",
                border: "none",
                fontSize: "13px",
                fontWeight: 600,
                fontFamily: "inherit",
                cursor: "pointer",
                transition: "all 0.2s ease",
                background: tab === id
                  ? "rgba(10, 132, 255, 0.22)"
                  : "transparent",
                color: tab === id ? "#ffffff" : "#8b95a5",
                boxShadow: tab === id
                  ? "inset 0 1px 0 rgba(255,255,255,0.15), 0 0 0 1px rgba(10,132,255,0.4)"
                  : "none",
              }}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>

        {/* Form Body */}
        <div style={{ padding: "24px 28px 28px" }}>

          {/* Title row */}
          <div style={{ marginBottom: "22px" }}>
            <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 700, color: "#f4f6f9" }}>
              {tab === "login" ? "Welcome Back, Operator" : "Create Account"}
            </h2>
            <p style={{ margin: "5px 0 0", fontSize: "13px", color: "#8b95a5" }}>
              {tab === "login"
                ? "Sign in to control hardware relays, manage schedules, and view AI insights."
                : "Register to access the full Smart Panel dashboard and AI backend."}
            </p>
          </div>

          {/* Error / Success Messages */}
          {error && (
            <div style={{
              padding: "11px 14px",
              marginBottom: "16px",
              borderRadius: "10px",
              background: "rgba(255, 69, 58, 0.12)",
              border: "1px solid rgba(255, 69, 58, 0.35)",
              color: "#ff453a",
              fontSize: "13px",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}>
              <Zap size={14} />
              {error}
            </div>
          )}
          {success && (
            <div style={{
              padding: "11px 14px",
              marginBottom: "16px",
              borderRadius: "10px",
              background: "rgba(48, 209, 88, 0.12)",
              border: "1px solid rgba(48, 209, 88, 0.35)",
              color: "#30d158",
              fontSize: "13px",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}>
              <ShieldCheck size={14} />
              {success}
            </div>
          )}

          {/* LOGIN FORM */}
          {tab === "login" && (
            <form onSubmit={handleLogin} style={fieldWrap}>
              <div>
                <label style={labelStyle}>Email Address</label>
                <input
                  type="email"
                  placeholder="operator@smartpanel.local"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  style={inputStyle}
                  onFocus={(e) => (e.target.style.borderColor = "rgba(10,132,255,0.6)")}
                  onBlur={(e) => (e.target.style.borderColor = "rgba(255,255,255,0.12)")}
                />
              </div>

              <div>
                <label style={labelStyle}>Password</label>
                <div style={{ position: "relative" }}>
                  <input
                    type={showPass ? "text" : "password"}
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    style={{ ...inputStyle, paddingRight: 44 }}
                    onFocus={(e) => (e.target.style.borderColor = "rgba(10,132,255,0.6)")}
                    onBlur={(e) => (e.target.style.borderColor = "rgba(255,255,255,0.12)")}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    style={{
                      position: "absolute", right: 13, top: "50%", transform: "translateY(-50%)",
                      background: "none", border: "none", cursor: "pointer",
                      color: "#8b95a5", display: "flex", padding: 0,
                    }}
                  >
                    {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                style={{
                  width: "100%",
                  padding: "13px",
                  marginTop: "4px",
                  background: loading ? "rgba(10,132,255,0.3)" : "rgba(10,132,255,1)",
                  border: "none",
                  borderRadius: "12px",
                  color: "#ffffff",
                  fontSize: "14px",
                  fontWeight: 700,
                  fontFamily: "inherit",
                  cursor: loading ? "not-allowed" : "pointer",
                  letterSpacing: "0.03em",
                  transition: "all 0.2s ease",
                  boxShadow: loading ? "none" : "0 4px 16px rgba(10,132,255,0.4)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                }}
              >
                <LogIn size={16} />
                {loading ? "Authenticating..." : "Sign In"}
              </button>

              <p style={{ textAlign: "center", fontSize: "12px", color: "#8b95a5", marginTop: 4 }}>
                Don't have an account?{" "}
                <button type="button" onClick={() => switchTab("register")} style={{
                  background: "none", border: "none", color: "#70b6ff",
                  fontSize: "12px", fontFamily: "inherit", cursor: "pointer", fontWeight: 600,
                }}>
                  Register here
                </button>
              </p>
            </form>
          )}

          {/* REGISTER FORM */}
          {tab === "register" && (
            <form onSubmit={handleRegister} style={fieldWrap}>
              <div>
                <label style={labelStyle}>Email Address</label>
                <input
                  type="email"
                  placeholder="yourname@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  style={inputStyle}
                  onFocus={(e) => (e.target.style.borderColor = "rgba(10,132,255,0.6)")}
                  onBlur={(e) => (e.target.style.borderColor = "rgba(255,255,255,0.12)")}
                />
              </div>

              <div>
                <label style={labelStyle}>Password <span style={{ color: "#8b95a5", fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>(min. 8 characters)</span></label>
                <div style={{ position: "relative" }}>
                  <input
                    type={showPass ? "text" : "password"}
                    placeholder="Choose a strong password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={8}
                    style={{ ...inputStyle, paddingRight: 44 }}
                    onFocus={(e) => (e.target.style.borderColor = "rgba(10,132,255,0.6)")}
                    onBlur={(e) => (e.target.style.borderColor = "rgba(255,255,255,0.12)")}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    style={{
                      position: "absolute", right: 13, top: "50%", transform: "translateY(-50%)",
                      background: "none", border: "none", cursor: "pointer",
                      color: "#8b95a5", display: "flex", padding: 0,
                    }}
                  >
                    {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
                {/* Password strength bar */}
                {password.length > 0 && (
                  <div style={{ marginTop: 7 }}>
                    <div style={{ height: 3, borderRadius: 99, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                      <div style={{
                        height: "100%",
                        borderRadius: 99,
                        width: `${Math.min(100, (password.length / 16) * 100)}%`,
                        background: password.length < 8 ? "#ff453a" : password.length < 12 ? "#ff9f0a" : "#30d158",
                        transition: "width 0.3s ease, background 0.3s ease",
                      }} />
                    </div>
                    <span style={{ fontSize: "10px", color: password.length < 8 ? "#ff453a" : password.length < 12 ? "#ff9f0a" : "#30d158", marginTop: 4, display: "block" }}>
                      {password.length < 8 ? "Too short" : password.length < 12 ? "Good" : "Strong"}
                    </span>
                  </div>
                )}
              </div>

              <div>
                <label style={labelStyle}>Confirm Password</label>
                <input
                  type={showPass ? "text" : "password"}
                  placeholder="Repeat password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  style={{
                    ...inputStyle,
                    borderColor: confirmPassword && confirmPassword !== password
                      ? "rgba(255,69,58,0.5)"
                      : confirmPassword && confirmPassword === password
                      ? "rgba(48,209,88,0.5)"
                      : "rgba(255,255,255,0.12)",
                  }}
                  onFocus={(e) => (e.target.style.borderColor = "rgba(10,132,255,0.6)")}
                  onBlur={(e) => {
                    if (confirmPassword && confirmPassword !== password) {
                      e.target.style.borderColor = "rgba(255,69,58,0.5)";
                    } else if (confirmPassword && confirmPassword === password) {
                      e.target.style.borderColor = "rgba(48,209,88,0.5)";
                    } else {
                      e.target.style.borderColor = "rgba(255,255,255,0.12)";
                    }
                  }}
                />
                {confirmPassword && confirmPassword !== password && (
                  <span style={{ fontSize: "11px", color: "#ff453a", marginTop: 5, display: "block" }}>
                    Passwords don't match
                  </span>
                )}
              </div>

              <div>
                <label style={labelStyle}>Account Role</label>
                <div style={{ display: "flex", gap: 10 }}>
                  {[
                    { val: "operator", label: "Operator", desc: "Full relay & schedule control" },
                    { val: "viewer", label: "Viewer", desc: "Read-only monitoring" },
                  ].map(({ val, label, desc }) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setRole(val)}
                      style={{
                        flex: 1,
                        padding: "10px 12px",
                        borderRadius: "10px",
                        border: role === val
                          ? "1px solid rgba(10,132,255,0.5)"
                          : "1px solid rgba(255,255,255,0.08)",
                        background: role === val
                          ? "rgba(10,132,255,0.15)"
                          : "rgba(255,255,255,0.03)",
                        cursor: "pointer",
                        textAlign: "left",
                        fontFamily: "inherit",
                        transition: "all 0.2s ease",
                      }}
                    >
                      <div style={{ fontSize: "13px", fontWeight: 600, color: role === val ? "#70b6ff" : "#9aa5b4" }}>
                        {label}
                      </div>
                      <div style={{ fontSize: "10px", color: "#8b95a5", marginTop: 2 }}>{desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                style={{
                  width: "100%",
                  padding: "13px",
                  marginTop: "4px",
                  background: loading ? "rgba(10,132,255,0.3)" : "rgba(10,132,255,1)",
                  border: "none",
                  borderRadius: "12px",
                  color: "#ffffff",
                  fontSize: "14px",
                  fontWeight: 700,
                  fontFamily: "inherit",
                  cursor: loading ? "not-allowed" : "pointer",
                  letterSpacing: "0.03em",
                  transition: "all 0.2s ease",
                  boxShadow: loading ? "none" : "0 4px 16px rgba(10,132,255,0.4)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                }}
              >
                <UserCheck size={16} />
                {loading ? "Creating Account..." : "Create Account & Sign In"}
              </button>

              <p style={{ textAlign: "center", fontSize: "12px", color: "#8b95a5", marginTop: 4 }}>
                Already have an account?{" "}
                <button type="button" onClick={() => switchTab("login")} style={{
                  background: "none", border: "none", color: "#70b6ff",
                  fontSize: "12px", fontFamily: "inherit", cursor: "pointer", fontWeight: 600,
                }}>
                  Sign in
                </button>
              </p>
            </form>
          )}
        </div>

        {/* Footer */}
        <div style={{
          borderTop: "1px solid rgba(255,255,255,0.07)",
          padding: "14px 28px",
          display: "flex",
          alignItems: "center",
          gap: 8,
          background: "rgba(0,0,0,0.2)",
        }}>
          <ShieldCheck size={13} color="#8b95a5" />
          <span style={{ fontSize: "11px", color: "#8b95a5" }}>
            AI advisory only — relay actuation always requires operator confirmation.
          </span>
        </div>
      </div>
    </div>
  );
}
