// Bewegungen der Reel-Figuren. Wird in index.html vor der Zeitleiste eingefügt (auch in der Musterseite).
// Alles über GSAP mit festen Werten, keine Zufallszahlen: jedes Bild stimmt beim Springen (seek).
window.FIGUREN = (function () {
  var KOERPER = { bewegung: "atmen", teile: ["koerper"], ursprung: "100 284" };  // Füsse bleiben stehen
  // Hin und her (yoyo), so oft wie ganz ins Fenster passt
  var DAUERND = {
    atmen:     { periode: 1.2,  von: { scaleY: 1 },     zu: { scaleY: 1.025 } },
    zeigen:    { periode: 0.45, von: { rotation: 0 },   zu: { rotation: -8 } },
    winken:    { periode: 0.35, von: { rotation: -12 }, zu: { rotation: 18 } },
    wippen:    { periode: 0.9,  von: { rotation: -6 },  zu: { rotation: 6 } },
    pulsieren: { periode: 0.6,  von: { scale: 1 },      zu: { scale: 1.08 } }
  };

  function teile(wurzel, namen) {
    var el = [];
    namen.forEach(function (n) {
      wurzel.querySelectorAll('[data-teil="' + n + '"]').forEach(function (e) { el.push(e); });
    });
    return el;
  }

  function mit(werte, f) { return Object.assign({ svgOrigin: f.ursprung }, werte); }

  // Bewegung eines Teils (Eintrag aus katalog.json) im Fenster start..start+dauer
  function bewege(tl, wurzel, f, start, dauer) {
    var el = teile(wurzel, f.teile);
    if (!el.length || dauer <= 0) return;
    if (f.bewegung === "wachsen") {
      tl.fromTo(el, mit({ scale: 0 }, f), mit({ scale: 1, duration: 0.6, ease: "back.out(1.7)" }, f), start);
    } else if (f.bewegung === "fallen") {
      tl.fromTo(el, { y: -260 }, { y: 0, duration: 0.8, ease: "bounce.out" }, start);
    } else if (f.bewegung === "drehen") {
      // eine Umdrehung pro 3 s
      tl.fromTo(el, mit({ rotation: 0 }, f), mit({ rotation: 120 * dauer, duration: dauer, ease: "none" }, f), start);
    } else {
      var b = DAUERND[f.bewegung], n = Math.floor(dauer / b.periode);
      if (n < 1) return;
      tl.fromTo(el, mit(b.von, f), mit(Object.assign({ duration: b.periode, ease: "sine.inOut",
        repeat: n - 1, yoyo: true }, b.zu), f), start);
    }
  }

  // Figurenszene einer Reel-Szene: weich einblenden, Figur atmet, Haltung und Gegenstände bewegen sich
  function szene(tl, wurzel, f, start, dauer) {
    var haltung = wurzel.querySelector(".haltung");
    tl.fromTo(wurzel, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.4, ease: "power2.out" }, start);
    bewege(tl, haltung, KOERPER, start, dauer);
    bewege(tl, haltung, f.haltung, start + 0.4, dauer - 0.4);
    f.gegenstaende.forEach(function (g, i) {
      var platz = wurzel.querySelector(".platz-" + (i + 1)), auftritt = start + 0.5 + 0.25 * i;
      tl.fromTo(platz, { autoAlpha: 0, scale: 0.6 }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: "back.out(1.8)" }, auftritt);
      bewege(tl, platz, g, auftritt + 0.45, start + dauer - auftritt - 0.45);
    });
  }

  return { szene: szene, bewege: bewege, KOERPER: KOERPER };
})();
