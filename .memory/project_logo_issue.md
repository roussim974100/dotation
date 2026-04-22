---
name: Logo collectivité — corrigé
description: Logo ville absent de login.html — corrigé en commit ae21c1a
type: project
---

**Corrigé** (commit ae21c1a). `login.html` avait le panneau gauche sans `data-brand-logo`.
Fix : structure alignée sur `signup.html` — ajout `.app-brand.app-brand--login` avec `.app-logo--login[data-brand-logo]`.

Les 3 pages (`login.html`, `signup.html`, `index.html`) chargent maintenant le logo ville via `branding.js`.
