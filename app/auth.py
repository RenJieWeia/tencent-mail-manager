import functools
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from app.db import get_db
from app.audit import log_audit

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/register', methods=('GET', 'POST'))
def register():
    # Only Admin or Renjie can register users in this logic? 
    # Or strict existing logic? The existing app only had pre-seeded users.
    # Let's keep it simple: Public registration is NOT in the original code, 
    # only admin creation. But let's add a login view.
    return redirect(url_for('auth.login'))

@bp.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        error = None
        user = db.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()

        if user is None:
            error = '用户名不存在。'
        elif not check_password_hash(user['password_hash'], password):
            error = '密码错误。'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            log_audit(username, 'LOGIN', 'User logged in successfully')
            return redirect(url_for('main.index'))

        flash(error)

    return render_template('login.html') # We need to move simple htmls later

@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
        g.is_super_admin = False
        g.can_access_dashboard = False
    else:
        db = get_db()
        g.user = db.execute(
            'SELECT * FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        
        g.is_super_admin = (g.user['username'] == 'renjie') if g.user else False
        
        # Check permission for admin dashboard
        g.can_access_dashboard = False
        if g.user:
            if g.is_super_admin:
                g.can_access_dashboard = True
            elif g.user['username'] == 'admin':
                # Check system setting
                row = db.execute("SELECT value FROM system_settings WHERE key='allow_admin_dashboard'").fetchone()
                g.can_access_dashboard = (row['value'] == '1') if row else False

@bp.route('/logout')
def logout():
    log_audit(session.get('username', 'unknown'), 'LOGOUT', 'User logged out')
    session.clear()
    return redirect(url_for('auth.login'))

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view
