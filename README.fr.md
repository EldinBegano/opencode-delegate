# opencode-delegate

[English](README.md) | [Français](README.fr.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

Une compétence [Claude Code](https://claude.com/claude-code) qui confie le travail ingrat et peu exigeant en jugement à des modèles [opencode](https://opencode.ai) gratuits, pour que votre quota Claude serve aux parties qui en ont besoin.

Claude garde le contrôle. Il décide quoi déléguer, rédige le prompt, lance le modèle gratuit via un worker cloisonné, puis relit le diff et exécute les tests lui-même.

![Claude Code loading the skill, delegating 33 docstrings to a free model with the tests as the check, then reviewing the diff](docs/demo.gif)

Une vraie session Claude Code sur le fixture de benchmark, temps d'attente coupés. Elle a coûté $0.31 d'usage Claude. La même tâche coûtait en moyenne $0.63 sans la compétence.

## Ce que vous obtenez

- **`skill/SKILL.md`** : indique à Claude quand déléguer (code passe-partout, tests, docs, fixtures, modifications sur plusieurs fichiers), quand ne pas le faire (conception, bugs délicats, sécurité) et comment relire le résultat.
- **`bin/oc-delegate`** : exécute le worker avec une chaîne de repli de modèles gratuits. Si un modèle échoue ou se bloque, seuls les fichiers qu'il a modifiés sont annulés et le modèle suivant est essayé. Vos propres modifications non commitées sont laissées intactes.
- **`opencode/cc-worker.md`** : un agent opencode verrouillé. Il peut lire et modifier les fichiers du dépôt, et rien d'autre : pas de shell, pas de web, pas de `.git`, `.env*`, clés ni fichiers d'identifiants.
- **`claude-md-snippet.md`** : une section `CLAUDE.md` qui fait de la délégation le comportement par défaut de Claude pour le travail ingrat. Sans elle, Claude choisit rarement la compétence de lui-même.

## Prérequis

| Besoin | Notes |
| --- | --- |
| Claude Code | Toute version récente avec le support des compétences. |
| [opencode](https://opencode.ai) | Testé avec v2.0.32 et v2.1.3. Les modèles gratuits OpenCode Zen fonctionnent sans clé API. |
| `bash`, `git`, `jq` | |
| GNU coreutils | Linux les fournit. Sur macOS, installez `coreutils` avec Homebrew et placez son répertoire `gnubin` en tête du `PATH`. |
| `~/.local/bin` sur `PATH` | Où l'installateur place `oc-delegate`. |
| `bwrap` (optionnel, Linux) | [bubblewrap](https://github.com/containers/bubblewrap) cloisonne les écritures de fichiers du worker dans le dépôt. Recommandé. |

Installez opencode si vous ne l'avez pas, puis vérifiez qu'il liste des modèles gratuits :

```sh
curl -fsSL https://opencode.ai/install | bash
opencode models | grep -E -- '-free|big-pickle'
```

## Installation

### Laisser Claude Code le faire

Collez ceci dans Claude Code :

```text
Installez la compétence opencode-delegate depuis https://github.com/EldinBegano/opencode-delegate pour moi.

1. Vérifiez les prérequis dans son README : bash, git, jq, GNU coreutils et opencode. S'il manque quelque chose, indiquez-moi comment l'installer sur mon système et arrêtez-vous. N'installez pas vous-même de paquets système.
2. Clonez le dépôt dans ~/.local/share/opencode-delegate, ou faites git pull s'il y est déjà. Lisez install.sh, puis exécutez-le. S'il avertit que ~/.local/bin n'est pas dans le PATH, indiquez-moi la ligne à ajouter à ma configuration de shell.
3. Ajoutez "Bash(oc-delegate:*)" à permissions.allow dans ~/.claude/settings.json et conservez tout le reste de ce fichier. Si vous ne pouvez pas le modifier, montrez-moi le JSON exact à ajouter.
4. Ajoutez claude-md-snippet.md à la fin de ~/.claude/CLAUDE.md, sauf si ce fichier contient déjà une section "# opencode delegation".
5. Exécutez le test de fumée du README dans un dépôt git temporaire et montrez-moi la sortie d'oc-delegate et le diff git.
6. Résumez ce que vous avez modifié. N'approuvez aucun dépôt pour la délégation ; je répondrai lors de la première demande.
```

Démarrez une nouvelle session Claude Code ensuite pour que la compétence et la section `CLAUDE.md` se chargent.

### Manuellement

1. Clonez et installez :

   ```sh
   git clone https://github.com/EldinBegano/opencode-delegate.git
   cd opencode-delegate
   ./install.sh
   ```

   L'installateur crée des liens symboliques de la compétence, de l'agent worker et d'`oc-delegate` dans `~/.claude/skills/`, `~/.config/opencode/agents/` et `~/.local/bin/`, de sorte qu'un `git pull` les met à jour. Utilisez `./install.sh --copy` pour les copier à la place. Les fichiers existants qui diffèrent sont d'abord sauvegardés.

2. Permettez à Claude d'exécuter le wrapper sans demander à chaque fois. Ajoutez ceci à `~/.claude/settings.json`, en le fusionnant dans votre liste `permissions.allow` existante :

   ```json
   {
     "permissions": {
       "allow": ["Bash(oc-delegate:*)"]
     }
   }
   ```

3. Collez [`claude-md-snippet.md`](claude-md-snippet.md) dans `~/.claude/CLAUDE.md`. Ne sautez pas cette étape : avec seulement la compétence installée, Claude a tendance à écrire le travail ingrat lui-même. L'extrait conserve une liste des dépôts que vous avez approuvés pour les modèles gratuits. Claude vous demande une fois avant la première délégation dans un nouveau dépôt.

4. Test de fumée :

   ```sh
   tmp=$(mktemp -d) && cd "$tmp" && git init -q
   printf 'a\nb\n' > list.txt && git add . && git commit -qm init
   oc-delegate "Append a line containing exactly 'c' to list.txt. Change no other file."
   git diff
   ```

   Vous devriez voir `model: opencode/...`, `M list.txt` et un diff qui ajoute `c`.

## Utilisation

La plupart du temps, vous n'appelez rien. Claude délègue les gros travaux ingrats, comme les docstrings ou les tests sur plusieurs modules, et vous dit ce que le modèle gratuit a fait et ce qu'il a vérifié. Les petits travaux restent volontairement à Claude, car les déléguer coûte plus qu'ils ne rapportent.

Pour forcer, dites "delegate this", "use opencode" ou "use the free model", ou tapez `/opencode-delegate`.

Vous pouvez aussi exécuter le wrapper vous-même dans n'importe quel dépôt git :

```sh
oc-delegate "task"                                       # default model chain
oc-delegate -m opencode/deepseek-v4.1-flash-free "task"   # one model, no fallback
oc-delegate -c "pytest -q" "task"                        # run a check after the worker
```

Avec `-c`, un check en échec est renvoyé au worker pour correction, jusqu'à `-r` fois (2 par défaut). S'il échoue encore, les modifications de ce modèle sont annulées et le modèle suivant est essayé. Si le check échoue déjà avant l'exécution, il est ignoré.

### Paramètres

| Variable | Défaut | Effet |
| --- | --- | --- |
| `OC_DELEGATE_MODELS` | la chaîne ci-dessous | Chaîne de modèles séparés par des espaces, utilisée en l'absence de `-m`. |
| `OC_DELEGATE_TIMEOUT` | `300` | Secondes avant qu'une exécution de modèle soit tuée et que le modèle suivant soit essayé. |
| `OC_DELEGATE_IDLE` | `180` | Secondes sans sortie ni trafic réseau avant qu'un modèle soit considéré comme bloqué. |
| `OC_DELEGATE_TOTAL` | `540` | Secondes pour toute l'exécution. Gardez-la sous le timeout Bash de 600 s de Claude Code. |
| `OC_DELEGATE_CHECK` | aucune | Commande de vérification, utilisée en l'absence de `-c`. |
| `OC_DELEGATE_RETRIES` | `2` | Nouvelles tentatives de vérification par modèle, utilisées en l'absence de `-r`. |
| `OC_DELEGATE_CHECK_TIMEOUT` | `120` | Secondes par exécution de vérification. |
| `OC_DELEGATE_SANDBOX` | `1` | Mettez à `0` pour exécuter sans `bwrap`. |
| `OC_DELEGATE_TAIL` | `40` | Lignes du résumé du worker à afficher. |
| `OC_DELEGATE_LOG` | `~/.local/state/oc-delegate.log` | Journal de chaque tentative de modèle. Consultez-le avec `column -ts$'\t' ~/.local/state/oc-delegate.log`. |

### Modèles

La chaîne par défaut est `beam-free` → `deepseek-v4.1-flash-free` → `space-bunny-free` → `mimo-v2.6-flash-free` → `big-pickle`, toutes sous `opencode/`. La gamme gratuite change souvent. Si ces modèles deviennent obsolètes, vérifiez avec `opencode models | grep free` et définissez `OC_DELEGATE_MODELS`. Comment l'ordre a été choisi : [docs/development.md](docs/development.md#model-choice).

## Confidentialité et sécurité

- **Les modèles gratuits peuvent journaliser vos prompts et les utiliser pour l'entraînement.** Tout ce que le worker lit dans le dépôt est envoyé à ce fournisseur. Ne déléguez pas dans des dépôts confidentiels.
- La liste de refus du worker ne porte que sur les noms de fichiers. Un secret dans `config.yaml` reste lisible.
- Le worker ne peut pas toucher à `.git`. Avec `bwrap`, `.git` est aussi monté en lecture seule.
- Le worker peut modifier des fichiers ignorés par git, que `git diff` n'affiche pas. Le wrapper les liste sous `not in git diff`.
- Le worker ne peut pas exécuter de tests ni de builds. Claude vérifie le résultat.
- Ne mettez pas de secrets dans les prompts de tâche.

## Développement

Lancez `bats test` (pas de réseau, environ une minute). Les tests, le benchmark de modèles et les évaluations de compétence sont décrits dans [docs/development.md](docs/development.md).

## Désinstallation

```sh
rm ~/.claude/skills/opencode-delegate/SKILL.md ~/.config/opencode/agents/cc-worker.md ~/.local/bin/oc-delegate
rmdir ~/.claude/skills/opencode-delegate
```

Supprimez ensuite la règle de permission et la section `CLAUDE.md`.

## Licence

[MIT](LICENSE)
