/* Mapa para marcar o ponto do imóvel (templates/anuncios/localizacao.html).
   Leaflet servido pelo próprio site; tiles do OpenStreetMap. O ponto vai para os campos
   escondidos latitude/longitude; quem valida (perto da cidade escolhida) é o servidor.
   Arquivo próprio: a CSP não libera script inline. */
(function () {
  "use strict";
  const div = document.getElementById("mapa");
  if (!div || typeof L === "undefined") return;
  const form = document.getElementById("form-localizacao");
  const lat = form.querySelector("[name=latitude]");
  const lng = form.querySelector("[name=longitude]");
  const cidade = form.querySelector("[name=cidade]");
  const situacao = document.getElementById("mapa-situacao");
  const centros = JSON.parse(document.getElementById("centros-cidades").textContent);

  const mapa = L.map(div, { scrollWheelZoom: false });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(mapa);

  let marcador = null;

  function gravar(latlng) {
    lat.value = latlng.lat.toFixed(6);
    lng.value = latlng.lng.toFixed(6);
    situacao.textContent = "Ponto marcado. Arraste o marcador para ajustar.";
  }

  function marcar(latlng) {
    if (marcador) {
      marcador.setLatLng(latlng);
    } else {
      marcador = L.marker(latlng, { draggable: true, keyboard: true, title: "Imóvel" }).addTo(mapa);
      marcador.on("dragend", () => gravar(marcador.getLatLng()));
    }
    gravar(latlng);
  }

  function centralizarNaCidade() {
    const centro = centros[cidade.value];
    if (centro) mapa.setView(centro, 14);
  }

  if (lat.value && lng.value) {
    const inicial = L.latLng(parseFloat(lat.value.replace(",", ".")), parseFloat(lng.value.replace(",", ".")));
    mapa.setView(inicial, 16);
    marcar(inicial);
  } else {
    centralizarNaCidade();
    if (!mapa._loaded) mapa.setView([-13.6, -56.1], 6); /* Mato Grosso, se a cidade não tiver ponto */
  }

  mapa.on("click", (e) => marcar(e.latlng));
  cidade.addEventListener("change", centralizarNaCidade);
  document.getElementById("limpar-ponto").addEventListener("click", () => {
    if (marcador) mapa.removeLayer(marcador);
    marcador = null;
    lat.value = "";
    lng.value = "";
    situacao.textContent = "Sem ponto marcado.";
  });
})();
