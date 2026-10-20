import re
import unicodedata


def _strip_accents(text):
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def slugify(text, sep="-"):
    text = _strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9]+", sep, text)
    return text.strip(sep)


def truncate(text, width, suffix="..."):
    if len(text) <= width:
        return text
    if width <= len(suffix):
        return suffix[:width]
    return text[: width - len(suffix)].rstrip() + suffix


def title_case(text, minor=("a", "an", "and", "of", "the")):
    words = text.split()
    out = []
    for i, word in enumerate(words):
        if i > 0 and word.lower() in minor:
            out.append(word.lower())
        else:
            out.append(word[:1].upper() + word[1:].lower())
    return " ".join(out)


def count_words(s):
    return len(re.findall(r"\b\w+\b", s))


def normalize_whitespace(text):
    return " ".join(text.split())
