from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response

import sqlite3

import time

import random

import os

import csv

import io

import uuid

import json

from collections import defaultdict

from flask_socketio import SocketIO, emit, join_room, leave_room



app = Flask(__name__)

app.secret_key = "fifa23_ultimate_auction_key"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')



MASTER_DB = "master.db"



def safe_int(val):

    try: return int(val)

    except: return 0



# --- MASTER DB (GLOBAL USERS & ROOMS) ---

def get_master_connection():

    conn = sqlite3.connect(MASTER_DB, timeout=20.0)

    conn.row_factory = sqlite3.Row

    return conn



def init_master_db():

    conn = get_master_connection()

    conn.execute('''CREATE TABLE IF NOT EXISTS rooms (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, password TEXT, db_file TEXT, created_at INTEGER)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS global_users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, email TEXT UNIQUE, reset_token TEXT, reset_token_expiry INTEGER, role TEXT DEFAULT 'user')''')

    conn.commit()

    conn.close()



def upgrade_master_db():

    conn = get_master_connection()

    try:
        conn.execute("ALTER TABLE global_users ADD COLUMN role TEXT DEFAULT 'user'")
    except sqlite3.OperationalError:
        pass
        
    try:
        conn.execute("ALTER TABLE global_users ADD COLUMN email TEXT")
        conn.execute("ALTER TABLE global_users ADD COLUMN reset_token TEXT")
        conn.execute("ALTER TABLE global_users ADD COLUMN reset_token_expiry INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        # Make the very first registered user the Super Admin automatically
        conn.execute("UPDATE global_users SET role='superadmin' WHERE id = (SELECT MIN(id) FROM global_users)")
    except sqlite3.OperationalError:
        pass

    conn.commit()

    conn.close()



init_master_db()

upgrade_master_db()



# --- ROOM DB CONNECTION ---

def get_connection():

    db_file = session.get('room_db')

    if not db_file: return None

    conn = sqlite3.connect(db_file, timeout=20.0)

    conn.execute('pragma journal_mode=wal')

    conn.row_factory = sqlite3.Row

    

    # Auto-Patcher for Sealed Envelope Mode

    conn.execute('''CREATE TABLE IF NOT EXISTS blind_bids (player_id INTEGER, username TEXT, bid_amount INTEGER, PRIMARY KEY (player_id, username))''')

    conn.commit()

    

    return conn



def init_room_db(db_path):

    conn = sqlite3.connect(db_path, timeout=20.0)

    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, budget INTEGER NOT NULL DEFAULT 1000, role TEXT NOT NULL DEFAULT 'user', current_formation TEXT DEFAULT '4-4-2', club_name TEXT DEFAULT 'FC Ultimate', anthem_url TEXT DEFAULT '', pitch_theme TEXT DEFAULT 'classic')''')

    cur.execute('''CREATE TABLE IF NOT EXISTS players (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, image TEXT, club TEXT, nation TEXT, position TEXT NOT NULL, rating INTEGER NOT NULL, pac INTEGER, sho INTEGER, pas INTEGER, dri INTEGER, def INTEGER, phy INTEGER, pac_acc INTEGER, pac_sprint INTEGER, sho_pos INTEGER, sho_fin INTEGER, sho_pow INTEGER, sho_long INTEGER, sho_vol INTEGER, sho_pen INTEGER, pas_vis INTEGER, pas_cro INTEGER, pas_fk INTEGER, pas_short INTEGER, pas_long INTEGER, pas_curve INTEGER, dri_agi INTEGER, dri_bal INTEGER, dri_react INTEGER, dri_ball INTEGER, dri_comp INTEGER, def_inter INTEGER, def_head INTEGER, def_aware INTEGER, def_stand INTEGER, def_slide INTEGER, phy_jump INTEGER, phy_stam INTEGER, phy_str INTEGER, phy_agg INTEGER, current_bid INTEGER DEFAULT 0, highest_bidder TEXT DEFAULT NULL, auction_status TEXT DEFAULT 'waiting', auction_end_time INTEGER DEFAULT 0, paused_time_left INTEGER DEFAULT 0, is_sold INTEGER DEFAULT 0, pitch_position TEXT DEFAULT NULL, sold_time INTEGER DEFAULT 0, bid_count INTEGER DEFAULT 0, sudden_death INTEGER DEFAULT 0, player_id INTEGER DEFAULT NULL)''')

    cur.execute('''CREATE TABLE IF NOT EXISTS auction_folds (player_id INTEGER, username TEXT, PRIMARY KEY (player_id, username))''')

    cur.execute('''CREATE TABLE IF NOT EXISTS auction_bidders (player_id INTEGER, username TEXT, PRIMARY KEY (player_id, username))''')

    cur.execute('''CREATE TABLE IF NOT EXISTS blind_bids (player_id INTEGER, username TEXT, bid_amount INTEGER, PRIMARY KEY (player_id, username))''')

    cur.execute('''CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, proposer_id INTEGER NOT NULL, receiver_id INTEGER NOT NULL, offered_player_id INTEGER, requested_player_id INTEGER, money_offer INTEGER DEFAULT 0, money_request INTEGER DEFAULT 0, status TEXT DEFAULT 'pending', FOREIGN KEY(proposer_id) REFERENCES users(id), FOREIGN KEY(receiver_id) REFERENCES users(id))''')

    cur.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')

    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auction_state', 'active')")

    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_reaction', '')")

    conn.commit()



    csv_path = "players_cleaned.csv.csv"

    if os.path.exists(csv_path):

        players_data = []

        with open(csv_path, "r", encoding="utf-8") as f:

            reader = csv.DictReader(f)

            for row in reader:

                if safe_int(row.get('rating', 0)) > 77: players_data.append(row)

        

        pos_groups = defaultdict(list)

        for p in players_data: pos_groups[p.get('positions', 'RES').split(',')[0].strip()].append(p)

        pos_batches = defaultdict(list)

        for pos, pl in pos_groups.items():

            t1 = [p for p in pl if safe_int(p['rating']) >= 88]; t2 = [p for p in pl if 83 <= safe_int(p['rating']) <= 87]; t3 = [p for p in pl if safe_int(p['rating']) <= 82]

            random.shuffle(t1); random.shuffle(t2); random.shuffle(t3)

            while t1 or t2 or t3:

                batch = []

                for _ in range(2):

                    if t1: batch.append(t1.pop(0))

                    elif t2: batch.append(t2.pop(0))

                    elif t3: batch.append(t3.pop(0))

                for _ in range(2):

                    if t2: batch.append(t2.pop(0))

                    elif t3: batch.append(t3.pop(0))

                    elif t1: batch.append(t1.pop(0))

                for _ in range(2):

                    if t3: batch.append(t3.pop(0))

                    elif t2: batch.append(t2.pop(0))

                    elif t1: batch.append(t1.pop(0))

                random.shuffle(batch); pos_batches[pos].append(batch)

        

        master_queue = []; positions_list = list(pos_batches.keys()); random.shuffle(positions_list); active_positions = positions_list[:]

        while active_positions:

            for pos in list(active_positions):

                if pos_batches[pos]: master_queue.extend(pos_batches[pos].pop(0))

                else: active_positions.remove(pos)



        for row in master_queue:

            cur.execute("""INSERT INTO players (name, image, club, nation, position, rating, pac, sho, pas, dri, def, phy, pac_acc, pac_sprint, sho_pos, sho_fin, sho_pow, sho_long, sho_vol, sho_pen, pas_vis, pas_cro, pas_fk, pas_short, pas_long, pas_curve, dri_agi, dri_bal, dri_react, dri_ball, dri_comp, def_inter, def_head, def_aware, def_stand, def_slide, phy_jump, phy_stam, phy_str, phy_agg, player_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (

                row.get('name', 'Unknown'), row.get('image', ''), row.get('Club Name', 'Free Agent'), row.get('nation', ''), row.get('positions', 'RES').split(',')[0].strip(), safe_int(row.get('rating', 0)),

                safe_int(row.get('Pace Total')), safe_int(row.get('Shooting Total')), safe_int(row.get('Passing Total')), safe_int(row.get('Dribbling Total')), safe_int(row.get('Defending Total')), safe_int(row.get('Physicality Total')), safe_int(row.get('Acceleration')), safe_int(row.get('Sprint Speed')), safe_int(row.get('Positioning')), safe_int(row.get('Finishing')), safe_int(row.get('Shot Power')), safe_int(row.get('Long Shots')), safe_int(row.get('Volleys')), safe_int(row.get('Penalties')), safe_int(row.get('Vision')), safe_int(row.get('Crossing')), safe_int(row.get('Freekick Accuracy')), safe_int(row.get('Short Passing')), safe_int(row.get('LongPassing')), safe_int(row.get('Curve')), safe_int(row.get('Agility')), safe_int(row.get('Balance')), safe_int(row.get('Reactions')), safe_int(row.get('BallControl')), safe_int(row.get('Composure')), safe_int(row.get('Interceptions')), safe_int(row.get('Heading Accuracy')), safe_int(row.get('Marking')), safe_int(row.get('Standing Tackle')), safe_int(row.get('Sliding Tackle')), safe_int(row.get('Jumping')), safe_int(row.get('Stamina')), safe_int(row.get('Strength')), safe_int(row.get('Aggression')),

                safe_int(row.get('player_id')) if row.get('player_id') else None

            ))

    conn.commit()

    conn.close()



def upgrade_db():

    conn = get_connection()

    if not conn: return

    cur = conn.cursor()

    for col in [('sold_time', 'INTEGER DEFAULT 0'), ('bid_count', 'INTEGER DEFAULT 0'), ('sudden_death', 'INTEGER DEFAULT 0'), ('player_id', 'INTEGER DEFAULT NULL')]:

        try: cur.execute(f"ALTER TABLE players ADD COLUMN {col[0]} {col[1]}")

        except: pass

    for col in [('club_name', "TEXT DEFAULT 'FC Ultimate'"), ('anthem_url', "TEXT DEFAULT ''"), ('pitch_theme', "TEXT DEFAULT 'classic'")]:

        try: cur.execute(f"ALTER TABLE users ADD COLUMN {col[0]} {col[1]}")

        except: pass

    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('lobby_password', 'fifa23')")

    conn.commit()

    conn.close()



# 🛡️ SECURITY WALL


@app.before_request
def require_auth():
    public_routes = ['login', 'register', 'static', 'forgot_password', 'reset_password']
    if request.endpoint not in public_routes and 'global_user' not in session:
        return redirect(url_for('login'))

        

    room_required_routes = ['auction', 'auction_status', 'place_bid', 'fold', 'react', 'summary', 'api_leaderboard', 'api_history', 'api_teams', 'api_trade_players', 'propose_trade', 'my_trades', 'respond_trade', 'my_team', 'save_squad_state', 'export_my_team', 'admin_dashboard', 'change_pin', 'reset_player', 'make_admin', 'hard_reset_draft', 'delete_user']

    

    # KICK USER OUT IF SUPER ADMIN DELETED THEIR ROOM

    if request.endpoint in room_required_routes:

        if 'room_db' not in session or not os.path.exists(session['room_db']):

            session.pop('room_db', None)

            session.pop('room_name', None)

            return redirect(url_for('hub'))



# --- GLOBAL AUTH ROUTES ---



@app.route("/")

def index():

    return redirect(url_for("login"))



@app.route("/login", methods=["GET", "POST"])

def login():

    if request.method == "POST":

        conn = get_master_connection(); cur = conn.cursor()

        user = cur.execute("SELECT * FROM global_users WHERE username=?", (request.form["username"].strip(),)).fetchone()

        if user and user["password"] == request.form["password"]:

            session["global_user"] = user["username"]

            session["global_password"] = user["password"]

            session["global_role"] = user["role"]

            conn.close()

            return redirect(url_for("hub"))

        conn.close()

        return render_template("login.html", error="Invalid Credentials.")

    return render_template("login.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        conn = get_master_connection()
        count = conn.execute("SELECT COUNT(*) FROM global_users").fetchone()[0]
        role = "superadmin" if count == 0 else "user"
        try:
            email = request.form.get("email", "").strip()
            if not email: return render_template("register.html", error="Email is required!")
            conn.execute("INSERT INTO global_users (username, password, email, role) VALUES (?, ?, ?, ?)", (request.form["username"].strip(), request.form["password"], email, role))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close(); return render_template("register.html", error="Username or Email already taken!", user_exists=True)
        conn.close(); return redirect(url_for("login"))
    return render_template("register.html")



@app.route("/logout")
def logout(): 
    session.clear() 
    return redirect(url_for("login"))

def send_reset_email(to_email, token):
    sender = os.environ.get('SMTP_USERNAME')
    password = os.environ.get('SMTP_PASSWORD')
    server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    port = safe_int(os.environ.get('SMTP_PORT', 587))
    
    reset_link = url_for('reset_password', token=token, _external=True)
    
    if not sender or not password:
        print(f"\\n--- FORGOT PASSWORD TRIGGERED ---\\nLink: {reset_link}\\n----------------------------------\\n", flush=True)
        return True
        
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(f"Click the link to reset your password: {reset_link}")
        msg['Subject'] = "Password Reset - FIFA 23 Auction"
        msg['From'] = sender
        msg['To'] = to_email
        with smtplib.SMTP(server, port) as s:
            s.starttls()
            s.login(sender, password)
            s.send_message(msg)
        return True
    except Exception as e:
        print("Email sending failed:", e)
        return False

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        username = request.form.get("username", "").strip()
        conn = get_master_connection(); cur = conn.cursor()
        user = cur.execute("SELECT password FROM global_users WHERE email=? AND username=?", (email, username)).fetchone()
        conn.close()
        if user:
            return render_template("forgot_password.html", recovered_password=user['password'])
        else:
            return render_template("forgot_password.html", error="No matching account found for that username and email.")
    return render_template("forgot_password.html")

@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    conn = get_master_connection(); cur = conn.cursor()
    user = cur.execute("SELECT id FROM global_users WHERE reset_token=? AND reset_token_expiry > ?", (token, int(time.time()))).fetchone()
    if not user:
        conn.close()
        return render_template("reset_password.html", error="Invalid or expired token.")
    
    if request.method == "POST":
        new_password = request.form.get("password")
        cur.execute("UPDATE global_users SET password=?, reset_token=NULL, reset_token_expiry=NULL WHERE id=?", (new_password, user['id']))
        conn.commit()
        conn.close()
        return redirect(url_for("login"))
        
    conn.close()
    return render_template("reset_password.html", token=token)



@app.route("/exit_room")

def exit_room():

    """Clears room-specific session data but keeps the global user logged in."""

    session.pop('room_db', None)

    session.pop('room_name', None)

    session.pop('user_id', None)

    session.pop('role', None)

    session.pop('in_lobby', None)

    return redirect(url_for("hub"))



# --- HUB ROUTES ---



@app.route("/hub")

def hub():

    conn = get_master_connection()

    rooms = conn.execute("SELECT id, name, created_at FROM rooms ORDER BY created_at DESC").fetchall()

    conn.close()

    return render_template("hub.html", rooms=rooms)



@app.route("/create_room", methods=["POST"])

def create_room():

    room_name = request.form.get("room_name").strip()

    room_password = request.form.get("room_password").strip()

    if not room_name or not room_password: return redirect(url_for("hub"))

    db_file = f"room_{uuid.uuid4().hex[:8]}.db"

    

    conn = get_master_connection()

    try:

        conn.execute("INSERT INTO rooms (name, password, db_file, created_at) VALUES (?, ?, ?, ?)", (room_name, room_password, db_file, int(time.time())))

        conn.commit()

        

        session.pop('user_id', None)

        session.pop('username', None)

        session.pop('role', None)

        session.pop('in_lobby', None)

        

        init_room_db(db_file) 

        session['room_db'] = db_file

        session['room_name'] = room_name

        conn.close()

        return redirect(url_for("room_sync")) 

    except sqlite3.IntegrityError:

        rooms = conn.execute("SELECT id, name, created_at FROM rooms ORDER BY created_at DESC").fetchall()

        conn.close()

        return render_template("hub.html", rooms=rooms, error="Room name already exists. Go back and try another name.")



@app.route("/join_room", methods=["POST"])

def join_room():

    room_id = request.form.get("room_id")

    password = request.form.get("room_password").strip()

    

    conn = get_master_connection()

    rooms = conn.execute("SELECT id, name, created_at FROM rooms ORDER BY created_at DESC").fetchall()

    room = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()

    conn.close()

    

    if room and room["password"] == password:

        session.pop('user_id', None)

        session.pop('username', None)

        session.pop('role', None)

        session.pop('in_lobby', None)

        

        session['room_db'] = room["db_file"]

        session['room_name'] = room["name"]

        return redirect(url_for("room_sync"))

    

    return render_template("hub.html", rooms=rooms, error="Incorrect Room Password. Please try again.")



@app.route("/room_sync")

def room_sync():

    """Automatically maps the global user into the specific room DB."""

    if "global_user" not in session or "room_db" not in session: return redirect(url_for("hub"))

    

    upgrade_db() 

    

    username = session["global_user"]

    password = session["global_password"]

    

    conn = get_connection(); cur = conn.cursor()

    user = cur.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

    

    if not user:

        count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]

        role = 'admin' if count == 0 else 'user'

        cur.execute("INSERT INTO users (username, password, budget, role, club_name, anthem_url, pitch_theme) VALUES (?, ?, 1000, ?, ?, ?, ?)", (username, password, role, "FC " + username, "", "classic"))

        conn.commit()

        user = cur.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

        

    session["user_id"] = user["id"]

    session["username"] = user["username"]

    session["role"] = user["role"]

    session["budget"] = user["budget"]

    session["in_lobby"] = True

    conn.close()

    

    return redirect(url_for("league"))



# --- 🔥 SUPER ADMIN (GLOBAL SERVER ADMIN) ROUTES 🔥 ---



@app.route("/superadmin")

def superadmin_dashboard():

    if session.get("global_role") != "superadmin":

        return redirect(url_for("hub"))

        

    conn = get_master_connection()

    rooms = conn.execute("SELECT * FROM rooms ORDER BY created_at DESC").fetchall()

    global_users = conn.execute("SELECT * FROM global_users ORDER BY id ASC").fetchall()

    conn.close()

    return render_template("superadmin.html", rooms=rooms, global_users=global_users)



@app.route("/superadmin/delete_room/<int:room_id>", methods=["POST"])

def delete_room(room_id):

    if session.get("global_role") != "superadmin":

        return redirect(url_for("hub"))

        

    conn = get_master_connection()

    room = conn.execute("SELECT db_file FROM rooms WHERE id=?", (room_id,)).fetchone()

    if room:

        db_file = room["db_file"]

        conn.execute("DELETE FROM rooms WHERE id=?", (room_id,))

        conn.commit()

        

        # Safely delete the physical room database file

        if os.path.exists(db_file):

            try:

                os.remove(db_file)

                if os.path.exists(db_file + "-wal"): os.remove(db_file + "-wal")

                if os.path.exists(db_file + "-shm"): os.remove(db_file + "-shm")

            except Exception as e:

                pass

                

    conn.close()

    return redirect(url_for("superadmin_dashboard"))



# --- AUCTION ROUTES ---



@socketio.on('join')
def on_join(data):
    room = session.get('room_name')
    if room:
        join_room(room)

@socketio.on('check_time_up')
def on_check_time_up(data):
    room = session.get('room_name')
    if not room: return
    
    # Check if timer is up and trigger state evaluation
    # This directly simulates what the polling endpoint used to do automatically
    with app.test_request_context('/auction_status'):
        # Just calling the function will trigger the logic and emit if needed
        get_auction_state(room)

def emit_auction_update(room):
    with app.test_request_context('/auction_status'):
        state = get_auction_state(room)
        socketio.emit('auction_update', state, to=room)

@app.route("/auction")

def auction():

    conn = get_connection()

    if not conn: return redirect(url_for("hub"))

    cur = conn.cursor()

    

    user_row = cur.execute("SELECT budget FROM users WHERE id=?", (session["user_id"],)).fetchone()

    if not user_row:

        conn.close(); session.pop('room_db', None); return redirect(url_for("hub"))

        

    session["budget"] = user_row["budget"]

    state = cur.execute("SELECT value FROM settings WHERE key='auction_state'").fetchone()[0]

    if state == 'finished': conn.close(); return redirect(url_for("summary"))

        

    player = cur.execute("SELECT * FROM players WHERE auction_status IN ('live', 'paused')").fetchone()

    users = cur.execute("SELECT id, username FROM users WHERE id != ?", (session["user_id"],)).fetchall()

    remaining_players = cur.execute("SELECT COUNT(*) FROM players WHERE is_sold=0 AND auction_status='waiting'").fetchone()[0]

    

    waiting_players_list = cur.execute("SELECT id, name, rating, position FROM players WHERE is_sold=0 AND auction_status='waiting' ORDER BY rating DESC, name ASC").fetchall()

    

    has_folded = False

    if player: has_folded = bool(cur.execute("SELECT 1 FROM auction_folds WHERE player_id=? AND username=?", (player["id"], session["username"])).fetchone())

    conn.close()

    return render_template("auction.html", player=player, users=users, remaining_players=remaining_players, waiting_players=waiting_players_list, has_folded=has_folded, room_name=session.get("room_name"))



@app.route("/start_auction")

def start_auction():

    if session.get("role") != "admin": return redirect(url_for("auction"))

    conn = get_connection(); cur = conn.cursor()

    if cur.execute("SELECT id FROM players WHERE auction_status IN ('live', 'paused')").fetchone(): 

        conn.close(); return redirect(url_for("auction"))

    

    specific_player_id = request.args.get('player_id')

    

    if specific_player_id and specific_player_id.strip() != "":

        new_player = cur.execute("SELECT * FROM players WHERE id=? AND is_sold=0 AND auction_status='waiting'", (int(specific_player_id),)).fetchone()

    else:

        pos_filter = request.args.get('pos', 'ALL')

        query = "SELECT * FROM players WHERE is_sold=0 AND auction_status='waiting'"

        if pos_filter == 'ATT': query += " AND position IN ('ST', 'CF', 'RW', 'LW', 'RF', 'LF')"

        elif pos_filter == 'MID': query += " AND position IN ('CAM', 'CM', 'CDM', 'RM', 'LM')"

        elif pos_filter == 'DEF': query += " AND position IN ('CB', 'RB', 'LB', 'RWB', 'LWB')"

        elif pos_filter == 'GK': query += " AND position = 'GK'"

        query += " ORDER BY id ASC LIMIT 1"

        

        new_player = cur.execute(query).fetchone()

        if not new_player and pos_filter != 'ALL': 

            new_player = cur.execute("SELECT * FROM players WHERE is_sold=0 AND auction_status='waiting' ORDER BY id ASC LIMIT 1").fetchone()

            

    if not new_player: conn.close(); return redirect(url_for("auction"))

        

    cur.execute("UPDATE players SET auction_status='live', current_bid=0, highest_bidder=NULL, bid_count=0, sudden_death=0, auction_end_time=? WHERE id=?", (int(time.time()) + 35, new_player["id"]))

    cur.execute("DELETE FROM auction_folds")

    cur.execute("DELETE FROM auction_bidders")

    cur.execute("DELETE FROM blind_bids")

    conn.commit(); conn.close(); emit_auction_update(session.get('room_name')); return redirect(url_for("auction"))



@app.route("/end_entire_auction")

def end_entire_auction():

    if session.get("role") != "admin": return redirect(url_for("auction"))

    conn = get_connection(); cur = conn.cursor()

    cur.execute("UPDATE players SET auction_end_time=?, auction_status='processing' WHERE auction_status='live'", (int(time.time()) - 1,))

    cur.execute("UPDATE settings SET value='finished' WHERE key='auction_state'")

    conn.commit(); conn.close()

    emit_auction_update(session.get('room_name')); return redirect(url_for("summary"))



@app.route("/pause_auction")

def pause_auction():

    if session.get("role") != "admin": return redirect(url_for("auction"))

    conn = get_connection(); cur = conn.cursor()

    player = cur.execute("SELECT id, auction_end_time FROM players WHERE auction_status='live'").fetchone()

    if player: cur.execute("UPDATE players SET auction_status='paused', paused_time_left=? WHERE id=?", (max(0, player["auction_end_time"] - int(time.time())), player["id"])); conn.commit()

    conn.close(); emit_auction_update(session.get('room_name')); return redirect(url_for("auction"))



@app.route("/resume_auction")

def resume_auction():

    if session.get("role") != "admin": return redirect(url_for("auction"))

    conn = get_connection(); cur = conn.cursor()

    player = cur.execute("SELECT id, paused_time_left FROM players WHERE auction_status='paused'").fetchone()

    if player: cur.execute("UPDATE players SET auction_status='live', auction_end_time=?, paused_time_left=0 WHERE id=?", (int(time.time()) + player["paused_time_left"], player["id"])); conn.commit()

    conn.close(); emit_auction_update(session.get('room_name')); return redirect(url_for("auction"))



@app.route("/place_bid", methods=["POST"])

def place_bid():

    if "user_id" not in session: return jsonify({"error": "Session expired"})

    

    try: bid_amount = int(request.form["bid_amount"])

    except ValueError: return jsonify({"error": "Invalid bid amount"})

    username = session["global_user"]; conn = get_connection(); cur = conn.cursor()

    player = cur.execute("SELECT * FROM players WHERE auction_status='live'").fetchone()

    

    if not player or cur.execute("SELECT 1 FROM auction_folds WHERE player_id=? AND username=?", (player["id"], username)).fetchone(): conn.close(); return jsonify({"error": "Cannot bid right now."})

    

    # 🔥 EXCLUSIVE SEALED ENVELOPE (LEWANDOWSKI ONLY) 🔥

    if 'Lewandowski' in player["name"]:

        if bid_amount > cur.execute("SELECT budget FROM users WHERE username=?", (username,)).fetchone()["budget"]: conn.close(); return jsonify({"error": "INSUFFICIENT FUNDS!"})

        cur.execute("INSERT OR REPLACE INTO blind_bids (player_id, username, bid_amount) VALUES (?, ?, ?)", (player["id"], username, bid_amount))

        cur.execute("INSERT OR IGNORE INTO auction_bidders (player_id, username) VALUES (?, ?)", (player["id"], username))

        conn.commit(); conn.close()

        emit_auction_update(session.get('room_name')); return jsonify({"success": True, "sealed": True})



    # STANDARD BIDDING LOGIC (Everyone else)

    if player["highest_bidder"] == username: conn.close(); return jsonify({"error": "You are already winning!"})

    if bid_amount <= 0 or bid_amount <= player["current_bid"]: conn.close(); return jsonify({"error": "Bid must be higher than current bid!"})

    if bid_amount > cur.execute("SELECT budget FROM users WHERE username=?", (username,)).fetchone()["budget"]: conn.close(); return jsonify({"error": "INSUFFICIENT FUNDS!"})

    

    if player["sudden_death"] == 1:

        if not cur.execute("SELECT 1 FROM auction_bidders WHERE player_id=? AND username=?", (player["id"], username)).fetchone():

            conn.close(); return jsonify({"error": "SUDDEN DEATH: You didn't bid previously!"})



    cur.execute("INSERT OR IGNORE INTO auction_bidders (player_id, username) VALUES (?, ?)", (player["id"], username))

    cur.execute("UPDATE players SET current_bid=?, highest_bidder=?, auction_end_time=?, bid_count=bid_count+1 WHERE id=? AND auction_status='live' AND ? > current_bid", (bid_amount, username, int(time.time()) + 15, player["id"], bid_amount))

    conn.commit(); conn.close()

    emit_auction_update(session.get('room_name')); return jsonify({"success": True})



@app.route("/fold", methods=["GET", "POST"])

def fold():

    if request.method == "GET": return redirect(url_for('auction'))

    if "user_id" not in session: return jsonify({"error": "Session expired"})

    

    conn = get_connection(); cur = conn.cursor()

    player = cur.execute("SELECT * FROM players WHERE auction_status='live'").fetchone()

    if player:

        if player["highest_bidder"] == session["global_user"] and 'Lewandowski' not in player["name"]:

            conn.close(); return jsonify({"error": "You cannot fold while winning!"})

        try: cur.execute("INSERT INTO auction_folds (player_id, username) VALUES (?, ?)", (player["id"], session["global_user"])); conn.commit()

        except sqlite3.IntegrityError: pass

    conn.close()

    emit_auction_update(session.get('room_name')); return jsonify({"success": True})



@app.route("/react", methods=["POST"])

def react():

    if "global_user" not in session: return jsonify(success=False)

    emoji = request.json.get("emoji")

    val = f"{emoji}|{int(time.time() * 1000)}|{session['global_user']}"

    conn = get_connection(); cur = conn.cursor()

    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_reaction', ?)", (val,))

    conn.commit(); conn.close()

    emit_auction_update(session.get('room_name')); return jsonify(success=True)



def build_ended_payload(player_data, reaction):

    conn = get_connection(); cur = conn.cursor()

    winner_data = cur.execute("SELECT club_name, anthem_url FROM users WHERE username=?", (player_data["highest_bidder"],)).fetchone()

    conn.close()

    return {

        "status": "ended", "player_id": player_data["id"], 

        "sold_to": player_data["highest_bidder"], "amount": player_data["current_bid"], 

        "reaction": reaction, "player_rating": player_data["rating"],

        "club_name": winner_data["club_name"] if winner_data else "FC Ultimate",

        "anthem_url": winner_data["anthem_url"] if winner_data else ""

    }



def get_auction_state():

    client_player_id = request.args.get('current_id')

    conn = get_connection(); cur = conn.cursor()

    

    state = cur.execute("SELECT value FROM settings WHERE key='auction_state'").fetchone()[0]

    if state == 'finished': conn.close(); return {"status": "global_end"}

        

    react_row = cur.execute("SELECT value FROM settings WHERE key='last_reaction'").fetchone()

    reaction = react_row[0] if react_row else ""



    active_player = cur.execute("SELECT * FROM players WHERE auction_status IN ('live', 'paused', 'processing')").fetchone()

    if active_player:

        player_id = active_player["id"]

        

        folded_users_rows = cur.execute("SELECT username FROM auction_folds WHERE player_id=?", (player_id,)).fetchall()

        folded_users = [row['username'] for row in folded_users_rows]



        active_bidders_rows = cur.execute("SELECT username FROM auction_bidders WHERE player_id=?", (player_id,)).fetchall()

        active_bidders_list = [row['username'] for row in active_bidders_rows]



        if active_player["auction_status"] == 'paused':

            conn.close(); return {"status": "paused", "player_id": player_id, "player_name": active_player["name"], "current_bid": active_player["current_bid"], "highest_bidder": active_player["highest_bidder"], "time_left": active_player["paused_time_left"], "reaction": reaction, "folded_users": folded_users, "active_bidders_list": active_bidders_list}



        time_left = max(0, active_player["auction_end_time"] - int(time.time()))

        total_users = max(1, cur.execute("SELECT COUNT(*) FROM users").fetchone()[0])

        fold_count = len(folded_users)

        active_bidders = len(active_bidders_list)

        

        folds_needed = (total_users - 1) if active_player["highest_bidder"] or 'Lewandowski' in active_player["name"] else total_users



        if time_left <= 0 and active_player["sudden_death"] == 0 and active_bidders > 1 and fold_count < folds_needed and 'Lewandowski' not in active_player["name"]:

            cur.execute("UPDATE players SET sudden_death=1, auction_end_time=? WHERE id=?", (int(time.time()) + 5, player_id))

            cur.execute("INSERT OR IGNORE INTO auction_folds (player_id, username) SELECT ?, username FROM users WHERE username NOT IN (SELECT username FROM auction_bidders WHERE player_id=?)", (player_id, player_id))

            conn.commit()

            time_left = 5



        elif time_left <= 0 or fold_count >= folds_needed:

            

            # 🔥 RESOLVE SEALED ENVELOPE BIDS HERE FOR LEWANDOWSKI 🔥

            if 'Lewandowski' in active_player["name"]:

                top_bid = cur.execute("SELECT username, bid_amount FROM blind_bids WHERE player_id=? ORDER BY bid_amount DESC LIMIT 1", (player_id,)).fetchone()

                if top_bid:

                    cur.execute("UPDATE players SET current_bid=?, highest_bidder=? WHERE id=?", (top_bid["bid_amount"], top_bid["username"], player_id))

                    active_player = dict(active_player)

                    active_player["current_bid"] = top_bid["bid_amount"]

                    active_player["highest_bidder"] = top_bid["username"]



            cur.execute("UPDATE players SET auction_status='processing' WHERE id=? AND auction_status='live'", (player_id,))

            if cur.rowcount == 1:

                sold_to = active_player["highest_bidder"]

                amount = active_player["current_bid"]

                

                if sold_to or ('Lewandowski' in active_player["name"] and cur.execute("SELECT 1 FROM blind_bids WHERE player_id=?", (player_id,)).fetchone()):

                    cur.execute("UPDATE users SET budget = budget - ? WHERE username=?", (amount, sold_to))

                    cur.execute("UPDATE players SET is_sold=1, auction_status='done', sold_time=? WHERE id=?", (int(time.time()), player_id))

                    conn.commit(); conn.close()

                    return build_ended_payload(active_player, reaction)

                else:

                    cur.execute("UPDATE players SET is_sold=0, auction_status='unsold', sold_time=? WHERE id=?", (int(time.time()), player_id))

                    new_player = cur.execute("SELECT * FROM players WHERE is_sold=0 AND auction_status='waiting' ORDER BY id ASC LIMIT 1").fetchone()

                    if new_player:

                        cur.execute("UPDATE players SET auction_status='live', current_bid=0, highest_bidder=NULL, bid_count=0, sudden_death=0, auction_end_time=? WHERE id=?", (int(time.time()) + 35, new_player["id"]))

                        cur.execute("DELETE FROM auction_folds")

                        cur.execute("DELETE FROM auction_bidders")

                        cur.execute("DELETE FROM blind_bids")

                    conn.commit(); conn.close()

                    return {"status": "skipped", "reaction": reaction}

            else:

                data = cur.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()

                conn.close()

                if data["auction_status"] == 'unsold': return {"status": "skipped"}

                return build_ended_payload(data, reaction)



        highest_budget, avg_budget = cur.execute("SELECT MAX(budget), AVG(budget) FROM users").fetchone()

        scarcity_count = cur.execute("SELECT COUNT(*) FROM players WHERE position=? AND is_sold=0 AND auction_status='waiting'", (active_player["position"],)).fetchone()[0]

        users_without_pos = cur.execute("SELECT COUNT(*) FROM users WHERE username NOT IN (SELECT highest_bidder FROM players WHERE is_sold=1 AND position=? AND highest_bidder IS NOT NULL)", (active_player["position"],)).fetchone()[0]



        conn.close()

        return jsonify({

            "status": "live", 

            "player_id": player_id, 

            "player_name": active_player["name"],

            "current_bid": active_player["current_bid"], 

            "highest_bidder": active_player["highest_bidder"], 

            "time_left": time_left, 

            "reaction": reaction,

            "folded_users": folded_users,

            "active_bidders_list": active_bidders_list,

            "sudden_death": active_player["sudden_death"],

            "active_bidders": active_bidders,

            "scarcity_alert": bool(scarcity_count < 3),

            "highest_budget": highest_budget or 0,

            "avg_budget": round(avg_budget or 0, 1),

            "pos_remaining": scarcity_count,

            "pos_demand": users_without_pos,

            "bid_count": active_player["bid_count"],

            "rating": active_player["rating"]

        })



    if client_player_id and client_player_id != 'null':

        old_player = cur.execute("SELECT * FROM players WHERE id=?", (client_player_id,)).fetchone()

        if old_player and old_player["auction_status"] == 'done':

            conn.close()

            return build_ended_payload(old_player, reaction)

        elif old_player and old_player["auction_status"] == 'unsold':

            conn.close()

            return {"status": "skipped", "reaction": reaction}



    conn.close()

    return {"status": "waiting", "reaction": reaction}



@app.route("/summary")

def summary():

    conn = get_connection(); cur = conn.cursor()

    most_expensive = cur.execute("SELECT * FROM players WHERE is_sold=1 ORDER BY current_bid DESC, rating DESC LIMIT 1").fetchone()

    biggest_steal = cur.execute("SELECT * FROM players WHERE is_sold=1 AND current_bid > 0 ORDER BY (CAST(rating AS FLOAT)/current_bid) DESC LIMIT 1").fetchone()

    biggest_overpay = cur.execute("SELECT * FROM players WHERE is_sold=1 AND current_bid > 0 ORDER BY (current_bid/CAST(rating AS FLOAT)) DESC LIMIT 1").fetchone()

    most_contested = cur.execute("SELECT * FROM players WHERE is_sold=1 ORDER BY bid_count DESC, current_bid DESC LIMIT 1").fetchone()

    total_spent = cur.execute("SELECT SUM(current_bid) FROM players WHERE is_sold=1").fetchone()[0] or 0

    total_sold = cur.execute("SELECT COUNT(*) FROM players WHERE is_sold=1").fetchone()[0] or 1

    avg_price = round(total_spent / total_sold, 1)

    users = cur.execute("SELECT username, budget FROM users").fetchall()

    teams = []; champion = {"username": "TBD", "avg_rating": 0, "squad": [], "spent": 0, "won": 0, "budget": 0}

    big_spender = {"username": "TBD", "spent": 0}; tactical_genius = {"username": "TBD", "won": 0}

    for u in users:

        squad = cur.execute("SELECT * FROM players WHERE highest_bidder=? AND is_sold=1 ORDER BY rating DESC", (u["username"],)).fetchall()

        top_11 = squad[:11]

        avg_rating = round(sum(p["rating"] for p in top_11) / len(top_11), 1) if top_11 else 0

        spent = sum(p["current_bid"] for p in squad); won_count = len(squad)

        if spent > big_spender["spent"]: big_spender = {"username": u["username"], "spent": spent}

        if won_count > tactical_genius["won"]: tactical_genius = {"username": u["username"], "won": won_count}

        teams.append({"username": u["username"], "budget": u["budget"], "squad": squad, "avg_rating": avg_rating, "player_count": won_count, "spent": spent})

        if avg_rating > champion["avg_rating"]: champion = {"username": u["username"], "avg_rating": avg_rating, "squad": top_11, "spent": spent, "won": won_count, "budget": u["budget"]}

    teams = sorted(teams, key=lambda x: x["avg_rating"], reverse=True); conn.close()

    return render_template("summary.html", most_expensive=most_expensive, biggest_steal=biggest_steal, biggest_overpay=biggest_overpay, most_contested=most_contested, total_spent=total_spent, avg_price=avg_price, teams=teams, champion=champion, big_spender=big_spender, tactical_genius=tactical_genius)



@app.route("/api/leaderboard")

def api_leaderboard():

    conn = get_connection(); cur = conn.cursor()

    leaderboard = cur.execute("""SELECT u.username, u.budget, COUNT(p.id) as players_won FROM users u LEFT JOIN players p ON u.username = p.highest_bidder AND p.is_sold = 1 GROUP BY u.username ORDER BY u.budget DESC, players_won DESC""").fetchall()

    conn.close(); return jsonify([dict(row) for row in leaderboard])



@app.route("/api/history")

def api_history():

    conn = get_connection(); cur = conn.cursor()

    if session.get("role") == "admin": history = cur.execute("SELECT name, rating, position, is_sold, highest_bidder, current_bid FROM players WHERE auction_status IN ('done', 'unsold') ORDER BY sold_time DESC").fetchall()

    else: history = cur.execute("SELECT name, rating, position, is_sold, highest_bidder, current_bid FROM players WHERE auction_status='done' ORDER BY sold_time DESC").fetchall()

    conn.close(); return jsonify([dict(row) for row in history])



@app.route("/api/teams")

def api_teams():

    conn = get_connection(); cur = conn.cursor()

    users = cur.execute("SELECT username FROM users").fetchall(); teams_data = []

    for user in users:

        players = cur.execute("SELECT name, image, rating, position, current_bid FROM players WHERE highest_bidder=? AND is_sold=1", (user["username"],)).fetchall()

        teams_data.append({"username": user["username"], "players": [dict(p) for p in players]})

    conn.close(); return jsonify(teams_data)



@app.route("/api/trade_players/<int:partner_id>")

def api_trade_players(partner_id):

    conn = get_connection(); cur = conn.cursor()

    partner = cur.execute("SELECT username FROM users WHERE id=?", (partner_id,)).fetchone()

    if not partner: conn.close(); return jsonify({"my_players": [], "partner_players": []})

    my_players = cur.execute("SELECT id, name, rating, position FROM players WHERE highest_bidder=? AND is_sold=1", (session["global_user"],)).fetchall()

    partner_players = cur.execute("SELECT id, name, rating, position FROM players WHERE highest_bidder=? AND is_sold=1", (partner["username"],)).fetchall()

    conn.close(); return jsonify({"my_players": [dict(p) for p in my_players], "partner_players": [dict(p) for p in partner_players]})



@app.route("/trade/propose", methods=["POST"])

def propose_trade():

    data = request.json; conn = get_connection(); cur = conn.cursor()

    try:

        sender_budget = cur.execute("SELECT budget FROM users WHERE id=?", (session["user_id"],)).fetchone()["budget"]

        if data.get("money_offer", 0) > sender_budget: conn.close(); return jsonify({"success": False, "error": "Insufficient funds for offer."})

        cur.execute("INSERT INTO trades (proposer_id, receiver_id, offered_player_id, requested_player_id, money_offer, money_request) VALUES (?, ?, ?, ?, ?, ?)", (session["user_id"], data["receiver_id"], data.get("offered_player_id") or None, data.get("requested_player_id") or None, data.get("money_offer", 0), data.get("money_request", 0)))

        conn.commit(); conn.close(); return jsonify({"success": True})

    except Exception as e: conn.close(); return jsonify({"success": False, "error": str(e)})



@app.route("/api/my_trades")

def my_trades():

    conn = get_connection(); cur = conn.cursor()

    incoming = cur.execute("""SELECT t.*, u.username as proposer_name, p1.name as off_name, p1.rating as off_rating, p2.name as req_name, p2.rating as req_rating FROM trades t JOIN users u ON t.proposer_id = u.id LEFT JOIN players p1 ON t.offered_player_id = p1.id LEFT JOIN players p2 ON t.requested_player_id = p2.id WHERE t.receiver_id = ? AND t.status = 'pending'""", (session["user_id"],)).fetchall()

    conn.close(); return jsonify([dict(row) for row in incoming])



@app.route("/trade/respond/<int:trade_id>/<action>", methods=["POST"])

def respond_trade(trade_id, action):

    conn = get_connection(); cur = conn.cursor()

    trade = cur.execute("SELECT * FROM trades WHERE id=? AND receiver_id=? AND status='pending'", (trade_id, session["user_id"])).fetchone()

    if not trade: conn.close(); return jsonify({"error": "Trade not found"}), 404

    if action == 'reject': cur.execute("UPDATE trades SET status='rejected' WHERE id=?", (trade_id,))

    elif action == 'accept':

        proposer = cur.execute("SELECT username, budget FROM users WHERE id=?", (trade["proposer_id"],)).fetchone()

        receiver = cur.execute("SELECT username, budget FROM users WHERE id=?", (trade["receiver_id"],)).fetchone()

        if proposer["budget"] < trade["money_offer"] or receiver["budget"] < trade["money_request"]: conn.close(); return jsonify({"success": False, "error": "Budgets have changed. Trade failed."})

        cur.execute("UPDATE users SET budget = budget - ? + ? WHERE id=?", (trade["money_offer"], trade["money_request"], trade["proposer_id"]))

        cur.execute("UPDATE users SET budget = budget - ? + ? WHERE id=?", (trade["money_request"], trade["money_offer"], trade["receiver_id"]))

        if trade["offered_player_id"]: cur.execute("UPDATE players SET highest_bidder=?, pitch_position=NULL WHERE id=?", (receiver["username"], trade["offered_player_id"]))

        if trade["requested_player_id"]: cur.execute("UPDATE players SET highest_bidder=?, pitch_position=NULL WHERE id=?", (proposer["username"], trade["requested_player_id"]))

        cur.execute("UPDATE trades SET status='accepted' WHERE id=?", (trade_id,))

    conn.commit(); conn.close(); return jsonify({"success": True})



# 🔥 MY SQUAD ROUTE: AGGRESSIVE AUTO-PATCHER ADDED HERE 🔥

@app.route("/my_team")

def my_team():

    conn = get_connection(); cur = conn.cursor()

    

    # Aggressively try to fetch with pitch_theme. If it fails, patch it.

    try:

        user_row = cur.execute("SELECT current_formation, club_name, anthem_url, pitch_theme FROM users WHERE id=?", (session["user_id"],)).fetchone()

    except sqlite3.OperationalError:

        # Patch the database for older active rooms silently

        cur.execute("ALTER TABLE users ADD COLUMN pitch_theme TEXT DEFAULT 'classic'")

        conn.commit()

        user_row = cur.execute("SELECT current_formation, club_name, anthem_url, pitch_theme FROM users WHERE id=?", (session["user_id"],)).fetchone()

        

    players = cur.execute("SELECT * FROM players WHERE highest_bidder=? AND is_sold=1", (session["global_user"],)).fetchall()

    

    theme = user_row["pitch_theme"] if user_row and "pitch_theme" in user_row.keys() else "classic"

        

    conn.close()

    return render_template("my_team.html", players=players, formation=user_row["current_formation"], club_name=user_row["club_name"], anthem_url=user_row["anthem_url"], pitch_theme=theme)



# 🔥 SAVE SQUAD ROUTE: AGGRESSIVE AUTO-PATCHER ADDED HERE 🔥

@app.route("/save_squad_state", methods=["POST"])

def save_squad_state():

    data = request.json; conn = get_connection(); cur = conn.cursor()

    theme = data.get("pitch_theme", "classic")

    

    try:

        cur.execute("UPDATE users SET current_formation=?, club_name=?, anthem_url=?, pitch_theme=? WHERE id=?", (data["formation"], data.get("club_name", ""), data.get("anthem_url", ""), theme, session["user_id"]))

    except sqlite3.OperationalError:

        # Patch the database for older active rooms silently

        cur.execute("ALTER TABLE users ADD COLUMN pitch_theme TEXT DEFAULT 'classic'")

        cur.execute("UPDATE users SET current_formation=?, club_name=?, anthem_url=?, pitch_theme=? WHERE id=?", (data["formation"], data.get("club_name", ""), data.get("anthem_url", ""), theme, session["user_id"]))

        

    cur.execute("UPDATE players SET pitch_position=NULL WHERE highest_bidder=?", (session["global_user"],))

    for position, player_id in data["positions"].items():

        if player_id: cur.execute("UPDATE players SET pitch_position=? WHERE id=?", (position, player_id.replace('player-', '')))

    conn.commit(); conn.close(); return jsonify({"success": True})



@app.route("/export_my_team")

def export_my_team():

    conn = get_connection(); cur = conn.cursor()

    players = cur.execute("SELECT name, rating, position, current_bid, pitch_position FROM players WHERE highest_bidder=? AND is_sold=1 ORDER BY rating DESC", (session["global_user"],)).fetchall()

    conn.close()

    si = io.StringIO(); cw = csv.writer(si)

    cw.writerow(['Player Name', 'Rating', 'Position', 'Auction Price (M)', 'Squad Role'])

    for p in players: cw.writerow([p['name'], p['rating'], p['position'], p['current_bid'], p['pitch_position'] if p['pitch_position'] else 'Bench'])

    output = make_response(si.getvalue()); output.headers["Content-Disposition"] = f"attachment; filename={session['global_user']}_squad.csv"; output.headers["Content-type"] = "text/csv"

    return output



@app.route("/admin_dashboard")

def admin_dashboard():

    if session.get("role") != "admin": return redirect(url_for("auction"))

    conn = get_connection(); cur = conn.cursor()

    players = cur.execute("SELECT * FROM players WHERE is_sold=1 OR auction_status='unsold' ORDER BY sold_time DESC").fetchall()

    users = cur.execute("SELECT * FROM users ORDER BY id ASC").fetchall()

    conn.close()

    

    conn_m = get_master_connection()

    lobby_pin = conn_m.execute("SELECT password FROM rooms WHERE db_file=?", (session["room_db"],)).fetchone()[0]

    conn_m.close()

    return render_template("admin.html", players=players, users=users, room_name=session.get('room_name'), lobby_pin=lobby_pin)



@app.route("/change_pin", methods=["POST"])

def change_pin():

    if session.get("role") != "admin": return redirect(url_for("auction"))

    new_pin = request.form.get("new_pin", "").strip()

    if new_pin:

        conn = get_master_connection()

        conn.execute("UPDATE rooms SET password=? WHERE db_file=?", (new_pin, session["room_db"]))

        conn.commit(); conn.close()

    return redirect(url_for("admin_dashboard"))



@app.route("/reset_player/<int:player_id>", methods=["POST"])

def reset_player(player_id):

    if session.get("role") != "admin": return redirect(url_for("auction"))

    conn = get_connection(); cur = conn.cursor()

    player = cur.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()

    if player:

        if player["is_sold"] == 1 and player["highest_bidder"]: cur.execute("UPDATE users SET budget = budget + ? WHERE username=?", (player["current_bid"], player["highest_bidder"]))

        cur.execute("UPDATE players SET is_sold=0, auction_status='waiting', current_bid=0, highest_bidder=NULL, bid_count=0, sudden_death=0, auction_end_time=0, paused_time_left=0, sold_time=0 WHERE id=?", (player_id,))

        cur.execute("DELETE FROM auction_folds WHERE player_id=?", (player_id,))

        cur.execute("DELETE FROM auction_bidders WHERE player_id=?", (player_id,))

        cur.execute("DELETE FROM blind_bids WHERE player_id=?", (player_id,))

        conn.commit()

    conn.close(); return redirect(url_for("admin_dashboard"))



@app.route("/make_admin/<int:new_admin_id>", methods=["POST"])

def make_admin(new_admin_id):

    if session.get("role") != "admin": return redirect(url_for("auction"))

    conn = get_connection(); cur = conn.cursor()

    cur.execute("UPDATE users SET role='user' WHERE id=?", (session["user_id"],))

    cur.execute("UPDATE users SET role='admin' WHERE id=?", (new_admin_id,))

    conn.commit(); conn.close()

    session["role"] = "user"

    return redirect(url_for("auction"))



@app.route("/hard_reset_draft", methods=["POST"])

def hard_reset_draft():

    if session.get("role") != "admin": return redirect(url_for("auction"))

    conn = get_connection(); cur = conn.cursor()

    cur.execute("UPDATE users SET budget=1000, current_formation='4-4-2'")

    cur.execute("UPDATE players SET is_sold=0, auction_status='waiting', current_bid=0, highest_bidder=NULL, bid_count=0, sudden_death=0, auction_end_time=0, paused_time_left=0, sold_time=0, pitch_position=NULL")

    cur.execute("DELETE FROM auction_folds")

    cur.execute("DELETE FROM auction_bidders")

    cur.execute("DELETE FROM trades")

    cur.execute("DELETE FROM blind_bids")

    cur.execute("UPDATE settings SET value='active' WHERE key='auction_state'")

    cur.execute("UPDATE settings SET value='' WHERE key='last_reaction'")

    conn.commit(); conn.close()

    return redirect(url_for("admin_dashboard"))



@app.route("/delete_user/<int:delete_id>", methods=["POST"])

def delete_user(delete_id):

    if session.get("role") != "admin": return redirect(url_for("auction"))

    if delete_id == session.get("user_id"): return redirect(url_for("admin_dashboard"))

    conn = get_connection(); cur = conn.cursor()

    user = cur.execute("SELECT username FROM users WHERE id=?", (delete_id,)).fetchone()

    if user:

        username = user["username"]

        cur.execute("UPDATE players SET is_sold=0, auction_status='waiting', current_bid=0, highest_bidder=NULL, bid_count=0, sudden_death=0, auction_end_time=0, paused_time_left=0, sold_time=0 WHERE highest_bidder=?", (username,))

        cur.execute("DELETE FROM auction_folds WHERE username=?", (username,))

        cur.execute("DELETE FROM auction_bidders WHERE username=?", (username,))

        cur.execute("DELETE FROM blind_bids WHERE username=?", (username,))

        cur.execute("DELETE FROM trades WHERE proposer_id=? OR receiver_id=?", (delete_id, delete_id))

        cur.execute("DELETE FROM users WHERE id=?", (delete_id,))

        conn.commit()

    conn.close(); return redirect(url_for("admin_dashboard"))



# ════════════════════════════════════════════════════════════════

# USC LEAGUE ROUTES (UPDATED WITH TROPHY CABINET DATA)

# ════════════════════════════════════════════════════════════════



def init_league_tables(conn):

    """Create league_teams and league_matches tables and auto-patch new columns."""

    conn.execute('''CREATE TABLE IF NOT EXISTS league_teams (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        name TEXT NOT NULL,

        manager TEXT DEFAULT '',

        emoji TEXT DEFAULT '⚽',

        created_at INTEGER DEFAULT 0

    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS league_matches (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        home_id INTEGER NOT NULL,

        away_id INTEGER NOT NULL,

        home_score INTEGER DEFAULT 0,

        away_score INTEGER DEFAULT 0,

        matchday INTEGER DEFAULT 1,

        played_at INTEGER DEFAULT 0,

        h_scorers TEXT DEFAULT '',

        a_scorers TEXT DEFAULT '',

        motm TEXT DEFAULT ''

    )''')

    

    # Auto-patcher to add new columns to existing databases seamlessly

    cur = conn.cursor()

    try: cur.execute("ALTER TABLE league_matches ADD COLUMN h_scorers TEXT DEFAULT ''")

    except sqlite3.OperationalError: pass

    try: cur.execute("ALTER TABLE league_matches ADD COLUMN a_scorers TEXT DEFAULT ''")

    except sqlite3.OperationalError: pass

    try: cur.execute("ALTER TABLE league_matches ADD COLUMN motm TEXT DEFAULT ''")

    except sqlite3.OperationalError: pass

    

    conn.commit()



@app.route("/league")

def league():

    conn = get_connection()

    if not conn:

        return redirect(url_for("hub"))

    cur = conn.cursor()

    init_league_tables(conn)



    most_expensive = cur.execute(

        "SELECT * FROM players WHERE is_sold=1 ORDER BY current_bid DESC, rating DESC LIMIT 1"

    ).fetchone()

    biggest_steal = cur.execute(

        "SELECT * FROM players WHERE is_sold=1 AND current_bid > 0 ORDER BY (CAST(rating AS FLOAT)/current_bid) DESC LIMIT 1"

    ).fetchone()

    total_spent = cur.execute(

        "SELECT COALESCE(SUM(current_bid), 0) FROM players WHERE is_sold=1"

    ).fetchone()[0] or 0

    total_sold = cur.execute(

        "SELECT COUNT(*) FROM players WHERE is_sold=1"

    ).fetchone()[0] or 0



    users = cur.execute("SELECT username, budget FROM users").fetchall()

    teams = []

    champion = {"username": "TBD", "avg_rating": 0, "squad": [], "spent": 0, "player_count": 0, "budget": 0}

    big_spender = {"username": "TBD", "spent": 0}



    for u in users:

        squad = cur.execute(

            "SELECT * FROM players WHERE highest_bidder=? AND is_sold=1 ORDER BY rating DESC",

            (u["username"],)

        ).fetchall()

        top_11 = squad[:11]

        avg_rating = round(sum(p["rating"] for p in top_11) / len(top_11), 1) if top_11 else 0

        spent = sum(p["current_bid"] for p in squad)

        if spent > big_spender["spent"]:

            big_spender = {"username": u["username"], "spent": spent}

        teams.append({"username": u["username"], "budget": u["budget"], "squad": squad,

                       "avg_rating": avg_rating, "player_count": len(squad), "spent": spent})

        if avg_rating > champion["avg_rating"]:

            champion = {"username": u["username"], "avg_rating": avg_rating, "squad": top_11,

                        "spent": spent, "player_count": len(squad), "budget": u["budget"]}



    teams = sorted(teams, key=lambda x: x["avg_rating"], reverse=True)

    all_ratings = [t["avg_rating"] for t in teams if t["avg_rating"] > 0]

    avg_rating_overall = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else 0



    teams_json = json.dumps([{

        "username": t["username"], "avg_rating": t["avg_rating"],

        "player_count": t["player_count"], "spent": t["spent"], "budget": t["budget"],

        "squad": [{"name": p["name"], "rating": p["rating"], "position": p["position"]} for p in (t["squad"] or [])]

    } for t in teams])



    conn.close()

    return render_template("league.html",

        teams=teams, teams_json=teams_json, champion=champion,

        big_spender=big_spender, most_expensive=most_expensive,

        biggest_steal=biggest_steal, total_spent=total_spent,

        total_sold=total_sold, avg_rating=avg_rating_overall)



@app.route("/api/league_data")

def api_league_data():

    conn = get_connection()

    if not conn:

        return jsonify({"teams": [], "matches": []})

    init_league_tables(conn)

    cur = conn.cursor()

    

    teams = [dict(r) for r in cur.execute("SELECT * FROM league_teams ORDER BY created_at ASC").fetchall()]

    

    raw_matches = cur.execute("SELECT * FROM league_matches ORDER BY matchday ASC, played_at ASC").fetchall()

    matches = []

    

    for r in raw_matches:

        m = dict(r)

        # Re-mapping data for Javascript calculation logic

        m['hs'] = m['home_score']

        m['as'] = m['away_score']

        m['h_scorers'] = m['h_scorers'].split(',') if m.get('h_scorers') else []

        m['a_scorers'] = m['a_scorers'].split(',') if m.get('a_scorers') else []

        m['motm'] = m.get('motm', '')

        matches.append(m)

        

    conn.close()

    return jsonify({"teams": teams, "matches": matches})



@app.route("/league/add_team", methods=["POST"])

def league_add_team():

    conn = get_connection()

    if not conn:

        return jsonify({"success": False})

    init_league_tables(conn)

    data = request.get_json()

    name = data.get("name", "").strip().upper()

    manager = data.get("manager", "").strip()

    emoji = data.get("emoji", "⚽")

    if not name:

        conn.close()

        return jsonify({"success": False, "error": "Name required"})

    cur = conn.cursor()

    cur.execute("INSERT INTO league_teams (name, manager, emoji, created_at) VALUES (?, ?, ?, ?)",

                (name, manager, emoji, int(time.time())))

    conn.commit()

    new_id = cur.lastrowid

    conn.close()

    return jsonify({"success": True, "id": new_id})



@app.route("/league/add_result", methods=["POST"])

def league_add_result():

    conn = get_connection()

    if not conn:

        return jsonify({"success": False})

    init_league_tables(conn)

    data = request.get_json()

    cur = conn.cursor()

    

    # Process arrays into comma-separated strings for SQLite

    h_scorers_str = ",".join(data.get("h_scorers", []))

    a_scorers_str = ",".join(data.get("a_scorers", []))

    motm_str = data.get("motm", "")

    

    cur.execute(

        "INSERT INTO league_matches (home_id, away_id, home_score, away_score, matchday, played_at, h_scorers, a_scorers, motm) VALUES (?,?,?,?,?,?,?,?,?)",

        (data["home_id"], data["away_id"], data["home_score"], data["away_score"],

         data.get("matchday", 1), int(time.time()), h_scorers_str, a_scorers_str, motm_str)

    )

    conn.commit()

    new_id = cur.lastrowid

    conn.close()

    return jsonify({"success": True, "id": new_id})



@app.route("/league/delete_team/<int:team_id>", methods=["POST"])

def league_delete_team(team_id):

    conn = get_connection()

    if not conn:

        return jsonify({"success": False})

    init_league_tables(conn)

    cur = conn.cursor()

    cur.execute("DELETE FROM league_teams WHERE id=?", (team_id,))

    cur.execute("DELETE FROM league_matches WHERE home_id=? OR away_id=?", (team_id, team_id))

    conn.commit()

    conn.close()

    return jsonify({"success": True})



if __name__ == "__main__":

    socketio.run(app, debug=True, host='0.0.0.0', port=5000)















