"""Descoberta limitada de fontes oficiais de zoneamento em Carapicuíba.

Não faz login, não coleta dados particulares e não consulta APIs privadas.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import re
import time

import requests
from bs4 import BeautifulSoup

PREFEITURA = "https://www.carapicuiba.sp.gov.br/portal/carta-servicos/5/0/0/0/cidadao/0"
PLANO_DIRETOR = "https://carapicuiba.sp.gov.br/servico/view/223/plano-diretor"
GEOPIXEL = "https://carapicuiba.geopx.com.br/geopixelcidades3/"
LEI_3582 = "https://carapicuiba.sp.gov.br/legislacao/view/3055/lei-n-35822019-de-29-de-abril-de-2019"
USER_AGENT = "ZONAR/0.1 (+pesquisa interna de fontes publicas de zoneamento)"


@dataclass
class Fonte:
    titulo: str
    url: str
    categoria: str
    pagina_origem: str
    situacao: str
    verificada_em: str | None = None
    observacao: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def permitido(url: str) -> bool:
    """Restringe destino aos domínios municipais e ao visualizador indicado por eles."""
    p = urlparse(url)
    return p.scheme == "https" and p.hostname in {
        "www.carapicuiba.sp.gov.br", "carapicuiba.sp.gov.br",
        "carapicuiba.geopx.com.br",
    }


def candidatos(html: str, pagina_origem: str) -> list[Fonte]:
    """Extrai referências explicitamente ligadas a zoneamento de HTML público."""
    soup = BeautifulSoup(html, "html.parser")
    encontrados: list[Fonte] = []
    for a in soup.select("a[href]"):
        titulo = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        url = urljoin(pagina_origem, a.get("href", "").strip())
        texto = f"{titulo} {url}".casefold()
        if not permitido(url) or not titulo:
            continue
        if "zoneamento" not in texto:
            continue
        categoria = "Mapa / visualizador" if "mapa" in texto or "geopx.com.br" in url else "Documento relacionado"
        encontrados.append(Fonte(titulo, url, categoria, pagina_origem,
                                 "Encontrada no portal nesta execução"))
    return encontrados


def descobrir(timeout: int = 12) -> tuple[list[Fonte], list[str]]:
    """Duas consultas de páginas oficiais; referências de fallback são rotuladas."""
    fontes: dict[str, Fonte] = {}
    avisos: list[str] = []
    instante = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for pagina in (PREFEITURA, PLANO_DIRETOR):
        try:
            resposta = requests.get(pagina, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            resposta.raise_for_status()
            tipo = resposta.headers.get("Content-Type", "")
            if "html" not in tipo.lower() and not resposta.text.lstrip().startswith(("<!", "<html")):
                avisos.append(f"A resposta de {pagina} não parece ser HTML.")
                continue
            for f in candidatos(resposta.text, pagina):
                f.verificada_em = instante
                fontes[f.url] = f
        except requests.RequestException as exc:
            avisos.append(f"Falha ao consultar {pagina}: {type(exc).__name__}.")
        time.sleep(0.5)

    if GEOPIXEL not in fontes:
        fontes[GEOPIXEL] = Fonte(
            "Mapa de Zoneamento da Cidade — Geopixel Cidades",
            GEOPIXEL, "Mapa / visualizador", PREFEITURA,
            "Referência oficial catalogada (não verificada nesta execução)",
            observacao="A Prefeitura vincula este endereço ao serviço de mapa de zoneamento. Não equivale ao PDF do mapa."
        )
    fontes[PLANO_DIRETOR] = Fonte(
        "Plano Diretor — documentos e mapas de diagnóstico", PLANO_DIRETOR,
        "Documento complementar", PLANO_DIRETOR,
        "Referência oficial catalogada (não verificada nesta execução)",
        observacao="Mapas de diagnóstico não são necessariamente o mapa normativo vigente."
    )
    fontes[LEI_3582] = Fonte(
        "Lei nº 3.582/2019 — referência legislativa", LEI_3582,
        "Legislação", LEI_3582,
        "Referência oficial catalogada (não verificada nesta execução)",
        observacao="Referência de contexto; é necessário conferir a legislação atualmente aplicável."
    )
    ordem = {"Mapa / visualizador": 0, "Documento relacionado": 1,
             "Documento complementar": 2, "Legislação": 3}
    resultado = sorted(fontes.values(), key=lambda x: (ordem.get(x.categoria, 9), x.titulo))
    return resultado, avisos
