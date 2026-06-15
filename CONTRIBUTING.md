# Contribuindo com o labiia_lex

Obrigado por considerar contribuicoes para o `labiia_lex`.

## Antes de abrir uma issue

- Verifique se o problema ja foi reportado.
- Informe versao do app, Windows, R e passos para reproduzir.
- Se o erro depender de corpus, tente anexar um exemplo minimo anonimizavel.

## Antes de abrir um pull request

- Explique claramente o problema e o escopo da mudanca.
- Evite misturar refatoracao ampla com correcao pontual.
- Preserve identificadores operacionais com risco de quebra quando o ganho for apenas cosmetico.
- Nao adicione novas dependencias obrigatorias sem justificativa tecnica forte.

## Convencoes uteis

- O codigo ativo fica na raiz do repositorio.
- Recursos grandes usam Git LFS.
- O software depende de Python, R e recursos empacotados em `resources/`.
- Sempre que possivel, atualize tambem a documentacao do usuario.

## Verificacoes recomendadas

```powershell
$env:PYTHONPATH=(Get-Location).Path

py -3 -m py_compile main.py src\ui\main_window.py src\core\version.py
py -3 -m pytest -q tests
py -3 main.py --self-test --json-out tmp_self_test_contrib.json
```

## Como relatar mudancas

Em cada contribuicao, deixe explicito:

- o problema observado
- a estrategia adotada
- os riscos conhecidos
- a validacao executada
