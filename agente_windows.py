# -*- coding: utf-8 -*-
"""Agente SoloQ Challenge Monteros para Windows.
Requiere: pip install requests psutil
Detecta procesos del cliente Riot/League y manda latidos a Render.
"""
import json, os, sys, time
from pathlib import Path
import requests
import psutil

CONFIG_PATH = Path(os.environ.get("APPDATA", str(Path.home()))) / "SoloQChallenge" / "config.json"
INTERVALO = 10
API_DEFAULT = "https://soloqueuechallenge-monteros.onrender.com"
PROCESOS_RIOT = {"riotclientservices.exe", "riotclientux.exe", "riotclientuxrender.exe", "leagueclient.exe", "leagueclientux.exe", "leagueclientuxrender.exe"}


def cargar_config():
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if data.get("nombre") and data.get("token"):
                return data
        except Exception:
            pass
    print("=== SoloQ Challenge Monteros ===")
    nombre = input("Nombre exacto del participante en la web: ").strip()
    token = input("Código del agente entregado por la organización: ").strip()
    api = input(f"Servidor [{API_DEFAULT}]: ").strip() or API_DEFAULT
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"nombre": nombre, "token": token, "api": api.rstrip("/")}
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def cliente_riot_abierto():
    try:
        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if name in PROCESOS_RIOT:
                return True
    except (psutil.Error, OSError):
        pass
    return False


def main():
    cfg = cargar_config()
    if not cfg.get("nombre") or not cfg.get("token"):
        print("Falta el nombre o el código del agente.")
        input("Presioná Enter para cerrar...")
        return
    print(f"Agente activo para {cfg['nombre']}. No cierres esta ventana durante el torneo.")
    print("El seguimiento se activa cuando se detecta el cliente de Riot abierto.")
    while True:
        activo = cliente_riot_abierto()
        try:
            r = requests.post(cfg["api"] + "/api/agente/latido", json={"nombre": cfg["nombre"], "token": cfg["token"], "activo": activo}, timeout=8)
            if r.status_code == 403:
                print("Error: el nombre o código del agente no coincide. Revisá config.json.")
                time.sleep(30)
                continue
            r.raise_for_status()
            data = r.json()
            if data.get("completado"):
                print("Límite de 100 horas completado. El seguimiento terminó.")
                break
            print(f"Cliente Riot: {'ABIERTO' if activo else 'cerrado'} | Consumidas: {data.get('horas_jugadas', 0):.2f} h | Restantes: {data.get('horas_restantes', 100):.2f} h")
        except requests.RequestException as e:
            print(f"Sin conexión con Render: {e}. Se reintentará; el servidor limita los saltos de tiempo para evitar sumar horas de más.")
        time.sleep(INTERVALO)
    input("Presioná Enter para cerrar...")

if __name__ == "__main__":
    main()
