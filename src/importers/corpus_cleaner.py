"""
CorpusCleaner - Limpador de corpus para formato IRaMuTeQ.
==========================================================
Baseado em limpar_corpus_iramuteq.py com a lógica completa
de limpeza para análise no IRaMuTeQ.

Este módulo implementa:
- Remoção de caracteres proibidos
- Substituição de expressões compostas
- Validação de linhas de comando (****)
- Normalização para formato IRaMuTeQ
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

from ..core.lexicon import Lexicon, resolve_expression_path
from .internet_cleaner import clean_internet_artifacts
from ..utils.logger import get_logger


class CorpusCleaner:
    """
    Limpador de corpus para formato IRaMuTeQ.
    
    Esta classe prepara textos para análise no IRaMuTeQ,
    aplicando todas as transformações necessárias.
    """
    
    # Caracteres que devem ser removidos ou substituídos
    # Baseado em CARACTERES_PROIBIDOS de limpar_corpus_iramuteq.py
    CARACTERES_PROIBIDOS: Dict[str, str] = {
        '"': '',           # Aspas duplas
        "'": ' ',          # Aspas simples/apóstrofo
        ''': ' ',          # Apóstrofo tipográfico
        ''': ' ',          # Apóstrofo tipográfico
        '"': '',           # Aspas tipográficas
        '"': '',           # Aspas tipográficas
        '«': '',           # Aspas francesas
        '»': '',           # Aspas francesas
        '&': ' e ',        # E comercial
        '$': '',           # Cifrão
        '%': ' por_cento', # Porcentagem
        '…': '.',          # Reticências
        '–': ' ',          # Travessão
        '—': ' ',          # Travessão longo
        '−': ' ',          # Sinal de menos
        '¬': '',           # Negação
        '|': ' ',          # Pipe
        '\\': ' ',         # Barra invertida
        '/': ' ',          # Barra
        '<': '',           # Menor que
        '>': '',           # Maior que
        '{': '',           # Chave
        '}': '',           # Chave
        '[': '',           # Colchete
        ']': '',           # Colchete
        '#': '',           # Hashtag
        '@': '',           # Arroba
        '©': '',           # Copyright
        '®': '',           # Marca registrada
        '™': '',           # Trademark
        '°': ' graus',     # Símbolo de grau
        '§': '',           # Parágrafo
        '¹': '1',          # Superescrito
        '²': '2',          # Superescrito
        '³': '3',          # Superescrito
        '½': ' meio',      # Fração
        '¼': ' um_quarto', # Fração
        '¾': ' tres_quartos', # Fração
        '•': '',           # Bullet
        '·': '',           # Ponto médio
        '†': '',           # Cruz
        '‡': '',           # Cruz dupla
        '≠': ' diferente_de ',
        '≤': ' menor_ou_igual ',
        '≥': ' maior_ou_igual ',
        '±': ' mais_ou_menos ',
        '×': ' vezes ',
        '÷': ' dividido_por ',
        '\t': ' ',         # Tab
        '\r': '',          # Retorno de carro
        '\xa0': ' ',       # Espaço não quebrável
        '\u200b': '',      # Zero-width space
        '\ufeff': '',      # BOM
    }
    
    # Expressões compostas padrão em português
    EXPRESSOES_COMPOSTAS_PADRAO: List[Tuple[str, str]] = [
        # Políticas públicas e governo
        ('política pública', 'politica_publica'),
        ('políticas públicas', 'politicas_publicas'),
        ('poder público', 'poder_publico'),
        ('setor público', 'setor_publico'),
        ('gestão pública', 'gestao_publica'),
        ('administração pública', 'administracao_publica'),
        ('servidor público', 'servidor_publico'),
        ('servidores públicos', 'servidores_publicos'),
        ('serviço público', 'servico_publico'),
        ('saúde pública', 'saude_publica'),
        ('educação pública', 'educacao_publica'),
        ('segurança pública', 'seguranca_publica'),
        
        # Tecnologia e IA
        ('inteligência artificial', 'inteligencia_artificial'),
        ('aprendizado de máquina', 'aprendizado_de_maquina'),
        ('machine learning', 'machine_learning'),
        ('deep learning', 'deep_learning'),
        ('big data', 'big_data'),
        ('redes sociais', 'redes_sociais'),
        ('rede social', 'rede_social'),
        
        # Democracia e participação
        ('participação social', 'participacao_social'),
        ('participação popular', 'participacao_popular'),
        ('democracia participativa', 'democracia_participativa'),
        ('democracia digital', 'democracia_digital'),
        ('orçamento participativo', 'orcamento_participativo'),
        ('controle social', 'controle_social'),
        ('sociedade civil', 'sociedade_civil'),
        
        # Educação
        ('ensino superior', 'ensino_superior'),
        ('educação básica', 'educacao_basica'),
        ('educação infantil', 'educacao_infantil'),
        ('ensino fundamental', 'ensino_fundamental'),
        ('ensino médio', 'ensino_medio'),
        
        # Direitos e cidadania
        ('direitos humanos', 'direitos_humanos'),
        ('direitos fundamentais', 'direitos_fundamentais'),
        ('direitos sociais', 'direitos_sociais'),
        
        # Metodologia e pesquisa
        ('análise de conteúdo', 'analise_de_conteudo'),
        ('estudo de caso', 'estudo_de_caso'),
        ('grupo focal', 'grupo_focal'),
        ('revisão sistemática', 'revisao_sistematica'),
        ('pesquisa qualitativa', 'pesquisa_qualitativa'),
        ('pesquisa quantitativa', 'pesquisa_quantitativa'),
        
        # Expressões gerais
        ('por exemplo', 'por_exemplo'),
        ('ou seja', 'ou_seja'),
        ('isto é', 'isto_e'),
        ('entre outros', 'entre_outros'),
        ('por outro lado', 'por_outro_lado'),
        ('ao mesmo tempo', 'ao_mesmo_tempo'),
        ('a partir de', 'a_partir_de'),
        ('de acordo com', 'de_acordo_com'),
    ]
    
    def __init__(
        self,
        converter_minusculas: bool = False,
        remover_numeros: bool = False,
        remover_acentos: bool = False,
        limpar_dados_internet: bool = True,
        expressoes_customizadas: Optional[List[Tuple[str, str]]] = None,
        idioma: str = 'pt',
        usar_expressoes_padrao: bool = True,
    ) -> None:
        """
        Inicializa o limpador de corpus.
        
        Args:
            converter_minusculas: Se True, converte texto para minúsculas.
            remover_numeros: Se True, remove números do texto.
            remover_acentos: Se True, remove acentos do texto completo.
            limpar_dados_internet: Se True, remove URLs/emails/telefones/IPs.
            expressoes_customizadas: Lista de (expressao, substituicao).
            idioma: Idioma do corpus ('pt', 'en').
            usar_expressoes_padrao: Se False, nao carrega expressoes compostas padrao.
        """
        self._logger = get_logger(__name__)
        self.converter_minusculas = converter_minusculas
        self.remover_numeros = remover_numeros
        self.remover_acentos = remover_acentos
        self.limpar_dados_internet = bool(limpar_dados_internet)
        self.idioma = idioma
        
        # Combina expressoes em arquivo com customizadas
        if usar_expressoes_padrao:
            self.expressoes_compostas = self._load_default_expressions(idioma)
        else:
            self.expressoes_compostas = []
        if expressoes_customizadas:
            self.expressoes_compostas.extend(expressoes_customizadas)
        
        # Ordena por tamanho decrescente (expressões maiores primeiro)
        self.expressoes_compostas.sort(key=lambda x: len(x[0]), reverse=True)
        # Variante normalizada para um segundo passe opcional (após remoção de acentos/minúsculas).
        self.expressoes_compostas_normalizadas = self._normalizar_expressoes(
            self.expressoes_compostas
        )

    def _load_default_expressions(self, idioma: str) -> List[Tuple[str, str]]:
        """Carrega expressoes compostas do dicionario externo."""
        expression_path = resolve_expression_path(idioma or "portuguese")
        lexicon = Lexicon()
        loaded_map = lexicon.load_expressions(expression_path)
        if loaded_map:
            # Mantém base interna completa e aplica overrides/adicoes do arquivo externo.
            merged_map: Dict[str, str] = {
                str(expr): str(repl)
                for expr, repl in self.EXPRESSOES_COMPOSTAS_PADRAO
                if str(expr).strip() and str(repl).strip()
            }
            for expr, repl in loaded_map.items():
                key = str(expr or "").strip()
                value = str(repl or "").strip()
                if not key or not value:
                    continue
                merged_map[key] = value
            self._logger.info(
                "Expressoes compostas carregadas de %s (%s itens externos, %s totais)",
                expression_path,
                len(loaded_map),
                len(merged_map),
            )
            return list(merged_map.items())

        self._logger.warning(
            "Arquivo de expressoes nao encontrado ou vazio em %s. Usando fallback interno.",
            expression_path,
        )
        return list(self.EXPRESSOES_COMPOSTAS_PADRAO)
    
    def limpar(self, texto: str) -> str:
        """
        Executa pipeline completo de limpeza do corpus.
        
        Args:
            texto: Texto bruto do corpus.
            
        Returns:
            Texto limpo e formatado para IRaMuTeQ.
        """
        self._logger.debug("Iniciando limpeza de corpus para IRaMuTeQ")
        
        # 1. Protege linhas de comando
        texto = self._proteger_asteriscos(texto)
        
        # 2. Remove dados de internet (URLs, emails, telefones etc.)
        if self.limpar_dados_internet:
            texto = self._limpar_dados_internet(texto)
        
        # 3. Substitui caracteres proibidos
        texto = self._substituir_caracteres_proibidos(texto)
        
        # 4. Remove asteriscos do texto (exceto linhas protegidas)
        texto = self._remover_asteriscos_texto(texto)
        
        # 5. Processa hífens
        texto = self._processar_hifen(texto)
        
        # 6. Processa números
        texto = self._processar_numeros(texto)
        
        # 7. Substitui expressões compostas
        texto = self._substituir_expressoes_compostas(texto)
        
        # 8. Restaura linhas de comando
        texto = self._restaurar_asteriscos(texto)
        
        # 9. Valida linhas de comando
        texto = self._validar_linhas_comando(texto)
        
        # 10. Remove acentos das variáveis
        texto = self._remover_acentos_variaveis(texto)
        
        # 10.1 Remove acentos do texto completo se configurado
        if self.remover_acentos:
            texto = self._remover_acentos_texto(texto)

        # 11. Converte para minúsculas se configurado
        if self.converter_minusculas:
            texto = self._converter_para_minusculas(texto)
        
        # 11.1 Segundo passe de compostos após normalizações opcionais.
        # Garante união mesmo quando o usuário seleciona expressão sem acento
        # e também marca "remover acentos".
        if self.remover_acentos or self.converter_minusculas:
            texto = self._substituir_expressoes_compostas(
                texto,
                expressoes=self.expressoes_compostas_normalizadas,
            )
        
        # 12. Normaliza espaços
        texto = self._normalizar_espacos(texto)
        
        # 13. Normaliza quebras de linha
        texto = self._normalizar_quebras_linha(texto)
        
        # 14. Remove blocos UCI sem conteúdo textual
        texto = self._remover_ucis_vazias(texto)

        # 15. Garante linha em branco inicial
        texto = self._garantir_linha_branco_inicial(texto)
        
        self._logger.debug("Limpeza de corpus concluída")
        return texto
    
    def get_estatisticas(self, original: str, limpo: str) -> Dict[str, int]:
        """
        Retorna estatísticas da limpeza.
        
        Args:
            original: Texto original.
            limpo: Texto após limpeza.
            
        Returns:
            Dicionário com estatísticas.
        """
        def contar_palavras(texto: str) -> int:
            return len(re.findall(r'\b\w+\b', texto))
        
        def contar_linhas_comando(texto: str) -> int:
            return len(re.findall(r'^\*{4}', texto, re.MULTILINE))
        
        char_original = len(original)
        char_limpo = len(limpo)
        
        return {
            'caracteres_original': char_original,
            'caracteres_limpo': char_limpo,
            'palavras_original': contar_palavras(original),
            'palavras_limpo': contar_palavras(limpo),
            'linhas_comando': contar_linhas_comando(limpo),
            'reducao_caracteres': char_original - char_limpo,
            'reducao_percentual': round(
                (1 - char_limpo / char_original) * 100, 2
            ) if char_original > 0 else 0
        }
    
    # --- Métodos privados de limpeza ---
    
    def _proteger_asteriscos(self, texto: str) -> str:
        """Protege asteriscos das linhas de comando antes da limpeza."""
        linhas = texto.split('\n')
        resultado = []
        
        for linha in linhas:
            if linha.strip().startswith('****'):
                linha_protegida = re.sub(r'^\s*\*{4}', 'QUATRO_AST_MARCADOR', linha)
                linha_protegida = linha_protegida.replace(' *', ' AST_VAR_MARCADOR')
                resultado.append('LINHA_CMD_INICIO' + linha_protegida + 'LINHA_CMD_FIM')
            else:
                resultado.append(linha)
        
        return '\n'.join(resultado)
    
    def _restaurar_asteriscos(self, texto: str) -> str:
        """Restaura linhas de comando após limpeza."""
        texto = texto.replace('LINHA_CMD_INICIO', '')
        texto = texto.replace('LINHA_CMD_FIM', '')
        texto = texto.replace('QUATRO_AST_MARCADOR', '****')
        texto = texto.replace('AST_VAR_MARCADOR', '*')
        return texto
    
    def _remover_asteriscos_texto(self, texto: str) -> str:
        """Remove asteriscos do texto (exceto linhas protegidas)."""
        linhas = texto.split('\n')
        resultado = []
        
        for linha in linhas:
            if 'LINHA_CMD_INICIO' in linha or 'QUATRO_AST_MARCADOR' in linha:
                resultado.append(linha)
            else:
                resultado.append(linha.replace('*', ''))
        
        return '\n'.join(resultado)
    
    def _substituir_caracteres_proibidos(self, texto: str) -> str:
        """Substitui caracteres não suportados pelo IRaMuTeQ."""
        for char, substituto in self.CARACTERES_PROIBIDOS.items():
            texto = texto.replace(char, substituto)
        return texto
    
    def _remover_urls(self, texto: str) -> str:
        """Remove URLs do texto."""
        texto = re.sub(r'https?://\S+', '', texto)
        texto = re.sub(r'www\.\S+', '', texto)
        return texto
    
    def _remover_emails(self, texto: str) -> str:
        """Remove endereços de email do texto."""
        texto = re.sub(r'\S+@\S+\.\S+', '', texto)
        return texto

    def _limpar_dados_internet(self, texto: str) -> str:
        """Remove artefatos comuns de internet mantendo marcadores IRaMuTeQ."""
        try:
            return clean_internet_artifacts(texto, preserve_command_lines=True)
        except Exception:
            # Fallback extremo: preserva comportamento anterior sem interromper importação.
            self._logger.exception(
                "Falha na limpeza web com pacote externo; aplicando fallback regex legado."
            )
            texto = self._remover_urls(texto)
            texto = self._remover_emails(texto)
            return texto
    
    def _processar_hifen(self, texto: str) -> str:
        """Processa hífens de forma inteligente."""
        # Remove hífens no início ou fim de palavras
        texto = re.sub(r'(\s)-+', r'\1', texto)
        texto = re.sub(r'-+(\s)', r'\1', texto)
        texto = re.sub(r'^-+', '', texto, flags=re.MULTILINE)
        texto = re.sub(r'-+$', '', texto, flags=re.MULTILINE)
        # Múltiplos hífens viram um só
        texto = re.sub(r'-{2,}', '-', texto)
        return texto
    
    def _processar_numeros(self, texto: str) -> str:
        """Processa números conforme configuração."""
        if self.remover_numeros:
            linhas = texto.split('\n')
            resultado = []
            for linha in linhas:
                if (
                    'LINHA_CMD_INICIO' in linha
                    or 'QUATRO_AST_MARCADOR' in linha
                    or linha.strip().startswith('****')
                ):
                    resultado.append(linha)
                else:
                    resultado.append(re.sub(r'\d+', '', linha))
            texto = '\n'.join(resultado)
        return texto
    
    @staticmethod
    def _fold_accents(value: str) -> str:
        """Remove acentos de um texto preservando demais caracteres."""
        normalized = unicodedata.normalize("NFD", str(value or ""))
        return "".join(
            char for char in normalized
            if unicodedata.category(char) != "Mn"
        )

    def _normalizar_expressoes(
        self,
        expressoes: Sequence[Tuple[str, str]],
    ) -> List[Tuple[str, str]]:
        """
        Gera variante normalizada de expressões (sem acento, minúscula e espaços canônicos).
        """
        normalized: List[Tuple[str, str]] = []
        seen: set[Tuple[str, str]] = set()
        for expressao, substituicao in expressoes or []:
            expr = re.sub(r"\s+", " ", self._fold_accents(expressao).strip().lower())
            repl = re.sub(r"\s+", "_", self._fold_accents(substituicao).strip().lower())
            if not expr or not repl:
                continue
            pair = (expr, repl)
            if pair in seen:
                continue
            seen.add(pair)
            normalized.append(pair)
        normalized.sort(key=lambda x: len(x[0]), reverse=True)
        return normalized

    @staticmethod
    def _build_compound_pattern(expressao: str) -> re.Pattern:
        """
        Compila padrão com fronteiras de palavra e espaço flexível.
        Ex.: "sistema wayfinding" casa também com "sistema   wayfinding".
        """
        tokens = [token for token in re.split(r"\s+", str(expressao or "").strip()) if token]
        if not tokens:
            return re.compile(r"$^")
        body = r"\s+".join(re.escape(token) for token in tokens)
        pattern = rf"(?<![\w_]){body}(?![\w_])"
        return re.compile(pattern, re.IGNORECASE)

    def _substituir_expressoes_compostas(
        self,
        texto: str,
        expressoes: Optional[Sequence[Tuple[str, str]]] = None,
    ) -> str:
        """Substitui expressões compostas por versões com underscore."""
        pairs = expressoes if expressoes is not None else self.expressoes_compostas
        for expressao, substituicao in pairs:
            padrao = self._build_compound_pattern(expressao)
            texto = padrao.sub(str(substituicao), texto)
        return texto
    
    def _validar_linhas_comando(self, texto: str) -> str:
        """Valida e corrige linhas de comando do IRaMuTeQ."""
        linhas = texto.split('\n')
        resultado = []
        
        for linha in linhas:
            linha_strip = linha.strip()
            
            if linha_strip.startswith('****'):
                # Corrige formato da linha de comando
                linha_corrigida = re.sub(r'^\*{4}\s*', '**** ', linha_strip)
                
                # Corrige formato das variáveis
                partes = linha_corrigida.split()
                partes_corrigidas = [partes[0]]  # ****
                
                for parte in partes[1:]:
                    if parte.startswith('*'):
                        partes_corrigidas.append(self._sanitizar_variavel_iramuteq(parte))
                    else:
                        partes_corrigidas.append(parte)
                
                resultado.append(' '.join(partes_corrigidas))
            else:
                resultado.append(linha)
        
        return '\n'.join(resultado)
    
    def _remover_acentos_variaveis(self, texto: str) -> str:
        """Remove acentos apenas das linhas de variáveis."""
        linhas = texto.split('\n')
        resultado = []
        
        for linha in linhas:
            if linha.strip().startswith('****'):
                linha_normalizada = unicodedata.normalize('NFD', linha)
                linha_sem_acento = ''.join(
                    c for c in linha_normalizada 
                    if unicodedata.category(c) != 'Mn'
                )
                resultado.append(linha_sem_acento)
            else:
                resultado.append(linha)
        
        return '\n'.join(resultado)
    
    def _converter_para_minusculas(self, texto: str) -> str:
        """Converte texto para minúsculas (preservando linhas de comando)."""
        linhas = texto.split('\n')
        resultado = []
        
        for linha in linhas:
            if linha.strip().startswith('****'):
                resultado.append(linha)
            else:
                resultado.append(linha.lower())
        
        return '\n'.join(resultado)

    def _sanitizar_variavel_iramuteq(self, token: str) -> str:
        """Normaliza token para o formato *nome_valor aceito pelo validador."""
        bruto = str(token or "").strip()
        if not bruto.startswith("*"):
            bruto = f"*{bruto}"

        corpo = bruto[1:]
        corpo = unicodedata.normalize('NFD', corpo)
        corpo = ''.join(
            c for c in corpo
            if unicodedata.category(c) != 'Mn'
        ).lower()
        corpo = re.sub(r'[^a-z0-9_]+', '_', corpo)
        corpo = re.sub(r'_+', '_', corpo).strip('_')

        if '_' not in corpo:
            nome, valor = corpo or "var", "valor"
        else:
            nome, valor = corpo.split('_', 1)
            nome = nome or "var"
            valor = valor.strip('_') or "valor"

        return f"*{nome}_{valor}"

    def _remover_acentos_texto(self, texto: str) -> str:
        """Remove acentos do texto (preserva formatação de linhas)."""
        linhas = texto.split('\n')
        resultado = []

        for linha in linhas:
            linha_normalizada = unicodedata.normalize('NFD', linha)
            linha_sem_acento = ''.join(
                c for c in linha_normalizada
                if unicodedata.category(c) != 'Mn'
            )
            resultado.append(linha_sem_acento)

        return '\n'.join(resultado)
    
    def _normalizar_espacos(self, texto: str) -> str:
        """Normaliza espaços múltiplos."""
        texto = re.sub(r' +', ' ', texto)
        texto = '\n'.join(linha.strip() for linha in texto.split('\n'))
        return texto
    
    def _normalizar_quebras_linha(self, texto: str) -> str:
        """Normaliza quebras de linha."""
        texto = re.sub(r'\n{3,}', '\n\n', texto)
        return texto
    
    def _garantir_linha_branco_inicial(self, texto: str) -> str:
        """Garante uma linha em branco antes do primeiro texto."""
        texto = texto.lstrip('\n')
        if not texto.startswith('\n'):
            texto = '\n' + texto
        return texto

    def _remover_ucis_vazias(self, texto: str) -> str:
        """
        Remove linhas de comando sem conteúdo útil até a próxima UCI.

        Evita erros de validação "UCI sem conteúdo textual" após limpeza.
        """
        if not texto or '****' not in texto:
            return texto

        linhas = texto.split('\n')
        if not any(linha.strip().startswith('****') for linha in linhas):
            return texto

        blocos_validos: List[str] = []
        comando_atual: Optional[str] = None
        corpo_atual: List[str] = []
        removidas = 0

        def flush() -> None:
            nonlocal removidas
            if comando_atual is None:
                return
            corpo_limpo = [linha for linha in corpo_atual if linha.strip()]
            if corpo_limpo:
                blocos_validos.append(comando_atual.strip())
                blocos_validos.extend(corpo_limpo)
                blocos_validos.append('')
            else:
                removidas += 1

        for linha in linhas:
            if linha.strip().startswith('****'):
                flush()
                comando_atual = linha
                corpo_atual = []
            else:
                if comando_atual is None:
                    continue
                corpo_atual.append(linha)

        flush()

        if removidas:
            self._logger.info("Removidas %s UCI(s) vazias após limpeza.", removidas)

        return '\n'.join(blocos_validos).strip()
