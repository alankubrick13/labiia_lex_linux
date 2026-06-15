# Recursos Lexicais Opcionais (CCA Automático)

O CCA automático busca recursos locais nestes diretórios (recursivo):

1. `resources/semantic/`
2. `resources/semantic_sources/`
3. `dictionaries/semantic/`

Nenhum download é feito automaticamente. O aplicativo apenas usa arquivos que
você já colocou nessas pastas.

## Formatos suportados

1. Pares semânticos simples (`.tsv`, `.csv`, `.txt`)

```
palavra_a<TAB>palavra_b
```

Também aceita `;` e `,` como separador.

2. Tesauro por linha (`.csv`, `.tsv`, `.txt`)

```
palavra;sinonimo_1;sinonimo_2;sinonimo_3
```

3. Morfologia DELAF/MorphoBr-like (`.txt`, `.csv`, `.tsv`)

```
formas,lema.POS+tracos
```

ou com colunas explícitas `form/lemma`.

4. OpenWordNet-like em TTL (`.ttl`)

Linhas com `label` ou `writtenForm` em `@pt` são agrupadas por synset e
convertidas em pares semânticos.

## Fontes recomendadas

- OpenWordNet-PT: https://github.com/own-pt/openWordnet-PT
- MorphoBr: https://github.com/LR-POR/MorphoBr
- PortiLexicon-UD: https://github.com/LuceleneL/PortiLexicon-UD
- PT-LexicalSemantics: https://github.com/NLP-CISUC/PT-LexicalSemantics
- EticaAI linguistic datasets: https://github.com/EticaAI/linguistic-datasets-portuguese

## Observações de qualidade

- Recursos externos só reforçam o grafo; não sobrescrevem conceitos manuais.
- Se não houver arquivos válidos, o CCA automático continua com o pipeline local.
- Diagnósticos de uso dos recursos aparecem na prévia de sugestões.
