# LGPD — Proteção de Dados Pessoais

> Lei nº 13.709/2018. Este documento é o **registro das operações de tratamento**
> (art. 37) e o guia técnico de conformidade. Não substitui revisão por advogado
> antes do lançamento.

## 1. Papéis
- **Controlador:** D'Rocha Soluções (titular do CNPJ que operar a plataforma).
- **Operadores:** provedor do VPS, provedor de storage, Mercado Pago (para dados
  de pagamento ele também é controlador independente), serviço de e-mail, Sentry.
  Cada um precisa constar na Política de Privacidade.
- **Encarregado (DPO):** agentes de tratamento de pequeno porte podem ser
  dispensados de indicar encarregado (Resolução CD/ANPD nº 2/2022), **mas devem
  manter um canal de comunicação** com o titular. Criar `privacidade@negociosdiarios.com.br`.

## 2. Princípio guia: coletar menos
A melhor proteção é não ter o dado. Decisões já tomadas por isso:
- Visitante **não se cadastra** → quase nenhum dado de visitante.
- Contato vai direto pelo WhatsApp → não armazenamos mensagens/leads.
- Estatísticas contam visualizações com hash diário do IP (sal rotativo), sem guardar IP.
  Implementado na Sprint 3B (`estatisticas.services`): hash SHA-256 de sal aleatório do dia + IP + navegador,
  guardado **só no cache** até o fim do dia (o sal expira em 2 dias, então o hash não pode ser refeito);
  no banco ficam só totais por anúncio e dia (`EstatisticaDiaria`). Robôs, prévias de link e o próprio
  dono não contam. O mesmo vale para os cliques no WhatsApp.
- Localização do imóvel: o ponto exato e o endereço nunca vão para a página pública no modo aproximado (nem para o JSON do mapa da busca: ele usa o ponto já deslocado, `DetalheImovel.ponto_publico`, que também é o único usado pelo filtro "Buscar nesta área", para que perguntas repetidas por retângulos não revelem o ponto real)
  (o círculo de ~300 m tem o centro deslocado de forma fixa por anúncio); "só o bairro" não mostra mapa.
- Analytics sem cookies (Umami ou Plausible self-hosted).

## 3. Mapeamento de dados (inventário)

| Dado | Titular | Finalidade | Base legal (art. 7º) | Retenção |
|---|---|---|---|---|
| Nome, e-mail, senha (hash Argon2), data de criação e do último acesso (`contas.Usuario`) | Anunciante | Conta e acesso | Execução de contrato (V) | Enquanto ativo + 6 meses |
| Data da confirmação do e-mail (`Usuario.email_confirmado_em`) | Anunciante | Provar que o e-mail é de quem se cadastrou | Execução de contrato (V) | Enquanto a conta existir |
| Aceite dos Termos e da Privacidade: documento, versão e data (`contas.AceiteDocumento`; sem IP) | Anunciante | Provar o que foi aceito e quando | Execução de contrato (V) / exercício regular de direitos (VI) | Enquanto a conta existir + 5 anos |
| Contador de tentativas por IP (cadastro, senha), com o IP só como resumo HMAC, no cache | Quem usa os formulários | Proteção contra robôs | Legítimo interesse (IX) / segurança (art. 46) | 1 hora (some sozinho) |
| Nome, e-mail, senha (hash Argon2), data de criação e do último acesso (`contas.Usuario`) | Equipe (staff) | Acesso ao painel e auditoria das ações | Legítimo interesse (IX) / contrato de trabalho ou prestação de serviço (V) | Enquanto na equipe + 6 meses |
| Código de acesso por e-mail e código de emergência (`otp_email`, `otp_static`): código temporário, validade, horário do último envio/uso e contagem de erros | Equipe (staff) | Confirmar navegador novo no login do admin | Legítimo interesse (IX) / segurança (art. 46) | Código some ao ser usado ou vencer (10 min); o registro do dispositivo fica enquanto a pessoa estiver na equipe. **Nunca** entram na exportação "Meus dados" (são credenciais) |
| Cookie "navegador confiável" do admin (id do usuário + resumo da senha, assinado; sem IP nem e-mail) | Equipe (staff) | Não pedir código de novo no mesmo navegador | Legítimo interesse (IX) / cookie essencial de segurança (sem consentimento) | 30 dias no navegador; inválido ao trocar a senha |
| Tentativas de login com erro: e-mail digitado, IP, navegador, data/hora (`axes.AccessAttempt`) | Quem tenta entrar no admin | Bloquear ataque de senha | Legítimo interesse (IX) / segurança (art. 46) | Até 1 hora (fim do bloqueio), apagadas no login certo ou no desbloqueio. Logins certos **não** são gravados pelo axes |
| CPF (corretor autônomo) | Anunciante | Emissão de nota e verificação | Obrigação legal (II) / contrato (V) | 5 anos após último pagamento (fiscal) |
| CRECI / CNPJ (`anunciantes.Anunciante.documento_*`) | Anunciante | Verificação profissional | Contrato (V) / legítimo interesse (IX) | Enquanto ativo + 5 anos |
| Nome público da loja, e-mail público e cidade (`anunciantes.Anunciante`) | Anunciante | Página da loja e contato | Contrato (V) | Enquanto ativo |
| Página da loja: sobre, horário, Instagram, site, logo e capa (WebP, sem EXIF) e endereço público, que só aparece com `mostrar_no_mapa` (corretor autônomo pode ter o endereço de casa: por isso o padrão é não mostrar) | Anunciante | Divulgar a loja | Contrato (V) | Enquanto ativo; imagens apagadas com a conta |
| Solicitação de cidade: cidade pedida, situação, motivo da decisão e quem decidiu (`anunciantes.SolicitacaoCidade`) | Anunciante | Decidir a expansão e explicar a recusa | Legítimo interesse (IX) / contrato (V) | Enquanto a conta existir + 5 anos |
| Situação e motivo de aprovação/suspensão (`Anunciante.status`, `motivo_status`) | Anunciante | Moderação e prova das decisões | Legítimo interesse (IX) / contrato (V) | Enquanto ativo + 5 anos |
| Histórico de alterações do anunciante (`HistoricalAnunciante`, django-simple-history: cópia dos campos, quem alterou e quando) | Anunciante / equipe | Auditoria das mudanças | Legítimo interesse (IX) | Igual ao do cadastro; entra na exportação "Meus dados" e na anonimização (o histórico também é anonimizado) |
| Assinatura: plano, periodicidade, início, vencimento, situação (ativa/em atraso/cancelada) e histórico com quem mudou e o motivo, incluindo o texto da baixa manual de pagamento (`planos.Assinatura`) | Anunciante | Cobrança e limite de anúncios | Execução de contrato (V) / obrigação legal (II) | 5 anos após o fim da assinatura (fiscal); entra na exportação "Meus dados". O motivo da baixa não deve conter dados bancários nem CPF |
| Pedidos de troca de plano: planos, periodicidade, situação, motivo da decisão, quem decidiu e quando (`planos.PedidoTrocaPlano`) | Anunciante | Atender e provar o pedido | Execução de contrato (V) | Enquanto a conta existir + 5 anos; entra na exportação "Meus dados" |
| Telefone/WhatsApp público (`Anunciante.whatsapp`, E.164) | Anunciante | Contato com clientes | Contrato (V) | Enquanto ativo |
| Endereço exato e ponto no mapa do imóvel (`DetalheImovel.endereco`, `ponto`; nunca exibidos: o público vê aproximado, exato ou só o bairro, conforme `exibir_localizacao`, padrão aproximado) | Proprietário (terceiro) / anunciante | Conferência pela equipe e localização no mapa | Legítimo interesse (IX) do anunciante | Até o anúncio sair + 90 dias; entra na exportação "Meus dados" do anunciante e na anonimização (Sprint 7) |
| Ponto da loja no mapa (`Anunciante.ponto`; pode ser a casa de um corretor autônomo) | Anunciante | Mostrar a loja no mapa da busca de veículos e na página da loja | Consentimento do anunciante (I): só é exibido com "mostrar endereço e mapa" ligado, e ele pode tirar o ponto a qualquer hora | Enquanto a loja existir; entra na exportação "Meus dados" e na anonimização (Sprint 7) |
| Fotos de anúncios (`anuncios.Foto`: WebP sem EXIF/GPS; o envio original é apagado após o processamento; foto excluída pelo anunciante é apagada na hora) | Terceiros eventualmente visíveis | Divulgação | Legítimo interesse (IX) | Até o anúncio sair + 90 dias |
| Anúncio: textos, preço, situação, motivo da moderação, quem moderou e histórico (`anuncios.Anuncio`) | Anunciante | Publicar o anúncio e provar as decisões de moderação | Contrato (V) / legítimo interesse (IX) | Enquanto a conta existir + 5 anos (excluído = lógico); entra na exportação "Meus dados" |
| Faturas (`pagamentos.Fatura`): valor, período, vencimento, situação, forma, data do pagamento, observações da equipe e do anunciante, quem confirmou, histórico | Anunciante | Cobrança e obrigações fiscais | Execução de contrato (V) / obrigação legal (II) | 5 anos após o pagamento (fiscal); entra na exportação "Meus dados"; não é apagada na exclusão da conta (só o exigido por lei fica) |
| Comprovantes de pagamento (`Fatura.comprovante`: imagem ou PDF enviado no "Já paguei"; pode ter nome, banco e parte do CPF/CNPJ de quem pagou, às vezes um terceiro) | Anunciante / pagador | Conferir o pagamento | Execução de contrato (V) / obrigação legal (II) | 5 anos com a fatura paga; comprovante recusado é apagado quando outro o substitui. Guardado em armazenamento **privado** (nunca na mídia pública), imagem sem EXIF, acesso só do dono da fatura e da equipe Financeiro/Administrador; entra na exportação "Meus dados" |
| Registros de acesso (IP, data/hora) | Todos | Segurança; Marco Civil art. 15 | Obrigação legal (II) | 6 meses |
| Estatísticas de anúncio: totais diários de visualizações e cliques no WhatsApp (`estatisticas.EstatisticaDiaria`; **sem IP nem identificador**). Para não contar a mesma pessoa duas vezes no dia, um hash de IP + navegador + sal aleatório do dia fica só no cache até o fim do dia | Visitante (só o hash temporário) | Mostrar ao anunciante o desempenho dos anúncios | Legítimo interesse (IX) | Hash: até o fim do dia (sal: 2 dias). Totais: enquanto o anúncio existir (não são dado pessoal) |
| Patrocinador de publicidade (`publicidade.Patrocinador`: nome da empresa, CNPJ, nome, e-mail e WhatsApp da pessoa de contato) | Contato do patrocinador | Vender, cobrar e avisar sobre a campanha | Execução de contrato (V) | Enquanto houver relação comercial + 5 anos (fiscal); nunca apagado pelo admin (exclusão lógica) |
| Métricas de publicidade (`publicidade.MetricaDiaria`: totais de impressões e cliques por peça e dia) | — (nenhum dado do visitante: sem IP, sem cookie, sem identificador; o User-Agent só é lido na hora para pular robôs) | Relatório ao patrocinador | Não é dado pessoal | Enquanto a campanha existir |
| Denúncias (e-mail opcional do denunciante) | Visitante | Moderação | Legítimo interesse (IX) | 1 ano |
| Pedidos de titulares (`privacidade.PedidoTitular`: tipo, origem, descrição, contato informado só nos pedidos por e-mail, situação, prazo, resposta, histórico) | Titular | Atender e provar o atendimento (art. 18 e 19) | Obrigação legal (II) | 5 anos |
| Aceite dos Termos e da Política (`contas.AceiteDocumento`: documento, versão, data e hora; sem IP) | Anunciante | Provar o que foi aceito | Execução de contrato (V) / exercício regular de direitos (VI) | Enquanto a conta existir + 5 anos (fica ligado à conta anonimizada) |

**Regra:** novo campo com dado pessoal → nova linha nesta tabela no mesmo PR.

## 4. Cuidados específicos de classificados
- **Endereço do imóvel:** por padrão o mapa mostra **localização aproximada**
  (círculo de ~300 m). Exata só se o anunciante marcar.
- **Fotos:** EXIF removido (GPS do celular revela onde a foto foi tirada).
  Orientar o anunciante a não fotografar pessoas, documentos ou placas inteiras.
- **Placa do veículo:** não pedir a placa completa; no máximo o final.
- **CPF:** nunca exibido; mascarado no admin (`***.456.789-**`); campo criptografado.

## 5. Direitos do titular (art. 18) — implementação
| Direito | Como atendemos |
|---|---|
| Confirmação e acesso | Painel → "Meus dados" (`/painel/meus-dados/`) mostra o que guardamos e os aceites |
| Portabilidade | "Baixar meus dados": senha de novo, JSON com conta, loja, assinatura, pedidos de plano, anúncios (ficha, endereço e ponto privados, endereços das fotos), faturas e aceites; pedido registrado como atendido |
| Correção | Edição no próprio painel; o resto por e-mail (pedido registrado no admin) |
| Eliminação / anonimização | "Excluir minha conta": senha + a palavra EXCLUIR; e-mail vira `removido-<id>@anonimo.invalid`, nome "Conta removida", senha inutilizável, conta inativa; loja encerrada e anonimizada (também no histórico); anúncios removidos e fotos apagadas do storage; endereço/ponto do imóvel apagados (também no histórico); assinatura cancelada; tentativas de login e códigos de acesso apagados; e-mail de confirmação ao endereço antigo. Fica só o exigido por lei: faturas e comprovantes pela guarda fiscal (`Configuracao.retencao_fiscal_anos`, padrão 5) e o CRECI/CNPJ ligado a elas. Fatura em aberto é avisada, não impede |
| Revogação de consentimento | Não há consentimento hoje (nenhum cookie não essencial) |
| Informação sobre compartilhamento | Lista de operadores na Política de Privacidade |

Prazo para resposta completa: até **15 dias** (art. 19, II; `Configuracao.prazo_titular_dias`). Cada pedido fica em Admin › Privacidade › Pedidos dos titulares, com data, prazo e "prazo vencido".

Guarda fiscal: a rotina diária (4h) apaga o comprovante e as anotações das faturas pagas ou canceladas há mais que `Configuracao.retencao_fiscal_anos` (padrão 5 anos), também no histórico.

## 5a. Cookies (lista completa)
O site só grava cookies essenciais: **sem banner**. A seção "Cookies" da Política de Privacidade (`/privacidade/#cookies`, link no rodapé) mostra a mesma lista (`privacidade.services.COOKIES`; um teste confere que todo cookie gravado está aqui e lá). Cookie não essencial novo exige o banner com "Aceitar" e "Recusar" do mesmo tamanho e sem caixa pré-marcada.

| Cookie | Para que serve | Quem recebe | Duração | Tipo |
|---|---|---|---|---|
| `csrftoken` | Proteção de formulários contra envio forjado | Quem usa um formulário | 1 ano | Essencial |
| `sessionid` | Manter o login | Anunciantes e equipe | 2 semanas | Essencial |
| `messages` | Mostrar um aviso na página seguinte | Quem envia um formulário | Até o aviso aparecer | Essencial |
| `nd_admin_navegador` | Navegador confiável do admin (não pedir código de novo) | Só a equipe | 30 dias | Essencial |

Não gravam cookie: estatísticas de anúncios, métricas de publicidade (contadas sem cookie e sem IP) e os tiles do mapa (OpenStreetMap).

## 6. Documentos públicos necessários antes do lançamento
- [ ] Política de Privacidade (linguagem simples) — texto e versão no admin (`DocumentoLegal`), em `/privacidade/`,
  com o Encarregado (`Configuracao.encarregado_nome` + e-mail de privacidade) e a seção Cookies; falta revisão do advogado
  (o aviso "rascunho, revisão jurídica pendente" aparece só no admin)
- [ ] Termos de Uso — texto e versão no admin, em `/termos/`; falta revisão do advogado. Versão nova publicada → no
  próximo acesso ao painel o anunciante vê o resumo e aceita (aceite gravado com versão, data e hora)
- [ ] Contrato/Termos do Anunciante (responsabilidade pelo conteúdo, regras de anúncio, cancelamento, reembolso)
- [x] Cookies: só essenciais → sem banner; seção na Política (`/cookies/` redireciona para ela) e link no rodapé
- [ ] Canal de denúncia de anúncio (Marco Civil art. 19 + combate a golpes)

## 7. Incidente de segurança
1. Conter (derrubar acesso, trocar senhas/tokens).
2. Avaliar: quais dados, quantos titulares, risco.
3. Se houver risco ou dano relevante: comunicar **ANPD e titulares** no prazo
   da Resolução CD/ANPD nº 15/2024 (3 dias úteis; agentes de pequeno porte têm prazo em dobro).
4. Registrar o incidente em `docs/incidentes/AAAA-MM-DD.md` (manter por 5 anos).

## 8. Revisões
Revisar este documento a cada nova versão (V1, V2, V3) e a cada novo operador contratado.
