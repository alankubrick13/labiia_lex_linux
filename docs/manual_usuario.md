# Manual do Usuário - labiia_lex

**Versão 1.0.9**

Este manual orienta o uso do labiia_lex, uma ferramenta de análise textual e lexicométrica.

---

## Índice

1. [Introdução](#introdução)
2. [Importando Arquivos](#importando-arquivos)
3. [Preparando o Corpus](#preparando-o-corpus)
4. [Executando Análises](#executando-análises)
5. [Interpretando Resultados](#interpretando-resultados)
6. [Solução de Problemas](#solução-de-problemas)

---

## Introdução

O labiia_lex é um software para análise de textos e corpus. Ele permite:

- Importar textos de diversos formatos (TXT, PDF, DOCX, XLSX)
- Limpar e preparar o corpus para análise
- Executar análises estatísticas e lexicométricas
- Gerar visualizações como dendrogramas, grafos e nuvens de palavras

### Público-Alvo

O labiia_lex é destinado a:
- Pesquisadores de ciências sociais e humanas
- Estudantes de pós-graduação
- Profissionais que trabalham com análise de conteúdo
- Qualquer pessoa interessada em análise textual

---

## Importando Arquivos

### Formatos Suportados

| Formato | Extensão | Observações |
|---------|----------|-------------|
| Texto | .txt | UTF-8 recomendado |
| PDF | .pdf | Apenas texto extraível |
| Word | .docx | Apenas texto, sem formatação |
| Excel | .xlsx, .csv | Uma coluna de texto |

### Passo a Passo

1. **Abra o labiia_lex**
   - Execute `.\venv\Scripts\python.exe main.py` ou clique no executável

2. **Clique em "Importar"**
   - Na barra de ferramentas, clique no botão 📁 Importar

3. **Selecione o arquivo**
   - Navegue até o arquivo desejado
   - Formatos aceitos: TXT, PDF, DOCX, XLSX, CSV

4. **Escolha o modo de importação**
   - **Estruturado**: Para corpus já formatado com linhas `****`
   - **Tradicional**: Para texto livre sem formatação especial

5. **Configure as opções de limpeza**
   - ☐ Converter para minúsculas
   - ☐ Remover números
   - ☐ Remover acentos

6. **Visualize o preview**
   - O texto processado aparece na área de preview
   - Verifique se está correto antes de importar

7. **Clique em "Importar"**
   - O corpus será criado e aparecerá na árvore lateral

---

## Preparando o Corpus

### Formato Estruturado com Marcadores

O formato estruturado organiza o texto em documentos (UCIs) identificados por linhas de comando:

```
**** *genero_masculino *idade_jovem
Este é o texto do primeiro documento.
Pode ter várias frases e parágrafos.

**** *genero_feminino *idade_adulto
Este é o segundo documento do corpus.
```

### Regras do Formato

1. **Linhas de comando**
   - Começam com `****`
   - Variáveis começam com `*`
   - Formato: `*nome_valor`

2. **Nomes de variáveis**
   - Apenas letras, números e underscore
   - Sem acentos ou caracteres especiais
   - Sem espaços

3. **Valores de variáveis**
   - Apenas letras, números e underscore
   - Sem acentos

### Exemplos de Variáveis

```
**** *sexo_m *idade_30 *escolaridade_superior
Texto do entrevistado masculino de 30 anos.

**** *sexo_f *idade_45 *escolaridade_medio
Texto da entrevistada feminina de 45 anos.
```

---

### Normalizar Formas (Arquivo -> Normalizar Formas...)

**O que faz:** Identifica variações quase iguais de escrita (ex.: `analise`, `análise`, `analises`) para reduzir ruído lexical antes das análises.

**Por que usar:** Melhora a consistência estatística em CHD, Similitude, AFC e Especificidades, evitando que a mesma ideia seja contada como palavras diferentes.

**Fluxo recomendado:**
1. Rodar sugestão automática de pares próximos
2. Revisar e aceitar/recusar fusões
3. Aplicar no corpus antes de análises estruturais

---

### Tutorial Guiado

Ao abrir o software, o tutorial guiado inicia automaticamente para apresentar o fluxo completo:
1. Importar corpus
2. Normalizar Formas
3. Executar análises
4. Exportar resultados

Ele também pode ser reaberto em **Ajuda -> Tutorial Guiado**.

---

## Executando Análises

### Estatísticas Básicas (📊)

**O que faz:** Calcula contagens e métricas do corpus.

**Como usar:**
1. Com o corpus carregado, clique em "📊 Estatísticas"
2. Clique em "Executar"

**Resultados:**
- Número de documentos (UCIs)
- Número de segmentos (UCEs)
- Número de palavras únicas (formas)
- Total de ocorrências
- Hapax (palavras únicas)
- Type/Token Ratio

---

### CHD - Classificação Hierárquica (🌳)

**O que faz:** Agrupa segmentos de texto em classes temáticas usando o método Reinert (ALCESTE).

**Como usar:**
1. Clique em "🌳 CHD"
2. Configure os parâmetros:
   - **Número de classes**: Quantas classes deseja (2-10)
   - **Frequência mínima**: Palavras com menos ocorrências são ignoradas
   - **Método**: Algoritmo de clustering (ward.D2 recomendado)
3. Clique em "Executar"

**Parâmetros recomendados:**
| Tamanho do corpus | Classes | Freq. mínima |
|-------------------|---------|--------------|
| Pequeno (<100 UCEs) | 2-3 | 2 |
| Médio (100-500 UCEs) | 3-5 | 3 |
| Grande (>500 UCEs) | 5-10 | 5 |

**Resultados:**
- Dendrograma com classes coloridas
- Palavras características de cada classe
- Perfis das classes

---

### Análise de Similaridade (🔗)

**O que faz:** Cria um grafo mostrando relações de co-ocorrência entre palavras.

**Como usar:**
1. Clique em "🔗 Similitude"
2. Configure os parâmetros:
   - **Layout**: Como organizar os nós (fruchterman é bom para iniciantes)
   - **Frequência mínima**: Palavras menos frequentes são ignoradas
   - **Coeficiente**: Tipo de relação (cooccurrence é o mais comum)
3. Clique em "Executar"

**Layouts disponíveis:**
- **Fruchterman-Reingold**: Layout orgânico, bom para maioria dos casos
- **Kamada-Kawai**: Layout mais compacto
- **Circular**: Nós em círculo
- **Random**: Layout aleatório

**Resultados:**
- Grafo com palavras conectadas
- Tamanho dos nós = frequência
- Espessura das linhas = força da conexão

---

### Rede Textual (Extra) (🕸️)

**O que faz:** Cria uma visualização de rede avançada (Gephi-like) com detecção de comunidades e ajuste de rótulos (Noverlap).

**Como usar:**
1. Clique em "🕸️ Rede Textual"
2. Configure os parâmetros:
   - **Frequência mínima**: Filtra palavras raras
   - **Coocorrência mínima**: Filtra conexões fracas
   - **Ajuste de Rótulos**: Ative para evitar sobreposição de palavras
3. Clique em "Executar"

**Resultados:**
- Grafo interativo e exportável (PNG/SVG/GEXF)
- Comunidades coloridas automaticamente

---

### AFC - Análise Fatorial (📈)

**O que faz:** Projeta palavras e documentos em um espaço 2D ou 3D, mostrando proximidades e diferenças.

**Como usar:**
1. Clique em "📈 AFC"
2. Configure os parâmetros:
   - **Dimensões**: 2 para visualização simples, 3+ para análise mais detalhada
   - **Frequência mínima**: Palavras menos frequentes são ignoradas
3. Clique em "Executar"

**Resultados:**
- Gráfico 2D com palavras e variáveis
- Palavras próximas = uso similar
- Eixos explicam % da variância

---

---

### Nuvem de Palavras (☁️)

**O que faz:** Visualiza as palavras mais frequentes com tamanho proporcional.

**Como usar:**
1. Clique em "☁️ Nuvem"
2. Configure os parâmetros:
   - **Máximo de palavras**: Quantas palavras exibir (20-300)
   - **Frequência mínima**: Ignorar palavras raras
   - **Esquema de cores**: Paleta visual
3. Clique em "Executar"

**Esquemas de cores:**
- Dark2: Cores escuras, bom contraste
- Set1: Cores vivas
- Pastel1: Cores suaves

**Resultados:**
- Imagem PNG com a nuvem
- Palavras maiores = mais frequentes

---

### Especificidades (📌)

**O que faz:** Associa palavras a variáveis do corpus (ex: palavras mais usadas por homens vs mulheres). Baseado no cálculo de Qui-Quadrado ou Hipergeométrica.

**Como usar:**
1. Clique em "📌 Especificidades"
2. Selecione a **Variável** de interesse (ex: *sexo)
3. Clique em "Executar"

**Resultados:**
- Tabela listando palavras que são estatisticamente sup-representadas em cada grupo da variável.

---

### Concordância KWIC (🔎)

**O que faz:** Busca uma palavra e mostra o contexto (Key Word In Context).

**Como usar:**
1. Clique em "🔎 Concordância"
2. Digite o **Termo de busca**
3. Defina o **Tamanho do contexto** (caracteres antes/depois)
4. Clique em "Executar"

**Resultados:**
- Lista de ocorrências com o texto anterior e posterior alinhado.

---

### Análise Prototípica (📐)

**O que faz:** Cruza a Frequência das palavras com sua Ordem de Evocação (Rank). Útil para teoria das representações sociais.

**Como usar:**
1. Clique em "📐 Prototípica"
2. Configure os parâmetros (Corte de frequência, corte de rank)
3. Clique em "Executar"

**Resultados:**
- Matriz de 4 quadrantes identificando o Núcleo Central e Periferias.

---

### Análises Extras (Experimentais) (🧪)

Recursos novos e experimentais adicionados recentemente:

#### 1. Pacote Voyant (Novo)
Painel consolidado com visualizações textométricas:
- **TermsBerry**
- **Tendências**
- **Termos do Documento**
- **Gráfico de Bolhas (Bubblelines)**
- **Co-ocorrências**

#### 2. CCA (Textometrica)
Ferramenta de análise contextual complementar para inspeção textual dirigida.

#### 3. Rolling Window (Lexos)
Mostra evolução da frequência de termos ao longo da progressão do corpus.

#### 4. KWIC / Concordancer
Concordanciador dedicado (estilo AntConc) para busca de termo, contexto e distribuição.

#### 5. Keyness (Comparação)
Compara dois corpora/grupos e destaca termos distintivos por métricas de keyness.

#### 6. Árvore de Palavras (Word Tree) (🌳)
Cria um diagrama de ramificação a partir de uma palavra central, mostrando quais frases seguem ou antecedem esse termo.
- **Como usar:** Menu Análise -> Word Tree (Extra). Defina a palavra raiz e a profundidade.

#### 7. Keyness (Extra) (🔑)
Compara dois grupos e destaca quais palavras são "chaves" (únicas) para o grupo alvo em comparação ao resto.
- **Como usar:** Menu Análise -> Keyness (Extra). Escolha a variável e o valor alvo.

#### 8. Rede de Bigramas (🔗)
Cria um grafo conectando palavras que aparecem lado a lado (pares).
- **Como usar:** Menu Análise -> Bigramas (Extra).

#### 9. Heatmap Lexical (🔥)
Gera um mapa de calor cruzando Segmentos (UCEs) vs Termos, com agrupamento (cluster) para mostrar padrões visuais.
- **Como usar:** Menu Análise -> Heatmap Lexical (Extra).

#### 10. Wordfish (🐟)
Posiciona documentos em uma escala unidimensional (Esquerda <-> Direita) baseada em frequências de palavras. Útil para polarização.
- **Como usar:** Menu Análise -> Wordfish (Extra).

#### 11. X-Ray (Dispersão) (🩻)
Mostra onde uma palavra aparece ao longo do "tempo" ou "posição" dentro dos documentos.
- **Como usar:** Menu Análise -> X-Ray (Extra).

#### 12. Sentimentos (😊/b☹️)
Classifica palavras como Positivas, Negativas ou Neutras usando o dicionário OpLexicon e mostra a evolução temporal.
- **Como usar:** Menu Análise -> Sentimentos (Extra).

---

## Interpretando Resultados

### Dendrograma (CHD)

O dendrograma mostra como o corpus foi dividido em classes:

```
Classe 1 (25%) ─────┐
                    ├── Tema A
Classe 2 (20%) ─────┘
                           ├── Corpus
Classe 3 (30%) ─────┬──────┘
                    │
Classe 4 (25%) ─────┘─── Tema B
```

- Cada classe agrupa segmentos similares
- Porcentagem indica tamanho da classe
- Proximidade vertical indica similaridade

### Grafo de Similaridade

- **Nós grandes**: Palavras frequentes
- **Linhas grossas**: Co-ocorrência forte
- **Clusters**: Grupos de palavras relacionadas
- **Posição central**: Palavras conectoras

### AFC

- **Quadrantes**: Agrupam palavras/variáveis similares
- **Distância do centro**: Quanto mais longe, mais distintivo
- **Proximidade**: Palavras próximas = uso similar

---

## Exportando Dados

### Exportar Corpus Estruturado

Se você precisa salvar seu corpus em texto estruturado:
1. Selecione o corpus na árvore lateral
2. Clique no botão **"📤 Exportar corpus estruturado"**
3. Salve o arquivo TXT

### Exportar Resultados

Na visualização de resultados, use o botão direito do mouse ou os botões de exportação para salvar imagens (PNG/SVG) e tabelas (CSV).

---

## Solução de Problemas

### Erro: "R não encontrado"

**Causa:** O software R não está instalado ou não está no PATH.

**Solução:**
1. Baixe R de https://cran.r-project.org/
2. Instale normalmente
3. Reinicie o labiia_lex
4. Se persistir, configure manualmente em ⚙️ Configurações

### Erro: "Corpus muito pequeno"

**Causa:** O corpus não tem texto suficiente para a análise.

**Solução:**
- Para CHD: precisa de pelo menos 50-100 segmentos
- Adicione mais textos ao corpus
- Tente "Estatísticas" que funciona com qualquer tamanho

### Erro: "Problema de codificação"

**Causa:** O arquivo não está em UTF-8.

**Solução:**
1. Abra o arquivo no Bloco de Notas
2. Clique em "Arquivo" → "Salvar como"
3. Em "Codificação", selecione "UTF-8"
4. Salve e importe novamente

### Erro: "Pacotes R faltando"

**Causa:** Pacotes R necessários não estão instalados.

**Solução:**
1. Abra o R (não o RStudio)
2. Execute:
   ```r
   install.packages(c("igraph", "ca", "wordcloud", "ape"))
   ```
3. Aguarde a instalação
4. Reinicie o labiia_lex

### A interface está muito pequena

**Solução:**
- Maximize a janela
- Use as configurações de zoom do Windows (125% ou 150%)

### Análise está demorando muito

**Causa normal:** Análises em corpus grandes podem levar vários minutos.

**Se travar:**
1. A barra de progresso deve estar em movimento
2. Se parar por mais de 5 minutos, feche e reabra
3. Tente reduzir o corpus ou aumentar a frequência mínima

---

## Atalhos de Teclado

| Atalho | Ação |
|--------|------|
| Ctrl+O | Importar arquivo |
| Ctrl+S | Salvar projeto |
| Ctrl+Q | Sair |
| F1 | Ajuda |

---

## Validação Recente (Testes Automatizados)

A versão atual foi validada com suíte automatizada em `pytest`, incluindo:
- `tests/test_ui.py` (fluxos de interface, tabs, histórico e visualizadores)
- `tests/test_voyant_suite.py` (payload/painéis fixos do pacote Voyant)
- `tests/test_concordancer.py` (KWIC/Concordancer)
- `tests/test_network_text_analysis.py` e `tests/test_network_text_renderer.py` (Rede Textual)
- `tests/test_matrix_analysis.py` (AFC/CHD/Similitude em Matriz)

Também foi validada a suíte completa de regressão do diretório `tests/`.

---

## Contato e Suporte

- **Ajuda local:** docs/help/geral.html
- **Código-fonte:** repositório GitHub público do labiia_lex
- **Bugs:** Abra uma Issue no GitHub

---

*labiia_lex v1.0.9 - Software de Analise Textual*


