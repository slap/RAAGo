from unittest import TestCase
from datetime import date

import pandas as pd
import os

from . import tttratings


EXPECTED_COLUMNS = {"player_id", "time", "mu", "sigma", "date"}


def _game(gid, black, white, result, handicap=0, komi=6.5, d=None):
    return (gid, handicap, komi, result, d or date(2020, 1, gid), black, white)


def _small_dataframe():
    """Set chico: el jugador 100 siempre le gana al 200 (juegos parejos)."""
    games = []
    gid = 1
    for _ in range(6):
        # 100 negro gana
        games.append(_game(gid, black=100, white=200, result="black"))
        gid += 1
        # 100 blanco gana
        games.append(_game(gid, black=200, white=100, result="white"))
        gid += 1
    return pd.DataFrame(games, columns=[
        "id", "handicap", "komi", "result", "date", "black_player_id", "white_player_id"
    ])


class TTRatingsSmokeTest(TestCase):
    """Smoke test sobre el dump real de partidas."""

    def setUp(self):
        self.games = pd.read_csv(
            os.path.join(os.path.dirname(__file__), "games_dump.csv"),
        )
        self.games['date'] = pd.to_datetime(self.games['date']).dt.date

    def test_calculate_ratings_returns_expected_columns(self):
        ratings, log_evidence, mean_evidence = tttratings.calculate_ttt_ratings(self.games)

        self.assertEqual(EXPECTED_COLUMNS, set(ratings.columns))
        self.assertGreater(len(ratings), 0)
        self.assertIsInstance(log_evidence, float)
        self.assertGreater(mean_evidence, 0)

    def test_no_fictional_handi_players(self):
        ratings, _le, _me = tttratings.calculate_ttt_ratings(self.games)

        # player_id quedo numerico: los handi_0 / handi_1 deben haberse filtrado.
        self.assertTrue(pd.api.types.is_numeric_dtype(ratings["player_id"]))
        as_str = ratings["player_id"].astype(str)
        self.assertFalse(as_str.str.startswith("handi").any())


class TTRatingsSmallSetTest(TestCase):
    """Tests con asserts sobre un set chico y controlado."""

    def test_does_not_explode_on_small_set(self):
        ratings, log_evidence, mean_evidence = tttratings.calculate_ttt_ratings(
            _small_dataframe())

        self.assertEqual(EXPECTED_COLUMNS, set(ratings.columns))
        self.assertGreater(len(ratings), 0)

    def test_only_real_players_present(self):
        ratings, _le, _me = tttratings.calculate_ttt_ratings(_small_dataframe())

        self.assertEqual({100, 200}, set(ratings["player_id"].unique()))

    def test_consistent_winner_has_higher_mu(self):
        ratings, _le, _me = tttratings.calculate_ttt_ratings(_small_dataframe())

        last = ratings.sort_values("date").groupby("player_id").tail(1)
        mu_by_player = dict(zip(last["player_id"], last["mu"]))

        # El 100 gano todas; deberia terminar con mu mayor que el 200.
        self.assertGreater(mu_by_player[100], mu_by_player[200])
