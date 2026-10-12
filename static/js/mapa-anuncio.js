/* Mapa da página do anúncio (templates/anuncios/publico.html). Leaflet servido pelo site, tiles do OSM.
   O servidor só manda o que pode ser mostrado: o ponto (localização exata) ou o centro já deslocado
   de um círculo de ~300 m (aproximada). O ponto exato nunca chega ao navegador no modo aproximado.
   Arquivo próprio: a CSP não libera script inline. */
(function () {
  "use strict";
  const div = document.getElementById("mapa-anuncio");
  const dados = document.getElementById("localizacao-anuncio");
  if (!div || !dados || typeof L === "undefined") return;
  const local = JSON.parse(dados.textContent);
  const centro = [local.lat, local.lng];

  const mapa = L.map(div, { scrollWheelZoom: false, dragging: !L.Browser.mobile, tap: false });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(mapa);

  if (local.tipo === "exata") {
    L.marker(centro, { keyboard: false }).addTo(mapa);
    mapa.setView(centro, 16);
  } else {
    const circulo = L.circle(centro, {
      radius: local.raio,
      color: "#0e4a57",
      weight: 2,
      fillColor: "#f2b705",
      fillOpacity: 0.25,
    }).addTo(mapa);
    mapa.fitBounds(circulo.getBounds(), { padding: [24, 24] });
  }
})();
