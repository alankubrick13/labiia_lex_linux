from __future__ import annotations

from unittest.mock import MagicMock

from src.core.corpus import Corpus
from src.core.text_processor import TextProcessor


def _corpus_with_terms(freqs: dict[str, int]) -> Corpus:
    corpus = MagicMock(spec=Corpus)
    corpus.formes = {}
    corpus.lems = {}
    for token, freq in freqs.items():
        word = MagicMock()
        word.forme = token
        word.lem = token
        word.freq = int(freq)
        word.act = 1
        corpus.formes[token] = word
        corpus.lems[token] = word
    corpus.lexicon = None
    corpus.parametres = {}
    return corpus


def test_word_frequencies_filter_conversational_stopwords_without_lexicon() -> None:
    corpus = _corpus_with_terms(
        {
            "né": 30,
            "então": 25,
            "ali": 22,
            "lá": 21,
            "acho": 20,
            "gente": 19,
            "vacina": 12,
            "governo": 9,
            "saude_publica": 6,
        }
    )

    freqs = TextProcessor(corpus).get_word_frequencies(
        use_lemmas=True,
        active_only=True,
        exclude_stopwords=True,
    )

    terms = {term for term, _freq in freqs}
    assert {"vacina", "governo", "saude_publica"}.issubset(terms)
    assert {"né", "então", "ali", "lá", "acho", "gente"}.isdisjoint(terms)


def test_visual_content_filter_rejects_numeric_fragments_and_keeps_useful_acronyms() -> None:
    from src.core.stopword_policy import is_visual_content_term

    rejected = {"36", "10", "1015", "0", "A", "aa", "si", "Ainda", "né", "então", "assim"}
    accepted = {"vacina", "governo", "inteligencia_artificial", "OpenAI", "ChatGPT", "STF", "IA"}

    assert all(not is_visual_content_term(token) for token in rejected)
    assert all(is_visual_content_term(token) for token in accepted)


def test_user_reported_portuguese_stopwords_are_never_visual_terms() -> None:
    from src.core.stopword_policy import is_stopword_like, is_visual_content_term

    reported = {
        "de", "a", "o", "que", "e", "do", "da", "em", "um", "para",
        "com", "uma", "os", "no", "se", "na", "por", "mais", "as",
        "dos", "como", "mas", "foi", "ao", "ele", "das", "tem", "à",
        "seu", "sua", "ou", "ser", "quando", "muito", "há", "nos",
        "já", "está", "eu", "também", "só", "pelo", "pela", "até",
        "isso", "ela", "entre", "depois", "sem", "mesmo", "aos",
        "ter", "seus", "quem", "nas", "me", "esse", "eles", "estão",
        "você", "tinha", "foram", "essa", "num", "nem", "suas", "meu",
        "às", "minha", "têm", "numa", "pelos", "elas", "havia",
        "seja", "qual", "será", "nós", "tenho", "lhe", "deles",
        "essas", "esses", "pelas", "este", "fosse", "aquilo", "estava",
        "comigo", "contigo", "conosco", "vosco", "tudo", "todos",
        "todas", "nada", "cada", "outros", "outra", "outras", "isto",
        "aquele", "aquela", "aqueles", "aquelas", "meus", "minhas",
        "teu", "tua", "teus", "tuas", "nosso", "nossa", "nossos",
        "nossas", "vos", "lhes", "delas", "disto", "desta", "deste",
        "bem", "mal", "após", "antes", "sob", "sobre", "contra",
        "durante", "enquanto", "além", "então", "assim", "porque",
        "aqui", "ali", "ainda", "coisa", "são",
    }

    assert all(is_stopword_like(token) for token in reported)
    assert all(not is_visual_content_term(token) for token in reported)
