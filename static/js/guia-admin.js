/* Cadastro assistido do guia (admin): mostra só os campos que valem para o caso escolhido.
   - "Tem endereço" mostra endereço e mapa; "a domicílio" mostra a área de atendimento.
   - Empresa mostra CNPJ; autônomo mostra CPF; regulamentado (tipo ou categoria com *) mostra o registro e
     esconde a frase (se estiver vazia; com texto ou com erro, continua visível para a pessoa apagar).
   Só conforto: quem valida tudo é o servidor. Arquivo próprio: a CSP não libera script inline. */
(function () {
  "use strict";
  const form = document.getElementById("perfilguia_form");
  if (!form) return;
  const dados = document.getElementById("categorias-reguladas");
  const reguladas = new Set(dados ? JSON.parse(dados.textContent) : []);
  const categorias = form.querySelector("select[name=categorias]");
  const frase = form.querySelector("[name=frase]");

  function mostrar(campos, visivel) {
    campos.forEach((campo) => {
      const linha = form.querySelector(".field-" + campo);
      if (!linha) return;
      const comErro = linha.querySelector(".errorlist");
      linha.classList.toggle("nd-oculto", !visivel && !comErro);
    });
  }

  function marcado(nome) {
    const opcao = form.querySelector("input[name=" + nome + "]:checked");
    return opcao ? opcao.value : "";
  }

  function atualizar() {
    const endereco = marcado("atendimento") !== "atende_a_domicilio";
    mostrar(["endereco", "latitude"], endereco);
    mostrar(["area_atendimento"], !endereco);
    if (endereco) window.dispatchEvent(new Event("resize")); /* o Leaflet refaz o tamanho do mapa */

    const tipo = marcado("tipo");
    mostrar(["cnpj", "cnpj_verificado_em"], tipo === "empresa");
    mostrar(["cpf", "final_do_cpf"], tipo === "autonomo");
    const escolhidas = categorias ? Array.from(categorias.selectedOptions) : [];
    const regulada = tipo === "profissional_regulamentado" || escolhidas.some((o) => reguladas.has(Number(o.value)));
    mostrar(["registro_profissional"], regulada);
    mostrar(["frase"], !regulada || (frase && frase.value.trim() !== ""));
  }

  form.addEventListener("change", atualizar);
  atualizar();
})();
