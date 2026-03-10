"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

type Application = {
  id: number;
  campaign_id: number;
  platform: string;
  status: string;
  generated_message: string | null;
  response_message: string | null;
};

export default function ApplicationsPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    void loadApplications();
  }, []);

  async function loadApplications() {
    const res = await fetch(`${API}/applications`, { cache: "no-store" });
    if (res.ok) {
      setApplications(await res.json());
    }
  }

  async function markReplied(id: number) {
    const res = await fetch(`${API}/applications/${id}/status?status=replied`, { method: "PATCH" });
    if (!res.ok) {
      setMessage("Echec mise a jour statut");
      return;
    }
    setMessage(`Application #${id} marquee comme replied`);
    await loadApplications();
  }

  return (
    <section>
      {!!message && <div className="card"><small>{message}</small></div>}
      {applications.length === 0 && <div className="card">Aucune candidature envoyee.</div>}
      {applications.map((item) => (
        <article key={item.id} className="card">
          <h3>Application #{item.id} - Campaign #{item.campaign_id}</h3>
          <p>{item.platform} · {item.status}</p>
          <p><small>{item.response_message || "No response message"}</small></p>
          {item.status !== "replied" && (
            <button onClick={() => markReplied(item.id)}>Marquer Replied</button>
          )}
        </article>
      ))}
    </section>
  );
}
