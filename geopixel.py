"""Integração experimental para UMA consulta espacial sob ação do usuário.

O endpoint e o formato da consulta foram observados pelo usuário em uma sessão
pública do visualizador Geopixel Cidades (Carapicuíba/SP). A presença da camada
não implica licença de coleta automatizada nem garante estabilidade desta API.

Não usa cookies, tokens, sessões, engenharia reversa de autenticação, varredura
ou múltiplas requisições. Se o serviço exigir autenticação ou negar acesso, pare.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any

import requests
from pyproj import Transformer
from shapely.geometry import Point, mapping
from shapely.ops import transform
from shapely import wkb

ENDPOINT = "https://carapicuiba.geopx.com.br/geopixelcidades3_server/data/getData"
LAYER_ID = 5156
TABLE_NAME = "zoneamento_lei210799_validacao"
EPSG_ORIGEM = 3857
TO_3857 = Transformer.from_crs(4326, 3857, always_xy=True)
TO_4326 = Transformer.from_crs(3857, 4326, always_xy=True)

class GeoPixelErro(Exception):
    pass


def fabricar_payload(latitude: float, longitude: float) -> dict:
    """Reconstrói o filtro POINTING/INTERSECTS com buffer de 0,5 em EPSG:3857.

    Passa lon/lat ao transformador (always_xy=True). O teste só funciona se
    as coordenadas de entrada forem corretas; geocodificação não prova lote.
    """
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Latitude/longitude inválidas")
    x, y = TO_3857.transform(longitude, latitude)
    geometria = wkb.dumps(Point(x, y), hex=True, srid=EPSG_ORIGEM)
    return {
        "expressionType": "Filter",
        "themeId": LAYER_ID,
        "resultType": "BOTH",
        "selectList": None,
        "groupByList": None,
        "joinList": None,
        "limit": 0,
        "orderByList": None,
        "attributeFilter": None,
        "filterHint": "POINTING",
        "spatialFilter": {
            "queryExpression": {
                "expressionType": "SpatialRelationFunction",
                "type": "INTERSECTS",
                "arguments": [
                    {"expressionType": "PropertyName", "name": "geom", "tableName": TABLE_NAME},
                    {"expressionType": "SpatialFunction", "type": "BUFFER",
                     "arguments": [
                         {"expressionType": "LiteralGeometry", "type": "GEOMETRY", "srid": EPSG_ORIGEM, "value": geometria},
                         {"expressionType": "Literal", "type": "DOUBLE", "value": 0.5}
                     ], "autoTransformSRID": True}
                ], "autoTransformSRID": True
            }
        },
    }


def consultar(latitude: float, longitude: float, timeout: int = 18) -> dict:
    """Envia uma única chamada sem credenciais/cookies. Sem retries automáticos."""
    payload = fabricar_payload(latitude, longitude)
    try:
        r = requests.post(
            ENDPOINT, json=payload,
            headers={"Accept": "application/json", "User-Agent": "ZONAR/0.3 (consulta geoespacial pontual de uso interno)"},
            timeout=timeout,
            allow_redirects=False,
        )
        if r.status_code in (301, 302, 303, 307, 308, 401, 403):
            raise GeoPixelErro(f"A consulta não está acessível anonimamente (HTTP {r.status_code}). Não tentar contornar restrições.")
        if r.status_code == 429:
            raise GeoPixelErro("Serviço limitou as consultas (HTTP 429). Interrompa novas tentativas.")
        r.raise_for_status()
        if "json" not in r.headers.get("Content-Type", "").lower():
            raise GeoPixelErro("O servidor não retornou JSON; verifique a integração no portal.")
        data = r.json()
        if not isinstance(data, dict):
            raise GeoPixelErro("Formato inesperado da resposta.")
        return data
    except requests.RequestException as exc:
        raise GeoPixelErro(f"Falha na consulta ao serviço ({type(exc).__name__}).") from exc
    except ValueError as exc:
        raise GeoPixelErro("Não foi possível interpretar o JSON retornado.") from exc


def processar_resposta(data: dict, latitude: float, longitude: float) -> dict[str, Any]:
    """Transforma WKB/EWKB da API em GeoJSON, mantendo classificação indefinida."""
    if not isinstance(data, dict) or not isinstance(data.get("features", []), list):
        raise GeoPixelErro("Resposta JSON sem a coleção de feições esperada.")
    destino = []
    ponto = Point(longitude, latitude)
    erros = []
    for posicao, feature in enumerate(data.get("features", [])):
        if not isinstance(feature, dict):
            continue
        geoms = feature.get("geometriesWKB") or []
        if not isinstance(geoms, list):
            continue
        for j, hex_wkb in enumerate(geoms):
            try:
                geom = wkb.loads(bytes.fromhex(hex_wkb))
                if geom.geom_type not in ("Polygon", "MultiPolygon"):
                    raise ValueError("Geometria diferente de polígono")
                # A resposta observada utiliza EWKB com SRID 3857.
                # Conferimos o cabeçalho do EWKB, antes de aplicar a conversão.
                raw = bytes.fromhex(hex_wkb)
                endian = "little" if raw[0] == 1 else "big"
                marker = int.from_bytes(raw[1:5], endian)
                if not (marker & 0x20000000):
                    raise ValueError("EWKB sem SRID declarado")
                srid = int.from_bytes(raw[5:9], endian)
                if srid != EPSG_ORIGEM:
                    raise ValueError(f"SRID não suportado: {srid}")
                geo = transform(TO_4326.transform, geom)
                destino.append({
                    "type": "Feature", "geometry": mapping(geo),
                    "properties": {
                        "codigo_zona": None,
                        "classificacao_confirmada": False,
                        "origem": "Geopixel Cidades — getData", "tema": LAYER_ID,
                        "indice": posicao, "geometria_indice": j,
                        "ponto_no_poligono": geo.covers(ponto),
                        "observacao": "Geometria retornada sem código ZR/ZT. Não confirma zona urbanística nem lote."
                    }
                })
            except (TypeError, ValueError, Exception) as exc:
                # Não bloqueia outras geometrias se uma feição vier malformada.
                erros.append(f"Geometria {posicao}/{j}: {type(exc).__name__}")
    documento = {"type": "FeatureCollection", "features": destino}
    return {
        "geojson": documento,
        "num_poligonos": len(destino),
        "incluem_ponto": sum(1 for f in destino if f["properties"]["ponto_no_poligono"]),
        "erros": erros,
        "tem_atributos": bool(data.get("description", {}).get("attributes", [])),
        "classificacao_zoneamento": None,
        "status": "GEOMETRIA_ENCONTRADA_SEM_CLASSIFICACAO" if destino else "GEOMETRIA_NAO_ENCONTRADA",
        "processado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def geojson_texto(resultado: dict) -> str:
    return json.dumps(resultado["geojson"], ensure_ascii=False, indent=2)
