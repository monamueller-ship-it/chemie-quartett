# PSE-Quartett – digitales Chemie-Spiel

Eine lauffähige Echtzeit-Web-App für 2 bis 5 Personen. Die Anwendung ist für Chemie in Jahrgangsstufe 8 am Gymnasium konzipiert und orientiert sich am Kartenaufbau der bereitgestellten PDF-Vorlage, verwendet aber keine Bilder aus der PDF.

## Funktionsumfang

- sechsstelliger Raumcode ohne Registrierung
- personalisierte Echtzeit-Synchronisierung per WebSocket
- 34 Elementkarten von H bis Xe in der Auswahl der Vorlage
- exakt gleiche Startkartenzahl; zufällige Reserve bei 3 bis 5 Personen
- Supertrumpf-Regeln, Gleichstand/Stechen und serverseitige Gewinnerermittlung
- Bestätigung mit Pfeiltasten, Schaltflächen oder Wischgesten
- Live-Kartenstände, Pot, Reserve, Verbindungsstatus und Wiederverbindung
- Gastgeberfunktionen: Start, Entfernen in der Lobby, Abbruch, Revanche
- responsives, tastaturbedienbares Design mit Lern- und Tonmodus
- Tests der zentralen Spielregeln

## Schnellstart

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Danach `http://localhost:8000` aufrufen. Für einen lokalen Mehrspielertest mehrere Browserfenster oder Geräte im selben Netzwerk verwenden. Auf anderen Geräten wird statt `localhost` die IP-Adresse des Serverrechners verwendet, beispielsweise `http://192.168.1.20:8000`.

## Tests

```bash
pytest -q
```

## Docker

```bash
docker compose up --build
```

Für eine öffentliche Internetpartie muss der Container bei einem Hoster mit HTTPS- und WebSocket-Unterstützung bereitgestellt werden. Es gibt keine Datenbank; laufende Räume werden im Arbeitsspeicher gehalten und nach drei Stunden Inaktivität gelöscht. Für mehrere Serverinstanzen wäre ein gemeinsamer Zustandsdienst wie Redis erforderlich.

## Architektur

- `app/main.py`: HTTP-Endpunkte, WebSocket-Verbindungen, Raumverwaltung und Zeitüberschreitungen
- `app/game.py`: vollständig serverseitige Spiellogik
- `app/data/elements.json`: 34 strukturierte Elementdatensätze
- `app/static/`: responsive Benutzeroberfläche ohne Build-Schritt
- `tests/`: automatisierte Regeltests

Der Client kennt keine fremden verdeckten Karten und kann weder Gewinner noch Kartenübertragungen bestimmen. Jede Aktion wird vom Server validiert. Ein Wiederverbindungstoken wird nur lokal im Browser gespeichert.

## Kartenverteilung

| Spieler | aktive Karten | Karten je Spieler | Reserve |
|---:|---:|---:|---:|
| 2 | 34 | 17 | 0 |
| 3 | 33 | 11 | 1 |
| 4 | 32 | 8 | 2 |
| 5 | 30 | 6 | 4 |

## Fachliche Datengrundlage

Die strukturierte Datendatei wurde aus der im TeX-Live-System enthaltenen Datentabelle des Pakets **pgf-PeriodicTable** abgeleitet. Als allgemeine Prüfreferenzen sind PubChem und das NIST Chemistry WebBook auf jeder Karte hinterlegt. Die Atommasse ist als schülergerechter Einzelwert gespeichert; Dichten und Phasenübergänge können von Temperatur, Druck und Modifikation abhängen. Für Arsen wird die Sublimation ausdrücklich gekennzeichnet, für Helium bleibt der normale Schmelzpunkt leer.

Vor einem benoteten Einsatz empfiehlt sich die fachliche Endkontrolle der Werte und Rundungsregeln durch die Lehrkraft, insbesondere bei Kohlenstoff, Arsen und allotropen Elementen.

## Spielannahmen

- In allen Kategorien gewinnt der höchste Zahlenwert.
- Eine Kategorie ist gesperrt, sobald eine aktuelle Karte keinen vergleichbaren Zahlenwert besitzt.
- Beim Stechen bleiben alle bisherigen Karten im Pot; nur Gleichstands-Spieler mit Folgekarte spielen weiter.
- Haben alle Gleichstands-Spieler keine Folgekarte mehr, entscheidet der Server zufällig und fair.
- Bestätigt nicht jeder Spieler innerhalb von 15 Sekunden, überträgt der Server den Pot automatisch.
- Ein kurzzeitig getrennter Spieler bleibt in der Partie; seine Karten nehmen weiter am Vergleich teil.

## Datenschutz

Die App verlangt nur einen frei gewählten Anzeigenamen. Es gibt keine Konten, Werbung, Analyse-Skripte oder Chatfunktion. Raumdaten werden nicht dauerhaft gespeichert.
