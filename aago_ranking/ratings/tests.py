# -*- coding: utf-8 -*-
"""Tests de integracion del flujo TrueSkill Through Time.

Verifican que el recalculo:
  - guarda en TrueSkillPlayerRating (tabla separada),
  - NUNCA toca PlayerRating (ranking actual),
  - respeta el modo --dry-run (no escribe en la base),
  - puede volcar los resultados a CSV.
"""
import csv
import os
import tempfile
from datetime import date
from decimal import Decimal

from django.test import TestCase

from aago_ranking.games.models import Player, Game
from aago_ranking.events.models import Event, EventPlayer
from aago_ranking.ratings import tasks
from aago_ranking.ratings.models import PlayerRating, TrueSkillPlayerRating


EVENT_DATE = date(2020, 2, 1)


def _build_fixture():
    """Crea un evento con dos jugadores y varias partidas (100 le gana al 200)."""
    p1 = Player.objects.create(name="winner", is_aago_member=True)
    p2 = Player.objects.create(name="looser", is_aago_member=True)

    event = Event.objects.create(
        name="Test event", start_date=EVENT_DATE, end_date=EVENT_DATE,
    )
    EventPlayer.objects.create(event=event, player=p1, ranking="1d")
    EventPlayer.objects.create(event=event, player=p2, ranking="2d")

    for i in range(6):
        # p1 negro gana
        Game.objects.create(
            event=event, date=EVENT_DATE, black_player=p1, white_player=p2,
            handicap=0, komi=Decimal("6.5"), result="black", reason="resignation",
        )
        # p1 blanco gana
        Game.objects.create(
            event=event, date=EVENT_DATE, black_player=p2, white_player=p1,
            handicap=0, komi=Decimal("6.5"), result="white", reason="resignation",
        )
    return event, p1, p2


class GenerateTTTRatingsTest(TestCase):

    def setUp(self):
        self.event, self.p1, self.p2 = _build_fixture()
        # Un PlayerRating preexistente que NO debe ser tocado por el flujo TTT.
        self.existing = PlayerRating.objects.create(
            player=self.p1, event=self.event, mu=42.0, sigma=1.0,
        )

    def test_writes_to_separate_table(self):
        tasks.generate_ttt_ratings()

        self.assertTrue(TrueSkillPlayerRating.objects.exists())
        ttt_players = set(TrueSkillPlayerRating.objects.values_list('player', flat=True))
        self.assertEqual({self.p1.pk, self.p2.pk}, ttt_players)

    def test_does_not_touch_player_rating(self):
        tasks.generate_ttt_ratings()

        # El PlayerRating original sigue intacto.
        self.assertEqual(1, PlayerRating.objects.count())
        self.existing.refresh_from_db()
        self.assertEqual(42.0, self.existing.mu)

    def test_dry_run_writes_nothing(self):
        new_ratings, _le, _me = tasks.generate_ttt_ratings(dry_run=True)

        self.assertGreater(len(new_ratings), 0)
        self.assertEqual(0, TrueSkillPlayerRating.objects.count())
        self.assertEqual(1, PlayerRating.objects.count())

    def test_output_csv(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        tmp.close()
        try:
            tasks.generate_ttt_ratings(dry_run=True, output=tmp.name)
            with open(tmp.name, newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertGreater(len(rows), 0)
            self.assertEqual(
                {"player_id", "time", "mu", "sigma", "date"},
                set(rows[0].keys()),
            )
        finally:
            os.unlink(tmp.name)

    def test_winner_has_higher_mu(self):
        tasks.generate_ttt_ratings()

        mu_winner = TrueSkillPlayerRating.objects.get(player=self.p1).mu
        mu_looser = TrueSkillPlayerRating.objects.get(player=self.p2).mu
        self.assertGreater(mu_winner, mu_looser)
