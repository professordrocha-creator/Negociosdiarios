"""Sinais do app planos: avisam quando a assinatura entra em atraso ou é regularizada.

Quem tem anúncios (app `anuncios`, Sprint 3) se conecta aqui para PAUSAR os anúncios no
atraso e REATIVÁ-LOS no pagamento (nunca apagar; ARQUITETURA §5, regra 2). Assim o app
planos não precisa conhecer o modelo de anúncio. Argumento enviado: `assinatura`.
"""

from django.dispatch import Signal

assinatura_em_atraso = Signal()
assinatura_regularizada = Signal()
