/* Mapa da lista de uma categoria do Guia de Negócios (templates/guia/categoria.html). Leaflet e
   Leaflet.markercluster servidos pelo site, tiles do OSM. Arquivo próprio: a CSP não libera script inline.

   - Os pontos vêm de #pontos-guia (json_script dentro de #guia-resultados): só quem tem endereço comercial
     e só o ponto público. Quem atende a domicílio não entra no mapa.
   - Depois de cada troca do HTMX (filtros) os pontos são relidos.
   - O popup é montado com textContent (nome) e um link para a ficha: nada de HTML vindo dos dados. */
(function () {
  "use strict";
  const div = document.getElementById("mapa-guia");
  if (!div || typeof L === "undefined" || typeof L.markerClusterGroup === "undefined") return;

  const centro = [Number(div.dataset.lat) || -13.0, Number(div.dataset.lng) || -56.0];
  const mapa = L.map(div, { tap: false }).setView(centro, 13);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(mapa);

  const grupo = L.markerClusterGroup({
    showCoverageOnHover: false,
    maxClusterRadius: 48,
    iconCreateFunction: function (cluster) {
      return L.divIcon({ className: "nd-grupo", html: "<span>" + cluster.getChildCount() + "</span>", iconSize: L.point(40, 40) });
    },
  });
  mapa.addLayer(grupo);

  function popup(ponto) {
    const caixa = document.createElement("div");
    const nome = document.createElement("b");
    nome.textContent = ponto.nome;
    const link = document.createElement("a");
    link.href = ponto.url;
    link.textContent = "Ver ficha";
    caixa.append(nome, document.createElement("br"), link);
    return caixa;
  }

  function carregar() {
    const dados = document.getElementById("pontos-guia");
    const pontos = dados ? JSON.parse(dados.textContent) : [];
    grupo.clearLayers();
    pontos.forEach(function (ponto) {
      grupo.addLayer(L.marker([ponto.lat, ponto.lng], { title: ponto.nome, alt: ponto.nome }).bindPopup(popup(ponto)));
    });
    if (pontos.length) mapa.fitBounds(grupo.getBounds(), { padding: [32, 32], maxZoom: 16 });
  }

  carregar();
  document.body.addEventListener("htmx:afterSettle", carregar); /* a única troca da página é a lista */
  /* O mapa nasce escondido no celular (Lista | Mapa): ao mostrar, o Leaflet refaz o tamanho. */
  const opcaoMapa = document.getElementById("v-mapa");
  if (opcaoMapa) {
    opcaoMapa.addEventListener("change", function () {
      setTimeout(function () {
        mapa.invalidateSize();
        if (grupo.getLayers().length) mapa.fitBounds(grupo.getBounds(), { padding: [32, 32], maxZoom: 16 });
      }, 50);
    });
  }
})();
