import { useCallback, useEffect, useState } from "react";
import { athleteCoachApi, extractErrorMessage } from "../api/client";
import { Layout } from "../components/Layout";
import { LoadingState } from "../components/LoadingState";
import type { CoachConnection, CoachInvitation } from "../types";
import { formatDate } from "../utils/format";

export function CoachConnections() {
  const [invitations, setInvitations] = useState<CoachInvitation[]>([]);
  const [connections, setConnections] = useState<CoachConnection[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [pending, connected] = await Promise.all([athleteCoachApi.invitations(), athleteCoachApi.connected()]);
    setInvitations(pending); setConnections(connected); setStatus("ready");
  }, []);

  useEffect(() => { load().catch((err) => { setError(extractErrorMessage(err, "Couldn't load coach connections.")); setStatus("error"); }); }, [load]);

  async function accept(invitationId: number) {
    setError(null);
    try { await athleteCoachApi.accept(invitationId); await load(); }
    catch (err) { setError(extractErrorMessage(err, "Couldn't accept this invitation.")); }
  }
  async function reject(invitationId: number) {
    await athleteCoachApi.reject(invitationId); setInvitations((items) => items.filter((item) => item.id !== invitationId));
  }
  async function disconnect(connection: CoachConnection) {
    if (!confirm(`Disconnect ${connection.coach_name}? Existing workouts and comments will remain.`)) return;
    await athleteCoachApi.disconnect(connection.coach_id); setConnections((items) => items.filter((item) => item.coach_id !== connection.coach_id));
  }

  return <Layout>
    <div className="page-header"><h1>Coaches</h1><p className="page-subtitle">You control which coaches can view your rowing data.</p></div>
    {status === "loading" && <LoadingState status="loading" loadingLabel="Loading coach connections..." />}
    {status === "error" && <LoadingState status="error" errorLabel={error ?? undefined} />}
    {status === "ready" && error && <div className="auth-error" style={{ marginTop: "1rem" }}>{error}</div>}
    {status === "ready" && invitations.length > 0 && <div className="card" style={{ marginTop: "1.25rem" }}>
      <p className="card-title">Pending Invitations</p>
      {invitations.map((invitation) => <div className="connection-row" key={invitation.id}>
        <div><strong>{invitation.coach_name}</strong><p>Invited you on {formatDate(invitation.created_at)}</p></div>
        <div className="connection-actions"><button className="btn-secondary" type="button" onClick={() => void reject(invitation.id)}>Reject</button><button className="btn-primary" type="button" onClick={() => void accept(invitation.id)}>Accept</button></div>
      </div>)}
    </div>}
    {status === "ready" && <div className="card" style={{ marginTop: "1.25rem" }}>
      <p className="card-title">Connected Coaches</p>
      {connections.length === 0 ? <p className="metric-card-unavailable">You have not connected with a coach.</p> : connections.map((connection) => <div className="connection-row" key={connection.coach_id}>
        <div><strong>{connection.coach_name}</strong><p>{connection.coach_email} · Connected {formatDate(connection.assigned_at)}</p></div>
        <button className="btn-link danger-link" type="button" onClick={() => void disconnect(connection)}>Disconnect</button>
      </div>)}
    </div>}
  </Layout>;
}
