"""Grund eines Netzfehlers als festes deutsches Wort.

Die Meldungen «Briefkasten nicht erreichbar (URLError)» sagten nie, warum. Dieser Helfer macht aus dem Fehler ein
kurzes Wort für Log und Telegram. Es gibt nie den rohen Fehlertext zurück: Der kann bei Telegram den Token aus der
Adresse enthalten. Unbekanntes heisst «unbekannt».
"""
import errno
import socket
import ssl

# Texte, die URLError als reinen String mitbringt (z.B. macOS: «nodename nor servname provided»), in Reihenfolge.
_TEXTE = (
    (("nodename nor servname", "name or service not known", "getaddrinfo", "name resolution"), "Name nicht aufgelöst"),
    (("timed out", "timeout"), "Zeitüberschreitung"),
    (("refused",), "Verbindung abgelehnt"),
    (("no route to host", "host is down"), "Host nicht erreichbar"),
    (("network is unreachable", "network is down"), "Netz nicht erreichbar"),
)


def netzgrund(fehler: BaseException) -> str:
    """Eines von: Zeitüberschreitung, Name nicht aufgelöst, Verbindung abgelehnt, Verbindung zurückgesetzt,
    Netz nicht erreichbar, Host nicht erreichbar, TLS-Fehler, unbekannt."""
    grund = getattr(fehler, "reason", fehler)  # URLError trägt den eigentlichen Fehler in .reason
    if isinstance(grund, str):
        text = grund.lower()
        for woerter, wort in _TEXTE:
            if any(w in text for w in woerter):
                return wort
        return "unbekannt"
    if isinstance(grund, (TimeoutError, socket.timeout)):
        return "Zeitüberschreitung"
    if isinstance(grund, socket.gaierror):
        return "Name nicht aufgelöst"
    if isinstance(grund, ConnectionRefusedError):
        return "Verbindung abgelehnt"
    if isinstance(grund, ConnectionResetError):  # dazu gehört auch http.client.RemoteDisconnected
        return "Verbindung zurückgesetzt"
    if isinstance(grund, ssl.SSLError):
        return "TLS-Fehler"
    if isinstance(grund, OSError):
        if grund.errno in (errno.ENETUNREACH, errno.ENETDOWN):
            return "Netz nicht erreichbar"
        if grund.errno in (errno.EHOSTUNREACH, errno.EHOSTDOWN):
            return "Host nicht erreichbar"
    return "unbekannt"
