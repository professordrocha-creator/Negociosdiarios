/* Localização do anúncio (Parte 4): o seletor de bairro mostra só os bairros da cidade escolhida (data-cidade
   em cada opção) e o campo "Nome do bairro" só aparece com "Outro bairro". Bairro de outra cidade já escolhido
   volta para "escolha". Sem JavaScript, tudo aparece e o servidor confere. Arquivo próprio: a CSP não libera
   script inline. */
(function () {
  "use strict";
  const form = document.getElementById("form-localizacao");
  if (!form) return;
  const cidade = form.querySelector("select[name=cidade]");
  const bairro = form.querySelector("select[name=bairro]");
  const novo = document.getElementById("bairro-novo");
  if (!cidade || !bairro) return;

  function filtrar() {
    Array.from(bairro.options).forEach((opcao) => {
      const daCidade = !opcao.dataset.cidade || opcao.dataset.cidade === cidade.value;
      opcao.hidden = !daCidade;
      opcao.disabled = !daCidade;
      if (!daCidade && opcao.selected) bairro.value = "";
    });
    mostrarNovo();
  }

  function mostrarNovo() {
    if (!novo) return;
    const comErro = !!novo.querySelector(".text-danger");
    novo.hidden = bairro.value !== "outro" && !comErro;
  }

  cidade.addEventListener("change", filtrar);
  bairro.addEventListener("change", mostrarNovo);
  filtrar();
})();
