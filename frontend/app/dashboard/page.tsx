"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

type Stats = {
  campaigns_found: number;
  applications_sent: number;
  response_rate: number;
};

type Profile = {
  full_name: string;
  email: string;
  niche: string;
  bio: string;
  audience_size: number;
  platforms: string;
  min_budget: number;
  auto_apply: boolean;
};

type ProfileRecord = Profile & {
  id: number;
};

const defaultProfile: Profile = {
  full_name: "",
  email: "",
  niche: "",
  bio: "",
  audience_size: 0,
  platforms: "tiktok,instagram",
  min_budget: 0,
  auto_apply: false,
};

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats>({ campaigns_found: 0, applications_sent: 0, response_rate: 0 });
  const [profile, setProfile] = useState<Profile>(defaultProfile);
  const [profileId, setProfileId] = useState<number | null>(null);
  const [taskId, setTaskId] = useState<string>("");
  const [taskState, setTaskState] = useState<string>("");
  const [message, setMessage] = useState<string>("");

  const profileReady = useMemo(() => !!profile.full_name && !!profile.email && !!profile.niche, [profile]);

  useEffect(() => {
    void loadStats();
    void loadProfile();
  }, []);

  useEffect(() => {
    if (!taskId) return;
    const timer = setInterval(() => {
      void pollTask(taskId);
    }, 2000);
    return () => clearInterval(timer);
  }, [taskId]);

  async function loadStats() {
    const res = await fetch(`${API}/stats`, { cache: "no-store" });
    if (res.ok) {
      setStats(await res.json());
    }
  }

  async function loadProfile() {
    const res = await fetch(`${API}/profile`, { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      if (data) {
        const payload = data as ProfileRecord;
        setProfileId(payload.id);
        setProfile({
          full_name: payload.full_name,
          email: payload.email,
          niche: payload.niche,
          bio: payload.bio,
          audience_size: payload.audience_size,
          platforms: payload.platforms,
          min_budget: payload.min_budget,
          auto_apply: payload.auto_apply,
        });
      } else {
        setProfileId(null);
      }
    }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    const method = profileId ? "PATCH" : "POST";
    let res = await fetch(`${API}/profile`, {
      headers: { "Content-Type": "application/json" },
      method,
      body: JSON.stringify(profile),
    });
    if (!profileId && res.status === 409) {
      res = await fetch(`${API}/profile`, {
        headers: { "Content-Type": "application/json" },
        method: "PATCH",
        body: JSON.stringify(profile),
      });
    }
    if (!res.ok) {
      setMessage("Echec sauvegarde profil");
      return;
    }
    const data = (await res.json()) as ProfileRecord;
    setProfileId(data.id);
    setMessage(profileId ? "Profil mis a jour" : "Profil cree");
  }

  async function runScan() {
    setMessage("");
    const res = await fetch(`${API}/scan/async`, { method: "POST" });
    if (!res.ok) {
      setMessage("Impossible de lancer le scan");
      return;
    }
    const data = await res.json();
    setTaskId(data.task_id);
    setTaskState(data.status);
  }

  async function pollTask(id: string) {
    const res = await fetch(`${API}/tasks/${id}`);
    if (!res.ok) return;
    const data = await res.json();
    setTaskState(data.state);
    if (["SUCCESS", "FAILURE"].includes(data.state)) {
      await loadStats();
    }
  }

  return (
    <section>
      <div className="grid">
        <article className="card">
          <h3>Campagnes Trouvees</h3>
          <strong>{stats.campaigns_found}</strong>
        </article>
        <article className="card">
          <h3>Candidatures Envoyees</h3>
          <strong>{stats.applications_sent}</strong>
        </article>
        <article className="card">
          <h3>Taux de Reponse</h3>
          <strong>{stats.response_rate}%</strong>
        </article>
      </div>

      <div className="card">
        <h3>Actions</h3>
        <button onClick={runScan} disabled={!profileReady}>Lancer un scan (async)</button>
        {!!taskId && <p><small>Task {taskId} · Etat: {taskState}</small></p>}
        {!!message && <p><small>{message}</small></p>}
      </div>

      <form className="card" onSubmit={saveProfile}>
        <h3>Profil Createur</h3>
        <div className="grid">
          <label>
            Nom complet
            <input value={profile.full_name} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} />
          </label>
          <label>
            Email
            <input type="email" value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
          </label>
          <label>
            Niche
            <input value={profile.niche} onChange={(e) => setProfile({ ...profile, niche: e.target.value })} />
          </label>
          <label>
            Audience
            <input type="number" value={profile.audience_size} onChange={(e) => setProfile({ ...profile, audience_size: Number(e.target.value) || 0 })} />
          </label>
          <label>
            Plateformes
            <input value={profile.platforms} onChange={(e) => setProfile({ ...profile, platforms: e.target.value })} />
          </label>
          <label>
            Budget Min
            <input type="number" value={profile.min_budget} onChange={(e) => setProfile({ ...profile, min_budget: Number(e.target.value) || 0 })} />
          </label>
        </div>
        <label style={{ display: "block", marginTop: 10 }}>
          Bio
          <textarea value={profile.bio} onChange={(e) => setProfile({ ...profile, bio: e.target.value })} />
        </label>
        <label style={{ display: "block", marginTop: 10 }}>
          <input
            type="checkbox"
            checked={profile.auto_apply}
            onChange={(e) => setProfile({ ...profile, auto_apply: e.target.checked })}
          />
          Auto apply
        </label>
        <button type="submit">Sauvegarder profil</button>
      </form>

      <p><small>API: {API}</small></p>
    </section>
  );
}
