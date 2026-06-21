# Pi Node Status Bot - Client
# Copyright (C) 2026 Fingerkrampf
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import customtkinter as ctk
import threading
import time
from modules.docker_manager import PiDockerManager
from modules.api_client import PiAPIClient
import sys
import os
import platform
import requests
import webbrowser
from dotenv import load_dotenv

# Load environment variables from .env file
if getattr(sys, 'frozen', False):
    # If running as a bundled executable, look for .env in the bundle directory
    bundle_dir = sys._MEIPASS
    load_dotenv(os.path.join(bundle_dir, '.env'))
else:
    load_dotenv()

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class PiNodeClientApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.VERSION = "1.7"
        self.title(f"Pi Node Monitor & Remote v{self.VERSION}")
        self.geometry("600x500")

        self.docker_mgr = PiDockerManager()
        
        # Get API URL from environment variable or use fallback
        api_base_url = os.getenv("API_BASE_URL")
        self.api_client = PiAPIClient(base_url=api_base_url)

        self.setup_ui()

        # Start background monitoring thread
        self.stop_event = threading.Event()
        self.monitor_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
        self.monitor_thread.start()
        self.monitor_count = 0

        # Check for existing token on start
        self.after(500, self.check_existing_token)
        
        # Check for updates
        self.after(2000, self.check_for_updates)


    def setup_ui(self):
        # Update Notification Frame (hidden by default)
        self.update_frame = ctk.CTkFrame(self, fg_color="#1f538d")
        self.update_label = ctk.CTkLabel(self.update_frame, text="", font=ctk.CTkFont(size=12, weight="bold"), cursor="hand2")
        self.update_label.pack(pady=5, padx=10)
        
        # Header
        self.header_label = ctk.CTkLabel(self, text="Pi Node Link", font=ctk.CTkFont(size=24, weight="bold"))
        self.header_label.pack(pady=20)

        # Status Frame
        self.status_frame = ctk.CTkFrame(self)
        self.status_frame.pack(padx=20, pady=10, fill="both", expand=True)

        self.node_status_label = ctk.CTkLabel(self.status_frame, text="Suche Pi Node Container...", font=ctk.CTkFont(size=16))
        self.node_status_label.pack(pady=20)

        self.stats_text = ctk.CTkLabel(self.status_frame, text="", justify="left")
        self.stats_text.pack(pady=10)

        # Connection Area
        self.conn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.conn_frame.pack(pady=20, fill="x", padx=40)

        self.btn_connect = ctk.CTkButton(self.conn_frame, text="Verbindungscode generieren", command=self.generate_code, height=40)
        self.btn_connect.pack(fill="x")

        self.token_display = ctk.CTkLabel(self.conn_frame, text="", font=ctk.CTkFont(size=32, weight="bold", family="Consolas"))
        self.token_display.pack(pady=10)

        self.instruction_label = ctk.CTkLabel(self.conn_frame, text="", wraplength=400)
        self.instruction_label.pack()

        self.expiry_label = ctk.CTkLabel(self.conn_frame, text="", font=ctk.CTkFont(size=12), text_color="gray")
        self.expiry_label.pack()

        self.btn_unlink = ctk.CTkButton(self.conn_frame, text="Verknüpfung aufheben", command=self.confirm_unlink, 
                                        fg_color="transparent", border_width=1, text_color=("gray10", "gray90"),
                                        hover_color=("gray70", "gray30"), height=32)
        # Hidden by default
        self.btn_unlink.pack_forget()

        # Autostart Checkbox (DEACTIVATED to avoid Windows Defender False Positives)
        # self.autostart_var = ctk.BooleanVar(value=self.api_client.autostart)
        # self.autostart_checkbox = ctk.CTkCheckBox(self, text="Tool automatisch mit Windows starten", 
        #                                          variable=self.autostart_var, 
        #                                          command=self.toggle_autostart)
        # self.autostart_checkbox.pack(pady=(0, 20))
        
        # if platform.system() == "Darwin":
        #     self.autostart_checkbox.configure(text="Tool automatisch mit macOS starten")

    def toggle_autostart(self):
        # Functionality temporarily disabled to avoid AV detection
        pass
        # enabled = self.autostart_var.get()
        # self.api_client.autostart = enabled
        # self.api_client._save_config()
        # self.set_autostart_registry(enabled)

    def set_autostart_registry(self, enabled):
        """
        DEACTIVATED: Writing to the Windows Registry or creating LaunchAgents 
        without code signing often triggers Antivirus False Positives.
        """
        pass

    def confirm_unlink(self):
        import tkinter.messagebox as mbox
        if mbox.askyesno("Verknüpfung aufheben", "Möchtest du die Verknüpfung zu Telegram wirklich aufheben?"):
            if self.api_client.unlink_node():
                self.btn_connect.configure(state="normal", text="Verbindungscode generieren")
                self.token_display.configure(text="")
                self.instruction_label.configure(text="", cursor="")
                self.instruction_label.unbind("<Button-1>")
                self.expiry_label.configure(text="")
                self.btn_unlink.pack_forget()
                mbox.showinfo("Erfolg", "Verknüpfung wurde aufgehoben.")
            else:
                if mbox.askyesno("Fehler", "Verknüpfung konnte nicht am Server aufgehoben werden. Möchtest du die lokalen Daten trotzdem zurücksetzen?"):
                    self.api_client._reset_local_config()
                    self.btn_connect.configure(state="normal", text="Verbindungscode generieren")
                    self.token_display.configure(text="")
                    self.btn_unlink.pack_forget()
                    mbox.showinfo("Erfolg", "Lokale Daten wurden zurückgesetzt.")

    def check_for_updates(self):
        def _check():
            try:
                repo = "Fingerkrampf/Pi_ND_Node_Status_Bot"
                url = f"https://api.github.com/repos/{repo}/releases/latest"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    latest_version = data.get("tag_name", "").replace("v", "")
                    
                    # Einfacher Versionsvergleich
                    if latest_version and latest_version != self.VERSION:
                        self.after(0, lambda: self.show_update_notification(latest_version, data.get("html_url")))
            except Exception as e:
                print(f"Update-Check fehlgeschlagen: {e}")

        threading.Thread(target=_check, daemon=True).start()

    def show_update_notification(self, version, url):
        self.update_label.configure(text=f"🚀 Neue Version v{version} verfügbar! Hier klicken zum Herunterladen.")
        self.update_label.bind("<Button-1>", lambda e: webbrowser.open(url))
        self.update_frame.pack(side="top", fill="x", padx=20, pady=(10, 0), before=self.header_label)

    def check_existing_token(self):
        # Erst prüfen ob bereits verknüpft
        if self.api_client.check_link_status():
            self.display_linked_status()
        elif self.api_client.is_token_valid():
            self.display_token(self.api_client.connection_token)
            self.update_expiry_countdown()

    def display_linked_status(self):
        self.btn_connect.configure(state="disabled", text="Node ist verknüpft")
        self.token_display.configure(text="VERBUNDEN", text_color="green", font=ctk.CTkFont(size=24, weight="bold"))
        self.instruction_label.configure(text="Dein Node ist erfolgreich mit unserem Pi Netzwerk Deutschland Node Status Bot verknüpft.", cursor="")
        self.instruction_label.unbind("<Button-1>")
        self.expiry_label.configure(text="")
        self.btn_unlink.configure(text="Verknüpfung aufheben")
        self.btn_unlink.pack(pady=10)

    def display_token(self, token):
        self.token_display.configure(text=token, text_color="#1f538d", font=ctk.CTkFont(size=32, weight="bold"))
        self.instruction_label.configure(
            text="Gib den Code in unserer Telegram Gruppe ein. Klicke auf den Befehl unten, um ihn zu kopieren und in Telegram einzufügen:\n/nodeconnect " + token,
            cursor="hand2"
        )
        self.instruction_label.bind("<Button-1>", lambda e: self.copy_command_to_clipboard(token))
        self.btn_connect.configure(state="disabled")
        self.btn_unlink.configure(text="Code verwerfen / Reset")
        self.btn_unlink.pack(pady=10)

    def copy_command_to_clipboard(self, token):
        command = f"/nodeconnect {token}"
        self.clipboard_clear()
        self.clipboard_append(command)
        self.update()
        import tkinter.messagebox as mbox
        mbox.showinfo("Kopiert", f"Der Befehl wurde kopiert:\n{command}\n\nDu kannst ihn jetzt in Telegram einfügen.")

    def update_expiry_countdown(self):
        if not self.api_client.token_expires_at:
            return

        from datetime import datetime
        try:
            expiry = datetime.fromisoformat(self.api_client.token_expires_at.replace("Z", "+00:00"))
            remaining = expiry - datetime.now().astimezone()
            
            if remaining.total_seconds() > 0:
                mins, secs = divmod(int(remaining.total_seconds()), 60)
                self.expiry_label.configure(text=f"Code gültig für: {mins:02d}:{secs:02d}")
                self.after(1000, self.update_expiry_countdown)
            else:
                self.expiry_label.configure(text="Code abgelaufen.", text_color="red")
                self.btn_connect.configure(state="normal", text="Neuen Code generieren")
                self.token_display.configure(text="")
                self.instruction_label.configure(text="", cursor="")
                self.instruction_label.unbind("<Button-1>")
                self.btn_unlink.pack_forget()
        except Exception as e:
            print(f"Error updating countdown: {e}")

    def generate_code(self):
        try:
            # Bereits registriert? Zeige bestehenden Code
            if self.api_client.is_token_valid():
                self.display_token(self.api_client.connection_token)
                self.update_expiry_countdown()
                return

            if not self.api_client.node_id:
                if not self.api_client.register(public_name="My Pi Node"):
                    self.token_display.configure(text="Fehler: API nicht erreichbar", text_color="red", font=ctk.CTkFont(size=14))
                    return

            token = self.api_client.generate_connection_token()
            if token:
                self.display_token(token)
                self.update_expiry_countdown()
            else:
                self.token_display.configure(text="Token-Fehler (Backend offline?)", text_color="red", font=ctk.CTkFont(size=14))
        except Exception as e:
            self.token_display.configure(text=f"Verbindungsfehler: {str(e)}", text_color="red", font=ctk.CTkFont(size=12))

    def monitoring_loop(self):
        while not self.stop_event.is_set():
            containers = self.docker_mgr.find_pi_containers()
            if containers:
                c = containers[0] # Take first one for now
                stats = self.docker_mgr.get_container_stats(c.name)
                node_info = self.docker_mgr.get_node_json_status(c.name)
                
                combined_data = {**stats, **node_info}
                
                # Update UI
                self.after(0, self.update_ui_stats, combined_data)
                
                # Check if we need to register
                if not self.api_client.node_id:
                    self.api_client.register(public_name="Pi Node")
                    self.after(0, lambda: self.btn_connect.configure(state="normal", text="Verbindungscode generieren"))

                # Push to Server and check for commands
                try:
                    command = self.api_client.push_status(combined_data)
                    if command:
                        self.execute_remote_command(c.name, command)
                    
                    # Periodic link check
                    if self.monitor_count % 6 == 0: # Every 60 seconds
                        if self.api_client.node_id and self.api_client.check_link_status():
                            self.after(0, self.display_linked_status)
                except Exception as e:
                    print(f"Fehler beim Senden des Status: {e}")
            else:
                # Docker-Fehler oder keine Container
                error_msg = "Kein Pi Node gefunden (Docker läuft?)"
                if hasattr(self.docker_mgr, 'error') and self.docker_mgr.error:
                    if "permission denied" in self.docker_mgr.error.lower():
                        error_msg = "Docker-Zugriff verweigert (Admin-Rechte nötig?)"
                    else:
                        error_msg = f"Docker-Fehler: {self.docker_mgr.error[:40]}..."
                
                self.after(0, lambda m=error_msg: self.node_status_label.configure(text=m, text_color="orange"))
            
            self.monitor_count += 1
            time.sleep(10) # Update every 10 seconds (requested)

    def execute_remote_command(self, container_name, command):
        """Führt Befehle aus, die vom Telegram Bot kommen."""
        print(f"Remote-Befehl empfangen: {command}")
        success = False
        msg = ""
        
        if command == "start":
            success, msg = self.docker_mgr.start_container(container_name)
        elif command == "stop":
            success, msg = self.docker_mgr.stop_container(container_name)
        
        if success:
            print(f"Befehl {command} erfolgreich ausgeführt: {msg}")
        else:
            print(f"Fehler bei Befehl {command}: {msg}")

    def update_ui_stats(self, data):
        container_name = data.get('name', 'Unbekannt')
        self.node_status_label.configure(text=f"Node gefunden: {container_name}", text_color="green")
        
        status_str = (
            f"Status: {data.get('status', 'Unbekannt')} (Seit: {data.get('uptime', 'N/A')})\n"
            f"Image: {data.get('image', 'N/A')}\n"
            f"CPU: {data.get('cpu_usage', 0.0)}% | RAM: {data.get('memory_usage', 0.0)} MB\n"
            f"Sync: {data.get('sync_status', 'N/A')} ({data.get('sync_percentage', 0)}%)\n"
            f"Block: {data.get('block_height', 'N/A')}\n"
            f"Verbindungen: In: {data.get('connections_in', 0)} | Out: {data.get('connections_out', 0)}"
        )
        self.stats_text.configure(text=status_str)

if __name__ == "__main__":
    app = PiNodeClientApp()
    app.mainloop()
