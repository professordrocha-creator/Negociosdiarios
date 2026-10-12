/* Galeria da página do anúncio (templates/anuncios/publico.html).
   Sem JavaScript a galeria já funciona: o trilho rola com encaixe (no celular, deslizar com o dedo)
   e as miniaturas são âncoras. Aqui só entram as setas, o contador "1 / N", a miniatura atual e
   as teclas ← →. Arquivo próprio: a CSP não libera script inline. */
(function () {
  "use strict";
  const galeria = document.querySelector("[data-galeria]");
  if (!galeria) return;
  const trilho = galeria.querySelector(".nd-galeria-trilho");
  const fotos = [...trilho.children];
  const contador = galeria.querySelector("[data-contador]");
  const miniaturas = [...document.querySelectorAll(".nd-miniaturas [data-ir]")];
  const total = fotos.length;

  function atual() {
    return Math.round(trilho.scrollLeft / trilho.clientWidth);
  }

  function ir(indice) {
    const alvo = Math.max(0, Math.min(total - 1, indice));
    trilho.scrollTo({ left: alvo * trilho.clientWidth, behavior: "smooth" });
  }

  function marcar() {
    const i = atual();
    contador.textContent = `${i + 1} / ${total} fotos`;
    miniaturas.forEach((m, j) => {
      m.classList.toggle("atual", j === i);
      if (j === i) m.setAttribute("aria-current", "true");
      else m.removeAttribute("aria-current");
    });
  }

  let espera = null;
  trilho.addEventListener("scroll", () => {
    clearTimeout(espera);
    espera = setTimeout(marcar, 60);
  }, { passive: true });

  galeria.querySelector("[data-anterior]")?.addEventListener("click", () => ir(atual() - 1));
  galeria.querySelector("[data-proxima]")?.addEventListener("click", () => ir(atual() + 1));
  trilho.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); ir(atual() - 1); }
    if (e.key === "ArrowRight") { e.preventDefault(); ir(atual() + 1); }
  });
  miniaturas.forEach((m) => {
    m.addEventListener("click", (e) => {
      e.preventDefault(); /* sem pular a página para a âncora */
      ir(parseInt(m.dataset.ir, 10));
    });
  });
  marcar();
})();
