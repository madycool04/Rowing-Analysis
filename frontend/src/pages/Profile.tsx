import { useEffect, useState } from "react";
import { athletesApi, extractErrorMessage } from "../api/client";
import { Layout } from "../components/Layout";
import { useAuth } from "../context/AuthContext";

export function Profile() {
  const { athlete } = useAuth();
  const [weight, setWeight] = useState(""); const [resting, setResting] = useState(""); const [max, setMax] = useState(""); const [status, setStatus] = useState("");
  useEffect(() => { if (athlete) { setWeight(athlete.weight_kg?.toString() ?? ""); setResting(athlete.resting_hr?.toString() ?? ""); setMax(athlete.max_hr?.toString() ?? ""); } }, [athlete]);
  async function save() {
    if (!athlete) return; setStatus(""); const r=Number(resting), m=Number(max), w=Number(weight);
    if (!(w>0 && w<300)) return setStatus("Weight must be between 0 and 300 kg.");
    if (!(r>20 && r<250) || !(m>r && m<250)) return setStatus("Enter a valid resting HR and a maximum HR greater than resting HR.");
    try { await athletesApi.update(athlete.id,{weight_kg:w,resting_hr:r,max_hr:m}); setStatus("Saved successfully."); } catch(e) { setStatus(extractErrorMessage(e,"Could not save profile.")); }
  }
  return <Layout><div className="page-header"><h1>Athlete Profile</h1><p className="page-subtitle">Training and physiological settings</p></div><div className="card"><p className="card-title">Physiological Settings</p><label className="field"><span>Weight (kg)</span><input type="number" value={weight} onChange={e=>setWeight(e.target.value)} /></label><label className="field"><span>Resting HR</span><input type="number" value={resting} onChange={e=>setResting(e.target.value)} /></label><label className="field"><span>Maximum HR</span><input type="number" value={max} onChange={e=>setMax(e.target.value)} /></label><button className="btn-primary" onClick={save}>Save</button>{status && <p className="metric-note">{status}</p>}</div></Layout>;
}
