"""
Corpus Module for LabiiaLex.

This module provides data structures and management for textual corpora,
following IRaMuTeQ's structure with UCIs (documents), UCEs (text segments),
words, and lemmas. Uses SQLite for persistence.

Based on: iramuteq-master/corpus.py
"""

from __future__ import annotations

import sqlite3
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any, Iterator
from collections import defaultdict

from .lexicon import Lexicon, resolve_lexicon_path

log = logging.getLogger(__name__)

_ENGLISH_LEXICON_CACHE: Optional[Lexicon] = None
_ENGLISH_LEXICON_LOADED = False


def _load_cached_english_lexicon() -> Optional[Lexicon]:
    """Best-effort lazy loader for English lexicon used by PT-priority demotion."""
    global _ENGLISH_LEXICON_CACHE, _ENGLISH_LEXICON_LOADED
    if _ENGLISH_LEXICON_LOADED:
        return _ENGLISH_LEXICON_CACHE

    _ENGLISH_LEXICON_LOADED = True
    try:
        lexicon_path = resolve_lexicon_path("english")
        if not lexicon_path.exists():
            return None
        lex = Lexicon()
        loaded = lex.load(lexicon_path)
        if loaded <= 0:
            return None
        _ENGLISH_LEXICON_CACHE = lex
        return _ENGLISH_LEXICON_CACHE
    except Exception:
        return None


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Word:
    """
    Represents a word form in the corpus vocabulary.
    
    Attributes:
        forme: The actual word form as it appears in text
        lem: Lemmatized form of the word
        gram: Grammatical category (noun, verb, adj, etc.)
        ident: Unique identifier for this word form
        freq: Frequency count in corpus
        act: Active flag (1 = active/content word, 0 = inactive/function word)
    """
    forme: str
    gram: str
    ident: int
    lem: Optional[str] = None
    freq: int = 1
    act: int = 1
    
    def __post_init__(self):
        if self.lem is None:
            self.lem = self.forme


@dataclass
class Lem:
    """
    Represents a lemma grouping multiple word forms.
    
    Attributes:
        lem: The lemma string
        gram: Grammatical category
        formes: Dictionary mapping form identifiers to frequencies
        freq: Total frequency across all forms
        act: Active flag
    """
    lem: str
    gram: str
    formes: Dict[int, int] = field(default_factory=dict)
    freq: int = 0
    act: int = 1
    
    def add_forme(self, forme: Word) -> None:
        """Add a word form to this lemma group."""
        self.formes[forme.ident] = forme.freq
        self.freq += forme.freq


@dataclass
class Uce:
    """
    Represents a text segment (Unité de Contexte Élémentaire).
    
    An UCE is the smallest unit of analysis - typically a sentence or
    a segment of approximately 40 words.
    
    Attributes:
        ident: Unique identifier for this UCE
        para: Paragraph identifier
        uci: Parent UCI identifier
    """
    ident: int
    para: int
    uci: int


@dataclass
class Uci:
    """
    Represents a document (Unité de Contexte Initiale).
    
    A UCI is typically a complete text/document, identified by
    metadata lines starting with **** in IRaMuTeQ format.
    
    Attributes:
        ident: Unique identifier for this UCI
        etoiles: List of metadata tags (e.g., *var1_value1)
        uces: List of UCE objects belonging to this UCI
        paras: List of paragraph/theme tags
    """
    ident: int
    etoiles: List[str] = field(default_factory=list)
    uces: List[Uce] = field(default_factory=list)
    paras: List[str] = field(default_factory=list)
    
    @classmethod
    def from_line(cls, ident: int, line: str, paraset: Optional[str] = None) -> 'Uci':
        """Create UCI from a metadata line."""
        etoiles = line.split()
        paras = paraset.split() if paraset else []
        return cls(ident=ident, etoiles=etoiles, paras=paras)


# =============================================================================
# Text Segmentation Functions (from IRaMuTeQ)
# =============================================================================

# Separator weights for UCE boundary detection
SEPARATORS = [
    ('.', 6.0), ('?', 6.0), ('!', 6.0), ('£$£', 6.0),
    (':', 5.0), (';', 4.0), (',', 1.0), (' ', 0.01)
]
SEPARATOR_DICT = dict(SEPARATORS)


def decouperlist(chaine: List[str], longueur: int, longueur_optimale: int) -> Tuple[bool, List[str], List[str]]:
    """
    Segment text into UCEs using word list method.
    
    This algorithm finds optimal cut points based on punctuation and
    target segment length, preferring natural sentence boundaries.
    
    Args:
        chaine: List of words/tokens to segment
        longueur: Maximum segment length
        longueur_optimale: Target/optimal segment length
        
    Returns:
        Tuple of (found, segment, remainder)
    """
    trouve = False
    i_decoupe = 0
    
    longueur = min(longueur, len(chaine) - 1)
    chaine_travail = chaine[:longueur + 1]
    nb_car = longueur
    meilleur = ['', 0.0, 0]  # type, weight, position
    
    # Check for explicit segment marker
    try:
        indice = chaine_travail.index('$')
        trouve = True
        i_decoupe = indice - 1
    except ValueError:
        pass
    
    if not trouve:
        while nb_car >= 0:
            mot = chaine_travail[nb_car]
            distance = abs(longueur_optimale - nb_car) + 1
            meilleure_distance = abs(longueur_optimale - meilleur[2]) + 1

            if mot in SEPARATOR_DICT:
                poids = SEPARATOR_DICT[mot]
                if (poids / distance) > (meilleur[1] / meilleure_distance):
                    meilleur = [mot, poids, nb_car]
                    trouve = True
                    i_decoupe = nb_car
            else:
                if (SEPARATOR_DICT[' '] / distance) > (meilleur[1] / meilleure_distance):
                    meilleur = [' ', SEPARATOR_DICT[' '], nb_car]
                    trouve = True
                    i_decoupe = nb_car

            nb_car -= 1
    
    if trouve:
        fin = chaine[i_decoupe + 1:]
        retour = chaine_travail[:i_decoupe + 1]
        return len(retour) > 0, retour, fin
    
    return False, chaine, []


def decoupercharact(chaine: str, longueur: int, longueur_optimale: int) -> Tuple[bool, str, str]:
    """
    Segment text into UCEs using character-based method.
    
    Args:
        chaine: Text string to segment
        longueur: Maximum segment length in characters
        longueur_optimale: Target segment length in characters
        
    Returns:
        Tuple of (found, segment, remainder)
    """
    trouve = False
    i_decoupe = 0
    
    longueur = min(longueur, len(chaine) - 1)
    chaine_travail = chaine[:longueur + 1]
    nb_car = longueur
    meilleur = ['', 0.0, 0]
    
    try:
        indice = chaine_travail.index('$')
        trouve = True
        i_decoupe = indice - 1
    except ValueError:
        pass
    
    if not trouve:
        while nb_car >= 0:
            caractere = chaine_travail[nb_car]
            distance = abs(longueur_optimale - nb_car) + 1
            meilleure_distance = abs(longueur_optimale - meilleur[2]) + 1
            
            if caractere in SEPARATOR_DICT:
                if (SEPARATOR_DICT[caractere] / distance) > (meilleur[1] / meilleure_distance):
                    meilleur = [caractere, SEPARATOR_DICT[caractere], nb_car]
                    trouve = True
                    i_decoupe = nb_car
            else:
                if (SEPARATOR_DICT[' '] / distance) > (meilleur[1] / meilleure_distance):
                    meilleur = [' ', SEPARATOR_DICT[' '], nb_car]
                    trouve = True
                    i_decoupe = nb_car
            
            nb_car -= 1
    
    if trouve:
        fin = chaine[i_decoupe + 1:]
        retour = chaine_travail[:i_decoupe + 1]
        return len(retour) > 0, retour, fin
    
    return False, chaine, ''


def testetoile(line: str) -> bool:
    """Check if line is a UCI marker (starts with ****)."""
    return line.startswith('****')


def testint(line: str) -> bool:
    """Check if line starts with digits followed by asterisk."""
    return len(line) >= 4 and line[0:4].isdigit() and '*' in line


# =============================================================================
# Corpus Class
# =============================================================================

class CorpusError(Exception):
    """
    Exception for corpus-related errors.
    
    Provides user-friendly error messages following the What/Why/How pattern.
    """
    
    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        super().__init__(f"{what}\n\nMotivo: {why}\n\nSolução: {how}")


class Corpus:
    """
    Main corpus class for managing textual data.
    
    Handles UCIs (documents), UCEs (text segments), word forms, and lemmas.
    Provides SQLite persistence for large corpora.
    
    Attributes:
        ucis: List of UCI objects
        formes: Dictionary of word forms (forme -> Word)
        lems: Dictionary of lemmas (lem -> Lem)
        parametres: Configuration parameters
    """
    
    def __init__(
        self,
        parametres: Optional[Dict[str, Any]] = None,
        lexicon: Optional[Lexicon] = None,
    ):
        """
        Initialize corpus with optional parameters.
        
        Args:
            parametres: Configuration dictionary with keys like:
                - encoding: Text encoding (default: utf-8)
                - ucemethod: 0=character, 1=word list
                - ucesize: Target UCE size
                - keep_ponct: Keep punctuation
        """
        self.parametres = parametres or {}
        self.ucis: List[Uci] = []
        self.formes: Dict[str, Word] = {}
        self.lems: Dict[str, Lem] = {}
        self.idformesuces: Dict[int, Dict[int, int]] = {}
        self._idformes: Optional[Dict[int, Word]] = None
        self._iduces: Optional[Dict[int, Uce]] = None
        self._uce_texts: Dict[int, str] = {}
        self.lexicon = lexicon
        
        # Counters for generating IDs
        self._next_word_id = 0
        self._next_uci_id = 0
        self._next_uce_id = 0
        
        # Database connection
        self._conn: Optional[sqlite3.Connection] = None
        self._db_path: Optional[Path] = None
        
        # UCE segmentation settings
        self._uce_method = self.parametres.get('ucemethod', 0)
        if self._uce_method == 0:
            self._uce_size = self.parametres.get('ucesize', 240)  # characters
            self._decouper = decoupercharact
            self._prep_txt = lambda t: t + '$'
        else:
            self._uce_size = self.parametres.get('ucesize', 40)  # words
            self._decouper = decouperlist
            self._prep_txt = lambda t: t.split() + ['$']
    
    # -------------------------------------------------------------------------
    # Word Management
    # -------------------------------------------------------------------------
    
    def add_word(
        self,
        forme: str,
        gram: str = 'unknown',
        lem: Optional[str] = None,
        uce_id: Optional[int] = None,
    ) -> Word:
        """
        Add a word form to the corpus vocabulary.
        
        If the word already exists, increments its frequency.
        
        Args:
            forme: The word form string
            gram: Grammatical category
            lem: Lemma (defaults to forme if not provided)
            
        Returns:
            The Word object (new or existing)
        """
        resolved_lem, resolved_gram, resolved_act = self._resolve_word_attributes(
            forme=forme,
            gram=gram,
            lem=lem,
        )

        if forme in self.formes:
            word = self.formes[forme]
            word.freq += 1
            word.lem = resolved_lem
            word.gram = resolved_gram
            word.act = resolved_act
        else:
            word = Word(
                forme=forme,
                gram=resolved_gram,
                ident=self._next_word_id,
                lem=resolved_lem,
                freq=1,
                act=resolved_act,
            )
            self.formes[forme] = word
            self._next_word_id += 1

        # Update lemma dictionary without overcounting duplicate forms
        lem_key = word.lem or forme
        if lem_key in self.lems:
            self.lems[lem_key].formes[word.ident] = word.freq
            self.lems[lem_key].freq += 1
            self.lems[lem_key].gram = resolved_gram
            self.lems[lem_key].act = resolved_act
        else:
            new_lem = Lem(lem=lem_key, gram=resolved_gram, act=resolved_act)
            new_lem.formes[word.ident] = word.freq
            new_lem.freq = word.freq
            self.lems[lem_key] = new_lem

        self._track_word_uce(word.ident, self._resolve_target_uce(uce_id))
        
        self._idformes = None  # Invalidate cache
        return word
    
    def add_word_from_forme(self, word: Word, uce_id: int) -> None:
        """Add word from existing Word object, tracking UCE association."""
        if word.forme in self.formes:
            existing_word = self.formes[word.forme]
            existing_word.freq += 1
            lemma_key = existing_word.lem or existing_word.forme
            if lemma_key in self.lems:
                self.lems[lemma_key].formes[existing_word.ident] = existing_word.freq
                self.lems[lemma_key].freq += 1
            else:
                self.lems[lemma_key] = Lem(
                    lem=lemma_key,
                    gram=existing_word.gram,
                    formes={existing_word.ident: existing_word.freq},
                    freq=existing_word.freq,
                    act=existing_word.act,
                )
        else:
            new_word = Word(
                forme=word.forme,
                gram=word.gram,
                ident=self._next_word_id,
                lem=word.lem,
                freq=1,
                act=word.act,
            )
            self.formes[word.forme] = new_word
            self._next_word_id += 1
            lemma_key = new_word.lem or new_word.forme
            if lemma_key not in self.lems:
                self.lems[lemma_key] = Lem(
                    lem=lemma_key,
                    gram=new_word.gram,
                    formes={new_word.ident: 1},
                    freq=1,
                    act=new_word.act,
                )
            else:
                self.lems[lemma_key].formes[new_word.ident] = 1
                self.lems[lemma_key].freq += 1
                self.lems[lemma_key].act = new_word.act
                self.lems[lemma_key].gram = new_word.gram
        self._track_word_uce(self.formes[word.forme].ident, self._resolve_target_uce(uce_id))
        self._idformes = None

    def _resolve_word_attributes(
        self,
        forme: str,
        gram: str,
        lem: Optional[str],
    ) -> Tuple[str, str, int]:
        """Resolve lemma/grammar/active flag using lexicon when available."""
        token = (forme or "").strip().lower()
        resolved_lem = (lem or token).lower()
        resolved_gram = (gram or "unknown").lower()
        is_numeric = token.isdigit()

        if is_numeric:
            resolved_lem = token
            resolved_gram = "num"
        elif self.lexicon is not None:
            match = self.lexicon.lookup(token)
            if match:
                resolved_lem, resolved_gram = match
            elif resolved_gram == "unknown":
                resolved_gram = "nr"
        elif resolved_gram == "unknown":
            resolved_gram = "nr"

        # Optional PT-BR prioritization heuristic (disabled in strict clone).
        if bool(self.parametres.get("prefer_portuguese_br", False)) and self._is_english_only_token(token, resolved_gram):
            resolved_gram = "sw"

        if self.lexicon is not None:
            # IRaMuTeQ parity: activity is driven by grammatical class (key.cfg),
            # not by an additional stopword override on the raw token.
            resolved_act = 1 if self.lexicon.is_active(resolved_gram) else 2
        else:
            # Preserve legacy behavior without lexical dictionary:
            # words are active unless explicitly set later by analysis filters.
            resolved_act = 2 if is_numeric else 1

        return resolved_lem, resolved_gram, resolved_act

    def _is_english_only_token(self, token: str, resolved_gram: str) -> bool:
        """
        Detect English-only tokens in Portuguese corpora.

        Rule:
        - PT lexicon active and token unknown in PT;
        - token recognized by EN lexicon;
        - token is plain alphabetic ASCII (avoid penalizing ids/codes/noise).
        """
        lexicon = self.lexicon
        if lexicon is None:
            return False

        language_key = str(getattr(lexicon, "_language_key", "") or "").lower()
        if "pt" not in language_key and "portuguese" not in language_key:
            return False

        token_norm = str(token or "").strip().lower()
        if len(token_norm) < 2:
            return False
        if not token_norm.replace("-", "").isalpha():
            return False
        if not token_norm.isascii():
            return False

        # Allow conservative demotion of high-confidence English borrowings in "-ing",
        # even if they appear as nominal entries in PT lexicon.
        is_ing_candidate = token_norm.endswith(("ing", "ings"))
        if resolved_gram not in {"nr", "unknown", ""} and not is_ing_candidate:
            return False

        if lexicon.lookup(token_norm) is not None and not is_ing_candidate:
            return False

        en_lexicon = _load_cached_english_lexicon()
        if en_lexicon is None:
            return False

        return en_lexicon.lookup(token_norm) is not None

    def _resolve_target_uce(self, uce_id: Optional[int]) -> Optional[int]:
        """Resolve target UCE id for word occurrence tracking."""
        if uce_id is not None:
            return uce_id
        if self.ucis and self.ucis[-1].uces:
            return self.ucis[-1].uces[-1].ident
        return None

    def _track_word_uce(self, word_id: int, uce_id: Optional[int]) -> None:
        """Track word occurrence by UCE in memory and SQLite."""
        if uce_id is None:
            return
        if word_id not in self.idformesuces:
            self.idformesuces[word_id] = {}
        self.idformesuces[word_id][uce_id] = self.idformesuces[word_id].get(uce_id, 0) + 1

        if self._conn is not None:
            self._conn.execute(
                """
                INSERT INTO uce_formes (uce_id, forme_id, count)
                VALUES (?, ?, 1)
                ON CONFLICT(uce_id, forme_id) DO UPDATE SET count = count + 1
                """,
                (uce_id, word_id),
            )
    
    def get_forme(self, forme: str) -> Optional[Word]:
        """Get word by forme string."""
        return self.formes.get(forme)
    
    def make_idformes(self) -> Dict[int, Word]:
        """Build dictionary mapping word IDs to Word objects."""
        if self._idformes is None:
            self._idformes = {w.ident: w for w in self.formes.values()}
        return self._idformes
    
    # -------------------------------------------------------------------------
    # UCI/UCE Management
    # -------------------------------------------------------------------------
    
    def add_uci(self, line: str, paraset: Optional[str] = None) -> Uci:
        """
        Add a new UCI (document) to the corpus.
        
        Args:
            line: Metadata line (e.g., "**** *var1_val1 *var2_val2")
            paraset: Optional paragraph/theme tags
            
        Returns:
            The created UCI object
        """
        uci = Uci.from_line(self._next_uci_id, line, paraset)
        self.ucis.append(uci)
        self._next_uci_id += 1
        return uci
    
    def add_uce(self, uci_id: int, para_id: int, text: str) -> Uce:
        """
        Add a new UCE (text segment) to a UCI.
        
        Args:
            uci_id: Parent UCI identifier
            para_id: Paragraph identifier
            text: The text content (stored in SQLite)
            
        Returns:
            The created UCE object
        """
        uce = Uce(ident=self._next_uce_id, para=para_id, uci=uci_id)
        
        if uci_id < len(self.ucis):
            self.ucis[uci_id].uces.append(uce)
        
        # Store text in database if connected
        if self._conn:
            self._conn.execute(
                'INSERT INTO uces (id, content) VALUES (?, ?)',
                (uce.ident, text)
            )
        else:
            self._uce_texts[uce.ident] = text
        
        self._next_uce_id += 1
        self._iduces = None  # Invalidate cache
        return uce
    
    def make_iduces(self) -> Dict[int, Uce]:
        """Build dictionary mapping UCE IDs to UCE objects."""
        if self._iduces is None:
            self._iduces = {}
            for uci in self.ucis:
                for uce in uci.uces:
                    self._iduces[uce.ident] = uce
        return self._iduces
    
    def get_uci(self, uci_id: int) -> Optional[Uci]:
        """Get UCI by identifier."""
        if 0 <= uci_id < len(self.ucis):
            return self.ucis[uci_id]
        return None
    
    def get_uces(self, uci_ids: Optional[List[int]] = None) -> Iterator[Tuple[int, str]]:
        """
        Get UCE texts for specified UCIs.
        
        Args:
            uci_ids: List of UCI IDs to retrieve (None for all)
            
        Yields:
            Tuples of (uce_id, text_content)
        """
        if not self._conn:
            selected_ids = None
            if uci_ids is not None:
                selected_ids = {int(uci_id) for uci_id in uci_ids}
            for idx, uci in enumerate(self.ucis):
                if selected_ids is not None and idx not in selected_ids and uci.ident not in selected_ids:
                    continue
                for uce in uci.uces:
                    yield uce.ident, self._uce_texts.get(uce.ident, "")
            return
        
        if uci_ids is None:
            cursor = self._conn.execute('SELECT id, content FROM uces ORDER BY id')
        else:
            uce_ids = []
            self.make_iduces()
            for uci_id in uci_ids:
                if uci_id < len(self.ucis):
                    uce_ids.extend(u.ident for u in self.ucis[uci_id].uces)
            if not uce_ids:
                return
            placeholders = ','.join('?' * len(uce_ids))
            cursor = self._conn.execute(
                f'SELECT id, content FROM uces WHERE id IN ({placeholders}) ORDER BY id',
                uce_ids
            )
        
        for row in cursor:
            yield row[0], row[1]
    
    def getalluces(self) -> List[Tuple[int, str]]:
        """Get all UCE texts as list of (id, content) tuples."""
        return list(self.get_uces())
    
    def getconcorde(self, uce_ids: List[int]) -> List[Tuple[int, str]]:
        """Get UCE texts for specific UCE IDs."""
        if not uce_ids:
            return []
        if not self._conn:
            normalized = sorted({int(uce_id) for uce_id in uce_ids})
            return [(uce_id, self._uce_texts.get(uce_id, "")) for uce_id in normalized]
        
        placeholders = ','.join('?' * len(uce_ids))
        cursor = self._conn.execute(
            f'SELECT id, content FROM uces WHERE id IN ({placeholders}) ORDER BY id',
            uce_ids
        )
        return list(cursor)

    def getlemuces(self, lem: str) -> List[int]:
        """Return sorted UCE ids where lemma appears."""
        lemma = self.lems.get(lem)
        if lemma is None:
            return []

        uce_ids = set()
        for forme_id in lemma.formes:
            for uce_id in self.idformesuces.get(forme_id, {}):
                uce_ids.add(uce_id)
        return sorted(uce_ids)

    def getlemuceseff(self, lem: str) -> Dict[int, int]:
        """Return UCE frequency map for a lemma (uce_id -> count)."""
        lemma = self.lems.get(lem)
        if lemma is None:
            return {}

        frequencies: Dict[int, int] = {}
        for forme_id in lemma.formes:
            for uce_id, count in self.idformesuces.get(forme_id, {}).items():
                frequencies[uce_id] = frequencies.get(uce_id, 0) + count
        return frequencies

    def make_actives_nb(self, nbmax: int, key: int) -> Tuple[List[str], int]:
        """
        IRaMuTeQ-compatible make_actives_nb selection.

        Mirrors `iramuteq-master/corpus.py::make_actives_nb`:
        - keeps lemmas with `act == key` and `freq >= 3`
        - sorts with `sorted(..., reverse=True)` on `[freq, lemma]`
        - applies IRaMuTeQ tie-cut semantics on `nbmax`
        """
        if self._idformes is None:
            self.make_idformes()

        try:
            nbmax_int = int(nbmax)
        except Exception:
            nbmax_int = 0
        if nbmax_int <= 0:
            nbmax_int = 10**9

        allactives: List[List[Any]] = [
            [int(getattr(self.lems[lem], "freq", 0)), str(lem)]
            for lem in self.lems
            if int(getattr(self.lems[lem], "act", 1)) == int(key)
            and int(getattr(self.lems[lem], "freq", 0)) >= 3
        ]
        allactives = sorted(allactives, reverse=True)
        self.activenb = len(allactives)

        if self.activenb == 0:
            return [], 0

        if len(allactives) <= nbmax_int:
            min_eff = int(allactives[-1][0])
            return [str(val[1]) for val in allactives], min_eff

        effs = [int(val[0]) for val in allactives]
        if effs.count(effs[nbmax_int - 1]) > 1:
            lim = effs[nbmax_int - 1] + 1
            nok = True
            while nok:
                try:
                    stop = effs.index(lim)
                    nok = False
                except ValueError:
                    lim -= 1
        else:
            stop = nbmax_int - 1
            lim = effs[stop]

        # Keep IRaMuTeQ slice behavior [0:stop] (stop index excluded).
        return [str(val[1]) for val in allactives[0:stop]], int(lim)

    def make_and_write_profile(
        self,
        actives: List[str],
        ucecl: List[List[int]],
        fileout: Path,
        uci: bool = False,
    ) -> None:
        """
        Write lexical profile table lemma x class.

        `uci=True` is currently unsupported and falls back to UCE-based counts.
        """
        rows: List[str] = []
        for lemma in actives:
            uce_set = set(self.getlemuces(lemma))
            counts = [len(uce_set.intersection(set(class_uces))) for class_uces in ucecl]
            if sum(counts) >= 3:
                rows.append(";".join([lemma] + [str(val) for val in counts]))

        file_path = Path(fileout)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as file:
            if rows:
                file.write("\n".join(rows))
                file.write("\n")

    @staticmethod
    def _signed_chi2(obs1: float, obs2: float, obs3: float, obs4: float) -> float:
        """Compute signed chi2 for a 2x2 contingency table."""
        total = obs1 + obs2 + obs3 + obs4
        if total <= 0:
            return 0.0

        row1 = obs1 + obs2
        row2 = obs3 + obs4
        col1 = obs1 + obs3
        col2 = obs2 + obs4

        exp1 = (row1 * col1) / total if total > 0 else 0.0
        exp2 = (row1 * col2) / total if total > 0 else 0.0
        exp3 = (row2 * col1) / total if total > 0 else 0.0
        exp4 = (row2 * col2) / total if total > 0 else 0.0

        chi = 0.0
        if exp1 > 0:
            chi += ((obs1 - exp1) ** 2) / exp1
        if exp2 > 0:
            chi += ((obs2 - exp2) ** 2) / exp2
        if exp3 > 0:
            chi += ((obs3 - exp3) ** 2) / exp3
        if exp4 > 0:
            chi += ((obs4 - exp4) ** 2) / exp4

        return chi if obs1 >= exp1 else -chi

    def make_and_write_profile_et(
        self,
        ucecl: List[List[int]],
        fileout: Path,
        signed_chi2: bool = False,
    ) -> None:
        """
        Write metadata profile table (etoile x class).

        When `signed_chi2=False` (default), output mirrors IRaMuTeQ:
        one row per metadata token with raw counts by class:
            token;count_class1;count_class2;...

        When `signed_chi2=True`, output keeps the enriched format:
            variable;class_id;chi2;freq;pct_in_class;sign
        """
        class_sets = [set(values) for values in (ucecl or [])]
        all_uces = {uce.ident for uci in self.ucis for uce in uci.uces}
        total_uces = len(all_uces)
        metadata_tokens = sorted(self.make_etoiles())

        file_path = Path(fileout)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if not signed_chi2:
            with file_path.open("w", encoding="utf-8") as file:
                if not class_sets:
                    return
                for token in metadata_tokens:
                    token_uces: set[int] = set()
                    for uci in self.ucis:
                        if token in uci.etoiles:
                            token_uces.update(uce.ident for uce in uci.uces)
                    if not token_uces:
                        continue
                    counts = [
                        int(len(class_uces.intersection(token_uces)))
                        for class_uces in class_sets
                    ]
                    file.write(f"{token};" + ";".join(str(v) for v in counts) + "\n")
            return

        with file_path.open("w", encoding="utf-8") as file:
            file.write("variable;class_id;chi2;freq;pct_in_class;sign\n")
            if not class_sets or total_uces == 0:
                return
            for token in metadata_tokens:
                token_uces: set[int] = set()
                for uci in self.ucis:
                    if token in uci.etoiles:
                        token_uces.update(uce.ident for uce in uci.uces)
                if not token_uces:
                    continue

                for class_idx, class_uces in enumerate(class_sets, start=1):
                    class_size = len(class_uces)
                    outside_size = total_uces - class_size
                    if class_size <= 0 or outside_size <= 0:
                        continue
                    obs1 = float(len(class_uces.intersection(token_uces)))
                    obs2 = float(len((all_uces - class_uces).intersection(token_uces)))
                    obs3 = float(class_size - obs1)
                    obs4 = float(outside_size - obs2)
                    chi2 = self._signed_chi2(obs1, obs2, obs3, obs4)
                    pct = (obs1 / class_size) * 100.0 if class_size else 0.0
                    sign = "+" if chi2 >= 0 else "-"
                    file.write(
                        f"{token};{class_idx};{chi2:.6f};{int(obs1)};{pct:.4f};{sign}\n"
                    )
    
    # -------------------------------------------------------------------------
    # Text Segmentation
    # -------------------------------------------------------------------------
    
    def segment_text(self, text: str) -> List[str]:
        """
        Segment text into UCE-sized chunks.
        
        Uses the configured segmentation method (character or word-based).
        
        Args:
            text: Input text to segment
            
        Returns:
            List of text segments
        """
        # IRaMuTeQ make_uces equivalent.
        if self._uce_method == 1:
            txt = " ".join(str(text or "").split())
            if not txt:
                return []

            ponctuation_espace = (
                [' ', '']
                if bool(self.parametres.get('keep_ponct', False))
                else [' ', '.', '£$£', ';', '?', '!', ',', ':', '']
            )

            prepared = self._prep_txt(txt)
            out: List[str] = []
            max_len = int(self._uce_size) + 15
            opt_len = int(self._uce_size)

            found, texte_uce, suite = self._decouper(prepared, max_len, opt_len)
            while found:
                uce = " ".join([val for val in texte_uce if val not in ponctuation_espace]).strip()
                if uce:
                    out.append(uce)
                found, texte_uce, suite = self._decouper(suite, max_len, opt_len)

            uce = " ".join([val for val in texte_uce if val not in ponctuation_espace]).strip()
            if uce:
                out.append(uce)
            return out

        segments: List[str] = []
        prepared = self._prep_txt(text)
        longueur_max = int(self._uce_size * 1.5)
        longueur_optimale = self._uce_size

        while prepared:
            if self._uce_method == 0:
                if len(prepared) <= longueur_max:
                    segments.append(prepared.rstrip('$').strip())
                    break
            else:
                if len(prepared) <= longueur_max:
                    segment = ' '.join(prepared).rstrip('$').strip()
                    if segment:
                        segments.append(segment)
                    break

            found, segment, remainder = self._decouper(
                prepared, longueur_max, longueur_optimale
            )

            if found:
                if self._uce_method == 0:
                    seg_text = segment.strip()
                else:
                    seg_text = ' '.join(segment).strip()

                if seg_text and seg_text != '$':
                    segments.append(seg_text)
                prepared = remainder
            else:
                if self._uce_method == 0:
                    seg_text = prepared.rstrip('$').strip()
                else:
                    seg_text = ' '.join(prepared).rstrip('$').strip()
                if seg_text:
                    segments.append(seg_text)
                break

        return segments
    
    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------
    
    def getucinb(self) -> int:
        """Get number of UCIs in corpus."""
        return len(self.ucis)
    
    def getucenb(self) -> int:
        """Get total number of UCEs in corpus."""
        return sum(len(uci.uces) for uci in self.ucis)
    
    def getucisize(self) -> List[int]:
        """Get list of UCE counts per UCI."""
        return [len(uci.uces) for uci in self.ucis]
    
    def getwordnb(self) -> int:
        """Get number of unique word forms."""
        return len(self.formes)
    
    def gettokennb(self) -> int:
        """Get total token count (sum of all word frequencies)."""
        return sum(w.freq for w in self.formes.values())
    
    def make_etoiles(self) -> List[str]:
        """Get list of all unique metadata tags."""
        etoiles = set()
        for uci in self.ucis:
            etoiles.update(uci.etoiles[1:])  # Skip the **** marker
        return list(etoiles)

    def extract_subcorpus(self, variable: str, values: List[str]) -> Optional['Corpus']:
        """
        Build sub-corpus by filtering UCIs through metadata tokens.

        Args:
            variable: Metadata variable name (ex: "grupo")
            values: Accepted values (ex: ["a", "b"])

        Returns:
            New in-memory Corpus with selected UCIs, or None when empty.
        """
        var_name = str(variable or "").strip()
        selected_values = [str(value).strip() for value in values if str(value).strip()]
        if not var_name or not selected_values:
            return None

        accepted_etoiles = {f"*{var_name}_{value}" for value in selected_values}
        selected_ucis: List[Uci] = []
        for uci in self.ucis:
            if accepted_etoiles.intersection(set(uci.etoiles)):
                selected_ucis.append(uci)

        if not selected_ucis:
            return None

        sub = Corpus(
            parametres=dict(self.parametres) if isinstance(self.parametres, dict) else {},
            lexicon=self.lexicon,
        )
        sub.parametres["subcorpus_filter"] = f"{var_name}={','.join(selected_values)}"
        sub._conn = None
        sub._db_path = None
        sub.ucis = []
        sub.formes = {}
        sub.lems = {}
        sub.idformesuces = {}
        sub._idformes = None
        sub._iduces = None
        sub._uce_texts = {}
        sub._next_word_id = 0
        sub._next_uce_id = 0
        sub._next_uci_id = 0

        selected_uce_ids: set[int] = set()
        for new_uci_id, uci in enumerate(selected_ucis):
            new_uces = [
                Uce(ident=uce.ident, para=uce.para, uci=new_uci_id)
                for uce in uci.uces
            ]
            new_uci = Uci(
                ident=new_uci_id,
                etoiles=list(uci.etoiles),
                uces=new_uces,
                paras=list(uci.paras),
            )
            sub.ucis.append(new_uci)
            for uce in new_uces:
                selected_uce_ids.add(uce.ident)

        text_rows = self.getconcorde(sorted(selected_uce_ids))
        text_map = {int(uce_id): str(text or "") for uce_id, text in text_rows}
        for uce_id in selected_uce_ids:
            if uce_id in text_map:
                sub._uce_texts[uce_id] = text_map[uce_id]

        for forme_key, word in self.formes.items():
            source_map = self.idformesuces.get(word.ident, {})
            filtered_map = {
                int(uce_id): int(count)
                for uce_id, count in source_map.items()
                if int(uce_id) in selected_uce_ids and int(count) > 0
            }
            if not filtered_map:
                continue

            new_freq = int(sum(filtered_map.values()))
            new_word = Word(
                forme=word.forme,
                gram=word.gram,
                ident=word.ident,
                lem=word.lem,
                freq=new_freq,
                act=word.act,
            )
            sub.formes[forme_key] = new_word
            sub.idformesuces[new_word.ident] = filtered_map
            sub._next_word_id = max(sub._next_word_id, new_word.ident + 1)

            lemma_key = new_word.lem or new_word.forme
            if lemma_key not in sub.lems:
                sub.lems[lemma_key] = Lem(
                    lem=lemma_key,
                    gram=new_word.gram,
                    formes={},
                    freq=0,
                    act=new_word.act,
                )
            sub.lems[lemma_key].formes[new_word.ident] = new_word.freq
            sub.lems[lemma_key].freq += new_word.freq
            sub.lems[lemma_key].gram = new_word.gram
            sub.lems[lemma_key].act = new_word.act

        if selected_uce_ids:
            sub._next_uce_id = max(selected_uce_ids) + 1
        sub._next_uci_id = len(sub.ucis)
        return sub

    def _make_etoile_uce_sets(self, etoiles: List[str]) -> List[set[int]]:
        """Build UCE-id sets for each metadata token in `etoiles`."""
        etuces: List[List[int]] = [[] for _ in etoiles]
        etoile_index = {etoile: idx for idx, etoile in enumerate(etoiles)}

        for uci in self.ucis:
            selected = list(set(uci.etoiles).intersection(etoiles))
            if len(selected) > 1:
                log.warning(
                    "UCI %s contem mais de uma variavel alvo para a mesma tabela lexical: %s",
                    uci.ident,
                    selected,
                )
            if selected:
                target = selected[0]
                idx = etoile_index[target]
                etuces[idx].extend([uce.ident for uce in uci.uces])

        return [set(values) for values in etuces]

    def make_lexitable(
        self,
        mineff: int,
        listet: List[str],
        gram: int = 0,
    ) -> List[List[Any]]:
        """
        Build lexical table lemma x metadata tokens.

        Args:
            mineff: Minimum global lemma frequency.
            listet: Metadata tokens (e.g. *grupo_a, *grupo_b).
            gram: 0=actives+supplementary, 1=only active, 2=only supplementary.
        """
        mineff = int(mineff)
        if mineff < 1:
            mineff = 1
        if not listet:
            return [[""]]

        if gram == 0:
            grams = {1, 2}
        else:
            grams = {int(gram)}

        etuces = self._make_etoile_uce_sets(listet)
        table: List[List[Any]] = [[""] + list(listet)]

        for lemma_key, lemma in self.lems.items():
            if lemma.freq < mineff or lemma.act not in grams:
                continue

            eff_by_uce = self.getlemuceseff(lemma_key)
            if not eff_by_uce:
                continue

            available_uces = set(eff_by_uce.keys())
            counts = [
                sum(eff_by_uce[uce_id] for uce_id in et_set.intersection(available_uces))
                for et_set in etuces
            ]
            if sum(counts) >= mineff:
                table.append([lemma_key] + counts)

        return table

    def make_efftype_from_etoiles(self, listet: List[str]) -> List[List[Any]]:
        """
        Build grammatical-type frequency table gram x metadata tokens.

        Args:
            listet: Metadata tokens used as columns.
        """
        if not listet:
            return [[""]]

        etuces = self._make_etoile_uce_sets(listet)
        dtype: Dict[str, List[int]] = {}

        for lemma_key, lemma in self.lems.items():
            eff_by_uce = self.getlemuceseff(lemma_key)
            if not eff_by_uce:
                continue
            available_uces = set(eff_by_uce.keys())
            line = [
                sum(eff_by_uce[uce_id] for uce_id in et_set.intersection(available_uces))
                for et_set in etuces
            ]
            gram_key = lemma.gram or "unknown"
            if gram_key in dtype:
                dtype[gram_key] = [left + right for left, right in zip(dtype[gram_key], line)]
            else:
                dtype[gram_key] = line

        table = [[""] + list(listet)]
        for gram_key in sorted(dtype.keys()):
            table.append([gram_key] + dtype[gram_key])
        return table
    
    def make_lexique(self) -> Dict[str, Tuple[int, str, str]]:
        """
        Build vocabulary dictionary.
        
        Returns:
            Dictionary mapping forme to (frequency, lemma, gram)
        """
        return {
            forme: (word.freq, word.lem, word.gram)
            for forme, word in self.formes.items()
        }
    
    def get_hapaxes(self) -> List[str]:
        """Get list of words occurring only once (hapax legomena)."""
        return [forme for forme, word in self.formes.items() if word.freq == 1]
    
    # -------------------------------------------------------------------------
    # SQLite Persistence
    # -------------------------------------------------------------------------
    
    def connect(self, path: Path) -> None:
        """
        Connect to SQLite database for corpus storage.
        
        Args:
            path: Path to SQLite database file
        """
        self._db_path = Path(path)
        # Analises (CHD/similitude/AFC) rodam em thread separada na UI.
        # Permitir uso da mesma conexao fora da thread de criacao evita
        # "SQLite objects created in a thread can only be used in that same thread".
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._create_tables()
        log.info(f"Connected to corpus database: {path}")
    
    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        if not self._conn:
            return
        
        self._conn.executescript('''
            CREATE TABLE IF NOT EXISTS uces (
                id INTEGER PRIMARY KEY,
                content TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS formes (
                id INTEGER PRIMARY KEY,
                forme TEXT NOT NULL,
                lem TEXT,
                gram TEXT,
                freq INTEGER DEFAULT 1,
                act INTEGER DEFAULT 1
            );
            
            CREATE TABLE IF NOT EXISTS corpus_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS uce_formes (
                uce_id INTEGER NOT NULL,
                forme_id INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (uce_id, forme_id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_formes_forme ON formes(forme);
            CREATE INDEX IF NOT EXISTS idx_formes_lem ON formes(lem);
            CREATE INDEX IF NOT EXISTS idx_uce_formes_forme_id ON uce_formes(forme_id);
        ''')
        self._conn.commit()
    
    def save_corpus(self) -> None:
        """
        Save corpus to SQLite database.
        
        Saves word forms, metadata, and ensures all UCE texts are persisted.
        """
        if not self._conn:
            raise CorpusError(
                what="Não foi possível salvar o corpus.",
                why="Nenhuma conexão com banco de dados estabelecida.",
                how="Chame connect(path) antes de salvar."
            )
        
        # Save word forms
        self._conn.execute('DELETE FROM formes')
        for word in self.formes.values():
            self._conn.execute(
                'INSERT INTO formes (id, forme, lem, gram, freq, act) VALUES (?, ?, ?, ?, ?, ?)',
                (word.ident, word.forme, word.lem, word.gram, word.freq, word.act)
            )

        # Save UCE<->form frequencies
        self._conn.execute('DELETE FROM uce_formes')
        for forme_id, occurrences in self.idformesuces.items():
            for uce_id, count in occurrences.items():
                self._conn.execute(
                    'INSERT INTO uce_formes (uce_id, forme_id, count) VALUES (?, ?, ?)',
                    (uce_id, forme_id, count),
                )
        
        # Save metadata
        self._conn.execute('DELETE FROM corpus_meta')
        meta = {
            'uci_count': str(len(self.ucis)),
            'uce_count': str(self.getucenb()),
            'word_count': str(len(self.formes)),
            'token_count': str(self.gettokennb()),
        }
        for key, value in meta.items():
            self._conn.execute(
                'INSERT INTO corpus_meta (key, value) VALUES (?, ?)',
                (key, value)
            )
        
        self._conn.commit()
        log.info(f"Corpus saved: {len(self.ucis)} UCIs, {len(self.formes)} forms")
    
    def load_corpus(self, path: Path) -> None:
        """
        Load corpus from SQLite database.
        
        Args:
            path: Path to SQLite database file
        """
        self.connect(path)
        self._uce_texts = {}
        
        # Load word forms
        cursor = self._conn.execute(
            'SELECT id, forme, lem, gram, freq, act FROM formes'
        )
        self.formes.clear()
        self.lems.clear()
        max_id = -1
        
        for row in cursor:
            word = Word(
                forme=row[1],
                gram=row[3] or 'unknown',
                ident=row[0],
                lem=row[2],
                freq=row[4] or 1,
                act=row[5] if row[5] is not None else 1
            )
            self.formes[word.forme] = word
            max_id = max(max_id, word.ident)
            
            # Rebuild lemma dictionary
            lem_key = word.lem or word.forme
            if lem_key in self.lems:
                self.lems[lem_key].formes[word.ident] = word.freq
                self.lems[lem_key].freq += word.freq
                self.lems[lem_key].act = word.act
            else:
                lem = Lem(lem=lem_key, gram=word.gram, act=word.act)
                lem.formes[word.ident] = word.freq
                lem.freq = word.freq
                self.lems[lem_key] = lem
        
        self._next_word_id = max_id + 1
        self.idformesuces = {}
        try:
            cursor = self._conn.execute(
                'SELECT uce_id, forme_id, count FROM uce_formes'
            )
            for uce_id, forme_id, count in cursor:
                if forme_id not in self.idformesuces:
                    self.idformesuces[forme_id] = {}
                self.idformesuces[forme_id][uce_id] = int(count or 0)
        except sqlite3.OperationalError:
            # Backward compatibility for corpora created before uce_formes table
            self.idformesuces = {}
        self._idformes = None
        log.info(f"Corpus loaded: {len(self.formes)} word forms")
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            log.info("Corpus database connection closed")
    
    def __enter__(self) -> 'Corpus':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
    
    # -------------------------------------------------------------------------
    # Export Methods
    # -------------------------------------------------------------------------
    
    def export_dictionary(self, filepath: Path, encoding: str = 'utf-8') -> None:
        """
        Export vocabulary dictionary to file.
        
        Args:
            filepath: Output file path
            encoding: Output encoding
        """
        listformes = sorted(
            [(w.freq, w.forme, w.lem, w.gram) for w in self.formes.values()],
            reverse=True
        )
        
        with open(filepath, 'w', encoding=encoding) as f:
            for freq, forme, lem, gram in listformes:
                f.write(f"{forme}\t{lem}\t{gram}\t{freq}\n")
    
    def export_lems(self, filepath: Path, encoding: str = 'utf-8') -> None:
        """
        Export lemmas with their forms to file.
        
        Args:
            filepath: Output file path
            encoding: Output encoding
        """
        id_formes = self.make_idformes()
        
        with open(filepath, 'w', encoding=encoding) as f:
            for lem_key in sorted(self.lems.keys()):
                lem = self.lems[lem_key]
                formes_str = '\t'.join(
                    f"{id_formes[fid].forme}\t{freq}"
                    for fid, freq in lem.formes.items()
                    if fid in id_formes
                )
                f.write(f"{lem_key}\t{formes_str}\n")
