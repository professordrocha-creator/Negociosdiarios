/* Botões "Copiar" (Painel › Faturas: Pix copia e cola). O botão aponta para o campo com
   data-copiar="<id>"; usa a área de transferência do navegador e, sem ela (http sem TLS, navegador
   antigo), seleciona o texto para o usuário copiar. Arquivo próprio: a CSP não libera script inline. */
(function () {
  "use strict";
  document.querySelectorAll("[data-copiar]").forEach(function (botao) {
    const rotulo = botao.querySelector("span") || botao;
    const original = rotulo.textContent;
    botao.addEventListener("click", function () {
      const campo = document.getElementById(botao.dataset.copiar);
      if (!campo) return;
      function avisar(texto) {
        rotulo.textContent = texto;
        setTimeout(function () {
          rotulo.textContent = original;
        }, 2500);
      }
      function selecionar() {
        campo.focus();
        campo.select();
        avisar("Selecionado: copie com Ctrl+C");
      }
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(campo.value).then(function () {
          avisar("Copiado!");
        }, selecionar);
      } else {
        selecionar();
      }
    });
  });
})();
