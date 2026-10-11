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
- Analytics sem cookies (Umami ou Plausible self-hosted).

## 3. Mapeamento de dados (inventário)

| Dado | Titular | Finalidade | Base legal (art. 7º) | Retenção |
|---|---|---|---|---|
| Nome, e-mail, senha (hash Argon2), data de criação e do último acesso (`contas.Usuario`) | Anunciante | Conta e acesso | Execução de contrato (V) | Enquanto ativo + 6 meses |
| Nome, e-mail, senha (hash Argon2), data de criação e do último acesso (`contas.Usuario`) | Equipe (staff) | Acesso ao painel e auditoria das ações | Legítimo interesse (IX) / contrato de trabalho ou prestação de serviço (V) | Enquanto na equipe + 6 meses |
| Código de acesso por e-mail e código de emergência (`otp_email`, `otp_static`): código temporário, validade, horário do último envio/uso e contagem de erros | Equipe (staff) | Confirmar navegador novo no login do admin | Legítimo interesse (IX) / segurança (art. 46) | Código some ao ser usado ou vencer (10 min); o registro do dispositivo fica enquanto a pessoa estiver na equipe. **Nunca** entram na exportação "Meus dados" (são credenciais) |
| Cookie "navegador confiável" do admin (id do usuário + resumo da senha, assinado; sem IP nem e-mail) | Equipe (staff) | Não pedir código de novo no mesmo navegador | Legítimo interesse (IX) / cookie essencial de segurança (sem consentimento) | 30 dias no navegador; inválido ao trocar a senha |
| Tentativas de login com erro: e-mail digitado, IP, navegador, data/hora (`axes.AccessAttempt`) | Quem tenta entrar no admin | Bloquear ataque de senha | Legítimo interesse (IX) / segurança (art. 46) | Até 1 hora (fim do bloqueio), apagadas no login certo ou no desbloqueio. Logins certos **não** são gravados pelo axes |
| CPF (corretor autônomo) | Anunciante | Emissão de nota e verificação | Obrigação legal (II) / contrato (V) | 5 anos após último pagamento (fiscal) |
| CRECI / CNPJ (`anunciantes.Anunciante.documento_*`) | Anunciante | Verificação profissional | Contrato (V) / legítimo interesse (IX) | Enquanto ativo + 5 anos |
| Nome público da loja, e-mail público e cidade (`anunciantes.Anunciante`) | Anunciante | Página da loja e contato | Contrato (V) | Enquanto ativo |
| Situação e motivo de aprovação/suspensão (`Anunciante.status`, `motivo_status`) | Anunciante | Moderação e prova das decisões | Legítimo interesse (IX) / contrato (V) | Enquanto ativo + 5 anos |
| Histórico de alterações do anunciante (`HistoricalAnunciante`, django-simple-history: cópia dos campos, quem alterou e quando) | Anunciante / equipe | Auditoria das mudanças | Legítimo interesse (IX) | Igual ao do cadastro; entra na exportação "Meus dados" e na anonimização (o histórico também é anonimizado) |
| Telefone/WhatsApp público (`Anunciante.whatsapp`, E.164) | Anunciante | Contato com clientes | Contrato (V) | Enquanto ativo |
| Endereço exato do imóvel | Proprietário (terceiro) | Localização no mapa | Legítimo interesse (IX) do anunciante | Até o anúncio sair + 90 dias |
| Fotos de anúncios | Terceiros eventualmente visíveis | Divulgação | Legítimo interesse (IX) | Até o anúncio sair + 90 dias |
| Faturas e pagamentos | Anunciante | Cobrança e obrigações fiscais | Obrigação legal (II) | 5 anos |
| Registros de acesso (IP, data/hora) | Todos | Segurança; Marco Civil art. 15 | Obrigação legal (II) | 6 meses |
| Denúncias (e-mail opcional do denunciante) | Visitante | Moderação | Legítimo interesse (IX) | 1 ano |
| Cookies não essenciais | Visitante | Publicidade/medição de terceiros | Consentimento (I) | Até revogar |

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
| Confirmação e acesso | Painel → "Meus dados" mostra tudo que temos |
| Portabilidade | Botão "Baixar meus dados" (JSON + fotos em ZIP), gerado pelo Celery |
| Correção | Edição no próprio painel |
| Eliminação / anonimização | "Encerrar conta": apaga anúncios e fotos, anonimiza usuário; mantém só o exigido por lei (faturas) |
| Revogação de consentimento | Banner de cookies reabrível no rodapé |
| Informação sobre compartilhamento | Lista de operadores na Política de Privacidade |

Prazo para resposta completa: até **15 dias** (art. 19, II). Registrar cada pedido no admin.

## 6. Documentos públicos necessários antes do lançamento
- [ ] Política de Privacidade (linguagem simples) — rascunho em `/privacidade/`, falta revisão do advogado
- [ ] Termos de Uso para visitantes — rascunho em `/termos/`, falta revisão do advogado
- [ ] Contrato/Termos do Anunciante (responsabilidade pelo conteúdo, regras de anúncio, cancelamento, reembolso)
- [ ] Política de Cookies + banner com opção "Recusar" do mesmo tamanho de "Aceitar" — rascunho em
  `/cookies/` (hoje só cookies essenciais, sem banner); falta revisão do advogado
- [ ] Canal de denúncia de anúncio (Marco Civil art. 19 + combate a golpes)

## 7. Incidente de segurança
1. Conter (derrubar acesso, trocar senhas/tokens).
2. Avaliar: quais dados, quantos titulares, risco.
3. Se houver risco ou dano relevante: comunicar **ANPD e titulares** no prazo
   da Resolução CD/ANPD nº 15/2024 (3 dias úteis; agentes de pequeno porte têm prazo em dobro).
4. Registrar o incidente em `docs/incidentes/AAAA-MM-DD.md` (manter por 5 anos).

## 8. Revisões
Revisar este documento a cada nova versão (V1, V2, V3) e a cada novo operador contratado.
