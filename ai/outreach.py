import ollama
from config import OLLAMA_MODEL


def generate_outreach_email(
    cv_text: str,
    sender_name: str,
    target_company: str,
    contact_name: str = "",
    contact_role: str = "",
    job_type: str = "CDI",
) -> dict:
    """
    Génère un email de candidature spontanée personnalisé.
    Retourne {subject, body, linkedin_dm}.
    """
    greeting = f"Bonjour {contact_name.split()[0]}," if contact_name else "Bonjour,"

    prompt = f"""Tu es expert en rédaction de candidatures spontanées en français.
Génère un email de candidature spontanée professionnel et personnalisé.

Informations du candidat (CV résumé):
{cv_text[:2000]}

Destinataire:
- Nom: {contact_name or "Responsable RH"}
- Rôle: {contact_role or "Responsable recrutement"}
- Entreprise: {target_company}
- Type de contrat recherché: {job_type}

Règles:
- Commence par "{greeting}"
- 150-200 mots maximum
- Ton professionnel mais chaleureux
- Mentionne 2-3 compétences clés du CV qui correspondent à l'entreprise
- Termine par une demande d'entretien
- Pas de placeholders comme [votre nom]
- Pas de signature (ajoutée automatiquement)

Réponds avec ce format JSON exact:
{{
  "subject": "Candidature spontanée - [Poste visé] | [Prénom Nom]",
  "body": "corps de l'email complet",
  "linkedin_dm": "version courte pour DM LinkedIn (80 mots max)"
}}"""

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.7},
        )
        text = response["message"]["content"].strip()
        import json
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            result = json.loads(text[start:end])
            # Replace placeholder in subject
            if sender_name:
                result["subject"] = result.get("subject", "").replace("[Prénom Nom]", sender_name)
            return result
        return {
            "subject": f"Candidature spontanée | {sender_name}",
            "body": text,
            "linkedin_dm": text[:300],
        }
    except Exception as e:
        return {
            "subject": f"Candidature spontanée | {sender_name}",
            "body": f"Erreur génération: {e}",
            "linkedin_dm": "",
        }
