# Lecture de ton projet et nouvelle organisation

Cette version est un refactoring pédagogique de l'archive `rag.zip` fournie.
Les algorithmes de segmentation et de normalisation lexicale sont conservés,
répartis dans des modules plus ciblés et renommés. BM25, l'orchestration,
la persistance, la construction du contexte et la CLI sont réorganisés ou
réécrits. Ce n'est pas un algorithme entièrement nouveau ni une simple
substitution de noms. Les noms du contrat externe restent compatibles.

## Ce qui a été lu

Tous les fichiers Python de l'archive ont été lus, y compris les tests et
les points d'entrée. Les configurations et les trois documents Markdown
ont été lus. `uv.lock` a été parcouru et analysé comme fichier TOML :
2045 lignes et 74 entrées de paquets. Ce fichier généré contient des versions,
URLs, marqueurs de plateformes et empreintes, pas un algorithme à réécrire.
Les fichiers `__MACOSX/._*` et `.DS_Store` sont des métadonnées macOS, exclus
de la livraison ; ce ne sont pas des modules du programme.

## Chaque fichier original et sa destination

| Original | Ce qu'il fait réellement | Nouvelle destination |
|---|---|---|
| `src/__main__.py` | Lance Python Fire sur RagCLI | `src/__main__.py`, classe Commands |
| `src/__init__.py` | Déclare le package | Conservé, sans logique métier |
| `src/cli.py` | Valide les arguments, orchestre, lit/écrit le JSON et affiche | `cli.py`, `application/arguments.py`, `application/batches.py`, `infrastructure/json_store.py` |
| `src/models.py` | Huit contrats publics + Chunk et ScoredChunk | `domain/contracts.py`, Passage et RankedPassage |
| `src/corpus.py` | Filtre les extensions, calcule les chemins, cache les lectures | `documents/files.py` |
| `src/chunking.py` | Coupures récursives, AST, titres Markdown | `documents/intervals.py`, `python_code.py`, `markdown.py` |
| `src/text_processing.py` | Identifiants complets, sous-mots, stopwords, stemming | `retrieval/terms.py` |
| `src/bm25.py` | Prépare une matrice creuse de poids BM25 et la sauvegarde | `retrieval/lexical.py` |
| `src/indexer.py` | Collecte, tokenise, indexe, enregistre | `application/build.py`, `infrastructure/index_store.py` |
| `src/retriever.py` | Charge les index, classe, fusionne et traite les questions | `retrieval/search.py` |
| `src/generator.py` | Lit les preuves, construit un prompt et appelle Qwen | `generation/context.py`, `generation/local_model.py` |
| `src/embeddings.py` | Mean pooling, normalisation L2, index vectoriel optionnel | `retrieval/semantic.py` |
| `src/evaluation.py` | IoU et recall@k locaux | `application/assessment.py` |
| `tests/test_pipeline.py` | 11 tests de base | `tests/test_core.py`, 29 cas exécutés |
| `pyproject.toml` | Dépendances, Python, outils, source CPU de torch sur Linux | Conservé |
| `uv.lock` | Résolution reproductible des dépendances | Conservé, à gérer avec uv |
| `.python-version` | Version de développement choisie : 3.12 | Conservé |
| `.flake8` | Exclut corpus, caches et environnement du lint | Conservé |
| `.gitignore` | Exclut les données lourdes et fichiers temporaires | Conservé |
| `Makefile` | install/run/debug/clean/lint/test | Conservé avec nettoyage limité au code et aux caches |
| `README.md` | Installation, architecture, résultats annoncés | Réécrit avec les seules mesures vérifiées ici |
| `ARCHITECTURE.md` | Carte des appels de l'ancienne structure | Remplacé par ce guide |
| `MOULINETTE.md` | Documentation externe du correcteur | Procédure expliquée dans README ; pas d'import du correcteur |

## Lecture fonctionnelle du code original

### CLI et contrats

`guarded` entoure chaque commande et transforme les exceptions en message et
code de sortie. `functools.wraps` préserve la signature pour Fire. `as_int`
refuse notamment bool, qui est pourtant une sous-classe de int en Python.
`as_query` transforme les valeurs Fire en texte. `load_json_model` valide
le JSON. `save_json_model` sauvegarde un BaseModel. Chaque méthode de RagCLI
assemble ensuite les composants. Le problème principal ici est la combinaison
de nombreuses responsabilités dans le même module, pas l'existence de Fire.

`MinimalSource` localise un passage. `UnansweredQuestion` porte un UUID et une
question. `AnsweredQuestion` ajoute le corrigé. `RagDataset` accueille les deux.
`MinimalSearchResults` porte les sources trouvées et `MinimalAnswer` ajoute
la réponse générée. Les deux enveloppes Student ajoutent une liste et k.
`Chunk.context` est une métadonnée de classement, jamais du texte ajouté au
fichier d'origine. `ScoredChunk.score` est un score interne, pas une probabilité.

### Découpage

`_line_starts` construit les positions des débuts de ligne. `_trim` déplace
les bornes au lieu de modifier la chaîne. `_cut_points` trouve les séparateurs.
`_pack` rassemble des morceaux contigus tant qu'ils tiennent dans la limite.
`split_span` essaie successivement paragraphes, lignes et espaces, puis une
coupe stricte. `_finalize` applique ce travail et retire les morceaux vides.
`_merge_small` fusionne un petit morceau avec le suivant lorsque cela tient.

`chunk_markdown` maintient une pile de titres et suit les blocs délimités par
backticks ou tildes. Un `#` dans un bloc de code n'ouvre pas une section.
`chunk_python` utilise l'AST, inclut les décorateurs et les commentaires
immédiatement précédents, puis subdivise les grandes classes en méthodes.
Le repli sur du texte simple évite de perdre un fichier avec erreur de syntaxe.

### Indexation et recherche

`expand_word` garde l'identifiant composé et stemme ses composants utiles.
Le stemming rapproche par exemple des variantes grammaticales anglaises.
Le cache LRU évite de recalculer les mêmes transformations.
`BM25Index.build` compte les termes, calcule les longueurs et df, puis prépare
les contributions BM25. CSR facilite la construction par documents ; CSC
facilite la sélection des colonnes correspondant aux termes de la question.
`score` multiplie ces colonnes par les fréquences de la requête.

`Indexer.collect_chunks` ajoute le chemin et le contexte au texte indexé.
Ces mots supplémentaires aident à reconnaître une classe ou un module.
`Indexer.build` prépare toujours BM25, et les embeddings sur demande.
`save_chunks` utilise des colonnes compactes ; `load_chunks` reconstruit
les objets, mais sans validation avec `model_construct` et avec zip, qui peut
tronquer silencieusement des colonnes de tailles différentes.

`top_k` filtre les scores positifs. `argpartition` ne garantit pas un ordre
stable parmi les ex æquo à la frontière. `fuse_scores` normalise les meilleurs
scores de chaque moteur, puis applique 1.0 à BM25 et 0.25 au sémantique.
Le coefficient 0.25 est repris de l'original ; il n'a pas été réoptimisé ici.

### Génération et embeddings

`AnswerGenerator.load` charge le modèle tardivement. `build_context` lit les
sources et leur réserve un budget. Le coût fixe de 32 tokens pour les en-têtes
n'est pas une mesure réelle ; si le budget restant tombe sous 32, la tranche
`ids[:budget - 32]` devient négative. En Python une tranche négative garde
presque toute la liste au lieu de rendre une liste vide.
`build_messages` construit system/user. `answer` applique le template Qwen,
génère sous inference_mode et décode uniquement les tokens ajoutés.

`SentenceEncoder.encode` transforme des lots de textes en états de tokens,
ignore le padding grâce à attention_mask, calcule une moyenne et normalise
chaque vecteur. `SemanticIndex` stocke ces vecteurs, encode la question avec
le même modèle et calcule les produits scalaires. Les vecteurs stockés en
float16 sont rechargés en float32. Leur précision est donc légèrement réduite.

### Évaluation et tests

L'évaluation compare les chemins et l'IoU. Chaque source attendue compte au
maximum une fois, même si plusieurs résultats la recouvrent. Une question
sans prédiction compte zéro. Les tests originaux vérifient découpage,
tokenisation, BM25, fusion et chevauchement, mais pas le budget du prompt,
les JSON corrompus ni la sauvegarde des commandes individuelles.

## Corrections et limites identifiées

| Observation originale | Traitement dans cette version |
|---|---|
| search/answer affichent seulement, --as_json imprime un objet isolé | Toujours sauvegarder une enveloppe Student complète ; --output_path configurable |
| Bornes négatives/inversées acceptées par les types simples | Validateurs Pydantic explicites |
| SourceReader corrige silencieusement des indices négatifs | Références invalides refusées ; fin hors fichier refusée |
| Union Answered/Unanswered peut ignorer un corrigé mal formé | Prévalidation des entrées contenant answer ou sources |
| Chargement compact sans validation | Manifeste versionné avec liste de Passage validés |
| Budget de contexte estimé, tranches négatives possibles | Comptage du prompt formaté complet et préfixes positifs |
| Ex æquo dépendants d'argpartition | Tri déterministe par score, puis position du passage |
| « Student data is valid » basé seulement sur la longueur | Rapport explicitement local, sans certification officielle |
| README annonce des résultats moulinette et des temps | Nouvelles mesures locales, limites des tests clairement indiquées |

La nouvelle règle d'ex æquo change certains rangs 1 et 3. Pour ta question MoE,
NaiveBatchedExperts arrive désormais avant BatchedTritonExperts, à score égal
36.43 ; la région attendue reste deuxième. Le recall@5 global reste 0.89 docs
et 86/99 pour le code. Ce changement est documenté, pas masqué.

## Une structure par responsabilité

| Dossier | Question à laquelle il répond |
|---|---|
| domain | Quelles données circulent et quelles contraintes doivent-elles respecter ? |
| documents | Comment lire un fichier et découper son texte sans perdre ses positions ? |
| retrieval | Comment représenter la recherche et classer les passages ? |
| generation | Comment former un prompt et obtenir une réponse locale ? |
| infrastructure | Comment lire/écrire JSON et index de façon vérifiable ? |
| application | Comment assembler les étapes pour une commande ou un dataset ? |

Les champs imposés (`question_id`, `file_path`, `retrieved_sources`, etc.) et
les six noms de commandes restent identiques. Des noms internes changent :
RagCLI → Commands, Chunk → Passage, ScoredChunk → RankedPassage,
BM25Index → LexicalMatrix, Retriever → SearchEngine,
AnswerGenerator → LocalResponder, context → breadcrumb, score → relevance.

## Ce qui n'est pas implémenté ou certifié

Cette version garde le sémantique et l'hybride optionnels de l'original.
Elle n'ajoute pas les bonus API HTTP, indexation incrémentale ou cache complet
de résultats. Le cache des fichiers et du stemming ne prouve pas à lui seul
le bonus de cache complet.

Le corpus n'est pas figé par un hash. Il faut réindexer après modification
ou déplacement. La lecture des sources reste celle de fichiers locaux de
confiance ; ce programme n'est pas une API publique acceptant des chemins
arbitraires. Les écritures JSON sont atomiques fichier par fichier, mais
l'indexation concurrente avec une recherche n'est pas prise en charge.

Le seuil local est IoU >= 0.05 comme dans ton code original. Le PDF comporte
une nuance entre son schéma et sa prose à l'égalité : seul le correcteur
fourni permettra de confirmer ce cas frontière. Il n'est pas joint.
