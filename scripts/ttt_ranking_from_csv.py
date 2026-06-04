#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Calcula y muestra el ranking TrueSkill Through Time a partir de CSVs.

No necesita base de datos ni el stack Django: usa directamente el dump de
partidas (`games_dump.csv`) y, si esta disponible, `players.csv` para mostrar
nombres. Sirve para probar el modelo en local con datos reales.

Uso:
    python scripts/ttt_ranking_from_csv.py
    python scripts/ttt_ranking_from_csv.py --top 30 --output ranking_ttt.csv
"""
import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TTT_DIR = os.path.join(HERE, os.pardir, "aago_ranking", "ratings", "trueskill")
sys.path.insert(0, TTT_DIR)

import tttratings  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", default=os.path.join(TTT_DIR, "games_dump.csv"))
    parser.add_argument("--players", default=os.path.join(TTT_DIR, "players.csv"))
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--output", default=None, help="CSV con el ranking completo")
    args = parser.parse_args()

    games = pd.read_csv(args.games)
    games["date"] = pd.to_datetime(games["date"]).dt.date

    ratings, log_evidence, mean_evidence = tttratings.calculate_ttt_ratings(games)

    # Ultimo rating de cada jugador (su valor "actual").
    last = ratings.sort_values("date").groupby("player_id").tail(1).copy()

    if os.path.exists(args.players):
        players = pd.read_csv(args.players)[["id", "name"]]
        last = last.merge(players, left_on="player_id", right_on="id", how="left")
    else:
        last["name"] = last["player_id"].astype(str)

    last = last.sort_values("mu", ascending=False)
    last["rank"] = range(1, len(last) + 1)

    print("\nlog_evidence: %.4f   mean_evidence: %.4f   jugadores: %d\n"
          % (log_evidence, mean_evidence, len(last)))
    print("%-5s %-30s %8s %8s" % ("#", "Jugador", "mu", "sigma"))
    print("-" * 55)
    for _i, row in last.head(args.top).iterrows():
        print("%-5d %-30s %8.3f %8.3f"
              % (row["rank"], str(row["name"])[:30], row["mu"], row["sigma"]))

    if args.output:
        cols = ["rank", "player_id", "name", "mu", "sigma", "date"]
        last[cols].to_csv(args.output, index=False)
        print("\nRanking completo -> %s" % args.output)


if __name__ == "__main__":
    main()
