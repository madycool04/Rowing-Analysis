import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { extractErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";

const MIN_PASSWORD_LENGTH = 8;

export function Register() {
  const { register } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"athlete" | "coach">("athlete");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    setIsSubmitting(true);
    try {
      const registeredUser = await register(email, password, role, displayName);
      // Route using the role confirmed by the backend response, not local
      // form state. This also avoids racing the auth context state update.
      window.location.replace(registeredUser.role === "coach" ? "/coach" : "/");
    } catch (err) {
      setError(extractErrorMessage(err, "Could not create your account."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>Create your account</h1>
        <p className="auth-subtitle">Start tracking your rowing performance.</p>

        {error && <div className="auth-error">{error}</div>}

        <label className="field">
          <span>Account type</span>
          <select className="select" value={role} onChange={(e) => setRole(e.target.value as "athlete" | "coach")}>
            <option value="athlete">Athlete</option>
            <option value="coach">Coach</option>
          </select>
        </label>

        {role === "coach" && (
          <label className="field">
            <span>Coach name</span>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Coach Carter"
              required
              maxLength={255}
              autoComplete="name"
            />
          </label>
        )}

        <label className="field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            autoFocus
          />
        </label>

        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={MIN_PASSWORD_LENGTH}
            autoComplete="new-password"
          />
          <span className="field-hint">At least {MIN_PASSWORD_LENGTH} characters.</span>
        </label>

        <button type="submit" className="btn-primary" disabled={isSubmitting}>
          {isSubmitting ? "Creating account..." : "Sign up"}
        </button>

        <p className="auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </form>
    </div>
  );
}
