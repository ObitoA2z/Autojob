import ollama
from config import OLLAMA_MODEL


def analyze_match(cv_text: str, job_title: str, job_description: str) -> dict:
    """Analyze how well a CV matches a job offer. Returns score and reasoning."""
    prompt = f"""Tu es un expert en recrutement. Analyse la compatibilité entre ce CV et cette offre d'emploi.

CV du candidat:
{cv_text[:3000]}

Offre d'emploi:
Titre: {job_title}
Description: {job_description[:2000]}

Réponds UNIQUEMENT avec ce format JSON (pas de texte avant ou après):
{{
    "score": <nombre entre 0 et 1>,
    "reasoning": "<explication courte en 1-2 phrases>"
}}"""

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1},
        )
        text = response["message"]["content"].strip()
        # Extract JSON from response
        import json
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
        return {"score": 0.5, "reasoning": "Impossible d'analyser la compatibilité"}
    except Exception as e:
        return {"score": 0.5, "reasoning": f"Erreur Ollama: {str(e)}"}


def generate_cover_letter(cv_text: str, job_title: str, company: str, job_description: str) -> str:
    """Generate a personalized cover letter."""
    prompt = f"""Tu es un expert en rédaction de lettres de motivation en français.
Génère une lettre de motivation professionnelle et personnalisée.

CV du candidat:
{cv_text[:3000]}

Offre d'emploi:
Titre: {job_title}
Entreprise: {company}
Description: {job_description[:2000]}

Écris une lettre de motivation courte (max 250 mots), professionnelle et personnalisée.
Ne mets pas de placeholders comme [Nom] ou [Adresse]. Commence directement par "Madame, Monsieur,".
"""

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.7},
        )
        return response["message"]["content"].strip()
    except Exception as e:
        return f"Erreur lors de la génération: {str(e)}"
