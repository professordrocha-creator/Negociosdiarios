/* "Quero ser listado" (guia): o campo de texto "Qual cidade?" / "O que você faz?" só aparece quando a pessoa
   escolhe "Outra" na lista. Campo com erro continua visível. Sem JavaScript, os dois campos ficam sempre à
   mostra (quem valida é o servidor). Arquivo próprio: a CSP não libera script inline. */
(function () {
  "use strict";
  const OUTRA = "outra";

  document.querySelectorAll("[data-outra-de]").forEach((bloco) => {
    const lista = document.querySelector("select[name='" + bloco.dataset.outraDe + "']");
    if (!lista) return;
    const texto = bloco.querySelector("input");
    function ajustar() {
      const outra = lista.value === OUTRA;
      bloco.hidden = !outra && !bloco.querySelector(".text-danger");
      if (texto) texto.required = outra;
    }
    lista.addEventListener("change", ajustar);
    ajustar();
  });
})();
