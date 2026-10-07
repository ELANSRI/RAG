# Comprendre et exécuter la nouvelle version

Tu as demandé une lecture fichier par fichier, une autre structure, des noms
plus explicites et le code expliqué ligne par ligne. Cette archive contient
le code exécutable dans src, l'analyse de l'original dans
01_ANALYSE_ET_STRUCTURE.md et la lecture de chaque ligne dans
02_CODE_LIGNE_PAR_LIGNE.md. Le guide HTML réunit les mêmes explications.

## Installer sans écraser ton travail

Extrais cette archive dans un nouveau dossier, par exemple `~/RAG-v2`.
Copie ton corpus vers `data/raw/vllm-0.10.1/` et tes datasets vers
`data/datasets/AnsweredQuestions/` et `data/datasets/UnansweredQuestions/`.
Les datasets de l'archive d'origine se trouvent sous `datasets_public/public/`.
Le corpus, les poids et les index ne sont pas inclus dans la nouvelle archive.

Depuis la racine de la nouvelle version :

```bash
uv sync
uv run python -m src index --max_chunk_size 2000
uv run python -m src search \
  "What activation formats does the fused batched MoE layer return in vLLM?" \
  --k 5
uv run python -m src answer \
  "What activation formats does the fused batched MoE layer return in vLLM?" \
  --k 5
```

`search` enregistre `data/output/single/search.json`.
`answer` enregistre `data/output/single/answer.json`.
Ces noms sont configurables via `--output_path`. La prochaine exécution avec
le même chemin remplace le fichier ; change le chemin pour garder plusieurs
expériences. Les anciens index ne sont pas compatibles : reconstruis-les.

## Un exemple réel, étape par étape

La question MoE est une entrée du dataset code public. Son corrigé attend
une source dans `vllm/model_executor/layers/fused_moe/fused_batched_moe.py`,
aux caractères 28416 à 28975. Le moteur ne lit pas ce corrigé pour chercher.

1. `__main__.py` appelle Fire avec `Commands`. Fire transforme le terminal
   en appel `Commands.search(query=..., k=5)`.
2. `query_text` refuse une question vide. `positive_integer` valide k.
3. `SearchEngine` ouvre manifest.json, lexical.npz et vocabulary.json.
4. `lexical_terms` transforme `activation_formats` en identifiant complet
   et composants stemmés. Les mêmes règles ont servi pendant l'indexation.
5. `LexicalMatrix.scores_for` sélectionne les colonnes pertinentes et additionne
   leurs contributions BM25. Chaque ligne représente un passage.
6. `best_positions` ordonne les scores positifs. En cas d'égalité, l'ordre
   des passages dans l'index sert de second critère reproductible.
7. Les passages deviennent des `MinimalSource` : chemin, début, fin.
8. `StudentSearchResults` valide et enveloppe la liste avec k.
9. `write_record` produit un fichier temporaire puis le remplace atomiquement.
10. Pour `answer`, les mêmes sources vont dans `LocalResponder`.
11. `PassageReader` extrait les chaînes originales. `ContextComposer` ajoute
    consignes, numéros des sources et question, puis mesure le prompt complet.
12. Le tokenizer de Qwen transforme ce prompt en identifiants numériques.
13. Le modèle génère des tokens ; seuls les nouveaux tokens sont décodés.
14. `MinimalAnswer` associe cette chaîne aux sources du moteur.
15. `StudentSearchResultsAndAnswer` est écrit dans answer.json.

Sur l'exécution mesurée ici, le passage attendu [28416:28660] est au rang 2.
Il est inclus dans la référence [28416:28975], et son IoU vaut 244/559.
Cette information illustre le rappel, pas une exécution réelle de Qwen ici.
La réponse de référence précise un tuple de deux BatchedExperts.

## Les concepts à comprendre dans cet ordre

### Chaîne, positions et passage

Un fichier lu devient un str. `[a:b]` extrait les caractères a inclus à b
exclu. Avec `texte = "Bonjour"`, `texte[0:3]` vaut `"Bon"`. Le passage
conserve ses positions dans la chaîne originale. Il ne faut pas mesurer
les positions sur une version nettoyée ni sur les octets UTF-8.

### AST

`ast.parse` construit une représentation syntaxique du code Python sans
l'exécuter. Les objets ClassDef, FunctionDef et AsyncFunctionDef indiquent
les classes et fonctions. Le programme exploite leurs numéros de ligne,
convertis en positions de caractères. Les commentaires n'étant pas des nœuds
AST ordinaires, une logique séparée récupère les commentaires précédents.

### Récursion et séparation

Un bloc trop grand est d'abord découpé aux lignes vides. Les morceaux encore
trop grands sont découpés aux lignes, puis aux espaces. La récursion utilise
une liste de séparateurs de plus en plus courte : elle termine donc. Quand
aucun séparateur ne convient, des tranches strictes garantissent la limite.

### Tokenisation lexicale et stemming

La tokenisation extrait des mots et des identifiants. La séparation snake_case
et camelCase permet de rapprocher une question en anglais et du code. Le
stemming ramène certaines variations grammaticales à une racine. La suppression
des stopwords réduit le bruit, mais peut aussi perdre une nuance comme une
négation : le moteur lexical n'est pas un interprète complet du langage.

### BM25, matrice creuse et requête

`tf` compte un terme dans un passage. `df` compte les passages qui contiennent
ce terme. `idf` augmente l'importance des termes rares. `saturation` limite
l'avantage de répéter un terme ; `length_weight` ajuste la pénalité de longueur.
Une matrice creuse stocke essentiellement les valeurs non nulles. Les poids
sont préparés à l'indexation et une question sélectionne seulement les colonnes
utiles. Le nombre retourné est un score de classement, pas une confiance en %.

### Top-k et égalités

k est le nombre maximal de sources retournées. k=0 est accepté et donne une
liste vide. Des scores égaux ne prouvent pas que les passages sont identiques.
Le tri utilise une seconde clé stable pour que deux exécutions aient le même
ordre. Une bonne source au rang 6 ne compte pas dans recall@5.

### Pydantic et validation

Les annotations décrivent les types. Pydantic valide les objets reçus ou lus
sur disque à l'exécution. Les validators vérifient aussi des relations :
fin > début, identifiants uniques, nombre de sources <= k. Les annotations
seules n'effectuent pas ces contrôles. Mypy analyse le code sans le faire tourner.

### Union de modèles

Un dataset peut contenir AnsweredQuestion ou UnansweredQuestion. Sans garde,
une entrée corrigée invalide peut être acceptée comme question simple après
abandon des champs supplémentaires. La nouvelle prévalidation reconnaît les
champs answer/sources et impose alors le modèle corrigé.

### Prompt, tokens et génération

La query est seulement la question. Le prompt complet contient consignes,
question, extraits et format du chat. Le tokenizer du modèle n'est pas celui
de BM25. La fenêtre du modèle doit accueillir l'entrée et la sortie réservée.
On compte le template réel, pas une estimation fixe par source. Le budget
`max_context_tokens` couvre ici l'ajout formaté des sources ; question et
consignes sont aussi contrôlées contre la capacité totale du modèle.

### Chargement tardif et inférence

Le modèle est chargé seulement quand des preuves doivent être exploitées.
Cela garde index/search indépendants du coût mémoire de Qwen. `eval()` choisit
le comportement d'évaluation et `inference_mode()` évite les calculs de gradients.
La génération ne réentraîne pas les poids. Une réponse vide ou sans source est
traitée explicitement. Aucun appel réseau vers un service de génération n'est
nécessaire, mais les premiers téléchargements de poids peuvent utiliser le réseau.

### JSON, sérialisation et écriture atomique

`model_dump_json` transforme un modèle en texte JSON. Le fichier temporaire
est écrit complètement avant `os.replace`. Ainsi un lecteur n'obtient pas un
JSON à moitié écrit. Une erreur empêche la publication du fichier final et
le finally supprime le temporaire restant.

### Embeddings optionnels

Un encodeur distinct de Qwen transforme chaque passage en vecteur. Le masque
ignore les tokens de padding, mean pooling moyenne les états des vrais tokens,
et la normalisation L2 donne des vecteurs de norme 1. Leur produit scalaire
représente alors une similarité cosinus, à l'erreur d'arrondi près. La fusion
hybride normalise les meilleurs scores lexicaux et sémantiques avant combinaison.
Ces deux options sont conservées mais leur inférence réelle n'a pas été testée ici.

## Lire les fichiers sans se perdre

Lis d'abord `domain/contracts.py`, puis `documents/files.py`, puis les trois
modules de découpage, `retrieval/terms.py`, `retrieval/lexical.py`,
`application/build.py` et `retrieval/search.py`. Ensuite seulement, lis
`generation/context.py`, `generation/local_model.py` et la CLI.
Le guide ligne par ligne fournit le code exact numéroté et les explications.

Le meilleur exercice est de suivre une seule question MoE en plaçant des points
d'arrêt : entrée CLI, tokens de recherche, indices du top-k, sources, prompt,
texte généré, puis JSON final. N'imprime pas les 25298 passages : inspecte les
cinq sélectionnés pour comprendre le parcours.
