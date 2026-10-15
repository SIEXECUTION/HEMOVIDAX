"""Compara los modelos con el contrato o con tablas existentes, sin modificar nada."""

import json
from pathlib import Path
from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Verifica el contrato del schema. --database consulta la estructura real en modo de solo lectura."

    def add_arguments(self, parser):
        parser.add_argument("--database", action="store_true")

    def handle(self, *args, **options):
        contract = json.loads(
            (Path(settings.BASE_DIR) / "schema_contract.json").read_text(
                encoding="utf-8"
            )
        )
        errors = []
        models = [
            m
            for m in apps.get_models()
            if m._meta.app_label in ("seguridad", "donantes", "inventario")
        ]
        for model in models:
            table = model._meta.db_table
            expected = contract[table]
            fields = {f.column: f for f in model._meta.local_fields if f.column}
            if model._meta.managed:
                errors.append(f"{table}: managed debe ser False")
            if set(fields) != set(expected):
                errors.append(f"{table}: columnas distintas del contrato")
            for col, field in fields.items():
                if col in expected and field.null != expected[col]["nullable"]:
                    errors.append(f"{table}.{col}: nulabilidad distinta del contrato")
        if options["database"]:
            if connection.vendor != "postgresql":
                raise CommandError("--database requiere PostgreSQL / Supabase.")
            with connection.cursor() as cursor:
                cursor.execute("BEGIN READ ONLY")
                try:
                    for table, expected in contract.items():
                        actual = {
                            c.name: c
                            for c in connection.introspection.get_table_description(
                                cursor, table
                            )
                        }
                        if set(actual) != set(expected):
                            errors.append(
                                f"{table}: columnas reales distintas del contrato"
                            )
                        for col in set(actual) & set(expected):
                            if actual[col].null_ok != expected[col]["nullable"]:
                                errors.append(
                                    f"{table}.{col}: nulabilidad real distinta del contrato"
                                )
                finally:
                    cursor.execute("ROLLBACK")
        if errors:
            raise CommandError("\n".join(errors))
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(models)} modelos verificados; no se modificó el schema."
            )
        )
