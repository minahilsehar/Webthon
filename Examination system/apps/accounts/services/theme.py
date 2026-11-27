from ..models import User


def update_theme(user, theme):
    if theme not in User.Theme.values:
        raise ValueError("Invalid theme.")
    user.theme = theme
    user.save(update_fields=["theme"])
    return user
