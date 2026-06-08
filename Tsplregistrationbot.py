#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import asyncio
import logging
import sqlite3
import warnings
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode

warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURATION
# ============================================================

BOT_TOKEN = "8703006263:AAGG8bn7tOsyui6esJkqHFm8XsESgir6mrI"
ADMIN_IDS = [7691071175]
CHANNEL_ID = -1003947078545
PHOTO_FILE = "pfp.jpg"
MAX_PLAYERS_PER_LINK = 24

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

PLAYER_TYPE, CONFIRM = range(2)

# ============================================================
# DATABASE CLASS - PERFECT
# ============================================================

class Database:
    def __init__(self):
        self.conn = sqlite3.connect("tspl_reg.db", check_same_thread=False)
        self.cursor = self.conn.cursor()
        # Drop old tables and recreate fresh
        self.cursor.executescript("""
            DROP TABLE IF EXISTS players;
            DROP TABLE IF EXISTS settings;
            DROP TABLE IF EXISTS special_users;
            DROP TABLE IF EXISTS links;
        """)
        self.conn.commit()
        self._create_tables()

    def _create_tables(self):
        self.cursor.executescript("""
            CREATE TABLE players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                username TEXT DEFAULT 'N/A',
                full_name TEXT,
                player_type TEXT DEFAULT 'unknown',
                registration_number INTEGER UNIQUE,
                link_number INTEGER DEFAULT 1,
                registered_at TEXT
            );
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE special_users (
                user_id INTEGER PRIMARY KEY
            );
            CREATE TABLE links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link_number INTEGER UNIQUE,
                invite_link TEXT,
                created_at TEXT
            );
        """)
        self.conn.commit()
        self.cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_status', 'on')")
        self.conn.commit()

    def is_bot_on(self):
        self.cursor.execute("SELECT value FROM settings WHERE key='bot_status'")
        row = self.cursor.fetchone()
        if row:
            return row[0] == "on"
        return True

    def set_bot_status(self, status):
        self.cursor.execute("UPDATE settings SET value=? WHERE key='bot_status'", (status,))
        self.conn.commit()

    def get_total_players(self):
        self.cursor.execute("SELECT COUNT(*) FROM players")
        row = self.cursor.fetchone()
        if row:
            return row[0] or 0
        return 0

    def get_players_in_link(self, link_no):
        self.cursor.execute("SELECT COUNT(*) FROM players WHERE link_number=?", (link_no,))
        row = self.cursor.fetchone()
        if row:
            return row[0] or 0
        return 0

    def get_link_for_registration(self, reg_no):
        result = ((reg_no - 1) // MAX_PLAYERS_PER_LINK) + 1
        return result

    def get_link(self, link_no):
        self.cursor.execute("SELECT * FROM links WHERE link_number=?", (link_no,))
        row = self.cursor.fetchone()
        if not row:
            return None
        return {"link_number": row[1], "invite_link": row[2], "created_at": row[3]}

    def save_link(self, link_no, invite_link):
        now = datetime.now().isoformat()
        existing = self.get_link(link_no)
        if existing:
            self.cursor.execute("UPDATE links SET invite_link=?, created_at=? WHERE link_number=?", (invite_link, now, link_no))
        else:
            self.cursor.execute("INSERT INTO links (link_number, invite_link, created_at) VALUES (?, ?, ?)", (link_no, invite_link, now))
        self.conn.commit()

    def delete_link(self, link_no):
        self.cursor.execute("DELETE FROM links WHERE link_number=?", (link_no,))
        self.conn.commit()

    def add_player(self, user_id, username, full_name, ptype):
        self.cursor.execute("SELECT id FROM players WHERE user_id=?", (user_id,))
        if self.cursor.fetchone():
            return None
        self.cursor.execute("SELECT MAX(registration_number) FROM players")
        row = self.cursor.fetchone()
        max_reg = 0
        if row and row[0]:
            max_reg = row[0]
        reg_no = max_reg + 1
        link_no = self.get_link_for_registration(reg_no)
        now = datetime.now().isoformat()
        self.cursor.execute("INSERT INTO players (user_id, username, full_name, player_type, registration_number, link_number, registered_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, username, full_name, ptype, reg_no, link_no, now))
        self.conn.commit()
        total = self.get_players_in_link(link_no)
        return {"reg_no": reg_no, "link_no": link_no, "total_in_link": total}

    def get_player(self, user_id):
        self.cursor.execute("SELECT * FROM players WHERE user_id=?", (user_id,))
        row = self.cursor.fetchone()
        if not row:
            return None
        ptype = row[4]
        if not ptype:
            ptype = "unknown"
        return {"user_id": row[1], "username": row[2], "full_name": row[3], "player_type": ptype, "reg_no": row[5], "link_no": row[6], "registered_at": row[7]}

    def get_all_players(self):
        self.cursor.execute("SELECT * FROM players ORDER BY registration_number ASC")
        result = []
        for r in self.cursor.fetchall():
            ptype = r[4]
            if not ptype:
                ptype = "unknown"
            result.append({"user_id": r[1], "username": r[2], "full_name": r[3], "player_type": ptype, "reg_no": r[5], "link_no": r[6], "registered_at": r[7]})
        return result

    def get_players_by_link(self, link_no):
        self.cursor.execute("SELECT * FROM players WHERE link_number=? ORDER BY registration_number ASC", (link_no,))
        result = []
        for r in self.cursor.fetchall():
            ptype = r[4]
            if not ptype:
                ptype = "unknown"
            result.append({"user_id": r[1], "username": r[2], "full_name": r[3], "player_type": ptype, "reg_no": r[5], "link_no": r[6], "registered_at": r[7]})
        return result

    def get_player_by_reg(self, reg_no):
        self.cursor.execute("SELECT * FROM players WHERE registration_number=?", (reg_no,))
        row = self.cursor.fetchone()
        if not row:
            return None
        ptype = row[4]
        if not ptype:
            ptype = "unknown"
        return {"user_id": row[1], "username": row[2], "full_name": row[3], "player_type": ptype, "reg_no": row[5], "link_no": row[6], "registered_at": row[7]}

    def remove_player_by_reg(self, reg_no):
        self.cursor.execute("DELETE FROM players WHERE registration_number=?", (reg_no,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def add_special_user(self, user_id):
        self.cursor.execute("INSERT OR IGNORE INTO special_users (user_id) VALUES (?)", (user_id,))
        self.conn.commit()

    def remove_special_user(self, user_id):
        self.cursor.execute("DELETE FROM special_users WHERE user_id=?", (user_id,))
        self.conn.commit()

    def get_special_users(self):
        self.cursor.execute("SELECT user_id FROM special_users")
        return [r[0] for r in self.cursor.fetchall()]

    def get_all_links(self):
        self.cursor.execute("SELECT * FROM links ORDER BY link_number ASC")
        return [{"link_number": r[1], "invite_link": r[2], "created_at": r[3]} for r in self.cursor.fetchall()]

    def is_link_full(self, link_no):
        return self.get_players_in_link(link_no) >= MAX_PLAYERS_PER_LINK


db = Database()

def bold(text):
    return "<b>" + text + "</b>"

def safe_upper(text):
    if text is None:
        return "UNKNOWN"
    return str(text).upper()
    # ============================================================
# USER HANDLERS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_bot_on():
        await update.message.reply_text("Bot is currently OFF.", parse_mode=ParseMode.HTML)
        return

    user = update.effective_user
    existing = db.get_player(user.id)
    if existing:
        link = db.get_link(existing["link_no"])
        link_url = "No link set yet by admin"
        if link:
            link_url = link["invite_link"]
        msg = "You are already registered!\n\n"
        msg += "Name: " + bold(existing["full_name"]) + "\n"
        msg += "Reg No: " + bold("#" + str(existing["reg_no"])) + "\n"
        msg += "Role: " + bold(safe_upper(existing["player_type"])) + "\n"
        msg += "Team Link #" + bold(str(existing["link_no"])) + "\n"
        msg += "Join: " + link_url
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        return

    total = db.get_total_players()
    reg_no = total + 1
    link_no = db.get_link_for_registration(reg_no)

    caption = "TSPL TOUR\n\n"
    caption += "Welcome to TSPL Tour Registration Bot!\n\n"
    caption += "How to Register?\n"
    caption += "1. /register\n"
    caption += "2. Choose Batsman / Bowler / Allrounder\n"
    caption += "3. Confirm\n\n"
    caption += "You will get Registration Number #" + str(reg_no) + "\n"
    caption += "Link #" + str(link_no) + " - Players: " + str(db.get_players_in_link(link_no)) + "/" + str(MAX_PLAYERS_PER_LINK) + "\n\n"
    caption += "Powered by TSPL TOUR Management\n\n"
    caption += "Sponsered By CID Network (@CIDTEAMZS)"

    try:
        with open(PHOTO_FILE, "rb") as photo:
            await update.message.reply_photo(photo=photo, caption=caption, parse_mode=ParseMode.HTML)
    except FileNotFoundError:
        await update.message.reply_text(caption, parse_mode=ParseMode.HTML)


async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_bot_on():
        await update.message.reply_text("Bot is currently OFF.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    user = update.effective_user
    existing = db.get_player(user.id)
    if existing:
        msg = "Already Registered!\n"
        msg += "Reg No: " + bold("#" + str(existing["reg_no"])) + "\n"
        msg += "Type: " + bold(safe_upper(existing["player_type"]))
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Batsman", callback_data="type_batsman")],
        [InlineKeyboardButton("Bowler", callback_data="type_bowler")],
        [InlineKeyboardButton("Allrounder", callback_data="type_allrounder")],
        [InlineKeyboardButton("Cancel", callback_data="type_cancel")]
    ]

    await update.message.reply_text(
        "TSPL TOUR - Player Registration\n\nSelect your Player Type:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return PLAYER_TYPE


async def type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "type_cancel":
        await query.edit_message_text("Registration cancelled.")
        return ConversationHandler.END

    ptype = query.data.replace("type_", "")
    context.user_data["player_type"] = ptype

    user = update.effective_user
    username = user.username or "N/A"
    full_name = user.full_name

    total = db.get_total_players()
    next_reg = total + 1
    link_no = db.get_link_for_registration(next_reg)

    msg = "Registration Summary\n\n"
    msg += "Name: " + bold(full_name) + "\n"
    msg += "Username: @" + username + "\n"
    msg += "Role: " + bold(ptype.upper()) + "\n"
    msg += "Registration #" + bold(str(next_reg)) + "\n"
    msg += "Team Link #" + bold(str(link_no)) + "\n\n"
    msg += "Press Confirm to complete registration."

    keyboard = [
        [InlineKeyboardButton("Confirm", callback_data="confirm_yes")],
        [InlineKeyboardButton("Cancel", callback_data="confirm_no")]
    ]

    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRM


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        await query.edit_message_text("Registration cancelled.")
        return ConversationHandler.END

    user = update.effective_user
    username = user.username or "N/A"
    full_name = user.full_name
    ptype = context.user_data.get("player_type", "unknown")

    result = db.add_player(user.id, username, full_name, ptype)
    if not result:
        await query.edit_message_text("Registration Failed! You may already be registered.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    reg_no = result["reg_no"]
    link_no = result["link_no"]
    total_in_link = result["total_in_link"]

    link = db.get_link(link_no)
    link_url = "Link not set yet. Contact admin."
    if link:
        link_url = link["invite_link"]

    msg = "Registration Successful!\n\n"
    msg += "Name: " + bold(full_name) + "\n"
    msg += "Registration No: " + bold("#" + str(reg_no)) + "\n"
    msg += "Role: " + bold(ptype.upper()) + "\n"
    msg += "Team Link #" + bold(str(link_no)) + "\n"
    msg += "Link: " + link_url + "\n"
    msg += "Players in Team #" + str(link_no) + ": " + str(total_in_link) + "/" + str(MAX_PLAYERS_PER_LINK) + "\n\n"
    msg += "Send join request to the group link above.\nAdmin will approve manually.\n\n"
    msg += "Thank you for registering with TSPL TOUR! Join @Tsplregistration!\n\n"
    msg += "Sponsered By CID Network (@CIDTEAMZS)"

    await query.edit_message_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    # Channel forward
    channel_text = "TSPL TOUR - New Registration\n\n"
    channel_text += "Name: " + bold(full_name) + "\n"
    channel_text += "Username: @" + username + "\n"
    channel_text += "Reg No: " + bold("#" + str(reg_no)) + "\n"
    channel_text += "Role: " + bold(ptype.upper()) + "\n"
    channel_text += "Link #: " + bold(str(link_no)) + "\n"
    channel_text += "Players: " + str(total_in_link) + "/" + str(MAX_PLAYERS_PER_LINK) + "\n"
    channel_text += "Time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        if os.path.exists(PHOTO_FILE):
            with open(PHOTO_FILE, "rb") as photo:
                await context.bot.send_photo(CHANNEL_ID, photo=photo, caption=channel_text, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(CHANNEL_ID, text=channel_text, parse_mode=ParseMode.HTML)
    except:
        pass

    if db.is_link_full(link_no):
        next_link_no = link_no + 1
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=bold("Team #" + str(link_no) + " is FULL!") + "\n\n"
                         "Total: " + str(total_in_link) + "/" + str(MAX_PLAYERS_PER_LINK) + "\n"
                         "Next player will go to Team #" + str(next_link_no) + "\n\n"
                         "Set the next link:\n/setlink_" + str(next_link_no) + " [invite_link]",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.", parse_mode=ParseMode.HTML)
    return ConversationHandler.END


async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    p = db.get_player(user.id)
    if not p:
        await update.message.reply_text("You are not registered. Use /register to sign up!", parse_mode=ParseMode.HTML)
        return

    link = db.get_link(p["link_no"])
    link_url = "No link set yet"
    if link:
        link_url = link["invite_link"]

    msg = "Your Profile\n\n"
    msg += "Reg No: " + bold("#" + str(p["reg_no"])) + "\n"
    msg += "Name: " + bold(p["full_name"]) + "\n"
    msg += "Role: " + bold(safe_upper(p["player_type"])) + "\n"
    msg += "Team Link #" + bold(str(p["link_no"])) + "\n"
    msg += "Link: " + link_url + "\n"
    msg += "Registered: " + p["registered_at"]

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    # ============================================================
# ADMIN COMMANDS
# ============================================================

async def admin_setlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    command_part = parts[0]
    link_url = ""
    if len(parts) > 1:
        link_url = parts[1]

    if not link_url:
        await update.message.reply_text("Usage: /setlink_1 https://t.me/your_group_link")
        return

    try:
        link_no = int(command_part.replace("/setlink_", ""))
    except:
        await update.message.reply_text("Usage: /setlink_1 <url>, /setlink_2 <url>, etc.")
        return

    if link_no < 1:
        await update.message.reply_text("Link number must be positive.")
        return

    if not link_url.startswith("https://t.me/"):
        await update.message.reply_text("Invalid link! Link must start with https://t.me/")
        return

    db.save_link(link_no, link_url)

    players_in_link = db.get_players_in_link(link_no)
    total_players = db.get_total_players()
    start_reg = ((link_no - 1) * MAX_PLAYERS_PER_LINK) + 1
    end_reg = link_no * MAX_PLAYERS_PER_LINK

    msg = "Link #" + str(link_no) + " set successfully!\n\n"
    msg += "Link: " + link_url + "\n\n"
    msg += "Stats:\n"
    msg += "Players: " + str(players_in_link) + "/" + str(MAX_PLAYERS_PER_LINK) + "\n"
    msg += "Total registered: " + str(total_players) + "\n"
    msg += "Range: Registration #" + str(start_reg) + " - #" + str(end_reg) + "\n\n"
    msg += "Players in this link: /players_" + str(link_no)

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def admin_dellink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    try:
        link_no = int(" ".join(context.args))
    except:
        await update.message.reply_text("Usage: /dellink <link_number>")
        return

    if not db.get_link(link_no):
        await update.message.reply_text("Link #" + str(link_no) + " not found.", parse_mode=ParseMode.HTML)
        return

    db.delete_link(link_no)
    await update.message.reply_text("Link #" + str(link_no) + " removed from database.", parse_mode=ParseMode.HTML)


async def admin_players_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    command = update.message.text.split()[0]
    try:
        link_no = int(command.replace("/players_", ""))
    except:
        await update.message.reply_text("Usage: /players_1, /players_2, etc.")
        return

    players = db.get_players_by_link(link_no)
    link = db.get_link(link_no)

    if not link:
        await update.message.reply_text("Link #" + str(link_no) + " not set. Use /setlink_" + str(link_no) + " <url> first.", parse_mode=ParseMode.HTML)
        return

    msg = "Link #" + str(link_no) + "\n"
    msg += "URL: " + link["invite_link"] + "\n"
    msg += "Players: " + str(len(players)) + "/" + str(MAX_PLAYERS_PER_LINK) + "\n\n"

    if not players:
        msg += "No players in this link yet."
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        return

    msg += "Players:\n"
    for p in players:
        msg += "#" + str(p["reg_no"]) + " - " + p["full_name"][:20] + " (" + safe_upper(p["player_type"]) + ")\n"

    if len(msg) > 4000:
        filename = "players_link_" + str(link_no) + ".txt"
        with open(filename, "w") as f:
            f.write(msg.replace("<b>", "").replace("</b>", ""))
        with open(filename, "rb") as f:
            await update.message.reply_document(f, caption="Players - Link #" + str(link_no))
        os.remove(filename)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    # Clickable buttons
    keyboard = []
    row = []
    for i, p in enumerate(players):
        btn_text = "#" + str(p["reg_no"]) + " " + p["full_name"][:10]
        row.append(InlineKeyboardButton(btn_text, url="tg://user?id=" + str(p["user_id"])))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    if keyboard:
        await update.message.reply_text("Tap on player name to view profile:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def admin_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    links = db.get_all_links()
    if not links:
        await update.message.reply_text("No links set yet. Use /setlink_1 <url>")
        return

    msg = "TSPL TOUR - All Links\n\n"
    for ln in sorted(links, key=lambda x: x["link_number"]):
        players = db.get_players_in_link(ln["link_number"])
        status = ""
        if players >= MAX_PLAYERS_PER_LINK:
            status = " [FULL]"
        start_reg = ((ln["link_number"] - 1) * MAX_PLAYERS_PER_LINK) + 1
        end_reg = ln["link_number"] * MAX_PLAYERS_PER_LINK
        msg += "Link #" + str(ln["link_number"]) + status + "\n"
        msg += "   Players: " + str(players) + "/" + str(MAX_PLAYERS_PER_LINK) + "\n"
        msg += "   Range: #" + str(start_reg) + " - #" + str(end_reg) + "\n\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def admin_linkhistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    links = db.get_all_links()
    if not links:
        await update.message.reply_text("No links set yet.")
        return

    for ln in sorted(links, key=lambda x: x["link_number"]):
        players = db.get_players_by_link(ln["link_number"])
        if len(players) < MAX_PLAYERS_PER_LINK:
            status = "ACTIVE"
        else:
            status = "FULL"

        msg = "Link #" + str(ln["link_number"]) + " [" + status + "]\n"
        msg += "Players: " + str(len(players)) + "/" + str(MAX_PLAYERS_PER_LINK) + "\n"
        msg += "URL: " + ln["invite_link"] + "\n"

        if players:
            msg += "\nPlayers:\n"
            for p in players:
                msg += "  #" + str(p["reg_no"]) + " - " + p["full_name"][:20] + " (" + safe_upper(p["player_type"]) + ")\n"

            if len(msg) > 3500:
                filename = "link_" + str(ln["link_number"]) + ".txt"
                with open(filename, "w") as f:
                    f.write(msg.replace("<b>", "").replace("</b>", ""))
                with open(filename, "rb") as f:
                    await update.message.reply_document(f, caption="Link #" + str(ln["link_number"]) + " Players")
                os.remove(filename)
            else:
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

            keyboard = []
            row = []
            for i, p in enumerate(players):
                btn_text = "#" + str(p["reg_no"]) + " " + p["full_name"][:10]
                row.append(InlineKeyboardButton(btn_text, url="tg://user?id=" + str(p["user_id"])))
                if (i + 1) % 2 == 0:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)

            if keyboard:
                await update.message.reply_text("Tap on player name to view profile:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        await asyncio.sleep(0.5)


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    players = db.get_all_players()
    success = 0
    for p in players:
        try:
            await context.bot.send_message(chat_id=p["user_id"], text="TSPL TOUR Broadcast\n\n" + text, parse_mode=ParseMode.HTML)
            success += 1
        except:
            pass

    await update.message.reply_text("Broadcast sent to " + str(success) + "/" + str(len(players)) + " players.")


async def admin_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    try:
        reg_no = int(" ".join(context.args))
    except:
        await update.message.reply_text("Usage: /remove <registration_number>")
        return

    if db.remove_player_by_reg(reg_no):
        await update.message.reply_text("Player #" + str(reg_no) + " removed successfully.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("Player #" + str(reg_no) + " not found.", parse_mode=ParseMode.HTML)


async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    players = db.get_all_players()
    if not players:
        await update.message.reply_text("No players registered yet.")
        return

    text = "TSPL TOUR - All Players\n\n"
    for p in players:
        text += "#" + str(p["reg_no"]) + " | " + p["full_name"][:15] + " | @" + p["username"] + " | " + safe_upper(p["player_type"]) + " | Link #" + str(p["link_no"]) + "\n"

    if len(text) > 4000:
        with open("players.txt", "w") as f:
            f.write(text.replace("<b>", "").replace("</b>", ""))
        with open("players.txt", "rb") as f:
            await update.message.reply_document(f, caption="Full Player List")
        os.remove("players.txt")
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def admin_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    db.set_bot_status("on")
    await update.message.reply_text("Bot is now ON.", parse_mode=ParseMode.HTML)


async def admin_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    db.set_bot_status("off")
    await update.message.reply_text("Bot is now OFF.", parse_mode=ParseMode.HTML)


async def admin_smsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage:\n/smsg <user_id> <message>\n/smsg reg <reg_no> <message>")
        return

    target = args[0]
    text = " ".join(args[1:])

    user_id = None
    if target.lower() == "reg" and len(args) > 2:
        reg_no = int(args[1])
        text = " ".join(args[2:])
        p = db.get_player_by_reg(reg_no)
        if p:
            user_id = p["user_id"]
        else:
            await update.message.reply_text("Player with Registration #" + str(reg_no) + " not found.", parse_mode=ParseMode.HTML)
            return
    else:
        try:
            user_id = int(target)
        except:
            await update.message.reply_text("Invalid user_id. Use a number or 'reg <number>'.")
            return

    try:
        p = db.get_player(user_id)
        name = "User"
        if p:
            name = p["full_name"]
        await context.bot.send_message(chat_id=user_id, text="Special Message from Admin\n\n" + text, parse_mode=ParseMode.HTML)
        await update.message.reply_text("Message sent to " + name + " (ID: " + str(user_id) + ")", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text("Failed to send message. Error: " + str(e), parse_mode=ParseMode.HTML)


async def admin_add_special(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    try:
        uid = int(" ".join(context.args))
    except:
        await update.message.reply_text("Usage: /addspecial <user_id>")
        return

    db.add_special_user(uid)
    await update.message.reply_text("User " + str(uid) + " added to special list.", parse_mode=ParseMode.HTML)


async def admin_remove_special(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    try:
        uid = int(" ".join(context.args))
    except:
        await update.message.reply_text("Usage: /removespecial <user_id>")
        return

    db.remove_special_user(uid)
    await update.message.reply_text("User " + str(uid) + " removed from special list.", parse_mode=ParseMode.HTML)


async def admin_list_special(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    users = db.get_special_users()
    if not users:
        await update.message.reply_text("No special users.")
        return

    text = "Special Users:\n\n"
    for u in users:
        p = db.get_player(u)
        name = "Not registered"
        if p:
            name = p["full_name"]
        text += "- " + str(u) + " (" + name + ")\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def admin_special_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /smsgall <message>")
        return

    users = db.get_special_users()
    if not users:
        await update.message.reply_text("No special users added. Use /addspecial <user_id>")
        return

    success = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text="Special Message from Admin\n\n" + text, parse_mode=ParseMode.HTML)
            success += 1
        except:
            pass

    await update.message.reply_text("Sent to " + str(success) + "/" + str(len(users)) + " special users.")


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    text = "Admin Commands\n\n"
    text += "LINKS (unlimited)\n"
    text += "/setlink_1 [url] - Set Link #1\n"
    text += "/setlink_2 [url] - Set Link #2\n"
    text += "... upto /setlink_100\n"
    text += "/dellink [N] - Remove link\n"
    text += "/links - Show all links\n"
    text += "/linkhistory - Full details\n"
    text += "/players_1 - Players in Link #1\n\n"
    text += "PLAYERS\n"
    text += "/list - All players\n"
    text += "/remove [reg] - Remove player\n"
    text += "/broadcast [msg] - Message to all\n\n"
    text += "SPECIAL USERS\n"
    text += "/addspecial [id] - Add special user\n"
    text += "/removespecial [id] - Remove\n"
    text += "/listspecial - List all special\n"
    text += "/smsgall [msg] - Message to all special\n"
    text += "/smsg [id] [msg] - Message to one\n"
    text += "/smsg reg [no] [msg] - By reg number\n\n"
    text += "SETTINGS\n"
    text += "/on - Turn bot ON\n"
    text += "/off - Turn bot OFF\n"
    text += "/admin - This menu"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ============================================================
# MAIN
# ============================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            PLAYER_TYPE: [CallbackQueryHandler(type_callback, pattern="^type_")],
            CONFIRM: [CallbackQueryHandler(confirm_callback, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=False,
        per_message=False
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("myinfo", myinfo))

    for i in range(1, 101):
        app.add_handler(CommandHandler("setlink_" + str(i), admin_setlink))
        app.add_handler(CommandHandler("players_" + str(i), admin_players_link))

    app.add_handler(CommandHandler("dellink", admin_dellink))
    app.add_handler(CommandHandler("links", admin_links))
    app.add_handler(CommandHandler("linkhistory", admin_linkhistory))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("remove", admin_remove))
    app.add_handler(CommandHandler("list", admin_list))
    app.add_handler(CommandHandler("on", admin_on))
    app.add_handler(CommandHandler("off", admin_off))
    app.add_handler(CommandHandler("smsg", admin_smsg))
    app.add_handler(CommandHandler("smsgall", admin_special_broadcast))
    app.add_handler(CommandHandler("addspecial", admin_add_special))
    app.add_handler(CommandHandler("removespecial", admin_remove_special))
    app.add_handler(CommandHandler("listspecial", admin_list_special))
    app.add_handler(CommandHandler("admin", admin_help))

    logger.info("TSPL TOUR Bot started successfully!")
    app.run_polling()


if __name__ == "__main__":
    main()