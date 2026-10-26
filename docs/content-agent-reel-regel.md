# Regel für den Content-Agenten: Reels fürs Fliessband

Gehört in `~/.claude/agents/content-agent.md`, unter «Vorgehen», Punkt 3, direkt nach der Zeile «**Reel:** …».
Nach einem Update der Agentur (`~/.agentur-werkzeug/repo`) prüfen, ob die Regel noch drin ist.

```text
   - **Reel fürs Fliessband:** Jedes Reel bekommt zusätzlich den Abschnitt `## Szenen fürs Fliessband` (eigene `##`-Überschrift). Inhalt: der Voiceover-Text, aufgeteilt in Szenen, in genau diesem Format:

         **Szene 1 (Hook)**
         Sprechtext: <gesprochener Text, Zahlen ausgeschrieben, keine Abkürzungen>
         Einblendung: <max. 6 Wörter, Ziffern erlaubt>

         **Szene 2**
         Sprechtext: …
         Einblendung: …
         Grafik: zahl | <von> | <zu>                  (freiwillig)
         Grafik: vergleich | <ja> | <statt>           (freiwillig)
         Grafik: liste | <Punkt> | <Punkt> [| <Punkt>] (freiwillig)
         Bild: <Haltung> | <Gegenstand> [| <Gegenstand>] (jede Szene ausser Szene 1)

     Szene 1 ist immer der Hook, ohne Grafik und ohne Bild. Szenen fortlaufend nummerieren, keine Zeiten angeben. Pro Szene nur die Felder Sprechtext, Einblendung, Grafik und Bild, jedes höchstens einmal, keine weiteren Zeilen wie «Wichtig:». Jede Szene ausser Szene 1 bekommt eine Zeile `Bild:`, die zum Sprechtext passt: zuerst die Haltung der Figur, dann 0 bis 2 Gegenstände, getrennt mit `|`. In Szenen mit Grafik zeigt Figur klein auf die Grafik, Gegenstände erscheinen dort nicht. Erlaubte Namen:
     Haltungen: steht, zeigt, denkt, laptop, jubelt, schulterzucken, haelt, winkt
     Gegenstände: waage, uhr, spartopf, muenzen, kurve-hoch, kurve-runter, kalender, laptop, handy, haus, herz, gluehbirne, stopp, haekchen, kreuz, fragezeichen, ausrufezeichen, buch, ziel, schild-demo, notgroschen, kaffee, mond, sonne, familie-herz, geschenk, pfeil, lupe, schloss, rakete
     Unsicheres wie im übrigen Skript mit [prüfen] markieren. Bei Trading gehört der Risikohinweis gesprochen in eine Szene. Die Caption steht unter der Überschrift `## Caption`, ohne Zusatz in der Überschrift.
```

Die Namen stammen aus `vorlagen/reel-a/figuren/katalog.json`. Wächst der Baukasten, die Liste hier und im Agenten nachführen. Der Texter gibt sie ohnehin aus dem Katalog mit.
