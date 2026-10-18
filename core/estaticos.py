"""Armazenamento dos arquivos estáticos em produção, com nome versionado (ESTATICOS_VERSIONADOS=True).

Igual ao `ManifestStaticFilesStorage` do Django (nd.css vira nd.<hash>.css e o CSS aponta para fontes e
imagens com o nome versionado), menos uma coisa: não segue os comentários `sourceMappingURL`. As bibliotecas
que vêm prontas (Leaflet, Bootstrap, HTMX) citam arquivos `.map` que não estão no projeto, e o padrão do
Django pararia o collectstatic por isso. Os `.map` só servem para depurar no navegador; nada no site depende
deles.
"""

from django.contrib.staticfiles.storage import HashedFilesMixin, ManifestStaticFilesStorage


def _sem_source_map(padroes: tuple) -> tuple:
    """Os padrões do Django sem as regras de `sourceMappingURL` (CSS e JS)."""
    resultado = []
    for extensao, regras in padroes:
        mantidas = tuple(r for r in regras if "sourceMappingURL" not in (r[0] if isinstance(r, tuple) else r))
        if mantidas:
            resultado.append((extensao, mantidas))
    return tuple(resultado)


class EstaticosVersionados(ManifestStaticFilesStorage):
    """ManifestStaticFilesStorage que ignora `sourceMappingURL` (ver a docstring do módulo)."""

    patterns = _sem_source_map(HashedFilesMixin.patterns)
