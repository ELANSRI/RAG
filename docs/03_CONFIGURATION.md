# Fichiers de configuration et dépendances

Le lockfile est généré : ne renomme pas ses clés, paquets ni hashes. Les noms internes du programme peuvent changer, les formats compris par uv ne le peuvent pas.

## pyproject.toml

```text
001 [project]
002 name = "rag-against-the-machine"
003 version = "1.0.0"
004 description = "Retrieval-Augmented Generation over the vLLM codebase"
005 readme = "README.md"
006 requires-python = ">=3.10"
007 dependencies = [
008     "fire>=0.7.0",
009     "numpy>=1.26",
010     "pydantic>=2.7",
011     "scipy>=1.11",
012     "snowballstemmer>=2.2",
013     "torch>=2.2",
014     "tqdm>=4.66",
015     "transformers>=4.56",
016 ]
017 
018 [dependency-groups]
019 dev = [
020     "flake8>=7.0",
021     "mypy>=1.10",
022     "pytest>=8.0",
023     "scipy-stubs>=1.11",
024     "types-tqdm>=4.66",
025 ]
026 
027 # CPU-only PyTorch wheels on Linux: the campus machines have no GPU and the
028 # default CUDA wheels weigh several gigabytes.
029 [tool.uv.sources]
030 torch = [{ index = "pytorch-cpu", marker = "sys_platform == 'linux'" }]
031 
032 [[tool.uv.index]]
033 name = "pytorch-cpu"
034 url = "https://download.pytorch.org/whl/cpu"
035 explicit = true
036 
037 [tool.mypy]
038 exclude = ["^data/", "^\\.venv/"]
039 
040 # These libraries ship no type information.
041 [[tool.mypy.overrides]]
042 module = ["fire", "snowballstemmer"]
043 ignore_missing_imports = true
044 
045 [tool.pytest.ini_options]
046 testpaths = ["tests"]
047 pythonpath = ["."]
```

## Makefile

```text
001 # Usage: make run ARGS='search "How do I load a LoRA adapter?" --k 5'
002 ARGS ?= index --max_chunk_size 2000
003 MYPY_FLAGS = --warn-return-any --warn-unused-ignores --ignore-missing-imports \
004 	--disallow-untyped-defs --check-untyped-defs
005 
006 .PHONY: install run debug clean lint lint-strict test
007 
008 install:
009 	uv sync
010 
011 run:
012 	uv run python -m src $(ARGS)
013 
014 debug:
015 	uv run python -m pdb -m src $(ARGS)
016 
017 clean:
018 	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
019 	rm -rf .mypy_cache .pytest_cache
020 
021 lint:
022 	uv run flake8 .
023 	uv run mypy . $(MYPY_FLAGS)
024 
025 lint-strict:
026 	uv run flake8 .
027 	uv run mypy . --strict
028 
029 test:
030 	uv run pytest -q
```

## .flake8

```text
001 [flake8]
002 exclude = .venv,.git,data,__pycache__,.mypy_cache,.pytest_cache
```

## .gitignore

```text
001 # Python artifacts
002 __pycache__/
003 *.py[cod]
004 .venv/
005 .mypy_cache/
006 .pytest_cache/
007 *.egg-info/
008 build/
009 dist/
010 
011 # Data, indexes and generated outputs (rebuilt during the evaluation)
012 data/
013 *.zip
014 moulinette
015 moulinette-*
016 
017 # Editors / OS
018 .vscode/
019 .idea/
020 .DS_Store
021 
022 # Assignment material
023 *.pdf
```

## .python-version

```text
001 3.12
```

## Lecture des éléments

- pyproject.toml : [project] donne les métadonnées, requires-python la borne minimale et dependencies les bibliothèques installées. [dependency-groups].dev ajoute lint et tests. [tool.uv.sources] sélectionne torch CPU sur Linux. [tool.mypy] exclut les fichiers tiers et règle leurs informations de types. [tool.pytest.ini_options] indique où chercher les tests.
- Makefile : ARGS choisit la commande par défaut ; MYPY_FLAGS conserve les options imposées ; .PHONY évite la confusion avec des fichiers homonymes. Chaque ligne indentée est exécutée dans un shell. install synchronise ; run exécute ; debug lance pdb ; clean supprime les caches du code ; lint vérifie style et types ; test exécute pytest.
- .flake8 : la clé exclude empêche de contrôler les données et l’environnement comme du code étudiant.
- .gitignore : les motifs indiquent ce que Git doit ignorer lors de futurs ajouts ; ils ne retirent pas automatiquement un fichier déjà suivi.
- .python-version : uv utilise 3.12 comme interpréteur de développement ; la déclaration du projet reste >=3.10.

## Inventaire complet des paquets du lockfile

| Paquet | Version | Dépendances directes enregistrées |
|---|---|---|
| annotated-doc | 0.0.5 |  |
| annotated-types | 0.8.0 |  |
| anyio | 4.15.1 | exceptiongroup, idna, typing-extensions |
| ast-serialize | 0.11.2 |  |
| certifi | 2026.7.22 |  |
| click | 8.5.0 |  |
| colorama | 0.4.6 |  |
| exceptiongroup | 1.3.1 | typing-extensions |
| filelock | 4.0.7 |  |
| fire | 0.7.1 | termcolor |
| flake8 | 7.4.1 | mccabe, pycodestyle, pyflakes |
| fsspec | 2026.9.0 |  |
| h11 | 0.16.0 |  |
| hf-xet | 1.6.0 |  |
| httpcore | 1.0.9 | certifi, h11 |
| httpx | 0.28.1 | anyio, certifi, httpcore, idna |
| huggingface-hub | 1.33.0 | click, filelock, fsspec, hf-xet, httpx, packaging, pyyaml, tomli, tqdm, typing-extensions |
| idna | 3.20 |  |
| iniconfig | 2.3.0 |  |
| jinja2 | 3.1.6 | markupsafe |
| librt | 0.16.0 |  |
| markdown-it-py | 4.2.0 | mdurl |
| markupsafe | 3.0.3 |  |
| mccabe | 0.7.0 |  |
| mdurl | 0.1.2 |  |
| mpmath | 1.3.0 |  |
| mypy | 2.3.1 | ast-serialize, librt, mypy-extensions, pathspec, tomli, typing-extensions |
| mypy-extensions | 1.1.0 |  |
| networkx | 3.4.2 |  |
| networkx | 3.6.1 |  |
| networkx | 3.7 |  |
| numpy | 2.2.6 |  |
| numpy | 2.4.6 |  |
| numpy | 2.5.3 |  |
| numpy-typing-compat | 20251206.2.4 | numpy |
| numpy-typing-compat | 20260602.2.5 | numpy |
| optype | 0.9.3 | typing-extensions |
| optype | 0.17.1 | typing-extensions |
| optype | 0.18.0 | typing-extensions |
| packaging | 26.3 |  |
| pathspec | 1.1.1 |  |
| pluggy | 1.6.0 |  |
| pycodestyle | 2.15.0 |  |
| pydantic | 2.13.5 | annotated-types, pydantic-core, typing-extensions, typing-inspection |
| pydantic-core | 2.46.5 | typing-extensions |
| pyflakes | 4.0.0 |  |
| pygments | 2.21.0 |  |
| pytest | 9.1.1 | colorama, exceptiongroup, iniconfig, packaging, pluggy, pygments, tomli |
| pyyaml | 6.0.3 |  |
| rag-against-the-machine | 1.0.0 | fire, numpy, numpy, numpy, pydantic, scipy, scipy, scipy, snowballstemmer, torch, torch, tqdm, transformers |
| regex | 2026.9.29 |  |
| rich | 15.0.0 | markdown-it-py, pygments |
| safetensors | 0.8.0 |  |
| scipy | 1.15.3 | numpy |
| scipy | 1.17.1 | numpy |
| scipy | 1.18.1 | numpy |
| scipy-stubs | 1.15.3.0 | optype |
| scipy-stubs | 1.17.1.5 | optype |
| scipy-stubs | 1.18.1.1 | optype |
| setuptools | 84.0.0 |  |
| shellingham | 1.5.4 |  |
| snowballstemmer | 3.1.1 |  |
| sympy | 1.14.0 | mpmath |
| termcolor | 3.3.0 |  |
| tokenizers | 0.23.2 | huggingface-hub |
| tomli | 2.4.1 |  |
| torch | 2.14.0 | filelock, fsspec, jinja2, networkx, networkx, networkx, setuptools, sympy, typing-extensions |
| torch | 2.14.1+cpu | filelock, fsspec, jinja2, networkx, networkx, networkx, setuptools, sympy, typing-extensions |
| tqdm | 4.70.1 | colorama |
| transformers | 5.17.0 | huggingface-hub, numpy, numpy, numpy, packaging, pyyaml, regex, safetensors, tokenizers, tqdm, typer |
| typer | 0.27.2 | annotated-doc, colorama, rich, shellingham |
| types-tqdm | 4.70.0.20260906 |  |
| typing-extensions | 4.16.0 |  |
| typing-inspection | 0.4.4 | typing-extensions |

Chaque entrée peut ensuite contenir : source (index ou paquet local), dependencies (arêtes du graphe), sdist (archive source), wheels (archives compilées par plateforme), hash (intégrité), size (taille), resolution-markers (conditions de sélection), requires-dist (contraintes déclarées). Des dizaines de lignes de wheels décrivent des plateformes alternatives, pas autant de téléchargements pour ta machine.
