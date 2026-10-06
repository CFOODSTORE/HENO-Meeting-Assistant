from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import jwt
import keyring
import requests

from .config import Settings

AUTH_BASE = "https://auth.openai.com"
AUTHORIZE_URL = f"{AUTH_BASE}/api/accounts/authorize"
TOKEN_URL = f"{AUTH_BASE}/api/accounts/oauth/token"
OIDC_CONFIG_URL = f"{AUTH_BASE}/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
SERVICE = "HENO-Meeting-Assistant"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"


class ChatGPTAuthError(RuntimeError):
    pass


class _CredentialStore:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _key(self, name: str) -> str:
        subject = self.settings.chatgpt_subject or self.settings.chatgpt_email or "default"
        return f"{subject}:{name}"

    def get(self, name: str) -> str:
        try:
            return keyring.get_password(SERVICE, self._key(name)) or ""
        except Exception:
            return ""

    def set(self, name: str, value: str) -> None:
        if not value:
            return
        keyring.set_password(SERVICE, self._key(name), value)

    def delete_all(self) -> None:
        for name in ("access_token", "refresh_token", "id_token", "expires_at"):
            try:
                keyring.delete_password(SERVICE, self._key(name))
            except Exception:
                pass


class ChatGPTAuthManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.creds = _CredentialStore(settings)

    @property
    def is_connected(self) -> bool:
        return bool(self.settings.chatgpt_client_id and self.creds.get("refresh_token"))

    def sign_out(self) -> None:
        self.creds.delete_all()
        self.settings.chatgpt_client_id = ""
        self.settings.chatgpt_email = ""
        self.settings.chatgpt_subject = ""
        self.settings.chatgpt_model = ""
        self.settings.save()

    @staticmethod
    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    def connect(self, timeout: int = 180) -> dict[str, Any]:
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = self._b64url(hashlib.sha256(verifier.encode()).digest())

        result: dict[str, Any] = {}
        done = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler_self):  # noqa: N802
                parsed = urllib.parse.urlparse(handler_self.path)
                if parsed.path != "/auth/callback":
                    handler_self.send_response(404)
                    handler_self.end_headers()
                    return
                result.update({k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()})
                body = (
                    "<html><body style='font-family:Segoe UI,sans-serif;padding:40px'>"
                    "<h2>HENO est connecté à ChatGPT.</h2>"
                    "<p>Vous pouvez fermer cette fenêtre et revenir dans HENO.</p>"
                    "</body></html>"
                ).encode()
                handler_self.send_response(200)
                handler_self.send_header("Content-Type", "text/html; charset=utf-8")
                handler_self.send_header("Content-Length", str(len(body)))
                handler_self.end_headers()
                handler_self.wfile.write(body)
                done.set()

            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        redirect_uri = f"http://127.0.0.1:{port}/auth/callback"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        first_registration = not self.settings.chatgpt_client_id
        client_id = self.settings.chatgpt_client_id or "dynamic_agent_client"
        params = {
            "client_id": client_id,
            "ext_agent_host_id": self.settings.ext_agent_host_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }
        if first_registration:
            params["agent_name_hint"] = "HENO Meeting Assistant"
        else:
            id_token_hint = self.creds.get("id_token")
            if id_token_hint:
                params["id_token_hint"] = id_token_hint
            if self.settings.chatgpt_email:
                params["login_hint"] = self.settings.chatgpt_email

        webbrowser.open(AUTHORIZE_URL + "?" + urllib.parse.urlencode(params))
        if not done.wait(timeout):
            server.shutdown()
            raise ChatGPTAuthError("La connexion ChatGPT a expiré. Relancez la connexion.")
        server.shutdown()

        if result.get("state") != state:
            raise ChatGPTAuthError("État OAuth invalide.")
        if result.get("error"):
            raise ChatGPTAuthError(result.get("error_description") or result["error"])
        code = result.get("code")
        if not code:
            raise ChatGPTAuthError("Aucun code d'autorisation reçu.")

        issued_client_id = result.get("client_id") or self.settings.chatgpt_client_id
        if first_registration and not issued_client_id:
            raise ChatGPTAuthError("OpenAI n'a pas retourné le client_id dynamique attendu.")
        if not first_registration and result.get("client_id") and result["client_id"] != self.settings.chatgpt_client_id:
            raise ChatGPTAuthError("Le client_id retourné ne correspond pas au compte sélectionné.")

        token_response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": issued_client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "resource": RESOURCE,
            },
            timeout=30,
        )
        if not token_response.ok:
            raise ChatGPTAuthError(f"Échec de l'échange OAuth: {token_response.text[:300]}")
        tokens = token_response.json()
        self._validate_and_store(tokens, issued_client_id, nonce)
        return {
            "email": self.settings.chatgpt_email,
            "scopes": tokens.get("scope", "").split(),
            "client_id": issued_client_id,
        }

    def _validate_and_store(self, tokens: dict[str, Any], client_id: str, nonce: str | None = None) -> None:
        id_token = tokens.get("id_token")
        if not id_token:
            raise ChatGPTAuthError("Jeton d'identité manquant.")
        oidc = requests.get(OIDC_CONFIG_URL, timeout=20).json()
        jwks_uri = oidc["jwks_uri"]
        issuer = oidc["issuer"]
        jwk_client = jwt.PyJWKClient(jwks_uri)
        signing_key = jwk_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=client_id,
            issuer=issuer,
        )
        if nonce is not None and claims.get("nonce") != nonce:
            raise ChatGPTAuthError("Nonce OIDC invalide.")
        scopes = (tokens.get("scope") or "").split()
        if "chatgpt.tokens.use.direct" not in scopes:
            raise ChatGPTAuthError(
                "Connexion réussie, mais l'autorisation d'utiliser le plan ChatGPT n'a pas été accordée."
            )

        self.settings.chatgpt_client_id = client_id
        self.settings.chatgpt_email = claims.get("email", "")
        self.settings.chatgpt_subject = claims.get("sub", "")
        self.settings.save()
        self.creds = _CredentialStore(self.settings)
        self.creds.set("access_token", tokens.get("access_token", ""))
        self.creds.set("refresh_token", tokens.get("refresh_token", ""))
        self.creds.set("id_token", id_token)
        expires_at = str(int(time.time()) + int(tokens.get("expires_in", 3600)))
        self.creds.set("expires_at", expires_at)

    def access_token(self) -> str:
        token = self.creds.get("access_token")
        expires_at = int(self.creds.get("expires_at") or "0")
        if token and expires_at > time.time() + 120:
            return token
        return self.refresh()

    def refresh(self) -> str:
        refresh_token = self.creds.get("refresh_token")
        if not refresh_token or not self.settings.chatgpt_client_id:
            raise ChatGPTAuthError("HENO n'est pas connecté à ChatGPT.")
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.settings.chatgpt_client_id,
                "refresh_token": refresh_token,
                "resource": RESOURCE,
            },
            timeout=30,
        )
        if not response.ok:
            raise ChatGPTAuthError("La session ChatGPT doit être reconnectée.")
        tokens = response.json()
        if tokens.get("id_token"):
            if "refresh_token" not in tokens:
                tokens["refresh_token"] = refresh_token
            self._validate_and_store(tokens, self.settings.chatgpt_client_id, nonce=None)
        else:
            self.creds.set("access_token", tokens.get("access_token", ""))
            self.creds.set("refresh_token", tokens.get("refresh_token", refresh_token))
            expires_at = str(int(time.time()) + int(tokens.get("expires_in", 3600)))
            self.creds.set("expires_at", expires_at)
        return self.creds.get("access_token")
