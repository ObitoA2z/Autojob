"""
Send job application by email with CV attachment.
Uses Gmail SMTP (requires App Password when 2FA is enabled).
"""
import asyncio
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


def send_application_email(
    smtp_user: str,
    smtp_password: str,
    to_email: str,
    subject: str,
    body: str,
    cv_path: str,
    sender_name: str = "",
) -> dict:
    """
    Envoie une candidature par email avec le CV en pièce jointe.
    Utilise Gmail SMTP (port 587, TLS).
    """
    if not smtp_user or not smtp_password:
        return {"success": False, "message": "Email: configurer l'email SMTP dans le profil"}
    if not to_email:
        return {"success": False, "message": "Email: pas d'adresse de contact trouvée"}

    try:
        msg = MIMEMultipart()
        msg["From"] = f"{sender_name} <{smtp_user}>" if sender_name else smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Attach CV
        cv_file = Path(cv_path)
        if cv_file.exists():
            with open(cv_file, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={cv_file.name}")
            msg.attach(part)

        # Send via Gmail SMTP
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())

        return {"success": True, "message": f"Candidature envoyée par email à {to_email}"}

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "Email: authentification Gmail échouée. Utilisez un mot de passe d'application Gmail."}
    except smtplib.SMTPException as e:
        return {"success": False, "message": f"Erreur SMTP: {str(e)[:150]}"}
    except Exception as e:
        return {"success": False, "message": f"Erreur email: {str(e)[:150]}"}
