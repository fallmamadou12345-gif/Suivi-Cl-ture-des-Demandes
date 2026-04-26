# 🚀 SynDongo Pro — Guide de Déploiement sur Render

## Architecture
```
syndongo-app/
├── backend/
│   ├── main.py          # API FastAPI (Python)
│   └── requirements.txt
├── frontend/
│   └── index.html       # SPA complète
└── render.yaml          # Config déploiement
```

---

## Étape 1 — Préparer le code sur GitHub

1. Créez un repo GitHub : https://github.com/new
   - Nom : `syndongo-callcenter`
   - Visibilité : Privé (recommandé)

2. Uploadez les fichiers :
   ```
   syndongo-app/
   ├── backend/main.py
   ├── backend/requirements.txt
   ├── frontend/index.html
   └── render.yaml
   ```

---

## Étape 2 — Déployer le Backend (API)

1. Allez sur https://render.com → New → **Web Service**
2. Connectez votre repo GitHub
3. Configuration :
   - **Name** : `syndongo-api`
   - **Root Directory** : `backend`
   - **Runtime** : Python 3
   - **Build Command** : `pip install -r requirements.txt`
   - **Start Command** : `python main.py`
4. Environment Variables :
   - `JWT_SECRET` = (générer une valeur aléatoire)
   - `DB_PATH` = `/opt/render/project/src/syndongo.db`
   - `PORT` = `8000`
5. **Add Disk** :
   - Name : `syndongo-data`
   - Mount Path : `/opt/render/project/src`
   - Size : 1 GB
6. Cliquez **Deploy**

⏱ Attendre ~2 minutes. Notez l'URL : `https://syndongo-api.onrender.com`

---

## Étape 3 — Configurer l'URL API dans le Frontend

Dans `frontend/index.html`, ligne ~430, modifiez :
```javascript
const API = 'https://syndongo-api.onrender.com';  // ← Votre vraie URL ici
```

---

## Étape 4 — Déployer le Frontend (Site Statique)

1. Render → New → **Static Site**
2. Connectez le même repo
3. Configuration :
   - **Name** : `syndongo-app`
   - **Root Directory** : `frontend`
   - **Publish Directory** : `.`
4. Cliquez **Deploy**

URL finale : `https://syndongo-app.onrender.com`

---

## Comptes par défaut

| Rôle | Email | Mot de passe |
|------|-------|-------------|
| 👑 Directeur | directeur@syndongo.sn | Admin2025! |
| 🔰 Superviseur | superviseur@syndongo.sn | Super2025! |
| 👤 Agent | amadou@syndongo.sn | Agent2025! |
| 👤 Agent | fatou@syndongo.sn | Agent2025! |
| 🔧 Garage Xelcom | garage@xelcom.sn | Garage2025! |

---

## Accès par rôle

### 👑 Directeur (contrôle total)
- Voir TOUS les tickets de tous les agents
- Créer/modifier/désactiver des comptes
- Analytics globale
- Recevoir toutes les alertes urgences + blocages

### 🔰 Superviseur
- Voir tous les tickets
- Créer des comptes agents
- Voir les performances de chaque agent
- Recevoir alertes urgences + blocages
- Réassigner des tickets

### 👤 Agent
- Voir et gérer UNIQUEMENT ses propres tickets
- Créer des tickets post-appel
- Escalader vers superviseur/FM/Garage
- Voir l'historique de ses tickets non résolus

### 🔧 Garage Xelcom
- Voir uniquement les tickets PANNE
- Ajouter des notes d'intervention
- Mettre à jour le statut (En cours → Résolu)

---

## Fonctionnalités clés

### Cycle de vie ticket
```
Nouveau → En cours → Escaladé → Résolu → Clôturé
```

### Routage automatique des alertes
- 🔴 URGENCE → Notification Directeur + Superviseur
- 🟡 PANNE → Notification Garage Xelcom
- 🟠 BLOCAGE → Notification Directeur + Superviseur

### Suivi non-résolu
- Dashboard agent : section dédiée aux tickets non résolus
- Indicateur couleur durée : Vert (<30min) / Jaune (<2h) / Rouge (>2h)
- Badges en temps réel dans la sidebar

### Sécurité
- JWT tokens (expiration 12h)
- Hachage SHA-256 des mots de passe
- Isolation des données par rôle (agents ne voient que leurs tickets)
- Routes protégées par rôle côté API

---

## Test en local (optionnel)

```bash
cd backend
pip install -r requirements.txt
python main.py
# API sur http://localhost:8000

# Frontend : ouvrir frontend/index.html dans le navigateur
# Changer const API = 'http://localhost:8000'
```
