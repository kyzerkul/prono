from flask import Flask, jsonify, render_template, request, redirect, url_for, send_from_directory
import http.client
import json
from datetime import datetime, timedelta
import requests
import os
from dotenv import load_dotenv
from functools import lru_cache
import time

load_dotenv()  # Charge les variables d'environnement depuis .env

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default-dev-key')  # Utilise la clé depuis les variables d'environnement

API_KEY = os.environ.get('RAPIDAPI_KEY', 'dfa89bdb87mshcc417c376ac947fp100750jsn6f1aa9d00a91')

# Organisation des ligues par région
REGIONS = {
    'europe': {
        'name': 'Europe',
        'categories': {
            'major': {
                'name': 'Top 5',
                'leagues': {
                    'premier_league': {'id': 39, 'name': 'Premier League'},
                    'la_liga': {'id': 140, 'name': 'La Liga'},
                    'bundesliga': {'id': 78, 'name': 'Bundesliga'},
                    'serie_a': {'id': 135, 'name': 'Serie A'},
                    'ligue_1': {'id': 61, 'name': 'Ligue 1'}
                }
            },
            'european': {
                'name': 'Coupes Européennes',
                'leagues': {
                    'champions_league': {'id': 2, 'name': 'Champions League'},
                    'europa_league': {'id': 3, 'name': 'Europa League'}
                }
            },
            'other': {
                'name': 'Autres Championnats',
                'leagues': {
                    'eredivisie': {'id': 88, 'name': 'Eredivisie'},
                    'primeira_liga': {'id': 94, 'name': 'Primeira Liga'},
                    'super_lig': {'id': 203, 'name': 'Super Lig'}
                }
            }
        }
    },
    'americas': {
        'name': 'Amériques',
        'categories': {
            'north': {
                'name': 'Amérique du Nord',
                'leagues': {
                    'mls': {'id': 253, 'name': 'MLS'},
                    'liga_mx': {'id': 262, 'name': 'Liga MX'}
                }
            },
            'south': {
                'name': 'Amérique du Sud',
                'leagues': {
                    'brasileirao': {'id': 71, 'name': 'Brasileirão'},
                    'primera_division': {'id': 128, 'name': 'Primera División'}
                }
            }
        }
    },
    'asia': {
        'name': 'Asie',
        'categories': {
            'east': {
                'name': 'Asie de l\'Est',
                'leagues': {
                    'j1_league': {'id': 98, 'name': 'J1 League'},
                    'k_league': {'id': 292, 'name': 'K League 1'}
                }
            },
            'west': {
                'name': 'Moyen-Orient',
                'leagues': {
                    'saudi_league': {'id': 307, 'name': 'Saudi Pro League'}
                }
            }
        }
    }
}

# Créer un dictionnaire plat des ligues pour la recherche rapide
LEAGUES = {}
for region in REGIONS.values():
    for category in region['categories'].values():
        for league in category['leagues'].values():
            LEAGUES[league['id']] = league['name']

# Cache pour les appels API (30 minutes)
CACHE_DURATION = 1800

class APICache:
    def __init__(self):
        self.cache = {}
        
    def get(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < CACHE_DURATION:
                return data
            else:
                del self.cache[key]
        return None
        
    def set(self, key, data):
        self.cache[key] = (data, time.time())

api_cache = APICache()

def make_api_request(endpoint, params=""):
    # Créer une clé de cache unique
    cache_key = f"{endpoint}?{params}"
    
    # Vérifier le cache
    cached_data = api_cache.get(cache_key)
    if cached_data:
        return cached_data
    
    # Si pas en cache, faire l'appel API
    conn = http.client.HTTPSConnection('api-football-v1.p.rapidapi.com')
    headers = {
        'x-rapidapi-key': API_KEY,
        'x-rapidapi-host': 'api-football-v1.p.rapidapi.com'
    }
    try:
        url = f"/v3/{endpoint}?{params}"
        print(f"\nAPI Request URL: {url}")
        
        conn.request("GET", url, headers=headers)
        res = conn.getresponse()
        data = res.read()
        
        if res.status != 200:
            print(f"API Error Response: {res.status}")
            return None
            
        response_data = json.loads(data.decode('utf-8'))
        
        # Mettre en cache
        api_cache.set(cache_key, response_data)
        
        return response_data
    except Exception as e:
        print(f"API Request Error: {str(e)}")
        return None
    finally:
        conn.close()

@lru_cache(maxsize=32)
def get_match_statistics(fixture_id):
    # Cache au niveau de la fonction avec lru_cache
    return make_api_request('fixtures/statistics', f'fixture={fixture_id}')

@lru_cache(maxsize=32)
def get_match_events(fixture_id):
    return make_api_request('fixtures/events', f'fixture={fixture_id}')

@lru_cache(maxsize=32)
def get_match_score(fixture_id):
    return make_api_request('fixtures', f'id={fixture_id}')

@lru_cache(maxsize=32)
def get_prediction(fixture_id):
    prediction_data = make_api_request('predictions', f'fixture={fixture_id}')
    if not prediction_data or 'response' not in prediction_data:
        return None
        
    return process_prediction_data(prediction_data)

@app.template_filter('format_time')
def format_time(date_str):
    """Formate une date au format HH:MM"""
    try:
        if isinstance(date_str, str):
            # Si c'est une chaîne ISO, on la parse
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%H:%M')
        return ''
    except Exception as e:
        print(f"Erreur lors du formatage de la date {date_str}: {e}")
        return ''

# Gestionnaire d'erreurs global
@app.errorhandler(Exception)
def handle_error(e):
    print(f"Erreur: {str(e)}")
    return "Une erreur s'est produite. Veuillez réessayer plus tard.", 500

def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def safe_int_convert(value, default=0):
    """Convertit une valeur en entier de manière sécurisée"""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            # Supprimer les caractères non numériques
            value = ''.join(filter(str.isdigit, value))
        return int(value) if value else default
    except (ValueError, TypeError):
        return default

def safe_get(obj, *keys, default=None):
    """Récupère en toute sécurité une valeur dans un dictionnaire imbriqué."""
    current = obj
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
    return current if current is not None else default

def clean_numeric_string(value, default='0'):
    """Nettoie une chaîne de caractères pour la conversion en float."""
    if not value:
        return default
    
    # Si c'est un dictionnaire, on essaie d'extraire la valeur numérique
    if isinstance(value, dict):
        # Chercher une valeur numérique dans le dictionnaire
        for key in ['value', 'total', 'home', 'away']:
            if key in value and value[key] not in [None, 'None', '']:
                value = value[key]
                break
        else:
            return default
    
    # Convertir en chaîne si ce n'est pas déjà le cas
    value = str(value)
    
    if value == 'None':
        return default
        
    # Enlever le symbole % et autres caractères non numériques
    value = value.replace('%', '').replace(',', '.').strip()
    
    # Si la chaîne est vide après nettoyage, retourner la valeur par défaut
    return value if value else default

def check_prediction_accuracy(match, prediction):
    """Vérifie si la prédiction était correcte"""
    print(f"Vérification de la prédiction pour le match {match['fixture']['id']}")
    print("Score final:", match.get('score', {}).get('fulltime'))
    print("Prédiction:", prediction.get('predictions', {}).get('winner'))
    
    if not match.get('score') or not match['score'].get('fulltime'):
        return False
        
    home_score = match['score']['fulltime']['home']
    away_score = match['score']['fulltime']['away']
    
    # Vérifier la prédiction de victoire
    winner_prediction = prediction.get('predictions', {}).get('winner', {})
    if not winner_prediction:
        return False
        
    winner_id = winner_prediction.get('id')
    
    if winner_id == match['teams']['home']['id']:
        result = home_score > away_score
    elif winner_id == match['teams']['away']['id']:
        result = away_score > home_score
    else:  # Match nul prédit
        result = home_score == away_score
    
    print(f"Résultat de la prédiction: {'Correct' if result else 'Incorrect'}")
    return result

def process_prediction_data(prediction_data):
    """Traite les données de prédiction pour les rendre plus facilement utilisables"""
    prediction = prediction_data['response'][0]
    
    # Extraire toutes les prédictions under/over
    under_over_predictions = []
    if 'predictions' in prediction:
        predictions = prediction['predictions']
        # Under/Over principal
        if 'under_over' in predictions:
            under_over = predictions['under_over']
            if under_over:
                value = abs(float(under_over))
                prediction = 'over' if float(under_over) > 0 else 'under'
                under_over_predictions.append({
                    'value': value,
                    'prediction': prediction
                })
        
        # Autres prédictions under/over (0.5, 1.5, 2.5, 3.5, etc.)
        for key in predictions:
            if key.startswith('under_over_'):
                try:
                    value = float(key.split('_')[-1])
                    prediction = predictions[key]
                    if prediction:
                        under_over_predictions.append({
                            'value': value,
                            'prediction': prediction.lower()
                        })
                except (ValueError, AttributeError):
                    continue
    
    # Extraire la valeur over/under et la prédiction
    under_over_value = None
    under_over_prediction = None
    
    if 'predictions' in prediction and 'under_over' in prediction['predictions']:
        under_over = prediction['predictions']['under_over']
        if under_over:
            # La valeur négative indique "under", positive indique "over"
            under_over_value = abs(float(under_over))
            under_over_prediction = 'over' if float(under_over) > 0 else 'under'
    
    # Calcul des statistiques de comparaison
    comparison = prediction.get('comparison', {})
    
    # Distribution de Poisson
    poisson_home = round(float(clean_numeric_string(safe_get(comparison, 'poisson_distribution', 'home'), '50')), 2)
    poisson_away = round(float(clean_numeric_string(safe_get(comparison, 'poisson_distribution', 'away'), '50')), 2)
    
    # Force d'attaque et de défense
    att_home = round(float(clean_numeric_string(safe_get(comparison, 'att', 'home'), '50')), 2)
    att_away = round(float(clean_numeric_string(safe_get(comparison, 'att', 'away'), '50')), 2)
    def_home = round(float(clean_numeric_string(safe_get(comparison, 'def', 'home'), '50')), 2)
    def_away = round(float(clean_numeric_string(safe_get(comparison, 'def', 'away'), '50')), 2)
    
    # Déterminer l'équipe qui est favorisée pour win_or_draw
    winner = prediction['predictions'].get('winner', {})
    winner_name = winner.get('name') if winner else None
    raw_win_or_draw = prediction['predictions'].get('win_or_draw')
    print("Valeur brute win_or_draw:", raw_win_or_draw)
    print("Type de win_or_draw:", type(raw_win_or_draw))
    
    # Convertir win_or_draw en booléen de manière plus flexible
    win_or_draw = False
    if raw_win_or_draw:
        if isinstance(raw_win_or_draw, bool):
            win_or_draw = raw_win_or_draw
        else:
            win_or_draw = str(raw_win_or_draw).lower() in ['true', '1', 'yes', 'y']
    
    # Déterminer l'équipe pour win_or_draw
    win_or_draw_team = None
    if win_or_draw and winner_name:
        win_or_draw_team = winner_name
    
    predictions = {
        'winner': {
            'name': winner_name,
            'comment': winner.get('comment') if winner else None
        },
        'win_or_draw': win_or_draw,
        'win_or_draw_team': win_or_draw_team,
        'under_over': under_over_predictions,  # Liste de toutes les prédictions under/over
        'goals_home': prediction['predictions'].get('goals_home'),
        'goals_away': prediction['predictions'].get('goals_away'),
        'advice': prediction['predictions'].get('advice'),
        'comparison': {
            'att': {
                'home': round(att_home, 2),
                'away': round(att_away, 2)
            },
            'def': {
                'home': round(def_home, 2),
                'away': round(def_away, 2)
            }
        },
        'poisson': {
            'home': round(poisson_home, 2),
            'away': round(poisson_away, 2)
        },
        'strength': {
            'home': round(poisson_home, 2),
            'away': round(poisson_away, 2)
        }
    }

    return predictions

@app.route('/')
def home():
    try:
        # Récupérer la date actuelle
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Créer une clé de cache unique pour les matchs du jour
        cache_key = f"matches_{current_date}"
        cached_matches = api_cache.get(cache_key)
        
        if cached_matches:
            return render_template('index.html', matches=cached_matches, regions=REGIONS)
        
        # Si pas en cache, récupérer les matchs
        matches_data = make_api_request('fixtures', f'date={current_date}')
        
        if not matches_data or 'response' not in matches_data:
            return render_template('index.html', matches=[], regions=REGIONS)
        
        matches = []
        for match in matches_data['response']:
            # Filtrer uniquement les matchs des ligues qu'on suit
            league_id = match['league']['id']
            if league_id not in LEAGUES:
                continue
                
            # Récupérer uniquement les informations nécessaires
            match_info = {
                'id': match['fixture']['id'],
                'timestamp': match['fixture']['timestamp'],
                'date': match['fixture']['date'],
                'league': {
                    'id': league_id,
                    'name': LEAGUES[league_id],
                    'logo': match['league']['logo']
                },
                'teams': match['teams'],
                'goals': match['goals'],
                'status': match['fixture']['status']
            }
            
            # Ne récupérer les prédictions que pour les matchs à venir
            if match['fixture']['status']['short'] == 'NS':
                prediction = get_prediction(match['fixture']['id'])
                if prediction:
                    match_info['prediction'] = prediction
            
            matches.append(match_info)
        
        # Trier les matchs par heure
        matches.sort(key=lambda x: x['timestamp'])
        
        # Mettre en cache pour 30 minutes
        api_cache.set(cache_key, matches)
        
        return render_template('index.html', matches=matches, regions=REGIONS)
        
    except Exception as e:
        print(f"Erreur dans la route home: {str(e)}")
        return render_template('index.html', matches=[], regions=REGIONS)

@app.route('/search')
def search():
    search_term = request.args.get('q', '')
    if len(search_term) < 3:
        return render_template('search.html', 
                             search_term=search_term, 
                             matches=[],
                             error="Le terme de recherche doit contenir au moins 3 caractères.")

    # D'abord chercher les équipes
    teams_data = make_api_request("teams", f"search={search_term}")
    matches = []
    
    if teams_data.get('response'):
        # Pour chaque équipe trouvée
        for team in teams_data['response'][:5]:  # Limiter à 5 équipes
            team_id = team['team']['id']
            
            # Chercher les prochains matchs de cette équipe
            fixtures_data = make_api_request(
                "fixtures",
                f"team={team_id}&next=10&status=NS"  # Prochains 10 matchs non commencés
            )
            
            if fixtures_data.get('response'):
                for match in fixtures_data['response']:
                    # Vérifier si le match est dans une ligue suivie
                    league_id = match['league']['id']
                    if league_id in LEAGUES:
                        matches.append(match)

    # Trier les matchs par date
    matches.sort(key=lambda x: x['fixture']['date'])
    
    # Organiser les matchs par date
    matches_by_date = {}
    for match in matches:
        match_date = match['fixture']['date'].split('T')[0]
        if match_date not in matches_by_date:
            matches_by_date[match_date] = []
        matches_by_date[match_date].append(match)

    return render_template('search.html', 
                         search_term=search_term, 
                         matches_by_date=matches_by_date)

@app.route('/search-teams', methods=['GET'])
def search_teams():
    search_term = request.args.get('term', '')
    print(f"Recherche pour le terme: {search_term}")
    
    if len(search_term) < 3:
        return jsonify([])

    # D'abord chercher les équipes
    teams_data = make_api_request("teams", f"search={search_term}")
    
    suggestions = []
    if teams_data.get('response'):
        # Pour chaque équipe trouvée
        for team in teams_data['response'][:5]:  # Limiter à 5 équipes
            team_id = team['team']['id']
            
            # Chercher les prochains matchs de cette équipe
            fixtures_data = make_api_request(
                "fixtures",
                f"team={team_id}&next=10&status=NS"  # Prochains 10 matchs non commencés
            )
            
            if fixtures_data.get('response'):
                for match in fixtures_data['response']:
                    # Vérifier si le match est dans une ligue suivie
                    league_id = match['league']['id']
                    if league_id in LEAGUES:
                        suggestions.append({
                            'value': str(match['fixture']['id']),
                            'label': f"{match['teams']['home']['name']} vs {match['teams']['away']['name']} ({match['league']['name']})",
                            'home_team': match['teams']['home']['name'],
                            'away_team': match['teams']['away']['name'],
                            'league': match['league']['name'],
                            'date': match['fixture']['date'].split('T')[0],
                            'time': match['fixture']['date'].split('T')[1][:5]
                        })
                        print(f"Match ajouté: {match['teams']['home']['name']} vs {match['teams']['away']['name']}")

    # Trier les suggestions par date
    suggestions.sort(key=lambda x: x['date'])
    print(f"Nombre total de suggestions: {len(suggestions)}")
    return jsonify(suggestions)

@app.route('/predictions', methods=['POST'])
def get_predictions():
    fixture_id = request.form.get('fixture_id')
    if not fixture_id:
        return redirect(url_for('home'))
        
    # Récupérer les informations du match
    fixture_data = make_api_request("fixtures", f"id={fixture_id}")
    if not fixture_data.get('response'):
        return redirect(url_for('home'))
    match = fixture_data['response'][0]
    
    # Récupérer les prédictions
    pred_data = get_prediction(fixture_id)
    if not pred_data:
        return redirect(url_for('home'))
    prediction_data = pred_data

    # Debug logs
    print("Structure complète des prédictions:", prediction_data)
    print("Structure de predictions:", prediction_data.get('predictions', {}))
    print("Données win_or_draw brutes:", prediction_data.get('predictions', {}).get('win_or_draw'))
    print("Données winner brutes:", prediction_data.get('predictions', {}).get('winner'))
    
    # Formater les prédictions pour l'affichage
    formatted_prediction = {
        'teams': {
            'home': {
                'name': match['teams']['home']['name'],
                'league': {
                    'strength': round(safe_int_convert(safe_get(prediction_data, 'predictions', 'teams', 'home', 'win', default=50)), 2)
                }
            },
            'away': {
                'name': match['teams']['away']['name'],
                'league': {
                    'strength': round(safe_int_convert(safe_get(prediction_data, 'predictions', 'teams', 'away', 'win', default=50)), 2)
                }
            }
        },
        'strength': {
            'home': round(safe_int_convert(safe_get(prediction_data, 'predictions', 'teams', 'home', 'win', default=50)), 2),
            'away': round(safe_int_convert(safe_get(prediction_data, 'predictions', 'teams', 'away', 'win', default=50)), 2)
        },
        'comparison': {
            'att': {
                'home': round(safe_int_convert(safe_get(prediction_data, 'comparison', 'att', 'home', default=50)), 2),
                'away': round(safe_int_convert(safe_get(prediction_data, 'comparison', 'att', 'away', default=50)), 2)
            },
            'def': {
                'home': round(safe_int_convert(safe_get(prediction_data, 'comparison', 'def', 'home', default=50)), 2),
                'away': round(safe_int_convert(safe_get(prediction_data, 'comparison', 'def', 'away', default=50)), 2)
            }
        },
        'poisson': {
            'home': round(safe_int_convert(safe_get(prediction_data, 'comparison', 'poisson_distribution', 'home', default=50)), 2),
            'away': round(safe_int_convert(safe_get(prediction_data, 'comparison', 'poisson_distribution', 'away', default=50)), 2)
        },
        'predictions': {
            'winner': {
                'name': safe_get(prediction_data, 'winner', 'name') if safe_get(prediction_data, 'winner') else None,
                'comment': safe_get(prediction_data, 'winner', 'comment') if safe_get(prediction_data, 'winner') else None
            },
            'win_or_draw': safe_get(prediction_data, 'win_or_draw', default=False),
            'win_or_draw_team': safe_get(prediction_data, 'win_or_draw_team'),
            'under_over': safe_get(prediction_data, 'under_over'),  # Liste de toutes les prédictions under/over
            'goals_home': safe_get(prediction_data, 'goals_home'),
            'goals_away': safe_get(prediction_data, 'goals_away'),
            'advice': safe_get(prediction_data, 'advice')
        },
        'h2h': {
            'strength': 50,  # Valeur par défaut
            'goals': 2.5  # Valeur par défaut
        }
    }

    # Mettre à jour les valeurs si disponibles dans l'API
    if 'predictions' in prediction_data:
        if 'teams' in prediction_data['predictions']:
            if 'home' in prediction_data['predictions']['teams']:
                formatted_prediction['teams']['home']['league']['strength'] = round(safe_int_convert(safe_get(prediction_data, 'predictions', 'teams', 'home', 'win', default=50)), 2)
                formatted_prediction['strength']['home'] = formatted_prediction['teams']['home']['league']['strength']
            if 'away' in prediction_data['predictions']['teams']:
                formatted_prediction['teams']['away']['league']['strength'] = round(safe_int_convert(safe_get(prediction_data, 'predictions', 'teams', 'away', 'win', default=50)), 2)
                formatted_prediction['strength']['away'] = formatted_prediction['teams']['away']['league']['strength']

    print("Données formatées:", formatted_prediction)  # Debug log

    return render_template('prediction.html', 
                         match=match,
                         prediction=formatted_prediction)

@app.route('/prediction/<int:fixture_id>')
def show_prediction(fixture_id):
    # Obtenir les prédictions
    prediction_data = get_prediction(fixture_id)
    if not prediction_data:
        return redirect('/')

    prediction = prediction_data

    # Obtenir les statistiques des équipes
    home_team_id = prediction['teams']['home']['id']
    away_team_id = prediction['teams']['away']['id']
    league_id = prediction['league']['id']
    
    # Obtenir les statistiques des équipes sur les 3 dernières saisons
    current_season = 2023
    seasons = [current_season, current_season - 1, current_season - 2]
    
    home_stats = None
    away_stats = None
    
    # Essayer chaque saison jusqu'à trouver des statistiques valides
    for season in seasons:
        if not home_stats:
            home_stats_data = make_api_request("teams/statistics", 
                                             f"team={home_team_id}&season={season}&league={league_id}")
            if home_stats_data.get('response', {}).get('goals', {}).get('for', {}).get('average', {}).get('total'):
                home_stats = home_stats_data.get('response', {})
        
        if not away_stats:
            away_stats_data = make_api_request("teams/statistics", 
                                             f"team={away_team_id}&season={season}&league={league_id}")
            if away_stats_data.get('response', {}).get('goals', {}).get('for', {}).get('average', {}).get('total'):
                away_stats = away_stats_data.get('response', {})
        
        if home_stats and away_stats:
            break
    
    # Si toujours pas de stats, utiliser les dernières données disponibles
    if not home_stats:
        home_stats_data = make_api_request("teams/statistics", 
                                         f"team={home_team_id}&season={current_season}&league={league_id}")
        home_stats = home_stats_data.get('response', {})
    
    if not away_stats:
        away_stats_data = make_api_request("teams/statistics", 
                                         f"team={away_team_id}&season={current_season}&league={league_id}")
        away_stats = away_stats_data.get('response', {})
    
    # Convertir les statistiques en nombres
    if home_stats and 'goals' in home_stats:
        home_stats['goals']['for']['average']['total'] = safe_float(home_stats['goals']['for']['average']['total'])
        home_stats['goals']['against']['average']['total'] = safe_float(home_stats['goals']['against']['average']['total'])
    
    if away_stats and 'goals' in away_stats:
        away_stats['goals']['for']['average']['total'] = safe_float(away_stats['goals']['for']['average']['total'])
        away_stats['goals']['against']['average']['total'] = safe_float(away_stats['goals']['against']['average']['total'])
    
    # Obtenir l'historique des confrontations
    h2h = make_api_request("fixtures/headtohead", f"h2h={home_team_id}-{away_team_id}&last=5")

    return render_template(
        'prediction.html',
        prediction=prediction,
        home_stats=home_stats,
        away_stats=away_stats,
        h2h=h2h.get('response', [])
    )

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                             'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')
