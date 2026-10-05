import requests
import os
from datetime import datetime
from urllib.parse import quote


API_KEY = os.environ.get("RIOT_API_KEY")

REGION = "americas"
REGION_LOL = "la2"

HEADERS = {
    "X-Riot-Token": API_KEY
}

ULTIMO_CODIGO_HTTP = None

TIMEOUT = 15


# =========================================================
# CONTROL DE CÓDIGOS HTTP
# =========================================================

def guardar_codigo_http(codigo):
    global ULTIMO_CODIGO_HTTP
    ULTIMO_CODIGO_HTTP = codigo


def obtener_ultimo_codigo_http():
    return ULTIMO_CODIGO_HTTP


# =========================================================
# OBTENER PUUID MEDIANTE RIOT ID + TAG
# =========================================================

def obtener_puuid_por_riot_id(game_name, tag_line):

    if not game_name or not tag_line:
        return None

    game_name = quote(str(game_name), safe="")
    tag_line = quote(str(tag_line), safe="")

    url = (
        f"https://{REGION}.api.riotgames.com/"
        f"riot/account/v1/accounts/by-riot-id/"
        f"{game_name}/{tag_line}"
    )

    try:
        respuesta = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

    except requests.RequestException as error:

        print("ERROR DE CONEXIÓN AL OBTENER PUUID:")
        print(error)

        guardar_codigo_http(None)

        return None

    guardar_codigo_http(respuesta.status_code)

    if respuesta.status_code == 200:

        datos = respuesta.json()

        return datos.get("puuid")

    print("Error al obtener PUUID por Riot ID.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


# =========================================================
# OBTENER DATOS DEL SUMMONER MEDIANTE PUUID
# =========================================================

def obtener_summoner_por_puuid(puuid):

    if not puuid:
        return None

    puuid_url = quote(str(puuid), safe="")

    url = (
        f"https://{REGION_LOL}.api.riotgames.com/"
        f"lol/summoner/v4/summoners/by-puuid/"
        f"{puuid_url}"
    )

    try:

        respuesta = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

    except requests.RequestException as error:

        print("ERROR DE CONEXIÓN AL OBTENER SUMMONER:")
        print(error)

        guardar_codigo_http(None)

        return None

    guardar_codigo_http(respuesta.status_code)

    if respuesta.status_code == 200:

        datos = respuesta.json()

        return {
            "id": datos.get("id"),
            "puuid": datos.get("puuid", puuid),
            "name": datos.get("name"),
            "account_id": datos.get("accountId")
        }

    print("Error al obtener Summoner.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


# =========================================================
# OBTENER SUMMONER ID
#
# Esta función se mantiene para compatibilidad.
# La idea es utilizarla solamente al registrar/refrescar
# un jugador, NO en cada consulta de estado.
# =========================================================

def obtener_summoner_id(puuid, game_name=None):

    datos = obtener_summoner_por_puuid(puuid)

    if datos and datos.get("id"):

        return datos["id"]

    # Fallback antiguo por nombre
    if game_name:

        game_name_url = quote(str(game_name), safe="")

        url = (
            f"https://{REGION_LOL}.api.riotgames.com/"
            f"lol/summoner/v4/summoners/by-name/"
            f"{game_name_url}"
        )

        try:

            respuesta = requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT
            )

        except requests.RequestException as error:

            print(
                "ERROR DE CONEXIÓN AL OBTENER "
                "SUMMONER POR NOMBRE:"
            )

            print(error)

            guardar_codigo_http(None)

            return None

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
# REGISTRO COMPLETO DE UNA CUENTA
#
# Riot ID + Tag
#       ↓
# PUUID
#       ↓
# Summoner ID
#
# Devuelve ambos datos para que servidor.py pueda
# guardarlos en datos.json.
# =========================================================

def registrar_cuenta_riot(game_name, tag_line):

    print()
    print("========================================")
    print("REGISTRANDO CUENTA RIOT")
    print("========================================")
    print("Riot ID:", game_name)
    print("Tag:", tag_line)

    # -----------------------------------------
    # 1. Obtener PUUID
    # -----------------------------------------

    puuid = obtener_puuid_por_riot_id(
        game_name,
        tag_line
    )

    if not puuid:

        print("NO SE PUDO OBTENER EL PUUID.")

        return {
            "ok": False,
            "puuid": None,
            "summoner_id": None,
            "error": "No se pudo obtener el PUUID."
        }

    print("PUUID obtenido correctamente.")

    # -----------------------------------------
    # 2. Obtener Summoner ID
    # -----------------------------------------

    summoner = obtener_summoner_por_puuid(puuid)

    if not summoner:

        print("NO SE PUDO OBTENER EL SUMMONER.")

        return {
            "ok": False,
            "puuid": puuid,
            "summoner_id": None,
            "error": "No se pudo obtener el Summoner."
        }

    summoner_id = summoner.get("id")

    if not summoner_id:

        print("EL SUMMONER NO TIENE ID.")

        return {
            "ok": False,
            "puuid": puuid,
            "summoner_id": None,
            "error": "La cuenta no tiene Summoner ID."
        }

    print("Summoner ID obtenido correctamente.")
    print("Summoner ID:", summoner_id)

    print("========================================")
    print("REGISTRO COMPLETADO")
    print("========================================")
    print()

    return {
        "ok": True,
        "puuid": puuid,
        "summoner_id": summoner_id,
        "summoner_name": summoner.get("name")
    }


# =========================================================
# PARTIDAS DEL JUGADOR
# =========================================================

def obtener_partidas(puuid, cantidad=20):

    if not puuid:
        return None

    puuid_url = quote(str(puuid), safe="")

    url = (
        f"https://{REGION}.api.riotgames.com/"
        f"lol/match/v5/matches/by-puuid/"
        f"{puuid_url}/ids"
    )

    parametros = {
        "start": 0,
        "count": cantidad
    }

    try:

        respuesta = requests.get(
            url,
            headers=HEADERS,
            params=parametros,
            timeout=TIMEOUT
        )

    except requests.RequestException as error:

        print("ERROR DE CONEXIÓN AL OBTENER PARTIDAS:")
        print(error)

        guardar_codigo_http(None)

        return None

    guardar_codigo_http(respuesta.status_code)

    if respuesta.status_code == 200:

        return respuesta.json()

    print("Error al obtener partidas.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


# =========================================================
# DETALLE DE UNA PARTIDA
# =========================================================

def obtener_detalle_partida(match_id):

    if not match_id:
        return None

    match_id_url = quote(str(match_id), safe="")

    url = (
        f"https://{REGION}.api.riotgames.com/"
        f"lol/match/v5/matches/"
        f"{match_id_url}"
    )

    try:

        respuesta = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

    except requests.RequestException as error:

        print(
            "ERROR DE CONEXIÓN AL OBTENER "
            "DETALLE DE PARTIDA:"
        )

        print(error)

        guardar_codigo_http(None)

        return None

    guardar_codigo_http(respuesta.status_code)

    if respuesta.status_code == 200:

        return respuesta.json()

    print("Error al obtener detalle de partida.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


# =========================================================
# DETECCIÓN DE PARTIDA ACTIVA
#
# IMPORTANTE:
# Esta función YA NO busca el Summoner ID.
#
# Recibe directamente el Summoner ID guardado.
#
# Esto evita:
#
# PUUID → Summoner ID → Spectator
#
# en cada consulta.
#
# Ahora hacemos directamente:
#
# Summoner ID → Spectator V5
# =========================================================

def jugador_en_partida(summoner_id):

    if not summoner_id:

        print("No hay Summoner ID para consultar partida.")

        return None

    print("Consultando partida activa...")
    print("Summoner ID:", summoner_id)

    summoner_id_url = quote(
        str(summoner_id),
        safe=""
    )

    url = (
        f"https://{REGION_LOL}.api.riotgames.com/"
        f"lol/spectator/v5/active-games/"
        f"by-summoner/{summoner_id_url}"
    )

    try:

        respuesta = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

    except requests.RequestException as error:

        print(
            "ERROR DE CONEXIÓN AL CONSULTAR "
            "SPECTATOR:"
        )

        print(error)

        guardar_codigo_http(None)

        return None

    guardar_codigo_http(respuesta.status_code)

    print("RESPUESTA SPECTATOR:")
    print(respuesta.status_code)

    if respuesta.status_code == 200:

        try:
            datos = respuesta.json()

        except ValueError:

            print("La respuesta de Spectator no es JSON válido.")

            return None

        print("PARTIDA ACTIVA DETECTADA.")

        return {
            "game_id": datos.get("gameId"),
            "game_start_time": datos.get("gameStartTime")
        }

    if respuesta.status_code == 404:

        print("El jugador NO está en partida.")

        return None

    print("Error al consultar partida activa.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


# =========================================================
# OBTENER RANGO
# =========================================================

def obtener_rango(puuid):

    if not puuid:
        return None

    puuid_url = quote(str(puuid), safe="")

    url = (
        f"https://{REGION_LOL}.api.riotgames.com/"
        f"lol/league/v4/entries/by-puuid/"
        f"{puuid_url}"
    )

    try:

        respuesta = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

    except requests.RequestException as error:

        print("ERROR DE CONEXIÓN AL OBTENER RANGO:")
        print(error)

        guardar_codigo_http(None)

        return None

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
# ACTUALIZAR HISTORIAL DEL JUGADOR
# =========================================================

def actualizar_partidas_jugador(puuid, cantidad=10):

    partidas = obtener_partidas(
        puuid,
        cantidad
    )

    if partidas is None:
        return None

    if not partidas:
        return []

    resultado = []

    for match_id in partidas:

        datos = obtener_detalle_partida(
            match_id
        )

        if not datos:
            continue

        info = datos.get(
            "info",
            {}
        )

        participantes = info.get(
            "participants",
            []
        )

        jugador = None

        for participante in participantes:

            if participante.get("puuid") == puuid:

                jugador = participante

                break

        if not jugador:
            continue

        fecha = (
            info.get("gameEndTimestamp")
            or
            info.get("gameCreation")
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

            "modo": info.get(
                "gameMode"
            ),

            "duracion": info.get(
                "gameDuration"
            ),

            "resultado":
                "VICTORIA"
                if jugador.get("win")
                else "DERROTA",

            "campeon": jugador.get(
                "championName"
            )
        })

    return resultado