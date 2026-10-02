import time
import json
from datetime import datetime
from riot_api import obtener_puuid, obtener_partidas, obtener_detalle_partida

ARCHIVO = "datos.json"
TIEMPO_MAXIMO = 4 * 60 * 60


# ==========================================
# FECHA Y HORA
# ==========================================

def obtener_fecha():

    return datetime.now().strftime("%Y-%m-%d")


def obtener_hora():

    return datetime.now().strftime("%H:%M:%S")


# ==========================================
# CARGAR DATOS
# ==========================================

def cargar_datos():

    try:

        with open(ARCHIVO, "r") as archivo:
            datos = json.load(archivo)

    except FileNotFoundError:

        datos = {
            "fecha": obtener_fecha(),
            "jugadores": {}
        }

    # --------------------------------------
    # COMPATIBILIDAD CON VERSIONES ANTERIORES
    # --------------------------------------

    if "jugadores" not in datos:

        datos = {
            "fecha": obtener_fecha(),
            "jugadores": {}
        }

    # --------------------------------------
    # SI CAMBIÓ EL DÍA
    # --------------------------------------

    if datos["fecha"] != obtener_fecha():

        datos["fecha"] = obtener_fecha()

        for jugador in datos["jugadores"]:

            datos["jugadores"][jugador]["tiempo_usado"] = 0

            datos["jugadores"][jugador]["sesion_activa"] = False

            datos["jugadores"][jugador]["inicio_sesion"] = None

            datos["jugadores"][jugador]["historial"] = []

    # --------------------------------------
    # ASEGURAR CAMPOS
    # --------------------------------------

    for jugador in datos["jugadores"]:

        datos["jugadores"][jugador].setdefault("riot_id", "")

        datos["jugadores"][jugador].setdefault("riot_tag", "")

        datos["jugadores"][jugador].setdefault("tiempo_usado", 0)

        datos["jugadores"][jugador].setdefault("sesion_activa", False)

        datos["jugadores"][jugador].setdefault("inicio_sesion", None)

        datos["jugadores"][jugador].setdefault("historial", [])

    return datos


# ==========================================
# GUARDAR DATOS
# ==========================================

def guardar_datos(datos):

    with open(ARCHIVO, "w") as archivo:

        json.dump(
            datos,
            archivo,
            indent=4,
            ensure_ascii=False
        )


# ==========================================
# FORMATEAR TIEMPO
# ==========================================

def formatear_tiempo(segundos):

    segundos = int(segundos)

    horas = segundos // 3600

    minutos = (segundos % 3600) // 60

    segundos_restantes = segundos % 60

    return f"{horas:02d}:{minutos:02d}:{segundos_restantes:02d}"


# ==========================================
# AGREGAR JUGADOR
# ==========================================

def agregar_jugador(datos):

    nombre = input("\nNombre del jugador: ").strip()

    if nombre == "":
        print("❌ El nombre no puede estar vacío.")
        return

    if nombre in datos["jugadores"]:
        print("⚠️ Ese jugador ya existe.")
        return

    riot_id = input("Riot ID (Game Name): ").strip()

    riot_tag = input("Tag Line (por ejemplo LAS): ").strip()

    print("\nBuscando jugador en Riot...")

    datos_riot = obtener_puuid(riot_id, riot_tag)

    if datos_riot is None:
        print("\n❌ No se pudo encontrar ese Riot ID.")
        print("Revisá que el nombre y TAG estén escritos correctamente.")
        return

    print("✅ Jugador encontrado en Riot.")
    print("PUUID:", datos_riot["puuid"])

    jugador = {
        "riot_id": datos_riot["game_name"],
        "riot_tag": datos_riot["tag_line"],
        "puuid": datos_riot["puuid"],
        "tiempo_usado": 0,
        "sesion_activa": False,
        "inicio_sesion": None,
        "historial": []
    }

    datos["jugadores"][nombre] = jugador

    guardar_datos(datos)

    print(f"\n✅ Jugador '{nombre}' agregado.")
    print(f"🎮 Riot ID: {riot_id}#{riot_tag}")

# ==========================================
# MOSTRAR JUGADORES
# ==========================================

def mostrar_jugadores(datos):

    if not datos["jugadores"]:

        print("\n⚠️ No hay jugadores registrados.")

        return

    print("\n🏆 JUGADORES")

    print("-------------------------------")

    for numero, nombre in enumerate(datos["jugadores"], 1):

        jugador = datos["jugadores"][nombre]

        tiempo = jugador["tiempo_usado"]

        estado = (
            "🟢 ACTIVO"
            if jugador["sesion_activa"]
            else "🔴 INACTIVO"
        )

        riot_id = jugador["riot_id"]

        riot_tag = jugador["riot_tag"]

        if riot_id:

            riot = f"{riot_id}#{riot_tag}"

        else:

            riot = "No configurado"

        print(f"\n{numero}. {nombre}")

        print(f"   🎮 Riot ID: {riot}")

        print(
            f"   ⏱️ Tiempo: "
            f"{formatear_tiempo(tiempo)} / 04:00:00"
        )

        print(f"   Estado: {estado}")


# ==========================================
# SELECCIONAR JUGADOR
# ==========================================

def seleccionar_jugador(datos):

    jugadores = list(datos["jugadores"].keys())

    if not jugadores:

        print("\n⚠️ Primero tenés que agregar jugadores.")

        return None

    print("\n👤 Seleccioná un jugador:")

    for numero, nombre in enumerate(jugadores, 1):

        print(f"{numero}. {nombre}")

    try:

        opcion = int(input("\nNúmero: "))

        if opcion < 1 or opcion > len(jugadores):

            print("❌ Opción inválida.")

            return None

        return jugadores[opcion - 1]

    except ValueError:

        print("❌ Tenés que introducir un número.")

        return None

# ==========================================
# VER PARTIDAS DE RIOT
# ==========================================
def ver_partidas_riot():

    datos = cargar_datos()

    nombre = seleccionar_jugador(datos)

    if nombre is None:
        return

    jugador = datos["jugadores"][nombre]

    if "puuid" not in jugador:

        print("\n🔎 El jugador no tiene PUUID guardado.")
        print("Buscando automáticamente en Riot...")

        datos_riot = obtener_puuid(
            jugador["riot_id"],
            jugador["riot_tag"]
        )

        if datos_riot is None:
            print("\n❌ No se pudo encontrar el jugador en Riot.")
            return

        jugador["puuid"] = datos_riot["puuid"]

        guardar_datos(datos)

        print("✅ PUUID encontrado y guardado correctamente.")

    print("\n🎮 Consultando partidas en Riot...")

    partidas = obtener_partidas(jugador["puuid"], 10)

    if partidas is None:
        return

    if len(partidas) == 0:
        print("\nNo se encontraron partidas.")
        return

    print(f"\n📋 Últimas {len(partidas)} partidas:")

    partidas_riot = []

    for i, match_id in enumerate(partidas, 1):

        detalle = obtener_detalle_partida(match_id)

        if detalle is None:
            continue

        info = detalle["info"]
        partida_guardada = {
        "match_id": match_id,
        "fecha": datetime.fromtimestamp(
            info["gameStartTimestamp"] / 1000
            ).strftime("%Y-%m-%d %H:%M:%S"),
        "modo": info["gameMode"],
        "duracion": info["gameDuration"]
        }

        duracion = info["gameDuration"]

        minutos = duracion // 60
        segundos = duracion % 60

        resultado = "Desconocido"
        campeon = "Desconocido"

        for participante in info["participants"]:

            if participante["puuid"] == jugador["puuid"]:

                resultado = (
                    "VICTORIA"
                    if participante["win"]
                    else "DERROTA"
                )

                campeon = participante["championName"]

                partida_guardada["resultado"] = resultado
                partida_guardada["campeon"] = campeon

                break

        partidas_riot.append(partida_guardada)

        fecha = datetime.fromtimestamp(
            info["gameStartTimestamp"] / 1000
        )

        print("\n-----------------------------")
        print(f"🎮 Partida #{i}")
        print(f"🆔 Match ID: {match_id}")
        print(f"📅 Fecha: {fecha.strftime('%d/%m/%Y %H:%M')}")
        print(f"🎯 Modo: {info['gameMode']}")
        print(f"🧙 Campeón: {campeon}")
        print(f"🏆 Resultado: {resultado}")
        print(f"⏱️ Duración: {minutos}:{segundos:02d}")
        jugador["partidas_riot"] = partidas_riot

    guardar_datos(datos)

    print("\n💾 Partidas guardadas correctamente.")
# ==========================================
# ACTUALIZAR PARTIDAS DE RIOT
# ==========================================
def actualizar_partidas_riot():

    datos = cargar_datos()

    nombre = seleccionar_jugador(datos)

    if nombre is None:
        return

    jugador = datos["jugadores"][nombre]

    if "puuid" not in jugador:
        print("\n❌ Este jugador todavía no tiene PUUID.")
        return

    print("\n🔄 Buscando nuevas partidas en Riot...")

    partidas = obtener_partidas(jugador["puuid"], 20)

    if partidas is None:
        return

    if "partidas_riot" not in jugador:
        jugador["partidas_riot"] = []

    partidas_existentes = {
        partida["match_id"]
        for partida in jugador["partidas_riot"]
    }

    nuevas = 0

    for match_id in partidas:

        if match_id in partidas_existentes:
            continue

        detalle = obtener_detalle_partida(match_id)

        if detalle is None:
            continue

        info = detalle["info"]

        resultado = "Desconocido"
        campeon = "Desconocido"

        for participante in info["participants"]:

            if participante["puuid"] == jugador["puuid"]:

                resultado = (
                    "VICTORIA"
                    if participante["win"]
                    else "DERROTA"
                )

                campeon = participante["championName"]

                break

        partida = {
            "match_id": match_id,
            "fecha": datetime.fromtimestamp(
                info["gameStartTimestamp"] / 1000
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "modo": info["gameMode"],
            "duracion": info["gameDuration"],
            "resultado": resultado,
            "campeon": campeon
        }

        jugador["partidas_riot"].append(partida)

        nuevas += 1

    guardar_datos(datos)

    print(f"\n✅ Actualización terminada.")
    print(f"🆕 Partidas nuevas encontradas: {nuevas}")
# ==========================================
# INICIAR SESIÓN
# ==========================================

def iniciar_sesion(datos):

    nombre = seleccionar_jugador(datos)

    if nombre is None:

        return

    jugador = datos["jugadores"][nombre]

    if jugador["sesion_activa"]:

        print("⚠️ Este jugador ya tiene una sesión activa.")

        return

    if jugador["tiempo_usado"] >= TIEMPO_MAXIMO:

        print("🚫 Este jugador ya utilizó sus 4 horas de hoy.")

        return

    ahora = time.time()

    jugador["sesion_activa"] = True

    jugador["inicio_sesion"] = ahora

    guardar_datos(datos)

    print(f"\n🟢 Sesión iniciada para {nombre}")

    print(f"🕐 Hora: {obtener_hora()}")

    print("⏱️ El tiempo ya está corriendo.")


# ==========================================
# FINALIZAR SESIÓN
# ==========================================

def finalizar_sesion(datos):

    nombre = seleccionar_jugador(datos)

    if nombre is None:

        return

    jugador = datos["jugadores"][nombre]

    if not jugador["sesion_activa"]:

        print("⚠️ Este jugador no tiene una sesión activa.")

        return

    ahora = time.time()

    duracion = ahora - jugador["inicio_sesion"]

    tiempo_anterior = jugador["tiempo_usado"]

    jugador["tiempo_usado"] += duracion

    # No superar las 4 horas
    if jugador["tiempo_usado"] > TIEMPO_MAXIMO:

        jugador["tiempo_usado"] = TIEMPO_MAXIMO

    # --------------------------------------
    # CREAR HISTORIAL
    # --------------------------------------

    fecha = obtener_fecha()

    hora_inicio = datetime.fromtimestamp(
        jugador["inicio_sesion"]
    ).strftime("%H:%M:%S")

    hora_fin = obtener_hora()

    jugador["historial"].append({

        "fecha": fecha,

        "inicio": hora_inicio,

        "fin": hora_fin,

        "duracion": duracion

    })

    jugador["sesion_activa"] = False

    jugador["inicio_sesion"] = None

    guardar_datos(datos)

    restante = TIEMPO_MAXIMO - jugador["tiempo_usado"]

    print(f"\n🔴 Sesión finalizada para {nombre}")

    print(f"🕐 Inicio: {hora_inicio}")

    print(f"🕐 Fin: {hora_fin}")

    print(
        f"⏱️ Duración: "
        f"{formatear_tiempo(duracion)}"
    )

    print(
        f"📊 Total utilizado hoy: "
        f"{formatear_tiempo(jugador['tiempo_usado'])}"
    )

    print(
        f"⏳ Tiempo restante: "
        f"{formatear_tiempo(restante)}"
    )


# ==========================================
# VER HISTORIAL
# ==========================================

def ver_historial(datos):

    nombre = seleccionar_jugador(datos)

    if nombre is None:

        return

    jugador = datos["jugadores"][nombre]

    historial = jugador["historial"]

    print(f"\n📜 HISTORIAL DE {nombre}")

    print("==============================")

    if not historial:

        print("No hay sesiones registradas.")

        return

    for numero, sesion in enumerate(historial, 1):

        print(f"\nSesión #{numero}")

        print(f"📅 Fecha: {sesion['fecha']}")

        print(f"🟢 Inicio: {sesion['inicio']}")

        print(f"🔴 Fin: {sesion['fin']}")

        print(
            f"⏱️ Duración: "
            f"{formatear_tiempo(sesion['duracion'])}"
        )


# ==========================================
# EDITAR RIOT ID
# ==========================================

def editar_riot_id(datos):

    nombre = seleccionar_jugador(datos)

    if nombre is None:

        return

    jugador = datos["jugadores"][nombre]

    print(f"\n🎮 Riot ID actual:")

    if jugador["riot_id"]:

        print(
            f"{jugador['riot_id']}#{jugador['riot_tag']}"
        )

    else:

        print("No configurado.")

    nuevo_id = input(
        "\nNuevo Riot ID (Game Name): "
    ).strip()

    nuevo_tag = input(
        "Nuevo Tag Line: "
    ).strip()

    if nuevo_id == "" or nuevo_tag == "":

        print("❌ Los datos no pueden estar vacíos.")

        return

    jugador["riot_id"] = nuevo_id

    jugador["riot_tag"] = nuevo_tag

    guardar_datos(datos)

    print(
        f"\n✅ Riot ID actualizado: "
        f"{nuevo_id}#{nuevo_tag}"
    )


# ==========================================
# RECUPERAR SESIONES ABIERTAS
# ==========================================

def recuperar_sesiones(datos):

    hubo_cambios = False

    for nombre, jugador in datos["jugadores"].items():

        if jugador["sesion_activa"]:

            ahora = time.time()

            duracion = ahora - jugador["inicio_sesion"]

            jugador["tiempo_usado"] += duracion

            fecha = obtener_fecha()

            hora_inicio = datetime.fromtimestamp(
                jugador["inicio_sesion"]
            ).strftime("%H:%M:%S")

            hora_fin = obtener_hora()

            if jugador["tiempo_usado"] >= TIEMPO_MAXIMO:

                jugador["tiempo_usado"] = TIEMPO_MAXIMO

            # Guardar sesión recuperada
            jugador["historial"].append({

                "fecha": fecha,

                "inicio": hora_inicio,

                "fin": hora_fin,

                "duracion": duracion

            })

            jugador["sesion_activa"] = False

            jugador["inicio_sesion"] = None

            print(
                f"\n⚠️ Se encontró una sesión abierta "
                f"de {nombre}."
            )

            print(
                f"⏱️ Se contabilizaron "
                f"{formatear_tiempo(duracion)}."
            )

            hubo_cambios = True

    if hubo_cambios:

        guardar_datos(datos)


# ==========================================
# PROGRAMA PRINCIPAL
# ==========================================

datos = cargar_datos()

recuperar_sesiones(datos)

print("\n🏆 SOLO QUEUE CHALLENGE")

print("=======================")

while True:

    print("\n")

    print("1. 👤 Agregar jugador")

    print("2. 📋 Ver jugadores")

    print("3. 🟢 Iniciar sesión")

    print("4. 🔴 Finalizar sesión")

    print("5. 📜 Ver historial")

    print("6. 🎮 Editar Riot ID")

    print("7. 👀 Ver partidas de Riot")

    print("8. 🔄 Actualizar partidas de Riot")

    print("9. ❌ Salir")

    opcion = input("\nElegí una opción: ")

    if opcion == "1":

        agregar_jugador(datos)

    elif opcion == "2":

        mostrar_jugadores(datos)

    elif opcion == "3":

        iniciar_sesion(datos)

    elif opcion == "4":

        finalizar_sesion(datos)

    elif opcion == "5":

        ver_historial(datos)

    elif opcion == "6":

        editar_riot_id(datos)

    elif opcion == "7":
        ver_partidas_riot()
    
    elif opcion == "8":
        actualizar_partidas_riot()

    elif opcion == "9":
        print("Saliendo...")
    break

else:
    print("❌ Opción inválida.")