/* Mapa para marcar um ponto: o do imóvel (templates/anuncios/localizacao.html) e o da loja
   (templates/anunciantes/painel_loja.html). Leaflet servido pelo próprio site; tiles do OpenStreetMap.
   O ponto vai para os campos escondidos latitude/longitude do formulário em volta do mapa; quem valida
   (perto da cidade) é o servidor. Com um select "cidade" e os centros (json_script "centros-cidades"),
   o mapa acompanha a cidade escolhida; sem eles, começa no data-lat/data-lng do mapa.
   Arquivo próprio: a CSP não libera script inline. */
(function () {
  "use strict";
  const div = document.getElementById("mapa");
  if (!div || typeof L === "undefined") return;
  const form = div.closest("form");
  const lat = form.querySelector("[name=latitude]");
  const lng = form.querySelector("[name=longitude]");
  const cidade = form.querySelector("select[name=cidade]");
  const situacao = document.getElementById("mapa-situacao");
  const dadosCentros = document.getElementById("centros-cidades");
  const centros = dadosCentros ? JSON.parse(dadosCentros.textContent) : {};
  const nome = div.dataset.titulo || "Imóvel";

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
      marcador = L.marker(latlng, { draggable: true, keyboard: true, title: nome }).addTo(mapa);
      marcador.on("dragend", () => gravar(marcador.getLatLng()));
    }
    gravar(latlng);
  }

  function centralizarNaCidade() {
    const centro = cidade ? centros[cidade.value] : div.dataset.lat && [Number(div.dataset.lat), Number(div.dataset.lng)];
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
  if (cidade) cidade.addEventListener("change", centralizarNaCidade);
  document.getElementById("limpar-ponto").addEventListener("click", () => {
    if (marcador) mapa.removeLayer(marcador);
    marcador = null;
    lat.value = "";
    lng.value = "";
    situacao.textContent = "Sem ponto marcado.";
  });
})();
