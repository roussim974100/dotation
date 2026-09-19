"""Confiance dans les en-tetes X-Forwarded-* : automatique selon l'appelant direct.

Un reverse proxy (nginx, Apache, Traefik...) tourne sur la meme machine ou le meme reseau prive : son
adresse vue par l'application est loopback ou privee. Un acces direct depuis Internet arrive d'une IP
publique. On ne fait donc confiance a X-Forwarded-For / -Proto / -Host que si l'appelant direct est
local ou prive ; sinon les en-tetes sont ignores (ils seraient falsifiables).

Sans configuration : le meme code fonctionne derriere un proxy et en acces direct.
Surcharge facultative (cas rares) : APP_TRUSTED_PROXIES=0 desactive toute confiance ; un entier N (>=1) force
la confiance en N proxys meme si l'appelant direct a une IP publique (ex. load balancer cloud).
"""
import ipaddress
import os

from werkzeug.middleware.proxy_fix import ProxyFix


def is_trusted_peer(remote_addr):
    """Vrai si l'appelant direct est un proxy plausible : loopback, prive ou lien local."""
    try:
        address = ipaddress.ip_address(str(remote_addr or "").strip().split("%")[0])
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


def _configured_hops():
    """None = automatique ; 0 = jamais ; N = nombre de proxys de confiance."""
    raw = os.environ.get("APP_TRUSTED_PROXIES", "").strip().lower()
    if raw in ("", "auto"):
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


class AutoProxyFix:
    """Applique ProxyFix seulement quand l'appelant direct est de confiance."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app
        hops = _configured_hops()
        self.forced_off = hops == 0
        self.forced_on = bool(hops)
        count = hops or 1
        self.fixed_app = ProxyFix(wsgi_app, x_for=count, x_proto=count, x_host=count)

    def __call__(self, environ, start_response):
        if not self.forced_off and (self.forced_on or is_trusted_peer(environ.get("REMOTE_ADDR"))):
            return self.fixed_app(environ, start_response)
        return self.wsgi_app(environ, start_response)
