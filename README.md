# HENO — Meeting Assistant

HENO est un copilote de réunion Windows, local-first et open source. Il écoute le microphone et/ou le son de l'ordinateur, transcrit en direct avec Whisper local, détecte les questions, puis propose une réponse via le compte ChatGPT connecté. Si ChatGPT n'est pas connecté, HENO peut utiliser Ollama comme moteur IA local.

## V1 incluse

- Transcription locale en français avec `faster-whisper`
- Capture microphone
- Capture du son système Windows (Teams, Meet, Zoom, navigateur, etc.)
- Détection automatique des questions
- Suggestions de réponse en direct
- Connexion officielle **Continue with ChatGPT** via OAuth/PKCE, sans clé API
- Secours local avec Ollama
- Ajout de documents de contexte : PDF, DOCX, XLSX/XLSM, TXT, MD, CSV
- Recherche locale de passages pertinents dans les documents
- Compte rendu automatique
- Export Word
- Stockage local des réglages
- Jetons ChatGPT conservés via le gestionnaire d'identifiants du système avec `keyring`

## 1. Installation Windows la plus simple

### Prérequis

Installez **Python 3.11** depuis python.org. Pendant l'installation, cochez l'option qui ajoute Python au PATH si elle est proposée.

### Installer HENO

1. Décompressez le dossier HENO.
2. Double-cliquez sur `install_windows.bat`.
3. Une fois l'installation terminée, double-cliquez sur `run_windows.bat`.

Au premier démarrage d'une réunion, Whisper télécharge le modèle choisi. Le modèle `base` est sélectionné par défaut pour équilibrer vitesse et précision.

## 2. Connecter votre compte ChatGPT

1. Ouvrez HENO.
2. Cliquez sur **Continuer avec ChatGPT**.
3. Votre navigateur s'ouvre sur la page officielle OpenAI.
4. Choisissez votre compte ChatGPT.
5. Autorisez HENO à utiliser les fonctionnalités demandées.
6. Revenez dans HENO.

HENO utilise le flux officiel OpenAI pour les applications open source locales. Aucun mot de passe ChatGPT n'est demandé par HENO et aucune clé API n'est nécessaire.

La connexion ne donne pas à HENO l'accès à vos anciennes conversations ChatGPT.

## 3. Utiliser HENO pendant une réunion

### Réunion Teams / Google Meet / Zoom

Laissez cochés :

- `Microphone`
- `Son de l'ordinateur`

Puis cliquez sur **Démarrer la réunion**.

### Réunion physique dans une salle

Vous pouvez garder uniquement `Microphone`. HENO détecte les questions dans le son capté par le microphone.

### Documents de contexte

Avant la réunion, cliquez sur **Ajouter des documents** puis sélectionnez les TDR, budgets, rapports, comptes rendus ou autres documents utiles.

Quand une question est détectée, HENO recherche d'abord les passages les plus pertinents dans ces fichiers et les fournit au moteur IA comme contexte.

## 4. Générer le compte rendu

Après la réunion :

1. Cliquez sur **Arrêter la réunion**.
2. Cliquez sur **Générer le compte rendu**.
3. Cliquez sur **Exporter Word**.

Le fichier Word contient la synthèse et la transcription disponible.

## 5. Mode totalement local avec Ollama

HENO peut fonctionner sans ChatGPT pour les réponses si Ollama est installé.

Installez Ollama, puis installez un modèle local, par exemple un modèle Qwen ou Gemma adapté à votre ordinateur. HENO détecte automatiquement les modèles exposés par Ollama sur `http://127.0.0.1:11434`.

La transcription reste locale dans tous les cas.

## 6. Construire l'application Windows

Après installation des dépendances, lancez :

```bat
build_windows.bat
```

Le résultat est créé dans :

```text
dist\HENO-Meeting-Assistant\
```

L'exécutable principal est :

```text
HENO-Meeting-Assistant.exe
```

## 7. Déploiement gratuit avec GitHub Actions

Le dépôt contient déjà `.github/workflows/build-windows.yml`.

### Créer le dépôt

1. Sur GitHub, créez un nouveau dépôt **public** nommé `HENO-Meeting-Assistant`.
2. Choisissez une licence MIT ou conservez le fichier `LICENSE` fourni.
3. Téléversez tous les fichiers de ce projet dans le dépôt.
4. Ouvrez l'onglet **Actions**.
5. Sélectionnez **Build HENO for Windows**.
6. Cliquez sur **Run workflow**.

À la fin du build, GitHub fournit `HENO-Meeting-Assistant-Windows.zip` comme artefact téléchargeable.

### Publier une version

Créez un tag, par exemple :

```bash
git tag v0.1.0
git push origin v0.1.0
```

Le workflow construit HENO et crée automatiquement une Release GitHub avec le ZIP Windows.

## 8. Confidentialité

- La transcription Whisper est exécutée localement.
- Les documents restent locaux ; seuls les extraits utiles peuvent être inclus dans la requête envoyée à ChatGPT quand ce mode est activé.
- En mode Ollama, le traitement de réponse peut également rester entièrement local.
- HENO ne doit pas enregistrer une réunion à l'insu des participants. Informez les participants et respectez les règles de consentement applicables à votre réunion et à votre juridiction.

## 9. Limites de la V1

- La séparation précise des différents intervenants n'est pas encore incluse.
- Sur certains PC Windows, la capture du son système peut dépendre du pilote audio utilisé.
- La vitesse de Whisper dépend fortement du processeur.
- Les modèles Whisper plus grands améliorent généralement la précision mais sont plus lourds.
- Le flux `Continue with ChatGPT` dépend de l'éligibilité du compte et des limites d'usage du plan ChatGPT.

## Architecture

```text
Microphone ─────┐
                ├──> Audio local ──> Whisper local ──> Transcription
Son système ────┘                                │
                                                 ├──> Détection de question
Documents locaux ──> Recherche de contexte ─────┤
                                                 │
                          ChatGPT ou Ollama <────┘
                                  │
                                  └──> Réponse suggérée / Compte rendu
```

## Licence

MIT.
