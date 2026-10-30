/* Peças da campanha (admin): mostra só os campos que valem para o formato escolhido.
   - Banner: imagem (e o bloco "Avançado: imagem própria para celular"); esconde título e texto.
   - Card: imagem (logo), título e frase; esconde o bloco do celular.
   - Nativo: só título, texto e link; esconde imagens, prévia e texto alternativo.
   Campo com erro continua visível. Só conforto: quem valida é o servidor. Arquivo próprio: a CSP não libera
   script inline. */
(function () {
  "use strict";
  const ESCONDER = {
    banner: ["titulo", "texto"],
    card: ["envio_imagem_celular"],
    nativo: ["previa", "envio_imagem", "texto_alternativo", "envio_imagem_celular"],
  };

  function mostrar(elemento, visivel) {
    elemento.style.display = visivel ? "" : "none"; // via CSSOM: a CSP não bloqueia
  }

  function ajustar(peca) {
    const seletor = peca.querySelector("select[name$='-formato']");
    if (!seletor) return;
    const esconder = new Set(ESCONDER[seletor.value] || []);
    ["previa", "envio_imagem", "texto_alternativo", "titulo", "texto"].forEach((campo) => {
      const linha = peca.querySelector(".field-" + campo);
      if (linha) mostrar(linha, !esconder.has(campo) || !!linha.querySelector(".errorlist"));
    });
    const celular = peca.querySelector(".field-envio_imagem_celular");
    const bloco = celular && celular.closest("fieldset");
    if (bloco) {
      const comErro = !!bloco.querySelector(".errorlist");
      mostrar(bloco, !esconder.has("envio_imagem_celular") || comErro);
      const detalhes = bloco.querySelector("details");
      if (detalhes && comErro) detalhes.open = true;
    }
  }

  function ajustarTodas() {
    document.querySelectorAll(".inline-related").forEach(ajustar);
  }

  document.addEventListener("change", (evento) => {
    if (evento.target.matches("select[name$='-formato']")) ajustar(evento.target.closest(".inline-related"));
  });
  document.addEventListener("formset:added", (evento) => ajustar(evento.target));
  document.addEventListener("DOMContentLoaded", ajustarTodas);
})();
