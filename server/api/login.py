from typing import Union
import functools
import time
from datetime import datetime, timezone

import flask_login
from flask import Blueprint, request, jsonify, session, current_app

from src.services.authentication.manager import AuthService
from src.services.authentication.database import DBAuthService
from src.common.logging.logger import DebugLogger
from src.schema.user import User

login_router = Blueprint("login_router", __name__)
login_manager = flask_login.LoginManager()

auth_service = AuthService()
db_auth_service = DBAuthService()
logger = DebugLogger()


def setup_logger(class_name: str, main_feature: str):
    """
    A decorator factory to configure the logger context for a Flask route.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            user_email = getattr(flask_login.current_user, 'email', None)
            if user_email:
                logger.set_user(user_email)
            logger.set_class_name(class_name)
            logger.set_main_feature(main_feature)
            logger.api(f"{request.method}  {request.path}")
            return func(*args, **kwargs)
        return wrapper
    return decorator


@login_manager.user_loader
def user_loader(user_id: str) -> Union[User, None]:
    """
    Load a user by their user ID.
    """
    logger.set_user(user_id)
    logger.set_class_name("login")
    logger.set_main_feature("LOGIN")
    logger.info(f"Loading user with ID: {user_id}")
    return auth_service.get_user(user_id)


@login_router.before_app_request
def enforce_max_session_age():
    """
    Enforce an absolute max session duration of PERMANENT_SESSION_LIFETIME.
    """
    if not flask_login.current_user.is_authenticated:
        return

    try:
        login_ts = session.get('login_ts')
        if login_ts is None:
            session['login_ts'] = time.time()
            return

        max_age_seconds = int(current_app.permanent_session_lifetime.total_seconds())
        if (time.time() - float(login_ts)) > max_age_seconds:
            user_email = getattr(flask_login.current_user, 'email', 'unknown')
            logger.set_user(user_email)
            logger.set_class_name("login")
            logger.set_main_feature("LOGIN")
            logger.info("Session expired after max duration; auto-logging out.")
            flask_login.logout_user()
            for k in list(session.keys()):
                session.pop(k, None)
            return jsonify({"message": "Session expired. Please log in again."}), 401
    except Exception as e:
        logger.error(f"Error checking session age: {e}")
        return


@login_router.route("/login", methods=["POST"])
def login() -> Union[str, tuple]:
    """
    Authenticate the user and log them in.
    """
    logger.set_class_name("login")
    logger.set_main_feature("LOGIN")
    logger.api(request.method + "  " + request.path)
    logger.info("Login request received.")

    if flask_login.current_user.is_authenticated:
        logger.set_user(flask_login.current_user.email)
        logger.info(f"User {flask_login.current_user.email} is already logged in.")
        return jsonify({"message": "User already logged in"}), 400

    data = request.get_json() or {}
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    if not email or not password:
        logger.warning("E-mail or password missing in the request.")
        return jsonify({"message": "E-mail and password are required"}), 400

    try:
        user = auth_service.authenticate_user(email, password)
        flask_login.login_user(user)
        session.permanent = True
        session['login_ts'] = datetime.now(timezone.utc).timestamp()

        logger.set_user(user.email)
        logger.success(f"User {email} logged in successfully.")
        return user.to_json(), 200
    except Exception as e:
        logger.error(f"Login failed for {email}: {e}")
        return auth_service.handle_login_exceptions(email, e)


@login_router.route("/login", methods=["GET"])
@flask_login.login_required
@setup_logger(class_name="login", main_feature="LOGIN")
def get_loggedin() -> str:
    """
    Retrieve information about the currently logged-in user.
    """
    user_email = flask_login.current_user.email
    logger.info(f"Returning logged-in user: {user_email}")
    return flask_login.current_user.to_json()


@login_router.route("/logout", methods=["POST"])
@flask_login.login_required
@setup_logger(class_name="login", main_feature="LOGIN")
def logout() -> tuple[str, int]:
    """
    Log out the current user.
    """
    user_email = flask_login.current_user.email
    logger.info(f"User {user_email} logged out.")
    flask_login.logout_user()
    for k in list(session.keys()):
        session.pop(k, None)
    return '', 204