# Pi Node Status Client v1.7 🚀

Die Desktop-Anwendung für den **Pi Netzwerk Deutschland Node Status Bot**. Überwache deinen Pi Node bequem von überall über Telegram und steuere ihn remote.

## 📥 Download

Die vorkompilierte Version für Windows (.exe) findest du immer aktuell im Release-Bereich:

**👉 [Hier herunterladen](https://github.com/Fingerkrampf/Pi_ND_Node_Status_Bot/releases)**

---

## ✨ Features

- 🔍 **Automatische Erkennung:** Erkennt deine Pi Node Docker-Container automatisch.
- 📊 **Echtzeit-Monitoring:** Überwachung von CPU, RAM, Block-Height, Sync-Status und Verbindungen.
- 📱 **Telegram-Anbindung:** Generiere einen Code, um deinen Node mit dem Bot zu verknüpfen.
- 🛠️ **Remote Control:** Starte oder stoppe deinen Node direkt über Telegram-Befehle.
- 🔔 **Benachrichtigungen:** Erhalte sofort eine Nachricht bei Statusänderungen deines Nodes.
- 🔒 **Sicherheit:** End-to-End HMAC-Signierung der Status-Updates.

## 🚀 Installation & Nutzung

1. **Lade die `Pi_Node_Client.exe`** aus den [Releases](https://github.com/Fingerkrampf/Pi_ND_Node_Status_Bot/releases) herunter.
2. **Starte die Anwendung** auf deinem Pi Node PC (Admin-Rechte für Docker-Zugriff empfohlen).
3. Klicke auf **"Verbindungscode generieren"**.
4. Gib den Code in der Telegram-Gruppe oder dem Bot mit `/nodeconnect DEIN_CODE` ein.
5. Fertig! Dein Node sendet nun alle 10 Sekunden Updates an den Bot.

---

## 🛠️ Für Entwickler (Source Code)

Falls du die Anwendung aus dem Quellcode starten möchtest:

1. Python 3.10+ installieren.
2. Abhängigkeiten installieren:
   ```bash
   pip install -r requirements.txt
   ```
3. App starten:
   ```bash
   python main.py
   ```

### Build (exe erstellen)
Wir nutzen PyInstaller für den Build-Prozess. Der Workflow ist in `.github/workflows/build.yml` definiert.
