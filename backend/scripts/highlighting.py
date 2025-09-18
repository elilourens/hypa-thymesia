import re
from typing import List, Dict
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet

lemmatizer = WordNetLemmatizer()


def get_synonyms(word: str) -> List[str]:
    """
    Return a list of synonyms for the given word using WordNet.
    """
    syns = set()
    for syn in wordnet.synsets(word):
        for lemma in syn.lemmas():
            syns.add(lemma.name().replace("_", " "))
    return list(syns)


def normalize_token(token: str) -> str:
    """
    Normalize a token for comparison:
    - lowercase
    - lemmatize as a noun
    - heuristic stripping for certain nominal suffixes
    """
    token_lower = token.lower()
    lemma = lemmatizer.lemmatize(token_lower, pos="n")

    # Only strip certain *nominal* suffixes, not "ly"
    for suffix in ["ship", "ment", "ness", "ity", "tion", "sion"]:
        if token_lower.endswith(suffix):
            return token_lower[: -len(suffix)]

    return lemma


def find_highlights(text: str, query: str) -> List[Dict]:
    """
    Highlight tokens in `text` that match the query or its synonyms after normalization.
    """
    if not query or not text:
        return []

    query_norm = normalize_token(query)

    # Candidate normalized terms
    terms = {query_norm}
    for syn in get_synonyms(query):
        terms.add(normalize_token(syn))

    spans: List[Dict] = []

    # Tokenize text into words (whole tokens only)
    for match in re.finditer(r"\w+", text):
        token = match.group(0)
        token_norm = normalize_token(token)

        # ✅ Require exact equality of normalized forms
        if token_norm in terms:
            spans.append(
                {
                    "start": match.start(),
                    "end": match.end(),
                    "term": token,
                }
            )

    return spans
