"""Lexicon support for IRaMuTeQ-compatible lemma and grammar lookup."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, Optional, Set, Tuple

from ..utils.paths import PathManager


# Mirrors IRaMuTeQ's configuration/key.cfg behavior (1=active, 2=supplementary).
IRAMUTEQ_GRAM_STATUS = {
    "art_def": 2,
    "pre": 2,
    "adj_dem": 2,
    "ono": 2,
    "pro_per": 2,
    "ver_sup": 2,
    "adv": 1,
    "ver": 1,
    "adj_ind": 2,
    "adj_pos": 2,
    "aux": 2,
    "adj_int": 2,
    "pro_ind": 2,
    "adj": 1,
    "pro_dem": 2,
    "nom": 1,
    "art_ind": 2,
    "pro_pos": 2,
    "nom_sup": 2,
    "adv_sup": 2,
    "adj_sup": 2,
    "adj_num": 2,
    "pro_rel": 2,
    "con": 2,
    "num": 2,
    "nr": 1,
    "sw": 2,
    "pro": 2,
}
ACTIVE_GRAM_TYPES = {
    gram for gram, status in IRAMUTEQ_GRAM_STATUS.items()
    if int(status) == 1
}
SUPPLEMENTARY_GRAM_TYPES = {
    gram for gram, status in IRAMUTEQ_GRAM_STATUS.items()
    if int(status) != 1
}

# Fallback list used to improve coverage when lexical lookup misses variants.
# Based on spaCy Portuguese stopwords (416 words) + IRaMuTeQ supplements.
# This provides comprehensive coverage without requiring spaCy runtime import.
FALLBACK_STOPWORDS_PT = {
    # Artigos e determinantes
    "a", "à", "às", "as", "o", "os", "um", "uma", "uns", "umas",
    "ao", "aos", "aquela", "aquelas", "aquele", "aqueles", "aquilo",
    "aquí", "ela", "elas", "ele", "eles", "essa", "essas", "esse",
    "esses", "esta", "estas", "este", "estes", "isto", "isso",
    "outra", "outras", "outro", "outros",
    # Preposições
    "de", "da", "das", "do", "dos", "dela", "delas", "dele", "deles",
    "em", "na", "nas", "no", "nos", "num", "numa", "nuns", "numas",
    "com", "como", "sem", "sob", "sobre", "entre", "contra", "perante",
    "para", "por", "pela", "pelas", "pelo", "pelos", "até", "ate", "ateh",
    "até", "após", "apos", "antes", "depois", "desde", "durante",
    "conforme", "consoante", "durante", "excepto", "exceto", "mediante",
    "salvo", "segundo", "senão", "visto", "através", "atravez",
    # Conjunções
    "e", "ou", "mas", "nem", "que", "se", "quando", "quanto", "porque",
    "porquê", "pois", "então", "entao", "assim", "logo", "portanto",
    "contudo", "todavia", "no_entanto", "porém", "porem", "entretanto",
    "senão", "já", "ja", "tanto", "como", "assim_como", "bem_como",
    "quer", "ora", "já_que", "visto_que", "pois_que", "porquanto",
    # Advérbios
    "muito", "mais", "menos", "bem", "mal", "tão", "tao", "assim",
    "também", "tambem", "só", "so", "tudo", "nada", "algo", "cada",
    "sempre", "nunca", "jamais", "ainda", "já", "ja", "agora", "antes",
    "depois", "logo", "cedo", "tarde", "ontem", "hoje", "amanhã",
    "aqui", "aí", "ai", "ali", "lá", "la", "acolá", "acola", "onde",
    "aonde", "longe", "perto", "dentro", "fora", "acima", "abaixo",
    "adiante", "atrás", "atras", "através", "atravez", "defronte",
    "diante", "apenas", "somente", " unicamente", "mesmo", "próprio",
    "proprio", "outro", "talvez", "possivelmente", "provavelmente",
    "certamente", "realmente", "deveras", "bastante", "demais",
    "tanto", "quão", "quao", "quase", "menos", "tudo", "nada",
    # Pronomes pessoais
    "eu", "tu", "ele", "ela", "nós", "nos", "vós", "vos", "eles",
    "elas", "você", "voce", "vocês", "voces", "si",
    # Pronomes oblíquos
    "me", "te", "lhe", "lhes", "se", "nos", "vos", "o", "os", "a",
    "as", "lo", "la", "los", "las", "no", "na", "nos", "nas", "lhe",
    # Pronomes possessivos
    "meu", "minha", "meus", "minhas", "teu", "tua", "teus", "tuas",
    "seu", "sua", "seus", "suas", "nosso", "nossa", "nossos", "nossas",
    "vosso", "vossa", "vossos", "vossas",
    # Pronomes demonstrativos (já cobertos acima)
    # Pronomes indefinidos
    "qualquer", "quaisquer", "algum", "alguma", "alguns", "algumas",
    "outrem", "nenhum", "nenhuma", "todo", "toda", "todos", "todas",
    "qual", "quais", "quem", "cujo", "cuja", "cujos", "cujas",
    # Numerais cardinais escritos
    "zero", "um", "dois", "três", "tres", "quatro", "cinco", "seis",
    "sete", "oito", "nove", "dez", "onze", "doze", "treze", "catorze",
    "quinze", "dezesseis", "dezessete", "dezoito", "dezenove", "vinte",
    "cem", "mil",
    # Numerais ordinais escritos
    "primeiro", "primeira", "segundo", "segunda", "terceiro", "terceira",
    "quarto", "quarta", "quinto", "quinta", "sexto", "sexta",
    "sétimo", "setimo", "sétima", "setima", "oitavo", "oitava",
    "nono", "nona", "décimo", "decimo", "décima", "decima",
    # Verbos auxiliares e comuns (formas principais)
    "ser", "sou", "é", "e", "somos", "são", "sao", "era", "eras", "era",
    "éramos", "eram", "fui", "foste", "foi", "fomos", "foram", "fora",
    "foras", "foram", "fôramos", "foram", "seja", "sejas", "seja",
    "sejamos", "sejam", "fosse", "fosses", "fosse", "fôssemos", "fossem",
    "for", "fores", "for", "formos", "forem", "sendo", "sido",
    "estar", "estou", "está", "esta", "estamos", "estão", "estao",
    "estava", "estavas", "estava", "estávamos", "estavam", "estive",
    "estiveste", "esteve", "estivemos", "estiveram", "estivera",
    "estiveras", "estivera", "estivéramos", "estiveram", "esteja",
    "estejas", "esteja", "estejamos", "estejam", "estivesse",
    "estivesses", "estivesse", "estivéssemos", "estivessem",
    "haver", "hei", "há", "ha", "havemos", "hão", "hao", "havia",
    "havias", "havia", "havíamos", "haviam", "houve", "houveste",
    "houve", "houvemos", "houveram", "houvera", "houveras", "houvera",
    "houvéramos", "houveram", "haja", "hajas", "haja", "hajamos",
    "hajam", "houvesse", "houvesses", "houvesse", "houvéssemos",
    "houvessem", "tendo",
    "ter", "tenho", "tens", "tem", "temos", "têm", "tem", "tinha",
    "tinhas", "tinha", "tínhamos", "tinham", "tive", "tiveste", "teve",
    "tivemos", "tiveram", "tivera", "tiveras", "tivera", "tivéramos",
    "tiveram", "tenha", "tenhas", "tenha", "tenhamos", "tenham",
    "tivesse", "tivesses", "tivesse", "tivéssemos", "tivessem",
    "vir", "venho", "vens", "vem", "vimos", "vêm", "vem", "vinha",
    "vir", "viram", "virão",
    "dar", "dou", "dá", "da", "damos", "dão", "dao", "dei", "deste",
    "deu", "demos", "deram", "dê", "de", "demos", "deem",
    "ir", "vou", "vais", "vai", "vamos", "vão", "vao", "ia", "ias",
    "ia", "íamos", "iam", "fui", "foste", "foi", "fomos", "foram",
    "vá", "va", "vamos", "vão", "vao", "fosse", "fosses", "fosse",
    "fôssemos", "fossem",
    "fazer", "faço", "faco", "fazes", "faz", "fazemos", "fazeis",
    "fazem", "fiz", "fizeste", "fez", "fizemos", "fizeram", "fizera",
    "fizeras", "fizéramos", "fizeram", "faça", "facas", "faça",
    "façamos", "facamos", "façam", "facam", "fizesse", "fizesses",
    "fizesse", "fizéssemos", "fizessem",
    "poder", "posso", "podes", "pode", "podemos", "podeis", "podem",
    "podia", "podias", "podia", "podíamos", "podiam", "pude", "pudeste",
    "pôde", "pode", "pudemos", "puderam", "pudera", "puderas", "pudera",
    "pudéramos", "puderam", "possa", "possas", "possa", "possamos",
    "possam", "pudesse", "pudesses", "pudesse", "pudéssemos", "pudessem",
    "querer", "quero", "queres", "quer", "queremos", "quereis", "querem",
    "queria", "querias", "queria", "queríamos", "queriam",
    "saber", "sei", "sabes", "sabe", "sabemos", "sabeis", "sabem",
    "sabia", "sabias", "sabia", "sabíamos", "sabiam", "soube", "soubeste",
    "soube", "soubemos", "souberam", "soubera", "souberas", "soubera",
    "soubéramos", "souberam", "saiba", "saibas", "saiba", "saibamos",
    "saibam", "soubesse", "soubesses", "soubesse", "soubéssemos",
    "soubessem",
    "dizer", "digo", "dizes", "diz", "dizemos", "dizeis", "dizem",
    "dei", "deu", "deram", "dizia", "dizias", "dizia", "dizíamos",
    "diziam", "disse", "disseste", "disse", "dissemos", "disseram",
    "dissera", "disseras", "dissera", "disséramos", "disseram",
    "diga", "digas", "diga", "digamos", "digam", "dissesse", "dissesses",
    "dissesse", "disséssemos", "dissessem",
    "ver", "vejo", "vês", "ves", "vê", "ve", "vemos", "veis", "vêem",
    "veem", "via", "vias", "via", "víamos", "viam", "vi", "viste", "viu",
    "vimos", "viram", "vira", "viras", "vira", "viramos", "viram",
    "veja", "vejas", "veja", "vejamos", "vejam", "visse", "visses",
    "visse", "víssemos", "vissem",
    # Verbos de ligação/existência
    "parece", "parecer", "ficar", "fica", "ficam", "continuar",
    "continua", "permanecer", "permanece", "tornar-se", "tornar",
    "virar", "vira",
    # Palavras de negação/afirmação
    "não", "nao", "sim", "nunca", "jamais", "também", "tambem",
    # Interjeições comuns
    "oh", "ah", "eh", "ih", "uh", "ai", "ui", "olá", "ola", "adeus",
    # Expressões temporais
    "agora", "antes", "depois", "logo", "então", "entao", "hoje",
    "ontem", "amanhã", "sempre", "nunca", "já", "ja", "ainda",
    # Palavras genéricas
    "coisa", "coisas", "pessoa", "pessoas", "lugar", "lugares", "vez",
    "vezes", "tempo", "maneira", "modo", "caso", "fato", "fatos",
    "parte", "partes", "aspecto", "aspectos", "ponto", "pontos",
    "questão", "questao", "questões", "questoes", "relação", "relacao",
    "relações", "relacoes", "forma", "formas", "tipo", "tipos",
    "grupo", "grupos", "sistema", "sistemas", "estado", "estados",
    "nível", "nivel", "sentido", "valor", "exemplo", "final", "fim",
    "início", "inicio", "princípio", "principio", "momento", "caminho",
    "área", "area", "lado", "lugar", "pois", "entanto",
    # Artigos e formas variantes com acentos
    "à", "às", "á", "é", "í", "ó", "ú", "â", "ê", "ô",
    # Outras formas comuns
    "toda", "todas", "todo", "todos", "mesmo", "mesma", "mesmos", "mesmas",
    "outro", "outra", "outros", "outras", "certo", "certa", "certos",
    "certas", "tal", "tais", "qualquer", "quaisquer", "outrem",
    "demais", "tanto", "tanta", "tantos", "tantas", "quanto", "quanta",
    "quantos", "quantas", "vários", "varios", "várias", "varias",
    "pouco", "pouca", "poucos", "poucas", "bastante", "bastantes",
    "maior", "menor", "melhor", "pior", "maioria", "maiorias",
    "grande", "grandes", "pequeno", "pequena", "pequenos", "pequenas",
    "novo", "nova", "novos", "novas", "velho", "velha", "velhos",
    "velhas", "bom", "boa", "bons", "boas", "mau", "má", "ma",
    "máximo", "maximo", "mínimo", "minimo", "próximo", "proximo",
    "próxima", "proxima", "próximos", "proximos", "próximas", "proximas",
    "último", "ultimo", "última", "ultima", "últimos", "ultimos",
    "últimas", "ultimas", "próprio", "proprio", "própria", "propria",
    "próprios", "proprios", "próprias", "proprias",
    # English stopwords (para textos mistos)
    "the", "and", "for", "with", "from", "this", "that", "was", "were",
    "are", "not", "have", "has", "had", "can", "could", "will", "would",
    "off", "et", "al", "et_al",
    # Referências web/acadêmicas
    "http", "https", "www", "doi", "issn", "isbn", "url", "html", "pdf",
}
SUPPORTED_LANGUAGE_FILES = {
    "portuguese": "lexique_pt.txt",
    "pt": "lexique_pt.txt",
    "pt_br": "lexique_pt.txt",
    "english": "lexique_en.txt",
    "en": "lexique_en.txt",
    "french": "lexique_fr.txt",
    "fr": "lexique_fr.txt",
}
SUPPORTED_EXPRESSION_FILES = {
    "portuguese": "expression_pt.txt",
    "pt": "expression_pt.txt",
    "pt_br": "expression_pt.txt",
}


def resolve_lexicon_path(language: str) -> Path:
    """Resolve lexicon file path from user language setting."""
    key = (language or "portuguese").strip().lower()
    filename = SUPPORTED_LANGUAGE_FILES.get(key, SUPPORTED_LANGUAGE_FILES["portuguese"])
    return PathManager.dictionaries_dir() / filename


def resolve_expression_path(language: str) -> Path:
    """Resolve compound-expression file path from user language setting."""
    key = (language or "portuguese").strip().lower()
    filename = SUPPORTED_EXPRESSION_FILES.get(key, SUPPORTED_EXPRESSION_FILES["portuguese"])
    return PathManager.dictionaries_dir() / filename


def _strip_accents(value: str) -> str:
    """Remove accents from one token preserving alphanumeric chars."""
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _iter_portuguese_singular_candidates(token: str) -> Tuple[str, ...]:
    """
    Generate conservative singularization candidates for Portuguese tokens.

    This is a fallback used only when direct lexical lookup fails.
    """
    base = (token or "").strip().lower()
    if len(base) < 3:
        return ()

    candidates: list[str] = []
    seen: Set[str] = set()

    def _push(value: str) -> None:
        candidate = (value or "").strip().lower()
        if len(candidate) < 2 or candidate == base or candidate in seen:
            return
        seen.add(candidate)
        candidates.append(candidate)

    # Irregular/frequent Portuguese plural endings.
    if base.endswith("ões"):
        _push(base[:-3] + "ão")
    if base.endswith("ães"):
        _push(base[:-3] + "ão")
        _push(base[:-3] + "ãe")
    if base.endswith("ãos"):
        _push(base[:-3] + "ão")
    if base.endswith("ais"):
        _push(base[:-3] + "al")
    if base.endswith("eis"):
        _push(base[:-3] + "el")
    if base.endswith("óis"):
        _push(base[:-3] + "ol")
    if base.endswith("is"):
        _push(base[:-2] + "il")
    if base.endswith("ns"):
        _push(base[:-2] + "m")

    # Generic fallback: remove plural trailing "s".
    if base.endswith("s") and len(base) > 3 and not base.endswith("ss"):
        _push(base[:-1])

    return tuple(candidates)


@lru_cache(maxsize=8)
def build_portuguese_stopwords_from_lexicon(lexicon_path: Optional[str] = None) -> FrozenSet[str]:
    """
    Build a robust Portuguese stopword set from IRaMuTeQ lexical dictionary.

    Includes:
    - Words/lemmas tagged as supplementary grammatical classes
    - Fallback stopwords for orthographic variants
    - Accent-folded variants (nao for nao/nao)
    """
    path = Path(lexicon_path) if lexicon_path else resolve_lexicon_path("portuguese")
    stopwords: Set[str] = set(FALLBACK_STOPWORDS_PT)

    if path.exists():
        with path.open("r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                word = parts[0].strip().lower()
                lemma = parts[1].strip().lower() or word
                gram = parts[2].strip().lower() or "nr"
                if gram in SUPPLEMENTARY_GRAM_TYPES:
                    stopwords.add(word)
                    stopwords.add(lemma)

    for token in list(stopwords):
        normalized = _strip_accents(token).lower().strip()
        if normalized:
            stopwords.add(normalized)

    return frozenset(stopwords)


class Lexicon:
    """In-memory tab-separated lexicon loader and lookup helper."""

    def __init__(self, strict_mode: bool = False) -> None:
        self._entries: Dict[str, Tuple[str, str]] = {}
        self._entries_folded: Dict[str, Tuple[str, str]] = {}
        self._stopwords: Set[str] = set()
        self._stopwords_folded: Set[str] = set()
        self._language_key: str = ""
        self.strict_mode = strict_mode

    def load(self, path: Path) -> int:
        """
        Load a tab-separated lexicon file.

        Format expected:
            word<TAB>lemma<TAB>gram
        """
        loaded = 0
        self._entries.clear()
        self._entries_folded.clear()
        self._stopwords.clear()
        self._stopwords_folded.clear()
        self._language_key = Path(path).stem.lower()

        with Path(path).open("r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                word = parts[0].strip().lower()
                lemma = parts[1].strip().lower() or word
                gram = parts[2].strip().lower() or "nr"
                self._entries[word] = (lemma, gram)
                folded_word = _strip_accents(word).lower().strip()
                if folded_word and folded_word not in self._entries_folded:
                    self._entries_folded[folded_word] = (lemma, gram)
                if gram in SUPPLEMENTARY_GRAM_TYPES:
                    self._stopwords.add(word)
                    self._stopwords.add(lemma)
                loaded += 1

        if not self.strict_mode and ("pt" in self._language_key or "portuguese" in self._language_key):
            self._stopwords.update(FALLBACK_STOPWORDS_PT)

        for token in list(self._stopwords):
            normalized = _strip_accents(token).lower().strip()
            if normalized:
                self._stopwords_folded.add(normalized)
        return loaded

    def lookup(self, word: str) -> Optional[Tuple[str, str]]:
        """Return (lemma, gram) for a word if available."""
        candidate = (word or "").strip().lower()
        if not candidate:
            return None
        entry = self._lookup_direct(candidate)
        if entry is not None:
            return entry
        # Conservative fallback for plural variants not present in lexicon.
        # Only candidates that already exist in the lexicon can match.
        if not self.strict_mode:
            for singular in _iter_portuguese_singular_candidates(candidate):
                entry = self._lookup_direct(singular)
                if entry is not None:
                    return entry
        return None

    def _lookup_direct(self, token: str) -> Optional[Tuple[str, str]]:
        """Lookup helper with accent-folded fallback, without morphology."""
        entry = self._entries.get(token)
        if entry is not None:
            return entry
        if self.strict_mode:
            return None
        folded = _strip_accents(token).lower().strip()
        if not folded:
            return None
        return self._entries_folded.get(folded)

    def is_active(self, gram_type: str) -> bool:
        """Check if grammar type is active/content."""
        return (gram_type or "").strip().lower() in ACTIVE_GRAM_TYPES

    def is_stopword(self, word: str) -> bool:
        """Check if one token should be treated as stopword/supplementary."""
        token = (word or "").strip().lower()
        if not token:
            return False
        if token in self._stopwords:
            return True
        if not self.strict_mode:
            folded = _strip_accents(token).lower().strip()
            if folded and folded in self._stopwords_folded:
                return True
        match = self.lookup(token)
        if match is None:
            return False
        _lemma, gram = match
        return not self.is_active(gram)

    def get_stopwords(self) -> Set[str]:
        """Return current stopword set loaded with this lexicon."""
        return set(self._stopwords)

    def load_expressions(self, path: Path) -> Dict[str, str]:
        """
        Load compound expressions from file.

        Accepted separators:
        - tab: expressao<TAB>substituicao
        - multiple spaces: "expressao  substituicao"
        """
        expressions: Dict[str, str] = {}
        expression_path = Path(path)
        if not expression_path.exists():
            return expressions

        with expression_path.open("r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "\t" in line:
                    parts = line.split("\t", 1)
                else:
                    parts = re.split(r"\s{2,}", line, maxsplit=1)
                if len(parts) != 2:
                    continue

                source = parts[0].strip().lower()
                target = parts[1].strip().lower()
                if not source or not target:
                    continue
                expressions[source] = target
        return expressions
