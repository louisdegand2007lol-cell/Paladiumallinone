# Paladium Desktop — Fixed Windows Build

## Build automatique (Windows)
1) Pousse ce repo sur GitHub (branche `main`).
2) Onglet **Actions** → Workflow **build-windows** → **Run workflow**.
3) En fin de run (✅), récupère les **Artifacts** :
   - `dist/PaladiumDesktop/**` (version **ONEDIR** prête à lancer)
   - `Output/PaladiumDesktop-Setup.exe` (installeur, ONEDIR)

## Pourquoi ONEDIR ?
PyQt6/Qt6 nécessite beaucoup de DLL/plugins. ONEDIR est la méthode la plus robuste.
Le workflow peut être étendu pour ONEFILE si besoin (ajoute un step similaire en `--onefile`).

## Exécuter
- Portable : `dist/PaladiumDesktop/PaladiumDesktop.exe`
- Installeur : `Output/PaladiumDesktop-Setup.exe`

## Dépendances runtime
- Aucune. Toutes les DLL Qt sont incluses via `--collect-all`.
