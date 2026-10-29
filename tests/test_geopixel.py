import json
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from shapely import wkb
from pyproj import Transformer
from geopixel import fabricar_payload, consultar, processar_resposta, GeoPixelErro

class TestGeopixel(unittest.TestCase):
    def test_payload_contendo_ponto_e_buffer(self):
        p = fabricar_payload(-23.53792982312568, -46.841440662669235)
        self.assertEqual(p["themeId"], 5156)
        spatial = p["spatialFilter"]["queryExpression"]
        self.assertEqual(spatial["type"], "INTERSECTS")
        self.assertEqual(spatial["arguments"][0]["tableName"], "zoneamento_lei210799_validacao")
        buffer = spatial["arguments"][1]
        self.assertEqual(buffer["type"], "BUFFER")
        self.assertEqual(buffer["arguments"][1]["value"], 0.5)
        raw = bytes.fromhex(buffer["arguments"][0]["value"])
        ponto = wkb.loads(raw)
        lon, lat = Transformer.from_crs(3857,4326,always_xy=True).transform(ponto.x,ponto.y)
        self.assertAlmostEqual(lat,-23.53792982312568,places=6)
        self.assertAlmostEqual(lon,-46.841440662669235,places=6)

    def test_decodifica_wkb_da_amostra(self):
        src = Path(__file__).resolve().parents[1] / "exemplos" / "getData_amostra.json"
        j=json.loads(src.read_text(encoding="utf8"))
        r=processar_resposta(j,-23.53792982312568,-46.841440662669235)
        self.assertEqual(r["num_poligonos"],1)
        self.assertEqual(r["incluem_ponto"],1)
        self.assertIsNone(r["classificacao_zoneamento"])
        self.assertFalse(r["tem_atributos"])

    def test_nao_inventa_zona(self):
        self.assertEqual(processar_resposta({"description": {"attributes": []}, "features": []},-23.5,-46.8)["status"],"GEOMETRIA_NAO_ENCONTRADA")

    def test_nao_contorna_negativa(self):
        r=Mock(status_code=403)
        with patch("geopixel.requests.post",return_value=r) as m:
            with self.assertRaises(GeoPixelErro): consultar(-23.5,-46.8)
            self.assertEqual(m.call_count,1)
            self.assertFalse(m.call_args.kwargs["allow_redirects"])

if __name__=="__main__": unittest.main()
