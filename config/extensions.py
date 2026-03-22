"""
Flask extensions — diinisialisasi tanpa app agar bisa diimport dari mana saja.
Panggil <ext>.init_app(app) di dalam create_app() di app.py.
"""

from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager

bcrypt        = Bcrypt()
login_manager = LoginManager()
limiter       = Limiter(get_remote_address, default_limits=["300 per hour"], storage_uri="memory://")

login_manager.login_view = "pages.serve_login"
