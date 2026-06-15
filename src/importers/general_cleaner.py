"""
GeneralCleaner - Limpador para análises textuais tradicionais.
===============================================================
Implementa processamento de texto para análises que não seguem
o formato IRaMuTeQ, incluindo tokenização, remoção de stopwords
e lematização básica.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Set

from ..core.lexicon import build_portuguese_stopwords_from_lexicon
from ..utils.logger import get_logger


class GeneralCleaner:
    """
    Limpador para análises textuais tradicionais.
    
    Este limpador é usado para preparar textos para análises
    que não usam o formato específico do IRaMuTeQ.
    
    Funcionalidades:
    - Tokenização
    - Remoção de stopwords (usando lista expandida spaCy-based)
    - Normalização de texto
    - Lematização básica (regras simples)
    
    Note:
        As stopwords em português são carregadas dinamicamente de
        build_portuguese_stopwords_from_lexicon() para manter
        sincronização com o léxico IRaMuTeQ.
    """
    
    # Stopwords em português - lista expandida spaCy-based (~450+ palavras)
    # Sincronizada com FALLBACK_STOPWORDS_PT em core/lexicon.py
    STOPWORDS_PT: Set[str] = {
        # Artigos e determinantes
        'a', 'à', 'às', 'as', 'o', 'os', 'um', 'uma', 'uns', 'umas',
        'ao', 'aos', 'aquela', 'aquelas', 'aquele', 'aqueles', 'aquilo',
        'aquí', 'ela', 'elas', 'ele', 'eles', 'essa', 'essas', 'esse',
        'esses', 'esta', 'estas', 'este', 'estes', 'isto', 'isso',
        'outra', 'outras', 'outro', 'outros',
        # Preposições
        'de', 'da', 'das', 'do', 'dos', 'dela', 'delas', 'dele', 'deles',
        'em', 'na', 'nas', 'no', 'nos', 'num', 'numa', 'nuns', 'numas',
        'com', 'como', 'sem', 'sob', 'sobre', 'entre', 'contra', 'perante',
        'para', 'por', 'pela', 'pelas', 'pelo', 'pelos', 'até', 'ate', 'ateh',
        'após', 'apos', 'antes', 'depois', 'desde', 'durante',
        'conforme', 'consoante', 'excepto', 'exceto', 'mediante',
        'salvo', 'segundo', 'senão', 'visto', 'através', 'atravez',
        # Conjunções
        'e', 'ou', 'mas', 'nem', 'que', 'se', 'quando', 'quanto', 'porque',
        'porquê', 'pois', 'então', 'entao', 'assim', 'logo', 'portanto',
        'contudo', 'todavia', 'porém', 'porem', 'entretanto',
        'ora', 'porquanto',
        # Advérbios
        'muito', 'mais', 'menos', 'bem', 'mal', 'tão', 'tao', 'assim',
        'também', 'tambem', 'só', 'so', 'tudo', 'nada', 'algo', 'cada',
        'sempre', 'nunca', 'jamais', 'ainda', 'já', 'ja', 'agora', 'antes',
        'depois', 'logo', 'cedo', 'tarde', 'ontem', 'hoje', 'amanhã',
        'aqui', 'aí', 'ai', 'ali', 'lá', 'la', 'acolá', 'acola', 'onde',
        'aonde', 'longe', 'perto', 'dentro', 'fora', 'acima', 'abaixo',
        'adiante', 'atrás', 'atras', 'através', 'atravez', 'defronte',
        'diante', 'apenas', 'somente', 'mesmo', 'próprio', 'proprio',
        'outro', 'talvez', 'possivelmente', 'provavelmente',
        'certamente', 'realmente', 'bastante', 'demais',
        'tanto', 'quão', 'quao', 'quase',
        # Pronomes pessoais
        'eu', 'tu', 'ele', 'ela', 'nós', 'nos', 'vós', 'vos', 'eles',
        'elas', 'você', 'voce', 'vocês', 'voces', 'si',
        # Pronomes oblíquos
        'me', 'te', 'lhe', 'lhes', 'se', 'lo', 'la', 'los', 'las',
        # Pronomes possessivos
        'meu', 'minha', 'meus', 'minhas', 'teu', 'tua', 'teus', 'tuas',
        'seu', 'sua', 'seus', 'suas', 'nosso', 'nossa', 'nossos', 'nossas',
        'vosso', 'vossa', 'vossos', 'vossas',
        # Pronomes indefinidos
        'qualquer', 'quaisquer', 'algum', 'alguma', 'alguns', 'algumas',
        'outrem', 'nenhum', 'nenhuma', 'todo', 'toda', 'todos', 'todas',
        'qual', 'quais', 'quem', 'cujo', 'cuja', 'cujos', 'cujas',
        # Numerais cardinais escritos
        'zero', 'um', 'dois', 'três', 'tres', 'quatro', 'cinco', 'seis',
        'sete', 'oito', 'nove', 'dez', 'onze', 'doze', 'treze', 'catorze',
        'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove', 'vinte',
        'cem', 'mil',
        # Numerais ordinais escritos
        'primeiro', 'primeira', 'segundo', 'segunda', 'terceiro', 'terceira',
        'quarto', 'quarta', 'quinto', 'quinta', 'sexto', 'sexta',
        'sétimo', 'setimo', 'sétima', 'setima', 'oitavo', 'oitava',
        'nono', 'nona', 'décimo', 'decimo', 'décima', 'decima',
        # Verbos auxiliares (formas principais)
        'ser', 'sou', 'é', 'e', 'somos', 'são', 'sao', 'era', 'eras', 'era',
        'eram', 'fui', 'foste', 'foi', 'fomos', 'foram', 'fora', 'seja',
        'sejas', 'sejamos', 'sejam', 'fosse', 'fossess', 'fossem',
        'for', 'fores', 'formos', 'forem', 'sendo', 'sido',
        'estar', 'estou', 'está', 'esta', 'estamos', 'estão', 'estao',
        'estava', 'estavas', 'estavam', 'estive', 'estiveste', 'esteve',
        'estivemos', 'estiveram', 'estivera', 'esteja', 'estejas',
        'estejamos', 'estejam', 'estivesse', 'estivesses', 'estivessem',
        'haver', 'hei', 'há', 'ha', 'havemos', 'hão', 'hao', 'havia',
        'haviam', 'houve', 'houveste', 'houveram', 'houvera', 'haja',
        'hajas', 'hajamos', 'hajam', 'houvesse', 'houvesses', 'houvessem',
        'tendo', 'ter', 'tenho', 'tens', 'tem', 'temos', 'têm', 'tinha',
        'tinhas', 'tinham', 'tive', 'tiveste', 'teve', 'tivemos', 'tiveram',
        'tivera', 'tenha', 'tenhas', 'tenhamos', 'tenham', 'tivesse',
        'tivesses', 'tivessem', 'vir', 'venho', 'vens', 'vem', 'vimos',
        'vêm', 'vinha', 'viram', 'virão', 'dar', 'dou', 'dá', 'da',
        'damos', 'dão', 'dao', 'dei', 'deste', 'deu', 'demos', 'deram',
        'dê', 'deem', 'ir', 'vou', 'vais', 'vai', 'vamos', 'vão', 'vao',
        'ia', 'ias', 'iam', 'vá', 'va', 'vamos', 'fosse', 'fosses',
        'fôssemos', 'fazer', 'faço', 'faco', 'fazes', 'faz', 'fazemos',
        'fazeis', 'fazem', 'fiz', 'fizeste', 'fez', 'fizemos', 'fizeram',
        'fizera', 'faça', 'facas', 'fizéssemos', 'fizesses', 'fizessem',
        'poder', 'posso', 'podes', 'pode', 'podemos', 'podeis', 'podem',
        'podia', 'podias', 'podiam', 'pude', 'pudeste', 'pôde', 'pudemos',
        'puderam', 'pudera', 'possa', 'possas', 'possamos', 'possam',
        'pudesse', 'pudesses', 'pudessem', 'querer', 'quero', 'queres',
        'quer', 'queremos', 'quereis', 'querem', 'queria', 'querias',
        'queriam', 'saber', 'sei', 'sabes', 'sabe', 'sabemos', 'sabeis',
        'sabem', 'sabia', 'sabias', 'sabiam', 'soube', 'soubeste', 'soubemos',
        'souberam', 'soubera', 'saiba', 'saibas', 'saibamos', 'saibam',
        'soubesse', 'soubesses', 'soubessem', 'dizer', 'digo', 'dizes',
        'diz', 'dizemos', 'dizeis', 'dizem', 'dizia', 'dizias', 'diziam',
        'disse', 'disseste', 'dissemos', 'disseram', 'dissera', 'diga',
        'digas', 'digamos', 'digam', 'dissesse', 'dissesses', 'dissessem',
        'ver', 'vejo', 'vês', 'ves', 'vê', 've', 'vemos', 'veis', 'vêem',
        'veem', 'via', 'vias', 'viam', 'vi', 'viste', 'viu', 'vimos',
        'viram', 'vira', 'veja', 'vejas', 'vejamos', 'vejam', 'visse',
        'visses', 'víssemos', 'vissem',
        # Verbos de ligação/existência
        'parece', 'parecer', 'ficar', 'fica', 'ficam', 'continuar',
        'continua', 'permanecer', 'permanece', 'tornar-se', 'tornar',
        'virar', 'vira',
        # Palavras de negação/afirmação
        'não', 'nao', 'sim', 'nunca', 'jamais',
        # Interjeições comuns
        'oh', 'ah', 'eh', 'ih', 'uh', 'ai', 'ui', 'olá', 'ola', 'adeus',
        # Palavras genéricas
        'coisa', 'coisas', 'pessoa', 'pessoas', 'lugar', 'lugares', 'vez',
        'vezes', 'tempo', 'maneira', 'modo', 'caso', 'fato', 'fatos',
        'parte', 'partes', 'aspecto', 'aspectos', 'ponto', 'pontos',
        'questão', 'questao', 'questões', 'questoes', 'relação', 'relacao',
        'relações', 'relacoes', 'forma', 'formas', 'tipo', 'tipos',
        'grupo', 'grupos', 'sistema', 'sistemas', 'estado', 'estados',
        'nível', 'nivel', 'sentido', 'valor', 'exemplo', 'final', 'fim',
        'início', 'inicio', 'princípio', 'principio', 'momento', 'caminho',
        'área', 'area', 'lado', 'lugar', 'pois', 'entanto',
        # Outras formas comuns
        'mesma', 'mesmos', 'mesmas', 'certo', 'certa', 'certos',
        'certas', 'tal', 'tais', 'demais', 'tanta', 'tantos', 'tantas',
        'quanta', 'quantos', 'quantas', 'vários', 'varios', 'várias', 'varias',
        'pouco', 'pouca', 'poucos', 'poucas', 'bastante', 'bastantes',
        'maior', 'menor', 'melhor', 'pior', 'maioria', 'maiorias',
        'grande', 'grandes', 'pequeno', 'pequena', 'pequenos', 'pequenas',
        'novo', 'nova', 'novos', 'novas', 'velho', 'velha', 'velhos',
        'velhas', 'bom', 'boa', 'bons', 'boas', 'mau', 'má', 'ma',
        'máximo', 'maximo', 'mínimo', 'minimo', 'próximo', 'proximo',
        'próxima', 'proxima', 'próximos', 'proximos', 'próximas', 'proximas',
        'último', 'ultimo', 'última', 'ultima', 'últimos', 'ultimos',
        'últimas', 'ultimas', 'próprio', 'proprio', 'própria', 'propria',
        'próprios', 'proprios', 'próprias', 'proprias',
    }
    
    # Stopwords em inglês
    STOPWORDS_EN: Set[str] = {
        'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and',
        'any', 'are', 'as', 'at', 'be', 'because', 'been', 'before', 'being', 'below',
        'between', 'both', 'but', 'by', 'can', 'could', 'did', 'do', 'does', 'doing',
        'down', 'during', 'each', 'few', 'for', 'from', 'further', 'had', 'has', 'have',
        'having', 'he', 'her', 'here', 'hers', 'herself', 'him', 'himself', 'his', 'how',
        'i', 'if', 'in', 'into', 'is', 'it', 'its', 'itself', 'just', 'me', 'more', 'most',
        'my', 'myself', 'no', 'nor', 'not', 'now', 'of', 'off', 'on', 'once', 'only', 'or',
        'other', 'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', 'she', 'should',
        'so', 'some', 'such', 'than', 'that', 'the', 'their', 'theirs', 'them', 'themselves',
        'then', 'there', 'these', 'they', 'this', 'those', 'through', 'to', 'too', 'under',
        'until', 'up', 'very', 'was', 'we', 'were', 'what', 'when', 'where', 'which', 'while',
        'who', 'whom', 'why', 'will', 'with', 'would', 'you', 'your', 'yours', 'yourself',
        'yourselves',
        # Referencias web/academicas
        'http', 'https', 'www', 'doi', 'issn', 'isbn', 'url', 'html', 'pdf',
    }
    
    # Sufixos para lematização básica em português
    SUFIXOS_PT: List[tuple] = [
        # Verbos
        ('ando', 3, 'ar'),
        ('endo', 3, 'er'),
        ('indo', 3, 'ir'),
        ('aram', 3, 'ar'),
        ('eram', 3, 'er'),
        ('iram', 3, 'ir'),
        ('avam', 3, 'ar'),
        ('emos', 3, 'er'),
        ('amos', 3, 'ar'),
        ('imos', 3, 'ir'),
        # Substantivos/Adjetivos
        ('mente', 4, ''),
        ('ação', 3, ''),
        ('ções', 3, ''),
        ('dade', 3, ''),
        ('ismo', 3, ''),
        ('ista', 3, ''),
        # Plurais
        ('ões', 2, 'ão'),
        ('ães', 2, 'ão'),
        ('ais', 2, 'al'),
        ('éis', 2, 'el'),
        ('óis', 2, 'ol'),
        ('uis', 2, 'ul'),
        ('es', 1, ''),
        ('s', 0, ''),
    ]
    
    def __init__(
        self,
        idioma: str = 'pt',
        remover_stopwords: bool = True,
        lematizar: bool = True,
        minusculas: bool = True,
        remover_numeros: bool = False,
        remover_acentos: bool = False,
        tamanho_minimo: int = 2,
        stopwords_extras: Optional[Set[str]] = None,
    ) -> None:
        """
        Inicializa o limpador geral.
        
        Args:
            idioma: Idioma do texto ('pt' ou 'en').
            remover_stopwords: Se True, remove stopwords.
            lematizar: Se True, aplica lematização básica.
            minusculas: Se True, converte para minúsculas.
            remover_numeros: Se True, remove números.
            remover_acentos: Se True, remove acentos.
            tamanho_minimo: Tamanho mínimo de palavra para manter.
            stopwords_extras: Conjunto de stopwords adicionais.
        """
        self._logger = get_logger(__name__)
        self.idioma = idioma
        self.remover_stopwords = remover_stopwords
        self.lematizar = lematizar
        self.minusculas = minusculas
        self.remover_numeros = remover_numeros
        self.remover_acentos = remover_acentos
        self.tamanho_minimo = tamanho_minimo
        
        # Configura stopwords
        if idioma == 'pt':
            self.stopwords = self.STOPWORDS_PT.copy()
            try:
                self.stopwords.update(build_portuguese_stopwords_from_lexicon())
            except Exception:
                self._logger.debug(
                    "Falha ao carregar stopwords ampliadas do lexico PT.",
                    exc_info=True,
                )
        elif idioma == 'en':
            self.stopwords = self.STOPWORDS_EN.copy()
        else:
            self.stopwords = self.STOPWORDS_PT.copy()
        
        if stopwords_extras:
            self.stopwords.update(stopwords_extras)
    
    def limpar(self, texto: str) -> str:
        """
        Limpa texto para análise tradicional.
        
        Args:
            texto: Texto a ser limpo.
            
        Returns:
            Texto limpo e processado.
        """
        self._logger.debug("Iniciando limpeza geral de texto")
        
        # 1. Normaliza caracteres Unicode
        texto = self._normalizar_unicode(texto)
        
        # 2. Remove URLs e emails
        texto = self._remover_urls_emails(texto)
        
        # 3. Remove pontuação (mantém espaços)
        texto = self._remover_pontuacao(texto)
        
        # 4. Processa números
        if self.remover_numeros:
            texto = re.sub(r'\d+', '', texto)
        
        # 5. Converte para minúsculas
        if self.minusculas:
            texto = texto.lower()
        
        # 6. Tokeniza
        tokens = self.tokenizar(texto)
        
        # 7. Remove stopwords
        if self.remover_stopwords:
            tokens = self._filtrar_stopwords(tokens)
        
        # 8. Lematiza
        if self.lematizar:
            tokens = self._lematizar_tokens(tokens)
        
        # 9. Remove acentos
        if self.remover_acentos:
            tokens = [self._remover_acentos_str(t) for t in tokens]
        
        # 10. Filtra por tamanho mínimo
        tokens = [t for t in tokens if len(t) >= self.tamanho_minimo]
        
        resultado = ' '.join(tokens)
        self._logger.debug(f"Limpeza concluída: {len(tokens)} tokens")
        
        return resultado
    
    def tokenizar(self, texto: str) -> List[str]:
        """
        Tokeniza texto em lista de palavras.
        
        Args:
            texto: Texto a tokenizar.
            
        Returns:
            Lista de tokens.
        """
        # Tokenização simples por espaços/pontuação
        tokens = re.findall(r'\b\w+\b', texto.lower() if self.minusculas else texto)
        return tokens
    
    def get_estatisticas(self, original: str, limpo: str) -> Dict[str, int]:
        """
        Retorna estatísticas da limpeza.
        
        Args:
            original: Texto original.
            limpo: Texto após limpeza.
            
        Returns:
            Dicionário com estatísticas.
        """
        tokens_original = self.tokenizar(original)
        tokens_limpo = limpo.split()
        
        return {
            'tokens_original': len(tokens_original),
            'tokens_limpo': len(tokens_limpo),
            'tokens_unicos_original': len(set(tokens_original)),
            'tokens_unicos_limpo': len(set(tokens_limpo)),
            'reducao_tokens': len(tokens_original) - len(tokens_limpo),
            'reducao_percentual': round(
                (1 - len(tokens_limpo) / len(tokens_original)) * 100, 2
            ) if tokens_original else 0
        }
    
    # --- Métodos privados ---
    
    def _normalizar_unicode(self, texto: str) -> str:
        """Normaliza caracteres Unicode."""
        # Normalização NFC para composição canônica
        return unicodedata.normalize('NFC', texto)
    
    def _remover_urls_emails(self, texto: str) -> str:
        """Remove URLs e emails."""
        texto = re.sub(r'https?://\S+', '', texto)
        texto = re.sub(r'www\.\S+', '', texto)
        texto = re.sub(r'\S+@\S+\.\S+', '', texto)
        return texto
    
    def _remover_pontuacao(self, texto: str) -> str:
        """Remove pontuação mantendo espaços."""
        # Substitui pontuação por espaço
        texto = re.sub(r'[^\w\s]', ' ', texto)
        # Normaliza espaços múltiplos
        texto = re.sub(r'\s+', ' ', texto)
        return texto.strip()
    
    def _filtrar_stopwords(self, tokens: List[str]) -> List[str]:
        """Remove stopwords da lista de tokens."""
        return [t for t in tokens if t.lower() not in self.stopwords]
    
    def _lematizar_tokens(self, tokens: List[str]) -> List[str]:
        """Aplica lematização básica aos tokens."""
        if self.idioma != 'pt':
            return tokens  # Lematização só para português
        
        resultado = []
        for token in tokens:
            lema = self._lematizar_palavra(token)
            resultado.append(lema)
        return resultado
    
    def _lematizar_palavra(self, palavra: str) -> str:
        """
        Lematização básica de uma palavra em português.
        
        Usa regras simples de remoção de sufixos.
        Para lematização precisa, use spaCy ou NLTK.
        """
        if len(palavra) < 4:
            return palavra
        
        original = palavra.lower()
        
        for sufixo, tamanho_min, substituicao in self.SUFIXOS_PT:
            if original.endswith(sufixo):
                raiz = original[:-len(sufixo)]
                if len(raiz) >= tamanho_min:
                    return raiz + substituicao
        
        return palavra
    
    def _remover_acentos_str(self, texto: str) -> str:
        """Remove acentos de uma string."""
        normalizado = unicodedata.normalize('NFD', texto)
        sem_acentos = ''.join(
            c for c in normalizado 
            if unicodedata.category(c) != 'Mn'
        )
        return sem_acentos
