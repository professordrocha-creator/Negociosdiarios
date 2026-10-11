/* Pede confirmação antes de enviar formulários com data-confirmar="pergunta" (ex.: excluir).
   Arquivo próprio: a CSP não libera script inline. */
(function () {
  "use strict";
  document.querySelectorAll("form[data-confirmar]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      if (!window.confirm(form.dataset.confirmar)) e.preventDefault();
    });
  });
})();
