# Fixtures de referência — CHD / AFC de Perfis

Estes arquivos vêm da **execução ideal** do LabiiaLex instalado, usada como benchmark
para a correção da AFC de Perfis densa (ver `planejamentofable.md` na raiz).

## Origem

- **Artefato:** `C:\Users\cardo\AppData\Local\LabiiaLex\history\artifacts\84795c38db284a479153064953d0399e\chd\`
- **Data da execução:** 2026-06-10T11:59 (versão instalada / congelada)
- **Corpus:** entrevista transcrita (Ricardo Poppi — participação digital). Arquivo bruto é
  pessoal e **não** está versionado; o caminho não é gravado no `analysis_history.json`.
  Para rodar o teste de paridade end-to-end (`tests/test_chd_afc_parity_reference.py`),
  forneça o corpus via variável de ambiente `LABIIA_CHD_PARITY_CORPUS` apontando para o
  `.txt` original; sem ela, o teste é marcado como `skip`.

## Parâmetros da execução de referência

```
analysis_mode: strict, nb_classes: 10, nbcl_p1: 10, classif_mode: 1,
min_freq: 2, max_actives: 20000, svd_method: irlba,
stopword_policy: aggressive_pt, strict_iramuteq_clone: true
```

## Valores canônicos esperados

- **280 UCEs**; **5 classes finais** + classe 0 (não classificadas):
  `{0: 70, 1: 43, 2: 43, 3: 35, 4: 45, 5: 44}` (ver `n1.csv`).
- **Contout:** 463 formas ativas; **chistable:** 0 valores não-finitos.
- **Autovalores AFC:** 0.1954, 0.1568, 0.1382, 0.1066
  → **variâncias:** 32.74 / 26.27 / 23.15 / 17.85 % (ver `afc_facteur.csv`, `eigenvalues.csv`).

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `n1.csv` | classe final por UCE (sep `;`, última coluna = classe; 0 = não classificada) |
| `afc_facteur.csv` | autovalores e percentuais dos fatores da AFC de perfis |
| `eigenvalues.csv` | autovalores e variância (%) |
