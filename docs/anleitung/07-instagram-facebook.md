# 7. Instagram und Facebook

Ziel: Der Server darf auf deinem Instagram-Konto posten (und optional auf deiner Facebook-Seite), und er liest START-Kommentare. Prüfung: `./fliessband einrichten --online` zeigt Schritt 7 als `[OK]`.

Stand der Klickwege: November 2026, nicht von null getestet. Meta ändert seine Oberfläche oft. Es ist die offizielle Instagram-API (Instagram-Login), ohne Passwort-Weitergabe.

## Voraussetzungen

- Kapitel 5 und 6 sind fertig: Medien-Adressen und Server stehen.
- Dein Instagram-Konto ist **öffentlich** und ein **Professional-Account** (Creator oder Business).
- Du hast eine **eigene Meta-App** mit Instagram-Login. Die Agentur beschreibt in **Abschnitt 6 ihrer README** («Instagram verbinden») Schritt für Schritt, wie du die App anlegst, dein Konto verbindest und den Schlüssel speicherst. Folge dieser Anleitung, sie liegt unter `~/.social-agentur/repo/README.md`. Danach liegt der Schlüssel in `~/.social-agentur/instagram_token`.

**Wichtig für die START-Erkennung:** Die Meta-App muss im Modus **«Veröffentlicht»** laufen. Im Entwicklungsmodus liefert Instagram keine Kommentare von fremden Konten, die START-Erkennung funktioniert dann nicht. Die App braucht ausserdem die Berechtigung `instagram_business_manage_comments`.

## Schlüssel auf den Server bringen

```bash
server/instagram.sh
```

Das Skript prüft den Schlüssel zuerst bei Instagram und zeigt nur den Kontonamen. Ist er gültig, legt es ihn auf dem Server ab und startet den Briefkasten neu. Den Schlüssel selbst zeigt es nie.

Prüfen:

```bash
./fliessband poster status
```

Es zeigt, ob das Posten an oder aus ist, wie alt der Instagram-Schlüssel ist und welche Posts als Nächstes geplant sind.

## Der Schlüssel läuft ab

Ein Instagram-Schlüssel gilt **60 Tage**. Die Agentur erinnert dich ab Tag 50, und `/agentur instagram erneuern` verlängert ihn (frühestens 24 Stunden nach dem Erstellen). Danach noch einmal `server/instagram.sh`. Der Assistent warnt ab Tag 50 und meldet ab Tag 60 «abgelaufen».

## Posten einschalten

Das Posten ist nach der Einrichtung **aus**. Schalte es erst ein, wenn der Erste Lauf (Kapitel 9) mit einem Test-Beitrag geklappt hat:

```bash
./fliessband poster ein
```

Auch dann postet der Server nur, was du in Telegram freigegeben hast, und nur zum Termin.

## Kommentare mit START (optional)

```bash
./fliessband kommentare ein
```

Der Server liest die Kommentare unter deinen Beiträgen und meldet jedes «START» in Telegram. Der erste Lauf speichert nur, was schon da ist, und meldet nichts davon.

## Facebook (optional)

Facebook ist freiwillig. Du brauchst eine Facebook-Seite und die Meta-App.

1. In `.env`:
   ```
   FLIESSBAND_FB_APP_ID=deine-app-id
   FLIESSBAND_FB_SEITE=Name deiner Seite
   ```
   Die App-ID ist nicht geheim. Der Seitenname darf ein Teil des Namens sein, die Gross- und Kleinschreibung ist egal.
2. Den **App-Geheimcode** der Meta-App in den Schlüsselbund:
   ```bash
   security add-generic-password -s fliessband-facebook-app -a fliessband -w
   ```
3. Im **Graph API Explorer** von Meta einen kurzen Nutzer-Schlüssel für deine App erzeugen und in die Zwischenablage kopieren.
4. Dann:
   ```bash
   server/facebook.sh
   ```
   Das Skript tauscht den kurzen Schlüssel aus der Zwischenablage gegen einen dauerhaften Seiten-Schlüssel und bringt ihn auf den Server.
5. Einschalten:
   ```bash
   ./fliessband facebook ein
   ```
   Es gilt ab dem nächsten Instagram-Post. `./fliessband facebook aus` stoppt es, Instagram läuft weiter.

## Prüfen

```bash
./fliessband einrichten --online
```

Schritt 7 ist `[OK]`, wenn der Server einen gültigen Instagram-Schlüssel meldet. Bei Facebook prüft der Assistent nur, wenn du `FLIESSBAND_FB_APP_ID` gesetzt hast. Sonst steht dort «optional: nicht eingerichtet».

## Wenn es nicht klappt

- `instagram.sh`: «Instagram lehnt den Schlüssel ab»: In der Agentur Instagram neu verbinden, dann das Skript wiederholen.
- «Instagram-Schlüssel fehlt oder ungültig» im Assistenten: `server/instagram.sh` ausführen.
- Keine START-Meldungen: Läuft die Meta-App im Modus «Veröffentlicht»? Hat sie `instagram_business_manage_comments`? Ist `./fliessband kommentare ein` gesetzt?
- `facebook.sh`: «Die Zwischenablage ist leer»: Den Schlüssel aus dem Graph API Explorer kopieren und das Skript sofort wiederholen.
