# utils/auth.py

import streamlit as st
import json
import hashlib
import os
import functools

USERS_PATH = os.path.join("data", "users.json")

# -----------------------------
# INTERNAL HELPERS
# -----------------------------

def _load_users():
    """Load users.json safely."""
    if not os.path.exists(USERS_PATH):
        with open(USERS_PATH, "w") as f:
            json.dump({"users": []}, f, indent=2)

    with open(USERS_PATH, "r") as f:
        return json.load(f)


def _save_users(data):
    """Save users.json."""
    with open(USERS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# -----------------------------
# AUTH LOGIC
# -----------------------------

def signup(username, password):
    """Create a new user."""
    data = _load_users()

    # Check duplicate username
    for u in data["users"]:
        if u["username"] == username:
            return False, "Username already exists."

    user = {
        "username": username,
        "password": _hash_password(password)
    }

    data["users"].append(user)
    _save_users(data)
    return True, "User created."


def login(username, password):
    """Validate login."""
    data = _load_users()
    hashed = _hash_password(password)

    for u in data["users"]:
        if u["username"] == username and u["password"] == hashed:
            # Set session
            st.session_state["logged_in"] = True
            st.session_state["user"] = {"username": username}
            return True

    return False


def logout():
    st.session_state["logged_in"] = False
    st.session_state["user"] = None


def get_current_user():
    return st.session_state.get("user", {"username": "guest"})


# -----------------------------
# SAFE RERUN WRAPPER
# -----------------------------

def _rerun():
    """Safe rerun that works on all Streamlit versions."""
    try:
        st.experimental_rerun()
    except:
        st.rerun()


# -----------------------------
# LOGIN REQUIRED DECORATOR
# -----------------------------

def _require_login_check():
    if not st.session_state.get("logged_in"):
        st.sidebar.info("Please log in to access this page.")
        st.stop()


def require_login(func=None):

    if func is None:
        def decorator(f):
            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                _require_login_check()
                return f(*args, **kwargs)
            return wrapper
        return decorator

    if callable(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _require_login_check()
            return func(*args, **kwargs)
        return wrapper

    return func


# -----------------------------
# LOGIN UI (FIXED)
# -----------------------------

def login_ui():
    """Sidebar login/signup UI with forms to prevent duplicate submissions."""
    st.sidebar.title("Account")

    if not st.session_state.get("logged_in"):

        mode = st.sidebar.radio("Action", ["Login", "Sign up"])

        # ----------------------------------
        # LOGIN
        # ----------------------------------
        if mode == "Login":
            with st.sidebar.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Login")

            if submitted:
                if "last_login_user" not in st.session_state:
                    st.session_state["last_login_user"] = None

                # Prevent repeated login due to rerun
                if st.session_state["last_login_user"] == username:
                    pass
                else:
                    st.session_state["last_login_user"] = username
                    ok = login(username, password)
                    if ok:
                        st.sidebar.success("Logged in!")
                        _rerun()
                    else:
                        st.sidebar.error("Invalid username or password.")

        # ----------------------------------
        # SIGNUP
        # ----------------------------------
        else:
            with st.sidebar.form("signup_form"):
                username = st.text_input("Choose username")
                password = st.text_input("Choose password", type="password")
                submitted = st.form_submit_button("Create account")

            if submitted:
                ok, msg = signup(username, password)
                if ok:
                    st.sidebar.success("Account created. Please login.")
                else:
                    st.sidebar.error(msg)

    # --------------------------------------
    # LOGGED-IN VIEW
    # --------------------------------------
    else:
        st.sidebar.markdown(
            f"Logged in as **{st.session_state['user']['username']}**"
        )

        if st.sidebar.button("Logout"):
            logout()
            _rerun()
