import requests
import os
from datetime import datetime

API_KEY = os.environ.get("RIOT_API_KEY")

REGION = "americas"

HEADERS = {
    "X-Riot-Token": API_KEY
}

ULTIMO_CODIGO_HTTP = None


def guardar_codigo_http(codigo):
    global ULTIMO_CODIGO_HTTP
    ULTIMO_CODIGO_HTTP = codigo


def obtener_ultimo_codigo_http():
    return ULTIMO_CODIGO_HTTP


# =========================================================
# CUENTA RIOT
# =========================================================

def obtener_puuid_por_riot_id(game_name, tag_line):

    url = (
        f"https://americas.api.riotgames.com"
        f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    )

    respuesta = requests.get(url, headers=HEADERS)

    guardar_codigo_http(respuesta.status_code)

    if respuesta.status_code == 200:
        datos = respuesta.json()
        return datos.get("puuid")

    print("Error al obtener PUUID por Riot ID.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


# =========================================================
# SUMMONER
# =========================================================

def obtener_summoner_por_puuid(puuid):

    url = (
        f"https://la2.api.riotgames.com"
        f"/lol/summoner/v4/summoners/by-puuid/{puuid}"
    )

    respuesta = requests.get(url, headers=HEADERS)

    guardar_codigo_http(respuesta.status_code)

    if respuesta.status_code == 200:
        datos = respuesta.json()

        return {
            "id": datos.get("id"),
            "puuid": datos.get("puuid", puuid),
            "name": datos.get("name")
        }

    print("Error al obtener Summoner.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


def obtener_summoner_id(puuid, game_name=None):

    datos = obtener_summoner_por_puuid(puuid)

    if datos and datos.get("id"):
        return datos["id"]

    if game_name:

        url = (
            f"https://la2.api.riotgames.com"
            f"/lol/summoner/v4/summoners/by-name/{game_name}"
        )

        respuesta = requests.get(url, headers=HEADERS)

        guardar_codigo_http(respuesta.status_code)

        print("RESPUESTA BY NAME:")
        print(respuesta.status_code)
        print(respuesta.text)

        if respuesta.status_code == 200:
            datos = respuesta.json()

            if datos.get("id"):
                return datos["id"]

    print("No se pudo obtener el Summoner ID.")

    return None


# =========================================================
# PARTIDAS
# =========================================================

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

    guardar_codigo_http(respuesta.status_code)

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

    guardar_codigo_http(respuesta.status_code)

    if respuesta.status_code == 200:
        return respuesta.json()

    print("Error al obtener detalle de partida.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


# =========================================================
# PARTIDA ACTIVA
# =========================================================

def jugador_en_partida(puuid):
    if not puuid:
        print("SPECTATOR: No hay PUUID.")
        return None

    print("SPECTATOR: Consultando Summoner por PUUID...")
    
    summoner = obtener_summoner_por_puuid(puuid)

    if not summoner:
        print("SPECTATOR: No se pudo obtener el Summoner.")
        print("SPECTATOR: Código HTTP:", obtener_ultimo_codigo_http())
        return None

    summoner_id = summoner.get("id")

    print("SPECTATOR: Summoner obtenido.")
    print("SPECTATOR: Summoner ID:", summoner_id)

    if not summoner_id:
        print("SPECTATOR: El Summoner no tiene ID.")
        return None

    url = (
        f"https://la2.api.riotgames.com"
        f"/lol/spectator/v5/active-games/by-summoner/{summoner_id}"
    )

    print("SPECTATOR: Consultando partida activa...")

    respuesta = requests.get(url, headers=HEADERS)

    guardar_codigo_http(respuesta.status_code)

    print("RESPUESTA SPECTATOR:")
    print(respuesta.status_code)
    print(respuesta.text)

    if respuesta.status_code == 200:
        datos = respuesta.json()

        return {
            "game_id": datos.get("gameId"),
            "game_start_time": datos.get("gameStartTime")
        }

    if respuesta.status_code == 404:
        return None

    print("Error al consultar partida activa.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None

# =========================================================
# RANGO
# =========================================================

def obtener_rango(puuid):

    url = (
        f"https://la2.api.riotgames.com"
        f"/lol/league/v4/entries/by-puuid/{puuid}"
    )

    respuesta = requests.get(
        url,
        headers=HEADERS
    )

    guardar_codigo_http(respuesta.status_code)

    print("RESPUESTA RANKING:")
    print(respuesta.status_code)
    print(respuesta.text)

    if respuesta.status_code == 200:

        datos = respuesta.json()

        for liga in datos:

            if liga.get("queueType") == "RANKED_SOLO_5x5":

                return {
                    "tier": liga.get("tier"),
                    "rank": liga.get("rank"),
                    "lp": liga.get("leaguePoints"),
                    "wins": liga.get("wins"),
                    "losses": liga.get("losses")
                }

        return {
            "tier": "UNRANKED",
            "rank": "",
            "lp": 0,
            "wins": 0,
            "losses": 0
        }

    print("Error al obtener rango.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


# =========================================================
# ACTUALIZAR HISTORIAL
# =========================================================

def actualizar_partidas_jugador(puuid, cantidad=10):

    partidas = obtener_partidas(puuid, cantidad)

    if partidas is None:
        return None

    if not partidas:
        return []

    resultado = []

    for match_id in partidas:

        datos = obtener_detalle_partida(match_id)

        if not datos:
            continue

        info = datos.get("info", {})

        participantes = info.get("participants", [])

        jugador = None

        for participante in participantes:

            if participante.get("puuid") == puuid:
                jugador = participante
                break

        if not jugador:
            continue

        fecha = (
            info.get("gameEndTimestamp")
            or info.get("gameCreation")
        )

        if fecha:

            fecha = datetime.fromtimestamp(
                fecha / 1000
            ).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        resultado.append({
            "match_id": match_id,
            "fecha": fecha,
            "modo": info.get("gameMode"),
            "duracion": info.get("gameDuration"),
            "resultado":
                "VICTORIA"
                if jugador.get("win")
                else "DERROTA",
            "campeon": jugador.get("championName")
        })

    return resultado