import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { coachApi, extractErrorMessage } from "../api/client";
import { Layout } from "../components/Layout";
import { LoadingState } from "../components/LoadingState";
import type { CoachAthleteSummary, CoachInvitation } from "../types";
import { formatDate, formatDuration } from "../utils/format";

export function CoachDashboard() {
  const navigate = useNavigate();
  const [athletes, setAthletes] = useState<CoachAthleteSummary[]>([]);
  const [invitations, setInvitations] = useState<CoachInvitation[]>([]);
  const [athleteEmail, setAthleteEmail] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    const [assigned, pending] = await Promise.all([coachApi.athletes(), coachApi.invitations()]);
    setAthletes(assigned);
    setInvitations(pending);
    setStatus("ready");
  }, []);

  useEffect(() => {
    load().catch((err) => {
      setError(extractErrorMessage(err, "Couldn't load your coach dashboard."));
      setStatus("error");
    });
  }, [load]);

  async function invite(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const created = await coachApi.inviteAthlete(athleteEmail);
      setInvitations((items) => [created, ...items]);
      setAthleteEmail("");
      setMessage(`Invitation sent to ${created.athlete_name}. They must accept it in OarSight.`);
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't send the athlete invitation."));
    } finally {
      setSubmitting(false);
    }
  }

  async function cancelInvitation(invitationId: number) {
    await coachApi.cancelInvitation(invitationId);
    setInvitations((items) => items.filter((item) => item.id !== invitationId));
  }

  async function disconnect(athleteId: number, athleteName: string) {
    if (!confirm(`Disconnect ${athleteName}? Their workouts and comments will not be deleted.`)) return;
    await coachApi.removeAthlete(athleteId);
    setAthletes((items) => items.filter((item) => item.athlete.id !== athleteId));
  }

  return (
    <Layout>
      <div className="page-header">
        <h1>Coach Dashboard</h1>
        <p className="page-subtitle">Invite athletes and review those who have accepted.</p>
      </div>

      <div className="card" style={{ marginTop: "1.25rem" }}>
        <p className="card-title">Invite an Athlete</p>
        <p className="metric-card-unavailable">Enter the email used by their OarSight athlete account. Access begins only after they accept.</p>
        <form className="inline-invite-form" onSubmit={invite}>
          <input type="email" value={athleteEmail} onChange={(event) => setAthleteEmail(event.target.value)} placeholder="athlete@example.com" required />
          <button className="btn-primary" type="submit" disabled={submitting}>{submitting ? "Sending..." : "Send Invitation"}</button>
        </form>
        {message && <div className="success-message">{message}</div>}
        {error && status !== "error" && <div className="auth-error">{error}</div>}
      </div>

      {status === "loading" && <LoadingState status="loading" loadingLabel="Loading athletes..." />}
      {status === "error" && <LoadingState status="error" errorLabel={error ?? undefined} />}
      {status === "ready" && invitations.length > 0 && (
        <div className="card">
          <p className="card-title">Pending Invitations</p>
          <div className="table-scroll"><table className="data-table">
            <thead><tr><th>Athlete</th><th>Email</th><th>Sent</th><th>Action</th></tr></thead>
            <tbody>{invitations.map((invitation) => (
              <tr key={invitation.id}>
                <td className="data-table-text">{invitation.athlete_name}</td><td className="data-table-text">{invitation.athlete_email}</td>
                <td>{formatDate(invitation.created_at)}</td><td><button className="btn-link" type="button" onClick={() => void cancelInvitation(invitation.id)}>Cancel</button></td>
              </tr>
            ))}</tbody>
          </table></div>
        </div>
      )}
      {status === "ready" && athletes.length === 0 && (
        <LoadingState status="empty" emptyTitle="No connected athletes" emptyBody="Invite an athlete above. They will appear here after accepting." />
      )}
      {status === "ready" && athletes.length > 0 && (
        <div className="card">
          <p className="card-title">My Athletes</p>
          <div className="table-scroll"><table className="data-table">
            <thead><tr><th>Athlete</th><th>Training level</th><th>Recent workout</th><th>Last workout</th><th>2K PB</th><th>Workouts</th><th>Action</th></tr></thead>
            <tbody>{athletes.map(({ athlete, recent_workout, workout_count, two_k_pb_seconds }) => (
              <tr key={athlete.id} className="clickable" onClick={() => navigate(`/coach/athletes/${athlete.id}`)}>
                <td className="data-table-text"><strong>{athlete.name}</strong></td><td>{athlete.training_level?.replace(/^./, (c) => c.toUpperCase()) ?? "Not set"}</td>
                <td className="data-table-text">{recent_workout?.title ?? "No workouts"}</td><td>{recent_workout ? formatDate(recent_workout.date) : "-"}</td>
                <td>{two_k_pb_seconds != null ? formatDuration(two_k_pb_seconds) : "-"}</td><td>{workout_count}</td>
                <td><button className="btn-link danger-link" type="button" onClick={(event) => { event.stopPropagation(); void disconnect(athlete.id, athlete.name); }}>Disconnect</button></td>
              </tr>
            ))}</tbody>
          </table></div>
        </div>
      )}
    </Layout>
  );
}
