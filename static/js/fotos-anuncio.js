/* Ordem das fotos por arrastar (templates/anuncios/fotos.html).
   Ao soltar, a nova ordem (campos "ordem") é enviada sozinha. Sem JavaScript, as setas ↑ ↓
   fazem o mesmo (a confirmação de excluir fica no confirmar.js). Arquivo próprio: a CSP não libera script inline. */
(function () {
  "use strict";
  const lista = document.getElementById("lista-fotos");
  const form = document.getElementById("form-ordem");

  if (!lista || !form) return;

  let arrastado = null;

  lista.addEventListener("dragstart", (e) => {
    arrastado = e.target.closest("li");
    if (!arrastado) return;
    arrastado.classList.add("arrastando");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", arrastado.dataset.id);
  });

  lista.addEventListener("dragover", (e) => {
    const alvo = e.target.closest("li");
    if (!arrastado || !alvo || alvo === arrastado) return;
    e.preventDefault();
    lista.querySelectorAll(".alvo").forEach((li) => li.classList.remove("alvo"));
    alvo.classList.add("alvo");
  });

  lista.addEventListener("drop", (e) => {
    const alvo = e.target.closest("li");
    if (!arrastado || !alvo || alvo === arrastado) return;
    e.preventDefault();
    const itens = [...lista.children];
    const depois = itens.indexOf(arrastado) < itens.indexOf(alvo);
    lista.insertBefore(arrastado, depois ? alvo.nextSibling : alvo);
    form.requestSubmit(document.getElementById("salvar-ordem"));
  });

  lista.addEventListener("dragend", () => {
    lista.querySelectorAll(".alvo, .arrastando").forEach((li) => li.classList.remove("alvo", "arrastando"));
    arrastado = null;
  });
})();
