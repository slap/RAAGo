# -*- coding: utf-8 -*-
"""Recalcula los ratings con TrueSkill Through Time.

Por defecto guarda los resultados en la tabla ``TrueSkillPlayerRating`` (no pisa
``PlayerRating``, el ranking actual). Ejemplos:

    # Calcular y guardar en TrueSkillPlayerRating
    python manage.py run_ttt_ratings

    # Solo calcular y volcar a CSV, sin tocar la base
    python manage.py run_ttt_ratings --dry-run --output ratings_ttt.csv
"""
from django.core.management.base import BaseCommand

from aago_ranking.ratings import tasks


class Command(BaseCommand):
    help = "Recalcula los ratings con TrueSkill Through Time (tabla separada)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Calcula los ratings pero no escribe nada en la base de datos.',
        )
        parser.add_argument(
            '--output',
            metavar='RUTA_CSV',
            default=None,
            help='Vuelca los ratings calculados a un archivo CSV.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        output = options['output']

        if dry_run:
            self.stdout.write("Modo dry-run: no se escribira en la base de datos.")

        new_ratings, log_evidence, mean_evidence = tasks.generate_ttt_ratings(
            dry_run=dry_run,
            output=output,
        )

        if output:
            self.stdout.write(self.style.SUCCESS(
                "Ratings volcados a {}".format(output)))

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(
                "Guardados {} ratings en TrueSkillPlayerRating.".format(len(new_ratings))))

        self.stdout.write("log_evidence: {}".format(log_evidence))
        self.stdout.write("mean_evidence: {}".format(mean_evidence))
