/* Reduz as fotos no navegador antes do envio (Painel › Anúncio › Fotos). Campo: input[data-reduzir-fotos]
   com data-lado-maximo (px). Foto de celular de 10–20 MB vira um JPEG de até esse lado: o envio fica rápido
   no 4G e não esbarra no limite do servidor (que continua como rede de segurança, Configuracao).

   O navegador já desenha a foto na posição certa (orientação do celular). O servidor sempre confere o tipo
   real, tira o EXIF e regrava a imagem: aqui é só conforto. Tudo que der errado (navegador antigo, HEIC
   que o navegador não abre) envia o arquivo original: o servidor também aceita HEIC e converte.
   Arquivo próprio: a CSP não libera script inline. */
(function () {
  "use strict";
  const campo = document.querySelector("input[type=file][data-reduzir-fotos]");
  if (!campo || !campo.form || typeof DataTransfer === "undefined" || typeof createImageBitmap === "undefined") return;
  const form = campo.form;
  const ladoMaximo = Number(campo.dataset.ladoMaximo) || 2560;
  const PESO_OK = 3 * 1024 * 1024; // abaixo disso e dentro do lado máximo, envia como está
  let enviando = false;

  async function reduzir(arquivo) {
    if (!arquivo.type.startsWith("image/")) return arquivo;
    let imagem;
    try {
      imagem = await createImageBitmap(arquivo, { imageOrientation: "from-image" });
    } catch (erro) {
      return arquivo; // ex.: HEIC fora do Safari: o servidor converte
    }
    const maior = Math.max(imagem.width, imagem.height);
    if (maior <= ladoMaximo && arquivo.size <= PESO_OK) {
      imagem.close();
      return arquivo;
    }
    const escala = Math.min(1, ladoMaximo / maior);
    const tela = document.createElement("canvas");
    tela.width = Math.round(imagem.width * escala);
    tela.height = Math.round(imagem.height * escala);
    const desenho = tela.getContext("2d");
    desenho.fillStyle = "#fff"; // PNG com transparência: fundo branco no JPEG
    desenho.fillRect(0, 0, tela.width, tela.height);
    desenho.drawImage(imagem, 0, 0, tela.width, tela.height);
    imagem.close();
    const blob = await new Promise(function (resolver) {
      tela.toBlob(resolver, "image/jpeg", 0.85);
    });
    if (!blob || blob.size >= arquivo.size) return arquivo; // não ficou menor: manda o original
    const nome = arquivo.name.replace(/\.[^.]+$/, "") + ".jpg";
    return new File([blob], nome, { type: "image/jpeg", lastModified: arquivo.lastModified });
  }

  form.addEventListener("submit", async function (evento) {
    if (enviando || !campo.files.length) return;
    evento.preventDefault();
    enviando = true;
    const botao = evento.submitter || form.querySelector("[type=submit]");
    const rotulo = botao ? botao.innerHTML : "";
    if (botao) {
      botao.textContent = "Preparando fotos…";
      botao.classList.add("nd-preparando");
    }
    try {
      const prontos = new DataTransfer();
      for (const arquivo of Array.from(campo.files)) {
        prontos.items.add(await reduzir(arquivo));
      }
      campo.files = prontos.files;
    } catch (erro) {
      // qualquer falha: segue com os arquivos originais
    }
    if (botao) {
      botao.innerHTML = rotulo;
      botao.classList.remove("nd-preparando");
    }
    form.submit();
  });
})();
