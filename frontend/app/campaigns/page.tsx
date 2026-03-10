"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

type Campaign = {
  id: number;
  platform: string;
  title: string;
  brand: string;
  budget: number | null;
  niche: string | null;
  target_platform: string | null;
  status: string;
};

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [minBudget, setMinBudget] = useState<number>(0);
  const [niche, setNiche] = useState<string>("");
  const [targetPlatform, setTargetPlatform] = useState<string>("");
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    void loadCampaigns();
  }, []);

  async function loadCampaigns() {
    const params = new URLSearchParams();
    params.set("min_budget", String(minBudget));
    if (niche) params.set("niche", niche);
    if (targetPlatform) params.set("target_platform", targetPlatform);

    const res = await fetch(`${API}/campaigns?${params.toString()}`, { cache: "no-store" });
    if (res.ok) {
      setCampaigns(await res.json());
    }
  }

  async function applyCampaign(id: number) {
    setMessage("");
    const res = await fetch(`${API}/apply/${id}/async`, { method: "POST" });
    if (!res.ok) {
      setMessage("Echec lancement candidature");
      return;
    }
    const data = await res.json();
    setMessage(`Application queuee. task_id=${data.task_id}`);
  }

  return (
    <section>
      <div className="card">
        <h3>Filtres</h3>
        <div className="grid">
          <label>
            Budget Min
            <input type="number" value={minBudget} onChange={(e) => setMinBudget(Number(e.target.value) || 0)} />
          </label>
          <label>
            Niche
            <input value={niche} onChange={(e) => setNiche(e.target.value)} />
          </label>
          <label>
            Plateforme cible
            <input value={targetPlatform} onChange={(e) => setTargetPlatform(e.target.value)} />
          </label>
        </div>
        <button onClick={loadCampaigns}>Rafraichir</button>
        {!!message && <p><small>{message}</small></p>}
      </div>

      {campaigns.length === 0 && <div className="card">Aucune campagne en base.</div>}
      {campaigns.map((campaign) => (
        <article key={campaign.id} className="card">
          <h3>{campaign.title}</h3>
          <p>{campaign.brand} · {campaign.platform}</p>
          <p><small>Niche: {campaign.niche || "-"} · Plateforme cible: {campaign.target_platform || "-"}</small></p>
          <p><small>Budget: {campaign.budget ?? "N/A"} · Statut: {campaign.status}</small></p>
          <button onClick={() => applyCampaign(campaign.id)}>Postuler (async)</button>
        </article>
      ))}
    </section>
  );
}
