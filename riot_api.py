import requests
import os
import time
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
# FUNCIÓN CENTRALIZADA "ANTI-CRASH" PARA RATE LIMITS
# =========================================================
def hacer_peticion(url, params=None):
    for intento in range(3):  # Intenta hasta 3 veces si Riot lo bloquea
        try:
            # timeout=10 evita que Gunicorn en Render colapse
            respuesta = requests.get(url, headers=HEADERS, params=params, timeout=10)
            guardar_codigo_http(respuesta.status_code)

            if respuesta.status_code == 200:
                return respuesta.json()

            if respuesta.status_code == 404:
                return None  # Normal para jugadores sin rango o que no están en partida

            if respuesta.status_code == 429:
                # Si Riot nos pone Rate Limit, leemos cuántos segundos debemos pausar
                espera = int(respuesta.headers.get("Retry-After", 2))
                
                # Si la espera es enorme (>15s), abortamos para no trabar todo el servidor
                if espera > 15:
                    print(f"⚠️️ RATE LIMIT EXTREMO. Abortando petición...")
                    return None
                    
                print(f"⚠️ RATE LIMIT 429: Pausando script por {espera} segundos...")
                time.sleep(espera + 1)
                continue  # Vuelve a intentar la petición

            print(f"Error {respuesta.status_code} en URL: {url}")
            return None

        except requests.exceptions.RequestException as e:
            print(f"Caída de red (Intento {intento + 1}): {e}")
            time.sleep(2)  # Pausa antes de reintentar si hay corte de internet
            
    return None


# =========================================================
# CUENTA RIOT Y SUMMONER
# =========================================================

def obtener_puuid_por_riot_id(game_name, tag_line):
    url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    datos = hacer_peticion(url)
    return datos.get("puuid") if datos else None


def obtener_summoner_por_puuid(puuid):
    url = f"https://la2.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    datos = hacer_peticion(url)
    if datos:
        return {
            "id": datos.get("id"),
            "puuid": datos.get("puuid", puuid),
            "name": datos.get("name")
        }
    return None


def obtener_summoner_id(puuid, game_name=None):
    datos = obtener_summoner_por_puuid(puuid)
    if datos and datos.get("id"):
        return datos["id"]

    if game_name:
        url = f"https://la2.api.riotgames.com/lol/summoner/v4/summoners/by-name/{game_name}"
        datos_name = hacer_peticion(url)
        if datos_name and datos_name.get("id"):
            return datos_name["id"]
    return None


# =========================================================
# PARTIDAS Y SPECTATOR
# =========================================================

# Reducimos de 20 a 5 para cuidar drásticamente la cuota del Rate Limit
def obtener_partidas(puuid, cantidad=5):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    params = {"start": 0, "count": cantidad}
    return hacer_peticion(url, params)


def obtener_detalle_partida(match_id):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return hacer_peticion(url)


def jugador_en_partida(puuid):
    if not puuid:
        return None

    url = f"https://la2.api.riotgames.com/lol/spectator/v5/active-games/by-puuid/{puuid}"
    print("SPECTATOR: Consultando partida activa...")
    datos = hacer_peticion(url)
    
    if datos:
        return {
            "game_id": datos.get("gameId"),
            "game_start_time": datos.get("gameStartTime")
        }
    return None


# =========================================================
# RANGO
# =========================================================

def obtener_rango(puuid):
    summoner = obtener_summoner_por_puuid(puuid)
    
    if not summoner or not summoner.get("id"):
        return None
        
    summoner_id = summoner.get("id")
    url = f"https://la2.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
    
    datos = hacer_peticion(url)
    
    if datos:
        for liga in datos:
            if liga.get("queueType") == "RANKED_SOLO_5x5":
                return {
                    "tier": liga.get("tier"),
                    "rank": liga.get("rank"),
                    "lp": liga.get("leaguePoints"),
                    "wins": liga.get("wins"),
                    "losses": liga.get("losses")
                }
    return None


# =========================================================
# ACTUALIZAR HISTORIAL
# =========================================================

def actualizar_partidas_jugador(puuid, cantidad=5):
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

        fecha = info.get("gameEndTimestamp") or info.get("gameCreation")
        if fecha:
            fecha = datetime.fromtimestamp(fecha / 1000).strftime("%Y-%m-%d %H:%M:%S")

        resultado.append({
            "match_id": match_id,
            "fecha": fecha,
            "modo": info.get("gameMode"),
            "duracion": info.get("gameDuration"),
            "resultado": "VICTORIA" if jugador.get("win") else "DERROTA",
            "campeon": jugador.get("championName")
        })
        
        # Pausa microscópica para evitar bombardear a Riot de golpe
        time.sleep(0.3)

    return resultado