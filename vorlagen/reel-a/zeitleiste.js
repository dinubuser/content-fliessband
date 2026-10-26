// Feste Zeitleiste fürs Reel. Liest window.REEL (aus daten.js). Keine Zufallswerte, alles über GSAP.
(function () {
  var D = window.REEL;
  window.__timelines = window.__timelines || {};

  function bauen() {
    var tl = gsap.timeline({ paused: true });

    // Nur vorhandene Elemente animieren (Szenen ohne Grafik oder Hinweis), sonst warnt GSAP im check
    function ziel(sel) { var el = document.querySelectorAll(sel); return el.length ? el : null; }

    D.szenen.forEach(function (s) {
      var sel = "#sz-" + s.nummer;
      var balken = ziel(sel + " .balken"), einblendung = ziel(sel + " .einblendung");
      var grafik = ziel(sel + " .grafik > *"), hinweis = ziel(sel + " .hinweis");
      if (!s.hook) {
        if (balken) tl.fromTo(balken, { scaleX: 0, transformOrigin: "left center" },
          { scaleX: 1, duration: 0.45, ease: "power3.out" }, s.start);
        if (einblendung) tl.fromTo(einblendung, { opacity: 0, y: 40 },
          { opacity: 1, y: 0, duration: 0.55, ease: "back.out(1.4)" }, s.start + 0.05);
        if (grafik) tl.fromTo(grafik, { opacity: 0, y: 30 },
          { opacity: 1, y: 0, duration: 0.45, ease: "power3.out", stagger: 0.18 }, s.start + 0.35);
      }
      if (hinweis) tl.fromTo(hinweis, { opacity: 0 }, { opacity: 0.7, duration: 0.4, ease: "none" }, s.start + 0.5);
      var figur = document.querySelector(sel + " .figur");
      if (figur && s.figur) FIGUREN.szene(tl, figur, s.figur, s.start, s.dauer);
    });

    // Ein- und Ausblenden über tl.set, damit jedes Bild beim Springen (seek) stimmt
    function fenster(el, start, ende, auftritt) {
      tl.set(el, { autoAlpha: 0 }, 0);
      if (auftritt) tl.fromTo(el, { autoAlpha: 0, scale: 0.92 }, { autoAlpha: 1, scale: 1, duration: 0.22, ease: "back.out(2)" }, start);
      else tl.set(el, { autoAlpha: 1 }, start);
      tl.set(el, { autoAlpha: 0 }, ende);
    }

    D.hook.forEach(function (g) { fenster("#hk-" + g.index, g.start, g.ende, true); });

    // Nur das aktuelle Wort ist orange: ab seinem Start bis zum Start des nächsten Worts,
    // das letzte Wort der Gruppe bis zum Gruppenende. Farbe statt Klasse, weil GSAP sie beim
    // Rückwärts-Springen sauber zurücksetzt.
    var NORMAL = "#0B111E", AKTIV = "#FA6317";
    D.ut.forEach(function (g) {
      fenster("#ut-" + g.index, g.start, g.ende, false);
      g.woerter.forEach(function (w, j) {
        var wort = "#ut-" + g.index + "-" + j;
        var bis = j + 1 < g.woerter.length ? g.woerter[j + 1].start : g.ende;
        tl.set(wort, { color: NORMAL }, 0);
        tl.set(wort, { color: AKTIV }, w.start);
        tl.set(wort, { color: NORMAL }, Math.max(bis, w.start));
      });
    });

    window.__timelines["reel"] = tl;
  }

  if (document.fonts && document.fonts.ready) { document.fonts.ready.then(bauen); } else { bauen(); }
})();
