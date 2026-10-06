# Confidentialité — HENO Meeting Assistant

HENO est conçu comme une application local-first.

- L'audio est traité localement pour la transcription.
- HENO ne crée pas, dans cette V1, d'archive audio permanente de la réunion.
- La transcription reste en mémoire pendant la session et n'est exportée que lorsque l'utilisateur choisit explicitement d'enregistrer un compte rendu Word.
- Les documents de contexte sont lus localement.
- Si l'utilisateur connecte ChatGPT, le texte nécessaire à la génération d'une réponse ou d'un compte rendu est envoyé à OpenAI via la connexion autorisée par l'utilisateur.
- Si l'utilisateur utilise Ollama, les réponses peuvent rester entièrement locales.
- Les jetons d'authentification sont stockés via le gestionnaire d'identifiants du système lorsque celui-ci est disponible.

L'utilisateur doit informer les participants avant toute capture ou transcription lorsqu'une telle information ou autorisation est requise.
