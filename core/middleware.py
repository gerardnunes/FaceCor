from django.shortcuts import redirect

_ja_configurado = False


class SetupMiddleware:
    """Enquanto não existir nenhum usuário, tudo redireciona para /setup/ (criação do login master)."""

    LIVRES = ("/setup/", "/static/", "/saude/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        global _ja_configurado
        if not _ja_configurado:
            from .models import User

            _ja_configurado = User.objects.exists()
        if not _ja_configurado and not request.path.startswith(self.LIVRES):
            return redirect("setup")
        return self.get_response(request)


class SecurityHeadersMiddleware:
    CSP = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        "media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        r = self.get_response(request)
        r.headers.setdefault("Content-Security-Policy", self.CSP)
        r.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        if not request.path.startswith("/static/"):
            r.headers.setdefault("Cache-Control", "no-store")
        return r
