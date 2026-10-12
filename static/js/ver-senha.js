/* Botão "Mostrar" ao lado de todo campo de senha do site (login, cadastro, nova senha), para a pessoa
   conferir o que digitou. Só troca o tipo do campo no navegador: a senha não sai da página.
   Carregado no base.html (o admin tem login próprio). Arquivo próprio: a CSP não libera script inline. */
(function () {
  "use strict";
  document.querySelectorAll('input[type="password"]').forEach(function (campo) {
    const grupo = document.createElement("div");
    grupo.className = "input-group";
    campo.parentNode.insertBefore(grupo, campo);
    grupo.appendChild(campo);
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "btn btn-outline-secondary";
    botao.textContent = "Mostrar";
    botao.setAttribute("aria-pressed", "false");
    botao.setAttribute("aria-label", "Mostrar a senha");
    grupo.appendChild(botao);
    botao.addEventListener("click", function () {
      const mostrar = campo.type === "password";
      campo.type = mostrar ? "text" : "password";
      botao.textContent = mostrar ? "Ocultar" : "Mostrar";
      botao.setAttribute("aria-pressed", String(mostrar));
      botao.setAttribute("aria-label", mostrar ? "Ocultar a senha" : "Mostrar a senha");
      campo.focus();
    });
  });
})();
