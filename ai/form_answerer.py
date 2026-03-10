"""
AIHawk-style LLM form answerer.
Uses the full user profile to answer any form question automatically.
"""
import json
import ollama
from config import OLLAMA_MODEL


def answer_form_question(profile: dict, question: str, field_type: str = "text", options: list = None) -> str:
    """
    Use Ollama to answer a form question based on the user profile.
    field_type: text, textarea, select, radio, checkbox, number
    options: list of choices for select/radio
    """
    profile_str = json.dumps(profile, ensure_ascii=False, indent=2)
    options_str = f"\nOptions disponibles: {options}" if options else ""

    if field_type in ("select", "radio") and options:
        prompt = f"""Tu es un assistant qui remplit des formulaires de candidature d'emploi.

Profil du candidat:
{profile_str}

Question du formulaire: "{question}"
Type de champ: {field_type}{options_str}

Choisis LA MEILLEURE option parmi les options disponibles qui correspond au profil.
Réponds UNIQUEMENT avec le texte exact de l'option choisie, rien d'autre."""
    elif field_type == "number":
        prompt = f"""Tu es un assistant qui remplit des formulaires de candidature d'emploi.

Profil du candidat:
{profile_str}

Question du formulaire: "{question}"
Type de champ: nombre

Réponds UNIQUEMENT avec un nombre entier approprié basé sur le profil, rien d'autre."""
    elif field_type == "checkbox":
        prompt = f"""Tu es un assistant qui remplit des formulaires de candidature d'emploi.

Profil du candidat:
{profile_str}

Question du formulaire: "{question}"
Type de champ: case à cocher (oui/non)

Réponds UNIQUEMENT avec "Yes" ou "No" selon le profil."""
    else:
        prompt = f"""Tu es un assistant qui remplit des formulaires de candidature d'emploi.

Profil du candidat:
{profile_str}

Question du formulaire: "{question}"

Réponds de manière concise et professionnelle en utilisant les informations du profil.
Si la question concerne les années d'expérience, calcule à partir des dates dans le profil.
Réponds UNIQUEMENT avec la valeur à saisir dans le champ, rien d'autre."""

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1},
        )
        answer = response["message"]["content"].strip()
        # Clean up the answer - remove quotes if present
        answer = answer.strip('"\'')
        return answer[:500]
    except Exception as e:
        return ""


def get_profile_value(profile: dict, key: str) -> str:
    """Get a direct value from profile for common fields."""
    mapping = {
        "first_name": profile.get("personal_information", {}).get("name", ""),
        "last_name": profile.get("personal_information", {}).get("surname", ""),
        "email": profile.get("personal_information", {}).get("email", ""),
        "phone": profile.get("personal_information", {}).get("phone", ""),
        "city": profile.get("personal_information", {}).get("city", ""),
        "country": profile.get("personal_information", {}).get("country", ""),
        "linkedin": profile.get("personal_information", {}).get("linkedin", ""),
        "github": profile.get("personal_information", {}).get("github", ""),
        "salary": profile.get("salary_expectations", {}).get("salary_range_usd", ""),
        "notice_period": profile.get("availability", {}).get("notice_period", ""),
    }
    return mapping.get(key, "")
