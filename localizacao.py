"""Geocodificação opcional via Geoapify e validações das coordenadas.

Não confundir coordenadas estimadas com geometria oficial de um lote.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
import unicodedata

import requests

GEOAPIFY_ENDPOINT = "https://api.geoapify.com/v1/geocode/search"


class LocalizacaoErro(ValueError):
    pass


@dataclass
class Localizacao:
    latitude: float
    longitude: float
    endereco_retornado: str
    cidade_retornada: str | None
    precisao: str
    origem: str

    def to_dict(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "endereco_retornado": self.endereco_retornado,
            "cidade_retornada": self.cidade_retornada,
            "precisao": self.precisao,
            "origem": self.origem,
        }


def coordenadas(texto: str) -> Localizacao:
    """Aceita -23.52, -46.84 (ponto decimal; ordem lat, lon)."""
    padrao = r"\s*([+-]?\d+(?:\.\d+)?)\s*[,;]\s*([+-]?\d+(?:\.\d+)?)\s*"
    match = re.fullmatch(padrao, texto)
    if not match:
        raise LocalizacaoErro("Use o formato latitude, longitude (ex.: -23.5200, -46.8400).")
    lat, lon = map(float, match.groups())
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise LocalizacaoErro("As coordenadas estão fora dos limites geográficos válidos.")
    return Localizacao(lat, lon, "Coordenadas informadas pelo usuário", None,
                       "Ponto informado manualmente, sem verificação cadastral", "manual")


def normalizar(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor or "")
    return "".join(x for x in texto if not unicodedata.combining(x)).casefold().strip()


def municipio_confirmado(localizacao: Localizacao) -> bool | None:
    """True só para nome de município retornado; None sem evidência suficiente."""
    if not localizacao.cidade_retornada:
        return None
    return normalizar(localizacao.cidade_retornada) == "carapicuiba"


def geocodificar(endereco: str, api_key: str, timeout: int = 15) -> list[Localizacao]:
    """Uma consulta por clique, somente com credencial fornecida pelo usuário.

    Não acessa a Geopixel e não identifica zoneamento.
    """
    endereco = endereco.strip()
    if not endereco:
        raise LocalizacaoErro("Informe o endereço do terreno.")
    if not api_key or not api_key.strip():
        raise LocalizacaoErro("Configure uma chave Geoapify para pesquisar por endereço. Alternativamente, informe coordenadas.")
    params = {
        "text": f"{endereco}, Carapicuíba, São Paulo, Brasil",
        "filter": "countrycode:br",
        "limit": 3,
        "lang": "pt",
        "format": "geojson",
        "apiKey": api_key.strip(),
    }
    try:
        resp = requests.get(GEOAPIFY_ENDPOINT, params=params, timeout=timeout,
                            headers={"User-Agent": "ZONAR/0.2 (consulta individual de enderecos)"})
        resp.raise_for_status()
        dados = resp.json()
    except requests.HTTPError as err:
        if err.response is not None and err.response.status_code in (401, 403):
            raise LocalizacaoErro("A API Geoapify rejeitou a chave ou o acesso.") from err
        if err.response is not None and err.response.status_code == 429:
            raise LocalizacaoErro("Limite de requisições da Geoapify atingido.") from err
        raise LocalizacaoErro("O serviço de localização apresentou erro HTTP.") from err
    except (requests.RequestException, ValueError) as err:
        raise LocalizacaoErro("Não foi possível consultar ou interpretar a resposta do serviço de localização.") from err

    saida = []
    for feature in dados.get("features", []):
        try:
            lon, lat = feature["geometry"]["coordinates"][:2]
            prop = feature["properties"]
            cidade = prop.get("city") or prop.get("town") or prop.get("municipality")
            precisao = prop.get("result_type") or "não informada"
            saida.append(Localizacao(float(lat), float(lon),
                                     str(prop.get("formatted") or endereco),
                                     str(cidade) if cidade else None,
                                     str(precisao), "Geoapify"))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    if not saida:
        raise LocalizacaoErro("Nenhum endereço localizado. Confira rua, número, bairro e CEP, ou informe coordenadas.")
    return saida
