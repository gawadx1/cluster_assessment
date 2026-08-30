"""Name and text normalization utilities."""
from __future__ import annotations
import re
import unicodedata


PREFIX = re.compile(r"^(py/|ph/|p/)\s*", re.IGNORECASE)
NOISE = re.compile(
    r"\b(wh-\d+|branch\s*\d+|br\.?\s*\d+|6th zone|main road|station\s*st\.?|mall|\(\d+\))\b",
    re.IGNORECASE,
)
STOPWORDS = {"pharmacy", "pharma", "pharm", "el", "al", "the", "and", "ph"}


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).lower()
    text = PREFIX.sub("", text)
    text = NOISE.sub(" ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return normalize_whitespace(text)


def meaningful_tokens(name_norm: str) -> set[str]:
    return {t for t in name_norm.split() if t and t not in STOPWORDS}


def normalize_lookup_key(value) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return ""
    return normalize_whitespace(str(value).lower())


AREA_ALIASES = {
    "smouha": "Smouha",
    "smuoha": "Smouha",
    "smoouha": "Smouha",
    "smmouha": "Smouha",
    "smouhaa": "Smouha",
    "msouha": "Smouha",
    "smoua": "Smouha",
    "souha": "Smouha",
    "nasr city": "Nasr City",
    "nasr ity": "Nasr City",
    "nasrcity": "Nasr City",
    "nasr-city": "Nasr City",
    "nasr ciity": "Nasr City",
    "faisal": "Faisal",
    "faissal": "Faisal",
    "faysal": "Faisal",
    "mohandessin": "Mohandessin",
    "mohandseen": "Mohandessin",
    "mohandesin": "Mohandessin",
    "mohandiseen": "Mohandessin",
    "mohandessine": "Mohandessin",
}


def extract_area_from_text(text, official_areas=None):
    if text is None or (isinstance(text, float) and text != text):
        return None
    if official_areas is None:
        official_areas = ["Smouha", "Nasr City", "Faisal", "Mohandessin"]

    lowered = str(text).lower()
    lowered = re.sub(r"[^a-z0-9\s-]", " ", lowered)
    lowered = normalize_whitespace(lowered)

    for area in sorted(official_areas, key=len, reverse=True):
        if area.lower() in lowered:
            return area

    for alias, canonical in sorted(AREA_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if alias in lowered:
            return canonical
    return None
