import requests
import json
import os
from .security import sign_payload

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".pi_node_monitor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "node_config.json")

class PiAPIClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.node_id = None
        self.secret_key = None
        self.connection_token = None
        self.token_expires_at = None
        self.autostart = False
        self._load_config()

    def _load_config(self):
        """Lädt gespeicherte Node-Daten aus lokaler Datei."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                self.node_id = data.get("node_id")
                self.secret_key = data.get("secret_key")
                self.connection_token = data.get("connection_token")
                self.token_expires_at = data.get("token_expires_at")
                self.autostart = data.get("autostart", False)
            except Exception:
                pass

    def _save_config(self):
        """Speichert Node-Daten lokal ab."""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump({
                "node_id": self.node_id,
                "secret_key": self.secret_key,
                "connection_token": self.connection_token,
                "token_expires_at": self.token_expires_at,
                "autostart": self.autostart,
            }, f)

    def is_already_registered(self):
        """Prüft ob dieser Benutzer bereits registriert ist und einen validen Code hat."""
        return self.node_id is not None and self.connection_token is not None and self.is_token_valid()

    def is_token_valid(self):
        """Prüft ob der gespeicherte Token noch zeitlich gültig ist."""
        if not self.token_expires_at:
            return False
        from datetime import datetime
        try:
            expiry = datetime.fromisoformat(self.token_expires_at.replace("Z", "+00:00"))
            return expiry > datetime.now().astimezone()
        except Exception:
            return False

    def register(self, public_name=None):
        url = f"{self.base_url}/v1/nodes/register"
        resp = requests.post(url, json={"public_name": public_name})
        if resp.status_code == 200:
            data = resp.json()
            self.node_id = data["node_id"]
            self.secret_key = data["secret_key"]
            self._save_config()
            return True
        return False

    def generate_connection_token(self):
        # Falls bereits ein gültiger Token existiert, diesen zurückgeben
        if self.is_token_valid():
            return self.connection_token

        if not self.node_id:
            return None
        url = f"{self.base_url}/v1/nodes/generate-token"
        params = {"node_id": self.node_id}
        resp = requests.post(url, params=params)
        if resp.status_code == 200:
            data = resp.json()
            self.connection_token = data["token"]
            self.token_expires_at = data["expires_at"]
            self._save_config()
            return self.connection_token
        elif resp.status_code == 404:
            # Node am Server nicht mehr bekannt -> Lokal löschen für Re-Registrierung
            self._reset_local_config()
        return None

    def _reset_local_config(self):
        self.node_id = None
        self.secret_key = None
        self.connection_token = None
        self.token_expires_at = None
        if os.path.exists(CONFIG_FILE):
            try:
                os.remove(CONFIG_FILE)
            except:
                pass

    def push_status(self, status_data):
        if not self.node_id or not self.secret_key:
            return False
        
        url = f"{self.base_url}/v1/nodes/status"
        payload = {
            "node_id": self.node_id,
            "data": status_data
        }
        
        # Sign the 'data' part of the payload
        signature = sign_payload(status_data, self.secret_key)
        
        headers = {"X-Signature": signature}
        resp = requests.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            return resp.json().get("command")
        elif resp.status_code == 404:
            self._reset_local_config()
        return None

    def check_link_status(self):
        if not self.node_id:
            return False
        url = f"{self.base_url}/v1/nodes/link-status/{self.node_id}"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("is_linked", False)
        except:
            pass
        return False

    def unlink_node(self):
        if not self.node_id:
            return False
        url = f"{self.base_url}/v1/nodes/unlink/{self.node_id}"
        try:
            resp = requests.post(url, timeout=5)
            if resp.status_code == 200:
                self.connection_token = None
                self.token_expires_at = None
                self._save_config()
                return True
        except:
            pass
        return False

