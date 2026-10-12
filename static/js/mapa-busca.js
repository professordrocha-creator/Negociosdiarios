/* Mapa da busca (templates/busca/resultados.html; Sprint 5). Leaflet e Leaflet.markercluster servidos
   pelo site, tiles do OSM. Arquivo próprio: a CSP não libera script inline.

   - Os pontos vêm do JSON do mapa (#resultados[data-mapa-url]), com os mesmos filtros da lista. O
     servidor só manda o que pode ser mostrado: imóvel aproximado já vem no ponto DESLOCADO, nunca o real.
   - Depois de cada troca do HTMX (filtro, ordem, "Buscar nesta área") o #resultados novo traz a URL
     nova e o mapa recarrega os pontos.
   - Marcador = preço; ao clicar, o card (foto, título e link) é pedido ao servidor (HTML escapado lá).
   - Mover o mapa mostra "Buscar nesta área": grava o retângulo no campo oculto `area` do formulário e o
     envia (o HTMX troca a lista; os outros filtros continuam). */
(function () {
  "use strict";
  const div = document.getElementById("mapa-busca");
  if (!div || typeof L === "undefined" || typeof L.markerClusterGroup === "undefined") return;

  const form = document.getElementById("filtros-form");
  const campoArea = document.getElementById("f-area");
  const botaoArea = document.getElementById("mapa-buscar-area");
  const aviso = document.getElementById("mapa-aviso");
  const opcaoMapa = document.getElementById("v-mapa");
  const lojas = div.dataset.tipo === "veiculos";

  const centroPadrao = div.dataset.lat ? [Number(div.dataset.lat), Number(div.dataset.lng)] : [-13.0, -56.0];
  const mapa = L.map(div, { tap: false }).setView(centroPadrao, Number(div.dataset.zoom || 6));
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(mapa);

  const grupo = L.markerClusterGroup({
    showCoverageOnHover: false,
    maxClusterRadius: 48,
    iconCreateFunction: function (cluster) {
      return L.divIcon({
        className: "nd-grupo",
        html: "<span>" + cluster.getChildCount() + "</span>",
        iconSize: L.point(40, 40),
      });
    },
  });
  mapa.addLayer(grupo);

  let ajustando = false; // movimento feito pelo script (não mostra "Buscar nesta área")
  let pedido = null; // AbortController do JSON em andamento
  let urlCarregada = null;

  function escapar(texto) {
    const s = document.createElement("span");
    s.textContent = String(texto);
    return s.innerHTML;
  }

  function enquadrar(fn) {
    ajustando = true;
    try {
      fn();
    } finally {
      ajustando = false;
    }
  }

  function urlDoCartao(id) {
    const modelo = lojas ? div.dataset.cartaoLoja : div.dataset.cartaoAnuncio;
    return modelo.replace(/[^/]+\/$/, encodeURIComponent(id) + "/");
  }

  function abrirCartao(marcador, ponto) {
    const popup = L.popup({ minWidth: 220, maxWidth: 260, className: "nd-popup" })
      .setLatLng(marcador.getLatLng())
      .setContent('<p class="small mb-0">Carregando…</p>')
      .openOn(mapa);
    fetch(urlDoCartao(ponto.id), { headers: { Accept: "text/html" } })
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        popup.setContent(html); // HTML do template do servidor (texto do anunciante já escapado)
      })
      .catch(function () {
        popup.setContent('<p class="small mb-0">Este anúncio não está mais disponível.</p>');
      });
  }

  function marcador(ponto) {
    const icone = L.divIcon({
      className: "nd-pino",
      html: "<span>" + escapar(ponto.preco) + "</span>",
      iconSize: null,
      iconAnchor: [0, 0],
    });
    const m = L.marker([ponto.lat, ponto.lng], { icon: icone, title: ponto.titulo, alt: ponto.titulo });
    m.on("click", function () {
      abrirCartao(m, ponto);
    });
    return m;
  }

  function plural(n, um, varios) {
    return n + " " + (n === 1 ? um : varios);
  }

  function avisar(dados) {
    const partes = [];
    if (!dados.pontos.length) {
      partes.push(lojas ? "Nenhuma loja destes veículos mostra o endereço no mapa." : "Nenhum anúncio para mostrar no mapa.");
    }
    if (dados.sem_localizacao) {
      partes.push(
        lojas
          ? plural(dados.sem_localizacao, "veículo de loja que não mostra o endereço fica", "veículos de lojas que não mostram o endereço ficam") + " fora do mapa."
          : plural(dados.sem_localizacao, "anúncio sem localização no mapa", "anúncios sem localização no mapa") + " (só o bairro); estão na lista."
      );
    }
    if (dados.cortado) {
      partes.push("Mostrando " + dados.pontos.length + " de " + dados.total + ". Aproxime o mapa e use \"Buscar nesta área\" ou os filtros.");
    }
    aviso.textContent = partes.join(" ");
  }

  function areaAtual() {
    const area = (campoArea && campoArea.value) || "";
    const v = area.split(",").map(Number);
    if (v.length !== 4 || v.some(isNaN)) return null;
    return L.latLngBounds([v[1], v[0]], [v[3], v[2]]);
  }

  function carregar() {
    const resultados = document.getElementById("resultados");
    if (!resultados) return;
    if (campoArea) campoArea.value = resultados.dataset.area || ""; // a lista é a fonte da verdade
    const url = resultados.dataset.mapaUrl;
    if (!url || url === urlCarregada) return;
    if (pedido) pedido.abort();
    pedido = new AbortController();
    div.classList.add("carregando");
    fetch(url, { headers: { Accept: "application/json" }, signal: pedido.signal })
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(function (dados) {
        urlCarregada = url;
        grupo.clearLayers();
        grupo.addLayers(dados.pontos.map(marcador));
        avisar(dados);
        botaoArea.classList.add("d-none");
        const area = areaAtual();
        enquadrar(function () {
          if (area) mapa.fitBounds(area, { animate: false });
          else if (dados.pontos.length) mapa.fitBounds(grupo.getBounds(), { padding: [32, 32], maxZoom: 16, animate: false });
        });
      })
      .catch(function (erro) {
        if (erro.name !== "AbortError") aviso.textContent = "Não foi possível carregar o mapa agora. A lista continua funcionando.";
      })
      .finally(function () {
        div.classList.remove("carregando");
      });
  }

  mapa.on("moveend", function () {
    if (!ajustando && urlCarregada) botaoArea.classList.remove("d-none");
  });

  botaoArea.addEventListener("click", function () {
    const b = mapa.getBounds();
    campoArea.value = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map(function (n) {
      return n.toFixed(5);
    }).join(",");
    botaoArea.classList.add("d-none");
    form.requestSubmit();
  });

  // Celular/tablet: o mapa nasce escondido (Lista | Mapa); ao aparecer, recalcula o tamanho.
  if (opcaoMapa) {
    opcaoMapa.addEventListener("change", function () {
      enquadrar(function () {
        mapa.invalidateSize({ animate: false });
        const area = areaAtual();
        if (area) mapa.fitBounds(area, { animate: false });
        else if (grupo.getLayers().length) mapa.fitBounds(grupo.getBounds(), { padding: [32, 32], maxZoom: 16, animate: false });
      });
    });
  }
  window.addEventListener("resize", function () {
    enquadrar(function () {
      mapa.invalidateSize({ animate: false });
    });
  });

  document.body.addEventListener("htmx:afterSettle", carregar);
  carregar();
})();
