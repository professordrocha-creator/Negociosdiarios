/* Prévia ao vivo da Página da loja (templates/anunciantes/painel_loja.html).
   Só mostra no navegador como vai ficar; quem valida e otimiza as imagens é o servidor
   (tipo real, tamanho, WebP, sem EXIF). Arquivo próprio: a futura CSP não libera script inline. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const form = $("form-loja");
  if (!form) return;

  const cores = ["nd-cor-1", "nd-cor-2", "nd-cor-3", "nd-cor-4", "nd-cor-5", "nd-cor-6"];
  const nome = form.querySelector("[name=nome_publico]");
  const slug = form.querySelector("[name=slug]");
  const sobre = form.querySelector("[name=sobre]");

  function trocarCor(valor) {
    [$("prev-capa"), $("prev-logo")].forEach((el) => {
      el.classList.remove(...cores);
      el.classList.add("nd-cor-" + valor);
    });
  }

  function previaImagem(campo, destino) {
    const input = form.querySelector("[name=" + campo + "]");
    if (!input) return;
    input.addEventListener("change", () => {
      const arquivo = input.files[0];
      if (!arquivo) return;
      const img = document.createElement("img");
      img.alt = "";
      img.src = URL.createObjectURL(arquivo);
      destino.replaceChildren(img);
    });
  }

  nome.addEventListener("input", () => {
    $("prev-nome").textContent = nome.value || "Nome da loja";
  });
  slug.addEventListener("input", () => {
    // Mesma regra do servidor: minúsculas, sem acento, só letras, números e hífen.
    slug.value = slug.value.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9-]/g, "-");
    $("prev-slug").textContent = slug.value;
  });
  sobre.addEventListener("input", () => {
    $("sobre-n").textContent = sobre.value.length;
  });
  form.querySelectorAll("[name=cor]").forEach((radio) => {
    radio.addEventListener("change", () => trocarCor(radio.value));
  });
  previaImagem("logo_envio", $("prev-logo"));
  previaImagem("capa_envio", $("prev-capa"));
})();
