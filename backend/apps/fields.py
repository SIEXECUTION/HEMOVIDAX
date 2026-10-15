"""Lectura de timestamps del schema existente, almacenados sin zona en UTC."""

from datetime import timezone as datetime_timezone
from django.db import models
from django.utils import timezone


class UTCDateTimeField(models.DateTimeField):
    def from_db_value(self, value, expression, connection):
        if value is not None and timezone.is_naive(value):
            return timezone.make_aware(value, datetime_timezone.utc)
        return value
