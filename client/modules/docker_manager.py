import docker
import json
import requests
import re
from datetime import datetime, timezone


class PiDockerManager:
    def __init__(self):
        try:
            self.client = docker.from_env()
        except Exception as e:
            self.client = None
            self.error = str(e)

    def find_pi_containers(self):
        if not self.client:
            return []
        
        # Search for common Pi Node container names
        try:
            containers = self.client.containers.list(all=True)
            # Pi Node container names: Testnet, Testnet2, Mainnet, Community, pi-node, pi-consensus
            target_names = ["pi-node", "pi-consensus", "testnet", "mainnet", "community"]
            
            pi_containers = []
            for c in containers:
                name_lower = c.name.lower()
                if any(target in name_lower for target in target_names):
                    pi_containers.append(c)
                    
            return pi_containers
        except:
            return []

    def get_container_stats(self, container_name):
        if not self.client:
            return {"error": "Docker client not initialized"}
        
        try:
            container = self.client.containers.get(container_name)
            stats = {}
            try:
                stats = container.stats(stream=False)
            except:
                pass
            
            # Extract CPU
            cpu_usage = 0.0
            if stats:
                try:
                    cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
                    system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
                    
                    if system_delta > 0:
                        cpus = stats['cpu_stats'].get('online_cpus')
                        if cpus is None:
                            cpus = len(stats['cpu_stats']['cpu_usage'].get('percpu_usage', [1]))
                        cpu_usage = (cpu_delta / system_delta) * cpus * 100.0
                except (KeyError, TypeError):
                    cpu_usage = 0.0
            
            # Extract Memory
            mem_usage = 0.0
            if stats:
                mem_usage = stats['memory_stats'].get('usage', 0) / (1024 * 1024) # MB
            
            # Image name
            # Image name
            image_name = "Unbekannt"
            try:
                image_name = container.image.tags[0] if container.image.tags else container.image.id[:12]
            except:
                pass

            return {
                "name": container.name,
                "image": image_name,
                "status": container.status or "Unknown",
                "cpu_usage": round(cpu_usage, 2),
                "memory_usage": round(mem_usage, 2),
                "uptime": self._get_container_uptime(container)
            }
        except Exception as e:
            return {
                "error": str(e), 
                "name": container_name, 
                "image": "N/A",
                "status": "Error",
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "uptime": "N/A"
            }

    def _get_container_uptime(self, container):
        """Berechnet die Uptime des Containers aus dem StartedAt Zeitstempel."""
        try:
            started_at = container.attrs.get('State', {}).get('StartedAt')
            if not started_at or started_at == "0001-01-01T00:00:00Z":
                return "N/A"
            
            # Docker timestamp format: 2026-05-11T08:48:27.123456789Z
            # Python fromisoformat handle up to 6 digits for microseconds
            t_str = re.sub(r'(\.\d{6})\d+', r'\1', started_at)
            t_str = t_str.replace('Z', '+00:00')
            
            dt_start = datetime.fromisoformat(t_str)
            now = datetime.now(timezone.utc)
            
            diff = now - dt_start
            
            days = diff.days
            hours, remainder = divmod(diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            parts = []
            if days > 0:
                parts.append(f"{days} {'Tag' if days == 1 else 'Tage'}")
            if hours > 0:
                parts.append(f"{hours} Std.")
            if minutes > 0:
                parts.append(f"{minutes} Min.")
            
            if not parts:
                return f"{diff.seconds} Sek."
            
            return " ".join(parts)
        except Exception as e:
            print(f"[DockerManager] Fehler bei Uptime-Berechnung: {e}")
            return "N/A"

    def get_node_json_status(self, container_name):
        """
        Holt echte Blockchain-Daten aus dem Pi Node Container.
        Versucht mehrere Methoden:
        1. HTTP-Endpunkt des Containers (stellar-core Admin-Port 11626)
        2. Docker exec mit stellar-core Befehl
        3. Log-Parsing als Fallback
        """
        result = {
            "sync_status": "N/A",
            "sync_percentage": 0,
            "block_height": "N/A",
            "connections_in": 0,
            "connections_out": 0
        }
        
        try:
            container = self.client.containers.get(container_name)
            
            if container.status != "running":
                result["sync_status"] = "Container gestoppt"
                return result

            # --- Methode 1: HTTP-Endpunkt über Container-IP ---
            info_data = self._try_http_info(container)
            
            # --- Methode 2: Docker exec stellar-core ---
            if not info_data:
                info_data = self._try_exec_info(container)
            
            # Wenn eine Methode erfolgreich war, Daten extrahieren
            if info_data:
                result = self._parse_stellar_info(info_data)
                
                # NEU: Wenn der API-Status nur generisch "Catching up" ist, 
                # schauen wir in den Logs nach detaillierteren Informationen.
                if result["sync_status"] == "Catching up":
                    log_res = self._parse_logs(container)
                    if log_res["sync_status"] not in ["Unbekannt (Log-Fallback)", "Catching up"]:
                        result["sync_status"] = log_res["sync_status"]
                        # Falls Log einen besseren Prozentsatz hat, diesen auch nehmen
                        if log_res["sync_percentage"] > result["sync_percentage"]:
                            result["sync_percentage"] = log_res["sync_percentage"]

                # Versuche detaillierte Peer-Infos (HTTP oder Exec)
                peer_data = self._try_http_peers(container)
                if not peer_data:
                    peer_data = self._try_exec_peers(container)
                
                if peer_data:
                    in_out = self._parse_stellar_peers(peer_data)
                    # Korrekte Zuweisung: in -> connections_in, out -> connections_out
                    result["connections_in"] = in_out.get("in", 0)
                    result["connections_out"] = in_out.get("out", 0)
            else:
                # --- Methode 3: Log-Parsing als Fallback ---
                result = self._parse_logs(container)

        except Exception as e:
            result["error"] = str(e)
            print(f"[DockerManager] Fehler bei Status-Abfrage: {e}")
        
        return result

    def _try_http_info(self, container):
        """Versucht die stellar-core Info über den HTTP-Endpunkt (Port 11626) abzurufen."""
        try:
            # Container-IP ermitteln
            container.reload()
            networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
            
            for net_name, net_config in networks.items():
                ip = net_config.get('IPAddress', '')
                if ip:
                    try:
                        resp = requests.get(f"http://{ip}:11626/info", timeout=3)
                        if resp.status_code == 200:
                            return resp.json()
                    except:
                        pass
            
            # Versuche auch localhost mit verschiedenen Ports
            for port in [11626, 11625]:
                try:
                    resp = requests.get(f"http://127.0.0.1:{port}/info", timeout=2)
                    if resp.status_code == 200:
                        return resp.json()
                except:
                    pass
                    
        except Exception as e:
            print(f"[DockerManager] HTTP-Info fehlgeschlagen: {e}")
        
        return None

    def _try_http_peers(self, container):
        """Versucht die detaillierten Peer-Infos über den HTTP-Endpunkt (Port 11626) abzurufen."""
        try:
            container.reload()
            networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
            for net_name, net_config in networks.items():
                ip = net_config.get('IPAddress', '')
                if ip:
                    try:
                        resp = requests.get(f"http://{ip}:11626/peers", timeout=2)
                        if resp.status_code == 200:
                            return resp.json()
                    except:
                        pass
            
            # Versuche auch localhost
            try:
                resp = requests.get(f"http://127.0.0.1:11626/peers", timeout=1)
                if resp.status_code == 200:
                    return resp.json()
            except:
                pass
        except:
            pass
        return None

    def _try_exec_peers(self, container):
        """Versucht detaillierte Peer-Infos über Docker exec abzurufen."""
        return self._try_exec_http_command(container, "peers")

    def _try_exec_http_command(self, container, command):
        """Generische Methode um stellar-core Befehle über exec auszuführen."""
        commands = [
            f"stellar-core http-command {command}",
            f"/usr/local/bin/stellar-core http-command {command}",
            f"/opt/stellar/core/bin/stellar-core http-command {command}",
            f"curl -s http://localhost:11626/{command}",
        ]
        
        for cmd in commands:
            try:
                exec_res = container.exec_run(cmd, stderr=False)
                if exec_res.exit_code == 0:
                    output = exec_res.output.decode('utf-8', errors='replace').strip()
                    if output:
                        json_start = output.find('{')
                        if json_start >= 0:
                            return json.loads(output[json_start:])
            except:
                continue
        return None

    def _try_exec_info(self, container):
        """Versucht stellar-core info über Docker exec abzurufen."""
        return self._try_exec_http_command(container, "info")

    def _parse_stellar_info(self, data):
        """Parst die stellar-core /info JSON-Antwort."""
        result = {
            "sync_status": "N/A",
            "sync_percentage": 0,
            "block_height": "N/A",
            "connections_in": 0,
            "connections_out": 0
        }
        
        try:
            info = data.get("info", data)  # Manchmal ist es direkt, manchmal unter "info"
            
            # State / Sync-Status
            state = info.get("state", "Unknown")
            
            # Detaillierterer Status bei Catching up
            if state == "Catching up":
                catchup = info.get("catchup", {})
                if catchup and catchup.get("eta_ms"):
                    # Wenn ETA vorhanden, füge Details hinzu
                    eta_sec = int(catchup.get("eta_ms") / 1000)
                    mins, secs = divmod(eta_sec, 60)
                    state = f"Catching up (Noch {mins}m {secs}s)"
            
            result["sync_status"] = state
            
            # Sync-Prozentsatz berechnen
            if "Synced" in state:
                result["sync_percentage"] = 100
            elif "Catching up" in state:
                # Versuche Prozentsatz aus dem State-String zu extrahieren
                match = re.search(r'(\d+)%', state)
                if match:
                    result["sync_percentage"] = int(match.group(1))
                else:
                    # Berechne aus Ledger-Daten
                    result["sync_percentage"] = self._calc_sync_from_ledger(info)
            elif "Booting" in state or "Joining" in state:
                result["sync_percentage"] = 1
            
            # Block-Höhe (Ledger)
            ledger = info.get("ledger", {})
            if isinstance(ledger, dict):
                result["block_height"] = ledger.get("num", ledger.get("sequence", "N/A"))
            
            # Verbindungen (Peers) - Detailliert parsen
            peers = info.get("peers", {})
            if isinstance(peers, dict):
                in_count = peers.get("inbound_count")
                out_count = peers.get("outbound_count")
                
                if in_count is not None and out_count is not None:
                    # Direkte Zuweisung (Swap entfernt für Korrektheit)
                    result["connections_in"] = in_count
                    result["connections_out"] = out_count
                else:
                    # Fallback auf authenticated_count
                    result["connections_in"] = peers.get("authenticated_count", 0)
                    result["connections_out"] = 0
            elif isinstance(peers, int):
                result["connections_in"] = peers
                        
        except Exception as e:
            print(f"[DockerManager] Fehler beim Parsen der Stellar-Info: {e}")
        
        return result

    def _parse_stellar_peers(self, data):
        """Parst die /peers JSON-Antwort um Inbound/Outbound zu zählen."""
        res = {"in": 0, "out": 0}
        try:
            # Fall 1: authenticated_peers ist eine Liste (altes Format)
            peers = data.get("authenticated_peers", [])
            if isinstance(peers, list):
                for p in peers:
                    if p.get("type") == "inbound":
                        res["in"] += 1
                    else:
                        res["out"] += 1
            # Fall 2: authenticated_peers ist ein Dictionary (neues Format v22+)
            elif isinstance(peers, dict):
                res["in"] = len(peers.get("inbound", []))
                res["out"] = len(peers.get("outbound", []))
        except:
            pass
        return res

    def _calc_sync_from_ledger(self, info):
        """Berechnet den Sync-Prozentsatz aus Ledger-Daten."""
        try:
            ledger = info.get("ledger", {})
            current = ledger.get("num", 0)
            
            # Versuche die Ziel-Ledger-Nummer zu finden
            catchup = info.get("catchup", {})
            if catchup:
                target = catchup.get("target", 0)
                if target > 0 and current > 0:
                    return min(int((current / target) * 100), 99)
            
            # Historischer Ansatz: Status-String
            state = info.get("state", "")
            match = re.search(r'(\d+)/(\d+)', state)
            if match:
                done, total = int(match.group(1)), int(match.group(2))
                if total > 0:
                    return min(int((done / total) * 100), 99)
        except:
            pass
        
        return 0

    def _parse_logs(self, container):
        """Fallback: Parst die Container-Logs für Status-Informationen."""
        result = {
            "sync_status": "Unbekannt (Log-Fallback)",
            "sync_percentage": 0,
            "block_height": "N/A",
            "connections_in": 0,
            "connections_out": 0
        }
        
        try:
            logs = container.logs(tail=500).decode('utf-8', errors='replace')
            lines = logs.strip().split('\n')
            
            # Von unten nach oben durchsuchen (neueste zuerst)
            for line in reversed(lines):
                line_lower = line.lower()
                
                # Sync-Status erkennen
                if "synced" in line_lower and "catching" not in line_lower:
                    result["sync_status"] = "Synced!"
                    result["sync_percentage"] = 100
                    break
                elif any(k in line_lower for k in ["catching up", "downloading state file", "applying checkpoint", "verifying ledger"]):
                    # Versuche den detaillierten Teil zu extrahieren
                    keywords = ["catching up", "downloading state file", "applying checkpoint", "verifying ledger"]
                    found_k = next(k for k in keywords if k in line_lower)
                    idx = line.lower().find(found_k)
                    
                    if idx >= 0:
                        msg = line[idx:].strip()
                        if len(msg) > 150:
                            msg = msg[:147] + "..."
                        result["sync_status"] = msg
                    else:
                        result["sync_status"] = found_k.capitalize()
                        
                    # Prozentsatz aus Log extrahieren
                    match = re.search(r'(\d+)%', line)
                    if match:
                        result["sync_percentage"] = int(match.group(1))
                    # Ledger-Fortschritt
                    match = re.search(r'(\d+)/(\d+)', line)
                    if match:
                        done, total = int(match.group(1)), int(match.group(2))
                        if total > 0:
                            result["sync_percentage"] = min(int((done / total) * 100), 99)
                    break
                elif "booting" in line_lower:
                    result["sync_status"] = "Booting"
                    result["sync_percentage"] = 1
                    break
            
            # Verbindungen aus Logs suchen
            for line in reversed(lines):
                # Suche nach: "Peers: 2 inbound, 8 outbound"
                match_detail = re.search(r'peers.*?(\d+)\s*inbound.*?(\d+)\s*outbound', line, re.IGNORECASE)
                if match_detail:
                    # Direkte Zuweisung (Swap entfernt)
                    result["connections_in"] = int(match_detail.group(1))
                    result["connections_out"] = int(match_detail.group(2))
                    break
                
                # Fallback: Nur Gesamtzahl
                match = re.search(r'peers.*?(\d+)\s*authenticated', line, re.IGNORECASE)
                if match:
                    # Ohne Differenzierung alles als Inbound (User-Sicht: Incoming)
                    result["connections_in"] = int(match.group(1))
                    break
            
            # Block-Höhe aus Logs suchen
            for line in reversed(lines):
                match = re.search(r'ledger\s*(?:num|sequence|#)?\s*[=:]\s*(\d+)', line, re.IGNORECASE)
                if match:
                    result["block_height"] = int(match.group(1))
                    break
                match = re.search(r'closing\s+ledger\s+(\d+)', line, re.IGNORECASE)
                if match:
                    result["block_height"] = int(match.group(1))
                    break
                    
        except Exception as e:
            print(f"[DockerManager] Log-Parsing fehlgeschlagen: {e}")
        
        return result

    def start_container(self, name):
        try:
            container = self.client.containers.get(name)
            container.start()
            return True, "Gestartet"
        except Exception as e:
            return False, str(e)

    def stop_container(self, name):
        try:
            container = self.client.containers.get(name)
            container.stop()
            return True, "Gestoppt"
        except Exception as e:
            return False, str(e)

    def restart_container(self, name):
        try:
            container = self.client.containers.get(name)
            container.restart()
            return True, "Neugestartet"
        except Exception as e:
            return False, str(e)
