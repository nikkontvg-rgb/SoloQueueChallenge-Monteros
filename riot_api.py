import requests
from config import API_KEY


REGION = "americas"

HEADERS = {
    "X-Riot-Token": API_KEY
}


def obtener_puuid(game_name, tag_line):

    url = (
        f"https://{REGION}.api.riotgames.com"
        f"/riot/account/v1/accounts/by-riot-id/"
        f"{game_name}/{tag_line}"
    )

    respuesta = requests.get(url, headers=HEADERS)

    if respuesta.status_code == 200:
        datos = respuesta.json()

        return {
            "puuid": datos["puuid"],
            "game_name": datos["gameName"],
            "tag_line": datos["tagLine"]
        }

    print("Error al buscar Riot ID.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


def obtener_partidas(puuid, cantidad=20):

    url = (
        f"https://{REGION}.api.riotgames.com"
        f"/lol/match/v5/matches/by-puuid/"
        f"{puuid}/ids"
    )

    parametros = {
        "start": 0,
        "count": cantidad
    }

    respuesta = requests.get(
        url,
        headers=HEADERS,
        params=parametros
    )

    if respuesta.status_code == 200:
        return respuesta.json()

    print("Error al obtener partidas.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


def obtener_detalle_partida(match_id):

    url = (
        f"https://{REGION}.api.riotgames.com"
        f"/lol/match/v5/matches/{match_id}"
    )

    respuesta = requests.get(
        url,
        headers=HEADERS
    )

    if respuesta.status_code == 200:
        return respuesta.json()

    print("Error al obtener detalle de partida.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None

def jugador_en_partida(puuid):
    url = (
        f"https://la2.api.riotgames.com"
        f"/lol/spectator/v5/active-games/by-summoner/{puuid}"
    )

    respuesta = requests.get(url, headers=HEADERS)

    if respuesta.status_code == 200:
        return True

    if respuesta.status_code == 404:
        return False

    print("Error al consultar partida activa.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return False