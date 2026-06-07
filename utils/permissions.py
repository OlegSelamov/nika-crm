def is_accountant():
    return session.get("role") == "accountant"

def is_manager():
    return session.get("role") == "manager"

def is_cto():
    return session.get("role") == "cto"

def is_admin():
    return session.get("role") == "admin"