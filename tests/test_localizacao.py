import unittest
from unittest.mock import patch, Mock
from localizacao import Localizacao, LocalizacaoErro, coordenadas, municipio_confirmado, geocodificar


class TestLocalizacao(unittest.TestCase):
    def test_coordenadas(self):
        x = coordenadas("-23.52, -46.84")
        self.assertEqual((x.latitude, x.longitude), (-23.52, -46.84))
        self.assertIsNone(municipio_confirmado(x))

    def test_invalidas(self):
        for valor in ("abc", "90.1, 20", "23.53/-46.85", ""):
            with self.subTest(valor=valor), self.assertRaises(LocalizacaoErro):
                coordenadas(valor)

    def test_municipio_acentuado(self):
        x = Localizacao(-23.5, -46.8, "endereço", "Carapicuíba", "building", "Geoapify")
        self.assertTrue(municipio_confirmado(x))
        x.cidade_retornada = "Cotia"
        self.assertFalse(municipio_confirmado(x))

    def test_sem_chave_nao_faz_request(self):
        with patch("localizacao.requests.get") as requisicao:
            with self.assertRaises(LocalizacaoErro):
                geocodificar("Rua Ouro Preto, 100", "")
            requisicao.assert_not_called()

    def test_enderecos_diferentes_geram_consultas_diferentes(self):
        mock = Mock()
        mock.json.return_value = {"features": [{"geometry": {"coordinates": [-46.82, -23.53]},
            "properties": {"formatted": "Rua A, Carapicuíba", "city": "Carapicuíba", "result_type": "street"}}]}
        with patch("localizacao.requests.get", return_value=mock) as requisicao:
            a = geocodificar("Rua A, 10", "teste")
            b = geocodificar("Rua B, 20", "teste")
        self.assertEqual(a[0].latitude, -23.53)
        self.assertEqual(requisicao.call_count, 2)
        p1, p2 = [c.kwargs["params"]["text"] for c in requisicao.call_args_list]
        self.assertNotEqual(p1, p2)
        self.assertIn("Rua B", p2)


if __name__ == "__main__":
    unittest.main()
