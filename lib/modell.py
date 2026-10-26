from dataclasses import dataclass


@dataclass
class Slide:
    nummer: int
    typ: str  # hook | schritt | text | schluss
    ueberschrift: str
    text: str = ""
    schritt: int | None = None
    hinweis: str | None = None


@dataclass
class Beitrag:
    slides: list[Slide]
    caption: str
