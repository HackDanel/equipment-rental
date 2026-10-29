from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

phone_validator = RegexValidator(
    r'^\+?[0-9]{10,15}$',
    'Телефон: от 10 до 15 цифр, можно с «+» в начале.',
)


class User(AbstractUser):
    class Role(models.TextChoices):
        CLIENT = 'client', 'Клиент'
        MANAGER = 'manager', 'Менеджер'
        ADMIN = 'admin', 'Администратор'

    email = models.EmailField('e-mail', unique=True)
    phone = models.CharField('телефон', max_length=16, blank=True, validators=[phone_validator])
    role = models.CharField('роль', max_length=10, choices=Role.choices, default=Role.CLIENT)

    class Meta:
        verbose_name = 'пользователь'
        verbose_name_plural = 'пользователи'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return self.get_full_name() or self.username

    def save(self, *args, **kwargs):
        # createsuperuser не знает о ролях и оставил бы «Клиента» — суперпользователь всегда администратор.
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def is_client(self):
        return self.role == self.Role.CLIENT and not self.is_superuser

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER and not self.is_superuser

    @property
    def is_admin_role(self):
        # Суперпользователь Django тоже считается администратором проката.
        return self.role == self.Role.ADMIN or self.is_superuser
