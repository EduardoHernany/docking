# users/emails.py
from urllib.parse import urlencode
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def _build_reset_html(email: str, token: str) -> str:
    reset_link = None
    if getattr(settings, "PASSWORD_RESET_URL", ""):
        qs = urlencode({"email": email, "token": token})
        reset_link = f"{settings.PASSWORD_RESET_URL}?{qs}"

    html = (
        "<p>Você solicitou a recuperação de senha.</p>"
        f"<p>Seu token é: <strong>{token}</strong></p>"
    )
    if reset_link:
        html += f'<p>Ou clique: <a href="{reset_link}">{reset_link}</a></p>'
    html += "<p>Se você não solicitou, ignore este e-mail.</p>"
    return html


def send_password_recovery_email(email: str, token: str) -> None:
    """
    Envia e-mail de recuperação via Resend.
    - Em dev (ou sem API key), faz fallback para console (log).
    Lança exceção em caso de falha real no envio.
    """
    html = _build_reset_html(email, token)
    subject = "Recuperação de senha"
    from_email = getattr(settings, "RESEND_FROM_EMAIL", "PlasmoDocking <onboarding@resend.dev>")

    # Fallback para console quando não há API key ou quando parametrizado
    if not getattr(settings, "RESEND_API_KEY", "") or getattr(settings, "EMAIL_FALLBACK_TO_CONSOLE", False):
        logger.warning(
            "Resend desativado ou em modo console. Simulando envio.",
            extra={"to": email, "subject": subject, "from": from_email}
        )
        # Loga o “conteúdo” para dev
        logger.info("EMAIL SIMULADO:\nFrom: %s\nTo: %s\nSubject: %s\nHTML:\n%s",
                    from_email, email, subject, html)
        return

    # Envio real via Resend HTTP API
    try:
        import resend
        resend.api_key = settings.RESEND_API_KEY

        payload = {
            "from": from_email,            # precisa ser domínio verificado em prod
            "to": [email],                 # pode ser string única também
            "subject": subject,
            "html": html,
        }
        resp = resend.Emails.send(payload)
        logger.info("Resend OK: %s", resp)  # resp tem id, etc.

    except Exception as e:
        # captura ResendError e quaisquer outros problemas de rede
        logger.exception("Falha ao enviar e-mail via Resend")
        raise
