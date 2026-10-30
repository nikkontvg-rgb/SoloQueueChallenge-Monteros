# -*- coding: utf-8 -*-
"""Agente gráfico del SoloQ Challenge Monteros para Windows."""
import json
import os
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

import psutil
import requests

API_DEFAULT = "https://soloqueuechallenge-monteros.onrender.com"
INTERVALO = 10
PROCESOS_RIOT = {
    "riotclientservices.exe", "riotclientux.exe", "riotclientuxrender.exe",
    "leagueclient.exe", "leagueclientux.exe", "leagueclientuxrender.exe",
}
CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "SoloQChallenge"
CONFIG_PATH = CONFIG_DIR / "config.json"


def riot_abierto():
    try:
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").lower() in PROCESOS_RIOT:
                return True
    except (psutil.Error, OSError):
        pass
    return False


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("SoloQ Challenge Monteros")
        self.root.geometry("490x410")
        self.root.minsize(450, 390)
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.detener = threading.Event()
        self.hilo = None
        self.config = self.leer_config()

        ttk.Label(root, text="SOLOQ CHALLENGE MONTEROS",
                  font=("Segoe UI", 15, "bold")).pack(pady=(18, 4))
        ttk.Label(root, text="Agente de seguimiento de las 100 horas").pack(pady=(0, 14))
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="x")
        ttk.Label(frame, text="Nombre exacto en el torneo").grid(row=0, column=0, sticky="w", pady=5)
        self.nombre = tk.StringVar(value=self.config.get("nombre", ""))
        ttk.Entry(frame, textvariable=self.nombre, width=42).grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(frame, text="Código privado entregado por la organización").grid(row=2, column=0, sticky="w", pady=5)
        self.token = tk.StringVar(value=self.config.get("token", ""))
        ttk.Entry(frame, textvariable=self.token, show="*", width=42).grid(row=3, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(frame, text="Servidor").grid(row=4, column=0, sticky="w", pady=5)
        self.api = tk.StringVar(value=self.config.get("api", API_DEFAULT))
        ttk.Entry(frame, textvariable=self.api, width=42).grid(row=5, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)

        self.estado = tk.StringVar(value="Ingresá tus datos y presioná Iniciar.")
        ttk.Label(root, textvariable=self.estado, wraplength=450, justify="center").pack(padx=15, pady=10)
        self.horas = tk.StringVar(value="Consumidas: —   |   Restantes: —")
        ttk.Label(root, textvariable=self.horas, font=("Segoe UI", 10, "bold")).pack(pady=2)
        botones = ttk.Frame(root)
        botones.pack(pady=10)
        self.boton_iniciar = ttk.Button(botones, text="Iniciar seguimiento", command=self.iniciar)
        self.boton_iniciar.pack(side="left", padx=5)
        ttk.Button(botones, text="Cerrar", command=self.cerrar).pack(side="left", padx=5)
        ttk.Label(root, text="Dejá esta aplicación abierta durante el torneo.",
                  foreground="#555").pack(pady=(4, 12))

    def leer_config(self):
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def iniciar(self):
        nombre = self.nombre.get().strip()
        token = self.token.get().strip()
        api = self.api.get().strip().rstrip("/")
        if not nombre or not token or not api.startswith("https://"):
            messagebox.showerror("Datos incompletos", "Completá nombre, código privado y servidor HTTPS.")
            return
        self.config = {"nombre": nombre, "token": token, "api": api}
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
        self.detener.clear()
        self.boton_iniciar.configure(state="disabled")
        self.estado.set("Conectando con el servidor…")
        self.hilo = threading.Thread(target=self.bucle, daemon=True)
        self.hilo.start()

    def actualizar_ui(self, estado=None, horas=None):
        def cambio():
            if estado is not None:
                self.estado.set(estado)
            if horas is not None:
                self.horas.set(horas)
        self.root.after(0, cambio)

    def bucle(self):
        while not self.detener.is_set():
            riot_detectado = riot_abierto()
            try:
                r = requests.post(
                    self.config["api"] + "/api/agente/latido",
                    json={"nombre": self.config["nombre"], "token": self.config["token"], "activo": riot_detectado},
                    timeout=8,
                )
                if r.status_code == 403:
                    self.actualizar_ui("Código inválido o participante no reconocido. Contactá a la organización.")
                    break
                r.raise_for_status()
                data = r.json()
                consumidas = float(data.get("horas_jugadas", 0))
                restantes = float(data.get("horas_restantes", max(0, 100 - consumidas)))
                if data.get("completado"):
                    estado = "Límite de 100 horas completado. Ya no se contabiliza más tiempo."
                elif data.get("sesion_activa"):
                    estado = "Cliente Riot detectado: seguimiento activo."
                elif riot_detectado:
                    estado = "Riot detectado, pero el servidor no confirmó la sesión."
                else:
                    estado = "Cliente Riot cerrado: tiempo pausado."
                self.actualizar_ui(
                    estado,
                    f"Consumidas: {consumidas:.2f} h   |   Restantes: {restantes:.2f} h"
                )
                if data.get("completado"):
                    break
            except requests.RequestException:
                self.actualizar_ui("Sin conexión con el servidor. Se reintentará automáticamente.")
            if self.detener.wait(INTERVALO):
                break
        self.root.after(0, lambda: self.boton_iniciar.configure(state="normal"))

    def cerrar(self):
        self.detener.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
