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

MAX_PARTIDAS_GUARDADAS = 5


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
# Se utiliza principalmente durante el registro.
# =========================================================

def obtener_summoner_id(puuid, game_name=None):

    datos = obtener_summoner_por_puuid(puuid)

    if datos and datos.get("id"):

        return datos["id"]

    # Fallback antiguo por nombre
    if game_name:

        game_name_url = quote(
            str(game_name),
            safe=""
        )

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

        guardar_codigo_http(
            respuesta.status_code
        )

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
# REGISTRO COMPLETO DE CUENTA
#
# Riot ID + TAG
#       ↓
# PUUID
#       ↓
# Summoner ID
# =========================================================

def registrar_cuenta_riot(
    game_name,
    tag_line
):

    print()
    print("========================================")
    print("REGISTRANDO CUENTA RIOT")
    print("========================================")
    print("Riot ID:", game_name)
    print("Tag:", tag_line)

    # -----------------------------------------------------
    # 1. PUUID
    # -----------------------------------------------------

    puuid = obtener_puuid_por_riot_id(
        game_name,
        tag_line
    )

    if not puuid:

        print(
            "NO SE PUDO OBTENER EL PUUID."
        )

        return {
            "ok": False,
            "puuid": None,
            "summoner_id": None,
            "error": "No se pudo obtener el PUUID."
        }

    print(
        "PUUID obtenido correctamente."
    )

    # -----------------------------------------------------
    # 2. SUMMONER ID
    # -----------------------------------------------------

    summoner = obtener_summoner_por_puuid(
        puuid
    )

    if not summoner:

        print(
            "NO SE PUDO OBTENER EL SUMMONER."
        )

        return {
            "ok": False,
            "puuid": puuid,
            "summoner_id": None,
            "error": "No se pudo obtener el Summoner."
        }

    summoner_id = summoner.get(
        "id"
    )

    if not summoner_id:

        print(
            "EL SUMMONER NO TIENE ID."
        )

        return {
            "ok": False,
            "puuid": puuid,
            "summoner_id": None,
            "error": "La cuenta no tiene Summoner ID."
        }

    print(
        "Summoner ID obtenido correctamente."
    )

    print(
        "Summoner ID:",
        summoner_id
    )

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
# OBTENER IDs DE PARTIDAS
# =========================================================

def obtener_partidas(
    puuid,
    cantidad=5
):

    if not puuid:
        return None

    puuid_url = quote(
        str(puuid),
        safe=""
    )

    # Nunca pedir más de las necesarias.
    cantidad = min(
        int(cantidad),
        MAX_PARTIDAS_GUARDADAS
    )

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

        print(
            "ERROR DE CONEXIÓN AL OBTENER PARTIDAS:"
        )

        print(error)

        guardar_codigo_http(None)

        return None

    guardar_codigo_http(
        respuesta.status_code
    )

    if respuesta.status_code == 200:

        return respuesta.json()

    print("Error al obtener partidas.")
    print("Código:", respuesta.status_code)
    print("Respuesta:", respuesta.text)

    return None


# =========================================================
# OBTENER SOLO LA PARTIDA MÁS RECIENTE
#
# Esta es la consulta utilizada para jugadores que
# ya tienen historial guardado.
# =========================================================

def obtener_ultima_partida_id(
    puuid
):

    partidas = obtener_partidas(
        puuid,
        1
    )

    if partidas is None:

        return None

    if not partidas:

        return None

    return partidas[0]


# =========================================================
# DETALLE DE UNA PARTIDA
# =========================================================

def obtener_detalle_partida(
    match_id
):

    if not match_id:
        return None

    match_id_url = quote(
        str(match_id),
        safe=""
    )

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

    guardar_codigo_http(
        respuesta.status_code
    )

    if respuesta.status_code == 200:

        return respuesta.json()

    print(
        "Error al obtener detalle de partida."
    )

    print(
        "Código:",
        respuesta.status_code
    )

    print(
        "Respuesta:",
        respuesta.text
    )

    return None


# =========================================================
# CONVERTIR DETALLE DE PARTIDA A NUESTRO FORMATO
# =========================================================

def procesar_partida(
    puuid,
    match_id,
    datos
):

    if not datos:
        return None

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

        if participante.get(
            "puuid"
        ) == puuid:

            jugador = participante

            break

    if not jugador:

        return None

    fecha = (
        info.get(
            "gameEndTimestamp"
        )
        or
        info.get(
            "gameCreation"
        )
    )

    if fecha:

        fecha = datetime.fromtimestamp(
            fecha / 1000
        ).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    return {

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
    }


# =========================================================
# ACTUALIZAR HISTORIAL DE PARTIDAS
#
# COMPORTAMIENTO:
#
# JUGADOR NUEVO:
#   obtiene últimas 5 IDs
#   descarga detalles de las 5
#
# JUGADOR EXISTENTE:
#   obtiene solamente 1 ID
#   compara con la última guardada
#   si no cambió → no descarga detalles
#   si cambió → descarga solamente las nuevas
#
# SIEMPRE:
#   conserva máximo 5 partidas.
# =========================================================

def actualizar_partidas_jugador(
    puuid,
    partidas_existentes=None
):

    if not puuid:
        return None

    # -----------------------------------------------------
    # Normalizar historial existente
    # -----------------------------------------------------

    if not isinstance(
        partidas_existentes,
        list
    ):

        partidas_existentes = []

    # Limitar por seguridad
    partidas_existentes = partidas_existentes[
        :MAX_PARTIDAS_GUARDADAS
    ]

    # =====================================================
    # JUGADOR NUEVO
    # =====================================================

    if not partidas_existentes:

        print(
            "No existe historial guardado."
        )

        print(
            "Obteniendo últimas",
            MAX_PARTIDAS_GUARDADAS,
            "partidas..."
        )

        ids = obtener_partidas(
            puuid,
            MAX_PARTIDAS_GUARDADAS
        )

        if ids is None:

            return None

        if not ids:

            return []

        resultado = []

        for match_id in ids:

            datos = obtener_detalle_partida(
                match_id
            )

            if not datos:

                continue

            partida = procesar_partida(
                puuid,
                match_id,
                datos
            )

            if partida:

                resultado.append(
                    partida
                )

        return resultado[
            :MAX_PARTIDAS_GUARDADAS
        ]

    # =====================================================
    # JUGADOR EXISTENTE
    # =====================================================

    ultima_guardada = partidas_existentes[0]

    ultimo_match_id = ultima_guardada.get(
        "match_id"
    )

    if not ultimo_match_id:

        print(
            "La última partida guardada "
            "no tiene match_id."
        )

        # Si el historial está corrupto/incompleto,
        # reconstruimos las últimas 5.

        ids = obtener_partidas(
            puuid,
            MAX_PARTIDAS_GUARDADAS
        )

        if ids is None:

            return None

        resultado = []

        for match_id in ids:

            datos = obtener_detalle_partida(
                match_id
            )

            if not datos:
                continue

            partida = procesar_partida(
                puuid,
                match_id,
                datos
            )

            if partida:

                resultado.append(
                    partida
                )

        return resultado[
            :MAX_PARTIDAS_GUARDADAS
        ]

    # =====================================================
    # CONSULTAR SOLAMENTE EL ÚLTIMO ID
    # =====================================================

    print(
        "Consultando solamente la última partida..."
    )

    ultimo_match_riot = obtener_ultima_partida_id(
        puuid
    )

    if ultimo_match_riot is None:

        # No hubo respuesta válida.
        # Conservamos lo que ya teníamos.

        return partidas_existentes

    # =====================================================
    # NO HAY PARTIDA NUEVA
    # =====================================================

    if ultimo_match_riot == ultimo_match_id:

        print(
            "No hay partidas nuevas."
        )

        return partidas_existentes[
            :MAX_PARTIDAS_GUARDADAS
        ]

    # =====================================================
    # HAY UNA O MÁS PARTIDAS NUEVAS
    # =====================================================

    print(
        "Nueva partida detectada:",
        ultimo_match_riot
    )

    ids_nuevos = obtener_partidas(
        puuid,
        MAX_PARTIDAS_GUARDADAS
    )

    if ids_nuevos is None:

        return partidas_existentes

    # -----------------------------------------------------
    # Encontrar únicamente las partidas que todavía
    # no tenemos guardadas.
    # -----------------------------------------------------

    ids_existentes = set()

    for partida in partidas_existentes:

        match_id = partida.get(
            "match_id"
        )

        if match_id:

            ids_existentes.add(
                match_id
            )

    nuevas = []

    for match_id in ids_nuevos:

        if match_id in ids_existentes:

            break

        nuevas.append(
            match_id
        )

    # -----------------------------------------------------
    # Descargar solamente los detalles nuevos
    # -----------------------------------------------------

    nuevas_procesadas = []

    for match_id in nuevas:

        datos = obtener_detalle_partida(
            match_id
        )

        if not datos:

            continue

        partida = procesar_partida(
            puuid,
            match_id,
            datos
        )

        if partida:

            nuevas_procesadas.append(
                partida
            )

    # -----------------------------------------------------
    # Nuevas primero + antiguas
    # -----------------------------------------------------

    resultado = (
        nuevas_procesadas
        +
        partidas_existentes
    )

    # -----------------------------------------------------
    # Máximo 5
    # -----------------------------------------------------

    resultado = resultado[
        :MAX_PARTIDAS_GUARDADAS
    ]

    print(
        "Historial actualizado."
    )

    print(
        "Partidas guardadas:",
        len(resultado)
    )

    return resultado


# =========================================================
# DETECCIÓN DE PARTIDA ACTIVA
#
# Recibe directamente el Summoner ID guardado.
# =========================================================

def jugador_en_partida(
    summoner_id
):

    if not summoner_id:

        print(
            "No hay Summoner ID para consultar partida."
        )

        return None

    print(
        "Consultando partida activa..."
    )

    print(
        "Summoner ID:",
        summoner_id
    )

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

    guardar_codigo_http(
        respuesta.status_code
    )

    print(
        "RESPUESTA SPECTATOR:"
    )

    print(
        respuesta.status_code
    )

    if respuesta.status_code == 200:

        try:

            datos = respuesta.json()

        except ValueError:

            print(
                "La respuesta de Spectator "
                "no es JSON válido."
            )

            return None

        print(
            "PARTIDA ACTIVA DETECTADA."
        )

        return {
            "game_id": datos.get(
                "gameId"
            ),
            "game_start_time": datos.get(
                "gameStartTime"
            )
        }

    if respuesta.status_code == 404:

        print(
            "El jugador NO está en partida."
        )

        return None

    print(
        "Error al consultar partida activa."
    )

    print(
        "Código:",
        respuesta.status_code
    )

    print(
        "Respuesta:",
        respuesta.text
    )

    return None


# =========================================================
# OBTENER RANGO
# =========================================================

def obtener_rango(
    puuid
):

    if not puuid:
        return None

    puuid_url = quote(
        str(puuid),
        safe=""
    )

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

        print(
            "ERROR DE CONEXIÓN AL OBTENER RANGO:"
        )

        print(error)

        guardar_codigo_http(None)

        return None

    guardar_codigo_http(
        respuesta.status_code
    )

    print(
        "RESPUESTA RANKING:"
    )

    print(
        respuesta.status_code
    )

    print(
        respuesta.text
    )

    if respuesta.status_code == 200:

        datos = respuesta.json()

        for liga in datos:

            if liga.get(
                "queueType"
            ) == "RANKED_SOLO_5x5":

                return {

                    "tier": liga.get(
                        "tier"
                    ),

                    "rank": liga.get(
                        "rank"
                    ),

                    "lp": liga.get(
                        "leaguePoints"
                    ),

                    "wins": liga.get(
                        "wins"
                    ),

                    "losses": liga.get(
                        "losses"
                    )
                }

        return {

            "tier": "UNRANKED",

            "rank": "",

            "lp": 0,

            "wins": 0,

            "losses": 0
        }

    print(
        "Error al obtener rango."
    )

    print(
        "Código:",
        respuesta.status_code
    )

    print(
        "Respuesta:",
        respuesta.text
    )

    return None