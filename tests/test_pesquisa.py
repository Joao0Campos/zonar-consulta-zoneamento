import unittest
from pesquisa import candidatos, permitido, GEOPIXEL, PREFEITURA

class TestPesquisa(unittest.TestCase):
    def test_parser_encontra_mapa_publicado(self):
        pagina = '<html><a href="https://carapicuiba.geopx.com.br/geopixelcidades3/">Mapa de Zoneamento da Cidade</a><a href="https://example.com/login">zoneamento privado</a></html>'
        achados = candidatos(pagina, PREFEITURA)
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0].url, GEOPIXEL)
        self.assertEqual(achados[0].categoria, 'Mapa / visualizador')

    def test_nao_aceita_host_parecido(self):
        self.assertFalse(permitido('https://carapicuiba.sp.gov.br.attacker.test/arquivo.pdf'))
        self.assertFalse(permitido('http://carapicuiba.sp.gov.br/arquivo.pdf'))
        self.assertTrue(permitido(GEOPIXEL))

if __name__ == '__main__':
    unittest.main()
