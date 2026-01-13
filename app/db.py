import sqlite3
import os
import click
from flask import g, current_app
from werkzeug.security import generate_password_hash

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    
    # 启用外键支持
    db.execute("PRAGMA foreign_keys = ON")

    # 用户表
    db.execute('''CREATE TABLE IF NOT EXISTS users
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT NOT NULL UNIQUE,
                   password_hash TEXT NOT NULL)''')
                  
    # 账号表
    db.execute('''CREATE TABLE IF NOT EXISTS accounts 
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                   email TEXT NOT NULL, 
                   auth_code TEXT NOT NULL,
                   user_id INTEGER,
                   FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL)''')

    # Migration: Check if user_id column exists
    cursor = db.execute("PRAGMA table_info(accounts)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'user_id' not in columns:
        db.execute("ALTER TABLE accounts ADD COLUMN user_id INTEGER")
    
    # Migration: Check if status column exists
    if 'status' not in columns:
        db.execute("ALTER TABLE accounts ADD COLUMN status TEXT DEFAULT 'unknown'")

    # Migration: Check if has_new_mail column exists
    if 'has_new_mail' not in columns:
        db.execute("ALTER TABLE accounts ADD COLUMN has_new_mail INTEGER DEFAULT 0")

    # Migration: Check if last_mail_identifier column exists
    if 'last_mail_identifier' not in columns:
        db.execute("ALTER TABLE accounts ADD COLUMN last_mail_identifier TEXT")

    # 审计日志表
    db.execute('''CREATE TABLE IF NOT EXISTS audit_logs
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT NOT NULL,
                   action TEXT NOT NULL,
                   details TEXT,
                   ip_address TEXT,
                   timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
                   
    # 系统设置表 (用于存隔离模式开关)
    db.execute('''CREATE TABLE IF NOT EXISTS system_settings
                  (key TEXT PRIMARY KEY,
                   value TEXT NOT NULL)''')

    # 预置 Admin
    if not db.execute('SELECT id FROM users WHERE username = ?', ('admin',)).fetchone():
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                   ('admin', generate_password_hash('admin')))
    
    # 预置 renjie
    if not db.execute('SELECT id FROM users WHERE username = ?', ('renjie',)).fetchone():
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                   ('renjie', generate_password_hash('Weirenjie200029@')))
                   
    # 预置隔离模式 (默认关闭 '0')
    db.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('isolation_mode', '0')")
    
    # 预置轮询配置 (默认关闭 '0', 间隔 300 秒)
    db.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('polling_enabled', '0')")
    db.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('polling_interval', '300')")

    db.commit()

def init_app(app):
    app.teardown_appcontext(close_db)
    
    # 确保 data 目录存在
    if not os.path.exists(os.path.dirname(app.config['DATABASE'])):
        os.makedirs(os.path.dirname(app.config['DATABASE']))
        
    with app.app_context():
        init_db()
