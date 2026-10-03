import requests
import os

API_KEY = os.environ.get("RIOT_API_KEY")

REGION = "americas"

HEADERS = {
    "X-Riot-Token": API_KEY
}


def obtener_puuid_por_riot_id(game_name, tag_line):
    url = (
        f"https://americas.api.riotgames.com"
        f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    )

    respuesta = requests.get(url, headers=HEADERS)

    if respuesta.status_code == 200:
        datos = respuesta.json()
        return datos["puuid"]

    print("Error al obtener PUUID por Riot ID.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


def obtener_summoner_id(puuid, game_name=None):
    # Primer intento: buscar por PUUID
    url = (
        f"https://la2.api.riotgames.com"
        f"/lol/summoner/v4/summoners/by-puuid/{puuid}"
    )

    respuesta = requests.get(url, headers=HEADERS)

    if respuesta.status_code == 200:
        datos = respuesta.json()

        print("RESPUESTA SUMMONER API:")
        print(datos)

        if datos.get("id"):
            return datos["id"]

    # Segundo intento: buscar por nombre
    if game_name:
        url = (
            f"https://la2.api.riotgames.com"
            f"/lol/summoner/v4/summoners/by-name/{game_name}"
        )

        respuesta = requests.get(url, headers=HEADERS)

        print("RESPUESTA BY NAME:")
        print(respuesta.status_code)
        print(respuesta.text)

        if respuesta.status_code == 200:
            datos = respuesta.json()

            if datos.get("id"):
                return datos["id"]

    print("No se pudo obtener el Summoner ID.")
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


def jugador_en_partida(game_name, tag_line):
    puuid = obtener_puuid_por_riot_id(game_name, tag_line)

    if not puuid:
        return False

    url = (
        f"https://la2.api.riotgames.com"
        f"/lol/spectator/v5/active-games/by-summoner/{puuid}"
    )

    respuesta = requests.get(url, headers=HEADERS)

    print("RESPUESTA SPECTATOR:")
    print(respuesta.status_code)
    print(respuesta.text)

    if respuesta.status_code == 200:
        return True

    if respuesta.status_code == 404:
        return False

    print("Error al consultar partida activa.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return False