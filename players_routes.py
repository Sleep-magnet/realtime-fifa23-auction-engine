from flask import Blueprint, render_template, request, redirect, url_for
import sqlite3

players_bp = Blueprint('players', __name__)

def get_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


@players_bp.route("/")
def home():
    return redirect(url_for("players.players_page"))


@players_bp.route("/players")
def players_page():

    position = request.args.get("position")
    min_rating = request.args.get("rating")

    conn = get_connection()
    cur = conn.cursor()

    query = "SELECT * FROM players WHERE rating >= 77 AND is_sold = 0"
    params = []

    if position and position != "All":
        query += " AND position = ?"
        params.append(position)

    if min_rating:
        query += " AND rating >= ?"
        params.append(min_rating)

    query += " ORDER BY rating DESC"

    cur.execute(query, params)
    players = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM players WHERE is_sold = 1")
    sold_count = cur.fetchone()[0]

    conn.close()

    return render_template(
        "players.html",
        players=players,
        sold_count=sold_count,
        selected_position=position,
        selected_rating=min_rating
    )


@players_bp.route("/sell/<int:player_id>")
def sell_player(player_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "UPDATE players SET is_sold = 1, sold_to='Admin' WHERE id=?",
        (player_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("players.players_page"))


@players_bp.route("/unsell/<int:player_id>")
def unsell_player(player_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "UPDATE players SET is_sold=0, sold_to=NULL, current_bid=0 WHERE id=?",
        (player_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("players.sold_players"))


@players_bp.route("/reset_all_sold")
def reset_all_sold():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE players
        SET is_sold = 0,
            sold_to = NULL,
            current_bid = 0
        WHERE is_sold = 1
    """)

    conn.commit()
    conn.close()

    return redirect(url_for("players.players_page"))


@players_bp.route("/sold")
def sold_players():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM players WHERE is_sold = 1 ORDER BY rating DESC")
    players = cur.fetchall()

    conn.close()

    return render_template("sold.html", players=players)