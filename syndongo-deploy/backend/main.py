from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
import sqlite3, hashlib, jwt, datetime, os, uuid, shutil, threading

app = FastAPI(title="SynDongo API v1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET = os.environ.get("JWT_SECRET", "syndongo-secret-2025")
DB = os.environ.get("DB_PATH", "syndongo.db")
security = HTTPBearer()

# ─── DATABASE ───
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        nom TEXT NOT NULL,
        prenom TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'agent',
        actif INTEGER DEFAULT 1,
        created_at TEXT,
        last_login TEXT
    );
    CREATE TABLE IF NOT EXISTS tickets (
        id TEXT PRIMARY KEY,
        numero INTEGER,
        driver_yango TEXT,
        driver_nom TEXT,
        driver_tel TEXT,
        driver_plaque TEXT,
        categorie TEXT,
        sous_categorie TEXT,
        alerte TEXT DEFAULT 'STD',
        priorite TEXT DEFAULT 'normale',
        statut TEXT DEFAULT 'Nouveau',
        notes TEXT,
        agent_id TEXT,
        superviseur_id TEXT,
        created_at TEXT,
        updated_at TEXT,
        resolved_at TEXT,
        FOREIGN KEY(agent_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS ticket_activity (
        id TEXT PRIMARY KEY,
        ticket_id TEXT,
        user_id TEXT,
        user_nom TEXT,
        type TEXT,
        contenu TEXT,
        created_at TEXT,
        FOREIGN KEY(ticket_id) REFERENCES tickets(id)
    );
    CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        titre TEXT,
        message TEXT,
        type TEXT,
        ticket_id TEXT,
        lu INTEGER DEFAULT 0,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS agent_history (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        modifie_par TEXT NOT NULL,
        modifie_par_nom TEXT,
        champ TEXT NOT NULL,
        ancienne_valeur TEXT,
        nouvelle_valeur TEXT,
        created_at TEXT,
        FOREIGN KEY(agent_id) REFERENCES users(id)
    );
    """)
    # Seed admin + demo accounts
    now = datetime.datetime.now(datetime.UTC).isoformat()
    accounts = [
        (str(uuid.uuid4()), "Ndongo", "Fall", "directeur@syndongo.sn", hash_pw("Admin2025!"), "directeur"),
        (str(uuid.uuid4()), "Sy", "Mamadou", "superviseur@syndongo.sn", hash_pw("Super2025!"), "superviseur"),
        (str(uuid.uuid4()), "Amadou", "Mbaye", "amadou@syndongo.sn", hash_pw("Agent2025!"), "agent"),
        (str(uuid.uuid4()), "Fatou", "Diallo", "fatou@syndongo.sn", hash_pw("Agent2025!"), "agent"),
        (str(uuid.uuid4()), "Oumar", "Seck", "oumar@syndongo.sn", hash_pw("Agent2025!"), "agent"),
    ]
    for acc in accounts:
        try:
            c.execute("INSERT INTO users (id,nom,prenom,email,password,role,actif,created_at) VALUES (?,?,?,?,?,?,1,?)",
                     (*acc, now))
        except: pass
    # Seed demo tickets
    seed_tickets(c, now)
    conn.commit()
    conn.close()

def seed_tickets(c, now):
    agents = c.execute("SELECT id FROM users WHERE role='agent'").fetchall()
    if not agents: return
    existing = c.execute("SELECT COUNT(*) as n FROM tickets").fetchone()['n']
    if existing > 0: return
    tickets = [
        ("TKT-2851","YNG-31445","Ibrahima Diop","+221779001234","DK-5521-A","Accident / Urgence","Collision circulation","URGENCE","critique","Escaladé","Accident à Ngor - blessures légères - FM alerté"),
        ("TKT-2849","YNG-41882","Cheikh Ndiaye","+221773334455","DK-1882-B","Panne / Véhicule","Panne moteur grave","PANNE","haute","En cours","Moteur calé au Plateau - véhicule immobilisé"),
        ("TKT-2847","YNG-38874","Moussa Thiam","+221775556677","DK-3874-C","Finance / Solde","Retrait Wave bloqué","BLOCAGE","haute","Escaladé","Solde Wave bloqué 85.000 FCFA - validation FM requise"),
        ("TKT-2846","YNG-22341","Abdou Diagne","+221778889900","DK-2341-D","App Yango","Déconnexion répétée","APPLICATION","normale","En cours","App Yango se déconnecte toutes les 10 minutes"),
        ("TKT-2845","YNG-61103","Ousmane Sarr","+221772223344","DK-6110-E","App Yango","GPS ne fonctionne pas","APPLICATION","normale","Résolu","GPS désactivé - réactivation paramètres OK"),
        ("TKT-2843","YNG-17723","El Hadji Sow","+221771112233","DK-1772-F","Blocage Compte","Suspension Yango","BLOCAGE","haute","Nouveau","Compte suspendu sans notification"),
        ("TKT-2840","YNG-44510","Amadou Ba","+221774445566","DK-4451-G","App Yango","Erreur score chauffeur","APPLICATION","normale","Résolu","Score incorrect - corrigé après signalement Yango"),
    ]
    agent_ids = [a['id'] for a in agents]
    for i, t in enumerate(tickets):
        tid = str(uuid.uuid4())
        c.execute("""INSERT INTO tickets 
            (id,numero,driver_yango,driver_nom,driver_tel,driver_plaque,categorie,sous_categorie,alerte,priorite,statut,notes,agent_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tid, 2851-i, t[1],t[2],t[3],t[4],t[5],t[6],t[7],t[8],t[9],t[10],
             agent_ids[i % len(agent_ids)], now, now))
        c.execute("""INSERT INTO ticket_activity (id,ticket_id,user_id,user_nom,type,contenu,created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), tid, agent_ids[i % len(agent_ids)], "Système","creation","Ticket créé", now))

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

# ─── AUTH ───
def make_token(user_id, role):
    payload = {"sub": user_id, "role": role, "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=12)}
    return jwt.encode(payload, SECRET, algorithm="HS256")

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id=?", (payload["sub"],)).fetchone()
        conn.close()
        if not user: raise HTTPException(status_code=401, detail="Utilisateur introuvable")
        return dict(user)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée")
    except:
        raise HTTPException(status_code=401, detail="Token invalide")

def require_role(*roles):
    def checker(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Accès refusé")
        return user
    return checker

# ─── MODELS ───
class LoginRequest(BaseModel):
    email: str
    password: str

class TicketCreate(BaseModel):
    driver_yango: str
    driver_nom: Optional[str] = ""
    driver_tel: Optional[str] = ""
    driver_plaque: Optional[str] = ""
    categorie: str
    sous_categorie: str
    alerte: str = "STD"
    priorite: str = "normale"
    notes: str = ""

class TicketUpdate(BaseModel):
    statut: Optional[str] = None
    priorite: Optional[str] = None
    alerte: Optional[str] = None
    superviseur_id: Optional[str] = None

class ActivityCreate(BaseModel):
    contenu: str
    type: str = "note"

class UserCreate(BaseModel):
    nom: str
    prenom: str
    email: str
    password: str
    role: str = "agent"

class UserUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    role: Optional[str] = None
    actif: Optional[int] = None
    password: Optional[str] = None

# ─── ENDPOINTS ───

@app.get("/")
def root(): return {"status": "SynDongo API v1.0", "docs": "/docs"}

@app.post("/auth/login")
def login(req: LoginRequest):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email=? AND password=? AND actif=1",
                        (req.email, hash_pw(req.password))).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    conn.execute("UPDATE users SET last_login=? WHERE id=?",
                (datetime.datetime.now(datetime.UTC).isoformat(), user["id"]))
    conn.commit()
    conn.close()
    token = make_token(user["id"], user["role"])
    return {"token": token, "user": {
        "id": user["id"], "nom": user["nom"], "prenom": user["prenom"],
        "email": user["email"], "role": user["role"]
    }}

@app.get("/me")
def get_me(user=Depends(get_current_user)): return user

# ── TICKETS ──

@app.get("/tickets")
def list_tickets(statut: Optional[str] = None, alerte: Optional[str] = None,
                 agent_id: Optional[str] = None, user=Depends(get_current_user)):
    conn = get_db()
    q = "SELECT t.*, u.nom||' '||u.prenom as agent_nom FROM tickets t LEFT JOIN users u ON t.agent_id=u.id WHERE 1=1"
    params = []
    # Agents see only their tickets
    if user["role"] == "agent":
        q += " AND t.agent_id=?"; params.append(user["id"])
    if statut: q += " AND t.statut=?"; params.append(statut)
    if alerte: q += " AND t.alerte=?"; params.append(alerte)
    if agent_id and user["role"] in ("superviseur","directeur"):
        q += " AND t.agent_id=?"; params.append(agent_id)
    q += " ORDER BY t.created_at DESC LIMIT 200"
    tickets = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return tickets

@app.get("/tickets/stats")
def ticket_stats(user=Depends(get_current_user)):
    conn = get_db()
    base = "" if user["role"] in ("superviseur","directeur") else f"WHERE agent_id='{user['id']}'"
    def count(where): return conn.execute(f"SELECT COUNT(*) as n FROM tickets {where}").fetchone()['n']
    stats = {
        "total": count(base),
        "nouveau": count(f"{base} {'AND' if base else 'WHERE'} statut='Nouveau'" if base else "WHERE statut='Nouveau'"),
        "en_cours": count(f"{base} {'AND' if base else 'WHERE'} statut='En cours'" if base else "WHERE statut='En cours'"),
        "escalade": count(f"{base} {'AND' if base else 'WHERE'} statut='Escaladé'" if base else "WHERE statut='Escaladé'"),
        "resolu": count(f"{base} {'AND' if base else 'WHERE'} statut='Résolu'" if base else "WHERE statut='Résolu'"),
        "cloture": count(f"{base} {'AND' if base else 'WHERE'} statut='Clôturé'" if base else "WHERE statut='Clôturé'"),
        "urgences": count("WHERE alerte='URGENCE' AND statut NOT IN ('Résolu','Clôturé')"),
        "pannes": count("WHERE alerte='PANNE' AND statut NOT IN ('Résolu','Clôturé')"),
    }
    conn.close()
    return stats

@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str, user=Depends(get_current_user)):
    conn = get_db()
    t = conn.execute("SELECT t.*, u.nom||' '||u.prenom as agent_nom FROM tickets t LEFT JOIN users u ON t.agent_id=u.id WHERE t.id=?", (ticket_id,)).fetchone()
    if not t: raise HTTPException(404, "Ticket introuvable")
    t = dict(t)
    if user["role"] == "agent" and t["agent_id"] != user["id"]:
        raise HTTPException(403, "Accès refusé")
    activity = [dict(a) for a in conn.execute(
        "SELECT * FROM ticket_activity WHERE ticket_id=? ORDER BY created_at ASC", (ticket_id,)).fetchall()]
    t["activity"] = activity
    conn.close()
    return t

@app.post("/tickets")
def create_ticket(req: TicketCreate, user=Depends(get_current_user)):
    conn = get_db()
    num = (conn.execute("SELECT MAX(numero) as m FROM tickets").fetchone()['m'] or 2800) + 1
    tid = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC).isoformat()
    conn.execute("""INSERT INTO tickets 
        (id,numero,driver_yango,driver_nom,driver_tel,driver_plaque,categorie,sous_categorie,alerte,priorite,statut,notes,agent_id,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (tid, num, req.driver_yango, req.driver_nom, req.driver_tel, req.driver_plaque,
         req.categorie, req.sous_categorie, req.alerte, req.priorite,
         "Escaladé" if req.alerte in ("URGENCE","BLOCAGE") else "Nouveau",
         req.notes, user["id"], now, now))
    conn.execute("INSERT INTO ticket_activity (id,ticket_id,user_id,user_nom,type,contenu,created_at) VALUES (?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), tid, user["id"], f"{user['prenom']} {user['nom']}", "creation",
         f"Ticket TKT-{num} créé — Alerte: {req.alerte}", now))
    # Auto notifications
    if req.alerte == "URGENCE":
        _notify_role(conn, "directeur", "superviseur", "🔴 URGENCE", f"Accident/Urgence signalé par {user['prenom']} {user['nom']}", tid, now)
    elif req.alerte == "PANNE":
        _notify_role(conn, "superviseur", "directeur", "🟡 Panne véhicule", f"Véhicule immobilisé — signalé par {user['prenom']} {user['nom']}", tid, now)
    elif req.alerte == "BLOCAGE":
        _notify_role(conn, "directeur", "superviseur", "🟠 Blocage compte", f"Validation financière requise", tid, now)
    conn.commit()
    conn.close()
    return {"id": tid, "numero": num, "message": f"Ticket TKT-{num} créé"}

@app.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: str, req: TicketUpdate, user=Depends(get_current_user)):
    conn = get_db()
    t = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    if not t: raise HTTPException(404)
    if user["role"] == "agent" and dict(t)["agent_id"] != user["id"]: raise HTTPException(403)
    now = datetime.datetime.now(datetime.UTC).isoformat()
    updates, params = [], []
    changes = []
    if req.statut:
        updates.append("statut=?"); params.append(req.statut)
        if req.statut in ("Résolu","Clôturé"):
            updates.append("resolved_at=?"); params.append(now)
        changes.append(f"Statut → {req.statut}")
    if req.priorite: updates.append("priorite=?"); params.append(req.priorite); changes.append(f"Priorité → {req.priorite}")
    if req.alerte: updates.append("alerte=?"); params.append(req.alerte); changes.append(f"Alerte → {req.alerte}")
    if req.superviseur_id and user["role"] in ("superviseur","directeur"):
        updates.append("superviseur_id=?"); params.append(req.superviseur_id)
    updates.append("updated_at=?"); params.append(now); params.append(ticket_id)
    conn.execute(f"UPDATE tickets SET {','.join(updates)} WHERE id=?", params)
    if changes:
        conn.execute("INSERT INTO ticket_activity (id,ticket_id,user_id,user_nom,type,contenu,created_at) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), ticket_id, user["id"], f"{user['prenom']} {user['nom']}", "update",
             " | ".join(changes), now))
    conn.commit(); conn.close()
    return {"message": "Mis à jour"}

@app.post("/tickets/{ticket_id}/activity")
def add_activity(ticket_id: str, req: ActivityCreate, user=Depends(get_current_user)):
    conn = get_db()
    t = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    if not t: raise HTTPException(404)
    if user["role"] == "agent" and dict(t)["agent_id"] != user["id"]: raise HTTPException(403)
    now = datetime.datetime.now(datetime.UTC).isoformat()
    conn.execute("INSERT INTO ticket_activity (id,ticket_id,user_id,user_nom,type,contenu,created_at) VALUES (?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), ticket_id, user["id"], f"{user['prenom']} {user['nom']}", req.type, req.contenu, now))
    conn.execute("UPDATE tickets SET updated_at=? WHERE id=?", (now, ticket_id))
    conn.commit(); conn.close()
    return {"message": "Activité ajoutée"}

# ── USERS ──

@app.get("/users")
def list_users(user=Depends(require_role("superviseur","directeur"))):
    conn = get_db()
    users = [dict(u) for u in conn.execute(
        "SELECT id,nom,prenom,email,role,actif,created_at,last_login FROM users ORDER BY role,nom").fetchall()]
    # Add ticket counts
    for u in users:
        u["tickets_ouverts"] = conn.execute(
            "SELECT COUNT(*) as n FROM tickets WHERE agent_id=? AND statut NOT IN ('Résolu','Clôturé')", (u["id"],)).fetchone()['n']
        u["tickets_total"] = conn.execute(
            "SELECT COUNT(*) as n FROM tickets WHERE agent_id=?", (u["id"],)).fetchone()['n']
        u["tickets_resolus"] = conn.execute(
            "SELECT COUNT(*) as n FROM tickets WHERE agent_id=? AND statut IN ('Résolu','Clôturé')", (u["id"],)).fetchone()['n']
    conn.close()
    return users

@app.post("/users")
def create_user(req: UserCreate, user=Depends(require_role("superviseur","directeur"))):
    conn = get_db()
    uid = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC).isoformat()
    try:
        conn.execute("INSERT INTO users (id,nom,prenom,email,password,role,actif,created_at) VALUES (?,?,?,?,?,?,1,?)",
                    (uid, req.nom, req.prenom, req.email, hash_pw(req.password), req.role, now))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(400, "Email déjà utilisé")
    finally:
        conn.close()
    return {"id": uid, "message": f"Compte {req.prenom} {req.nom} créé"}

@app.patch("/me")
def update_me(req: UserUpdate, user=Depends(get_current_user)):
    conn = get_db()
    updates, params = [], []
    if req.nom: updates.append("nom=?"); params.append(req.nom)
    if req.prenom: updates.append("prenom=?"); params.append(req.prenom)
    if req.password: updates.append("password=?"); params.append(hash_pw(req.password))
    if not updates: raise HTTPException(400, "Aucun champ à modifier")
    params.append(user["id"])
    conn.execute(f"UPDATE users SET {','.join(updates)} WHERE id=?", params)
    conn.commit(); conn.close()
    return {"message": "Profil mis à jour"}

@app.patch("/users/{user_id}")
def update_user(user_id: str, req: UserUpdate, user=Depends(require_role("superviseur","directeur"))):
    conn = get_db()
    # Snapshot before update
    old = conn.execute("SELECT nom,prenom,role,actif FROM users WHERE id=?", (user_id,)).fetchone()
    if not old:
        conn.close(); raise HTTPException(404, "Utilisateur introuvable")
    updates, params = [], []
    if req.nom: updates.append("nom=?"); params.append(req.nom)
    if req.prenom: updates.append("prenom=?"); params.append(req.prenom)
    if req.role: updates.append("role=?"); params.append(req.role)
    if req.actif is not None: updates.append("actif=?"); params.append(req.actif)
    if req.password: updates.append("password=?"); params.append(hash_pw(req.password))
    if not updates: conn.close(); raise HTTPException(400, "Aucun champ à modifier")
    params.append(user_id)
    conn.execute(f"UPDATE users SET {','.join(updates)} WHERE id=?", params)
    # Log each changed field
    now = datetime.datetime.now(datetime.UTC).isoformat()
    modifier_nom = f"{user['prenom']} {user['nom']}"
    field_map = {"nom": (old["nom"], req.nom), "prenom": (old["prenom"], req.prenom),
                 "role": (old["role"], req.role), "actif": (str(old["actif"]), str(req.actif) if req.actif is not None else None)}
    if req.password:
        conn.execute("INSERT INTO agent_history VALUES(?,?,?,?,?,?,?,?)",
                     (str(uuid.uuid4()), user_id, user["id"], modifier_nom, "password", "***", "***", now))
    for champ, (old_val, new_val) in field_map.items():
        if new_val is not None and str(new_val) != str(old_val):
            conn.execute("INSERT INTO agent_history VALUES(?,?,?,?,?,?,?,?)",
                         (str(uuid.uuid4()), user_id, user["id"], modifier_nom, champ, old_val, new_val, now))
    conn.commit(); conn.close()
    return {"message": "Utilisateur mis à jour"}

@app.delete("/users/{user_id}")
def delete_user(user_id: str, user=Depends(require_role("directeur"))):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit(); conn.close()
    return {"message": "Compte désactivé"}

@app.get("/users/{user_id}/history")
def get_user_history(user_id: str, user=Depends(require_role("superviseur","directeur"))):
    conn = get_db()
    rows = conn.execute(
        "SELECT champ, ancienne_valeur, nouvelle_valeur, modifie_par_nom, created_at "
        "FROM agent_history WHERE agent_id=? ORDER BY created_at DESC LIMIT 50",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── EXPORT CSV ──

@app.get("/export/tickets")
def export_tickets_csv(user=Depends(require_role("superviseur","directeur"))):
    import csv, io
    conn = get_db()
    tickets = conn.execute("""
        SELECT t.numero, t.driver_nom, t.driver_yango, t.driver_tel, t.driver_plaque,
               t.categorie, t.sous_categorie, t.alerte, t.priorite, t.statut,
               t.notes, u.nom||' '||u.prenom as agent, t.created_at, t.updated_at, t.resolved_at
        FROM tickets t LEFT JOIN users u ON t.agent_id=u.id
        ORDER BY t.created_at DESC
    """).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['N°Ticket','Chauffeur','ID Yango','Téléphone','Plaque',
                     'Catégorie','Sous-catégorie','Alerte','Priorité','Statut',
                     'Notes','Agent','Créé le','Modifié le','Résolu le'])
    for t in tickets:
        writer.writerow(list(t))
    output.seek(0)
    from fastapi.responses import Response
    return Response(
        content=output.getvalue().encode('utf-8-sig'),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename=syndongo_tickets_{datetime.date.today()}.csv'}
    )

@app.get("/export/agents")
def export_agents_csv(user=Depends(require_role("directeur"))):
    import csv, io
    conn = get_db()
    agents = conn.execute("""
        SELECT u.nom, u.prenom, u.email, u.role,
               CASE WHEN u.actif=1 THEN 'Actif' ELSE 'Inactif' END as statut,
               u.created_at, u.last_login,
               COUNT(t.id) as total_tickets,
               SUM(CASE WHEN t.statut IN ('Résolu','Clôturé') THEN 1 ELSE 0 END) as resolus
        FROM users u LEFT JOIN tickets t ON u.id=t.agent_id
        GROUP BY u.id ORDER BY u.role, u.nom
    """).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Nom','Prénom','Email','Rôle','Statut','Créé le','Dernière connexion','Total tickets','Tickets résolus'])
    for a in agents:
        writer.writerow(list(a))
    output.seek(0)
    from fastapi.responses import Response
    return Response(
        content=output.getvalue().encode('utf-8-sig'),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename=syndongo_agents_{datetime.date.today()}.csv'}
    )

# ── NOTIFICATIONS ──

@app.get("/notifications")
def get_notifs(user=Depends(get_current_user)):
    conn = get_db()
    notifs = [dict(n) for n in conn.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (user["id"],)).fetchall()]
    conn.close()
    return notifs

@app.post("/notifications/read-all")
def mark_all_read(user=Depends(get_current_user)):
    conn = get_db()
    conn.execute("UPDATE notifications SET lu=1 WHERE user_id=?", (user["id"],))
    conn.commit(); conn.close()
    return {"message": "OK"}

def _notify_role(conn, role1, role2, titre, message, ticket_id, now):
    roles = [r for r in [role1, role2] if r]
    q = f"SELECT id FROM users WHERE role IN ({','.join(['?']*len(roles))}) AND actif=1"
    users = conn.execute(q, roles).fetchall()
    for u in users:
        conn.execute("INSERT INTO notifications (id,user_id,titre,message,type,ticket_id,created_at) VALUES (?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), u['id'], titre, message, "alerte", ticket_id, now))

# ── ANALYTICS ──

@app.get("/analytics")
def analytics(user=Depends(require_role("superviseur","directeur"))):
    conn = get_db()
    motifs = [dict(r) for r in conn.execute(
        "SELECT categorie, COUNT(*) as n FROM tickets GROUP BY categorie ORDER BY n DESC").fetchall()]
    par_agent = [dict(r) for r in conn.execute("""
        SELECT u.nom||' '||u.prenom as agent, 
               COUNT(t.id) as total,
               SUM(CASE WHEN t.statut IN ('Résolu','Clôturé') THEN 1 ELSE 0 END) as resolus,
               SUM(CASE WHEN t.statut NOT IN ('Résolu','Clôturé') THEN 1 ELSE 0 END) as ouverts
        FROM users u LEFT JOIN tickets t ON u.id=t.agent_id
        WHERE u.role='agent' AND u.actif=1
        GROUP BY u.id ORDER BY total DESC""").fetchall()]
    par_alerte = [dict(r) for r in conn.execute(
        "SELECT alerte, COUNT(*) as n FROM tickets GROUP BY alerte").fetchall()]
    conn.close()
    return {"motifs": motifs, "par_agent": par_agent, "par_alerte": par_alerte}

def auto_backup():
    try:
        backup_path = DB.replace('.db', f'_backup_{datetime.date.today()}.db')
        shutil.copy2(DB, backup_path)
        print(f"✅ Backup créé : {backup_path}")
    except Exception as e:
        print(f"⚠️ Backup échoué : {e}")
    threading.Timer(86400, auto_backup).start()

@app.get("/admin/backup")
def download_backup(user=Depends(require_role("directeur"))):
    backup_path = DB.replace('.db', f'_backup_{datetime.date.today()}.db')
    shutil.copy2(DB, backup_path)
    from fastapi.responses import FileResponse
    return FileResponse(backup_path, filename=f"syndongo_backup_{datetime.date.today()}.db")

if __name__ == "__main__":
    init_db()
    threading.Timer(86400, auto_backup).start()
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

init_db()
