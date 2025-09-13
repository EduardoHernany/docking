# users/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class RoleEnum(models.TextChoices):
    USER = "USER", "USER"
    ADMIN = "ADMIN", "ADMIN"


class User(AbstractUser):
    class Meta:
        db_table = "users"
        # username já é unique pelo AbstractUser
        constraints = [
            # unicidade case-insensitive para e-mail
            models.UniqueConstraint(
                Lower("email"),
                name="users_email_ci_unique",
            ),
        ]

    # seus extras
    role = models.CharField(max_length=10, choices=RoleEnum.choices, default=RoleEnum.USER)
    # active = models.BooleanField(default=True)
    deleted = models.BooleanField(default=False)

    def __str__(self):
        return self.username
