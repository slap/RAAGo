#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division
from aago_ranking.games.models import Player, Game
from aago_ranking.events.models import Event, EventPlayer
from .models import PlayerRating, TrueSkillPlayerRating

import io
import logging
import math
import subprocess
import pandas as pd

from .trueskill import tttratings

from django.conf import settings
from django.db.models import Q

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def generate_event_ratings(event_pk):
    event = Event.objects.get(pk=event_pk)
    is_previous_event = (Q(event__end_date__lt=event.end_date) |
                       (Q(event__end_date=event.end_date) & Q(event__start_date__lt=event.start_date)) |
                       (Q(event__end_date=event.end_date) & Q(event__start_date=event.start_date) & Q(event__pk__lt=event.pk)))
    ratings = PlayerRating.objects.filter(is_previous_event).order_by('-event')
    event_players = EventPlayer.objects.filter(event=event)
    data = io.StringIO()

    print('PLAYERS', file=data)
    for event_player in event_players:
        last_rating = ratings.filter(player=event_player.player).first()
        print(event_player.player.pk, event_player.ranking, file=data, end=' ')
        if last_rating:
            rating_age = (event.end_date - last_rating.event.end_date).days
            print(last_rating.mu, last_rating.sigma, rating_age, file=data)
        else:
            print("NULL", "NULL", "NULL", file=data)

    print('END_PLAYERS', file=data)
    
    playersWithGames = set()
    print('GAMES', file=data)
    for game in event.games.rated():
        playersWithGames.add(game.white_player.pk)
        playersWithGames.add(game.black_player.pk)
        print(
            game.white_player.pk,
            game.black_player.pk,
            game.handicap,
            math.floor(game.komi),
            game.result.upper(),
            file=data
        )
    print('END_GAMES', file=data)
    proc = subprocess.Popen(
        settings.RAAGO_COMMAND,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate(data.getvalue().encode('utf-8'))
    if proc.wait() != 0:
        raise Exception(
            "Failed execution of raago: '{}'. Exit code: {}. Stderr: '{}'".format(
                settings.RAAGO_COMMAND,
                proc.wait(),
                stderr,
            )
        )

    event.playerrating_set.all().delete()

    def readRangoOutputLine(line):
        player_id, mu, sigma = line.split()
        return int(player_id), float(mu), float(sigma)

    ratings_data = {}
    for line in stdout.decode('utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        player_id, mu, sigma = readRangoOutputLine(line)
        if player_id in playersWithGames:
            player = Player.objects.get(pk=player_id)
            event.playerrating_set.create(player=player,
                                          mu=mu,
                                          sigma=sigma, )
            ratings_data[str(player_id)] = {
                "name": player.name,
                "mu": mu,
                "sigma": sigma,
            }
            
    return ratings_data

def run_ratings_update_cpp():
    events = Event.objects.all()
    return {
        str(e.pk): {'name': e.name,
                    'rating_changes': generate_event_ratings(e.pk)}
        for e in events
    }



def create_games_dataframe():
    # event__isnull=False: el modelo TTT agrupa las partidas por la fecha de fin
    # del evento, asi que solo consideramos partidas asociadas a un evento.
    rated_games_query = Q(unrated=False) & Q(event__isnull=False)
    games = (Game.objects.filter(rated_games_query)
             .select_related('event', 'black_player', 'white_player')
             .order_by('date'))

    games_list = [
        (g.pk, g.handicap, g.komi, g.result, g.event.end_date, g.black_player.pk, g.white_player.pk)
        for g in games
    ]
    
    return pd.DataFrame(games_list, columns=[
        'id', 'handicap', 'komi','result','date', 'black_player_id', 'white_player_id'
    ])    
    
    

def generate_ttt_ratings(dry_run=False, output=None):
    """Calcula los ratings TrueSkill Through Time.

    Por seguridad, los resultados se guardan en ``TrueSkillPlayerRating`` (tabla
    separada) y NO se toca ``PlayerRating`` (el ranking actual AGA/RAAGo). Esto
    permite comparar ambos rankings sin destruir datos.

    Args:
        dry_run: si es True, calcula pero no escribe nada en la base.
        output: ruta opcional a un CSV donde volcar los ratings calculados.

    Returns:
        (new_ratings_df, log_evidence, mean_evidence)
    """
    game_df = create_games_dataframe()

    new_ratings, log_evidence, mean_evidence = tttratings.calculate_ttt_ratings(game_df)

    if output:
        new_ratings.to_csv(output, index=False)

    if dry_run:
        logger.info("dry-run: %d ratings calculados, no se escribio en la base",
                    len(new_ratings))
        return new_ratings, log_evidence, mean_evidence

    # Solo se borra la tabla de TTT, nunca PlayerRating.
    TrueSkillPlayerRating.objects.all().delete()

    skipped = 0
    for _i, row in new_ratings.iterrows():
        event = Event.objects.filter(end_date=row['date']).first()
        if event is None:
            # Puede pasar si la fecha del rating no coincide con ningun evento.
            skipped += 1
            continue

        TrueSkillPlayerRating.objects.create(
            event=event,
            player=Player.objects.get(pk=row['player_id']),
            mu=row['mu'],
            sigma=row['sigma'],
        )

    if skipped:
        logger.warning("%d ratings omitidos por no encontrar evento con esa fecha",
                       skipped)

    return new_ratings, log_evidence, mean_evidence



def run_ratings_update_ttt():
    _new_ratings, log_evidence, mean_evidence = generate_ttt_ratings()

    return {
        'message': 'TrueSkill ratings updated correctly (tabla TrueSkillPlayerRating)',
        'log_evidence': log_evidence,
        'mean_evidence': mean_evidence
    }