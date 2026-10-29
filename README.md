# ZONAR: consulta de zoneamento (MVP, Carapicuíba/SP)

Protótipo em Streamlit que localiza um terreno por endereço ou coordenadas, consulta a camada de zoneamento publicada no visualizador municipal (Geopixel Cidades) e exibe no mapa a geometria retornada, com exportação em GeoJSON. Ele também reúne as fontes oficiais de zoneamento da prefeitura.

## Problema

Para avaliar um terreno, é preciso saber em que zona urbanística ele está. Em Carapicuíba/SP essa informação fica num visualizador web e em documentos espalhados pelo portal da prefeitura. Não há uma API documentada que receba um endereço e devolva a zona.

## Solução

1. **Localização:** geocodifica o endereço via Geoapify, restrito ao Brasil e acrescido do município, ou aceita `latitude, longitude` digitadas. Também confere se o município retornado é Carapicuíba.
2. **Geometria de zoneamento (experimental):** converte o ponto para EPSG:3857 e monta o mesmo filtro espacial usado pelo visualizador (`INTERSECTS` com `BUFFER` de 0,5 sobre a camada `themeId=5156`). Em seguida:
   - faz um único `POST` ao endpoint `getData`;
   - decodifica as geometrias EWKB, validando o SRID declarado no cabeçalho;
   - reprojeta para WGS84 e mostra o(s) polígono(s) com pydeck;
   - informa se o ponto está contido em cada polígono.

   Também é possível importar uma resposta `getData` salva em JSON, sem acessar o serviço.
3. **Fontes oficiais:** lê duas páginas públicas da prefeitura, extrai links relacionados a zoneamento (só de domínios permitidos) e completa com referências catalogadas: visualizador, Plano Diretor e legislação.
4. **Registro:** permite baixar um JSON com a entrada, a localização, as fontes e o status da análise.

## Stack

Python 3.10+, Streamlit, requests, BeautifulSoup, Shapely (WKB/EWKB, operações geométricas), pyproj (EPSG:4326 ↔ EPSG:3857), pydeck, pandas e `unittest`.

## Arquitetura

```
app.py           interface Streamlit, estado da sessão, mapa e downloads
localizacao.py   geocodificação Geoapify, coordenadas manuais, validação do município
geopixel.py      montagem do payload espacial, POST único, decodificação EWKB → GeoJSON
pesquisa.py      descoberta de links oficiais com allowlist de domínios
tests/           testes unitários (rede simulada com unittest.mock)
exemplos/        resposta getData de exemplo (uma geometria pública, sem atributos)
```

## Decisões técnicas

- **Não inventar resultado:** a resposta observada da camada traz geometria, mas `attributes: []`. Por isso, o app nunca exibe um código de zona (ZR2, ZR3 etc.). O status fica explicitamente como `NAO_DETERMINADO` / `GEOMETRIA_ENCONTRADA_SEM_CLASSIFICACAO`, e há um teste que garante esse comportamento.
- **Acesso conservador ao serviço de terceiros:**
  - no máximo uma requisição por clique, sem retries, sem cookies ou login e com `allow_redirects=False`;
  - respostas 401/403/3xx/429 interrompem a consulta com uma mensagem, sem tentativa de contorno (também coberto por teste).
- **Validação de dados geográficos:** o SRID é conferido no cabeçalho EWKB antes de reprojetar. Uma geometria malformada não derruba as demais.
- **Allowlist de domínios** na descoberta de fontes, com teste contra hosts parecidos (`carapicuiba.sp.gov.br.attacker.test`) e contra `http`.
- **Chave de API fora do código:** lida de `GEOAPIFY_API_KEY` (ambiente ou `.env`) ou digitada num campo de senha na barra lateral. A chave não entra no JSON exportado. A busca por coordenadas funciona sem chave.

## Evolução

| Versão | O que entrou |
|---|---|
| 0.1 | Descoberta de links oficiais de zoneamento no portal da prefeitura (`pesquisa.py`) |
| 0.2 | Localização do terreno: geocodificação Geoapify ou coordenadas manuais, mapa do ponto e checagem do município (`localizacao.py`) |
| 0.3 | Consulta espacial à camada de zoneamento, decodificação EWKB → GeoJSON, mapa com polígonos, exportação e importação de JSON (`geopixel.py`) |

Este repositório contém a versão 0.3.

## Como rodar

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env              # opcional: preencha GEOAPIFY_API_KEY
python -m streamlit run app.py      # http://localhost:8501
```

Teste rápido sem chave: escolha **Coordenadas** e informe `-23.5379298, -46.8414407`. Depois carregue `exemplos/getData_amostra.json` em **Analisar JSON carregado**.

### Testes

```powershell
python -m unittest discover -s tests -v
```

São 11 testes, cobrindo payload espacial, decodificação da amostra EWKB, recusa a contornar o HTTP 403, parsing de coordenadas, validação de município, a regra de não chamar a API sem chave e a allowlist de domínios. Nenhum teste acessa a rede.

## Limitações conhecidas

- **Não determina o zoneamento:** a camada consultada devolve geometria sem o código da zona. O resultado não equivale a uma certidão de zoneamento e não identifica os limites do lote.
- O endpoint `getData` não é uma API pública documentada: o formato foi observado no tráfego do visualizador e pode mudar ou ser bloqueado. Só deve ser usado com autorização e dentro dos termos do serviço.
- A geocodificação pode retornar a rua ou o bairro, e não o número exato. O app avisa quando a precisão é baixa.
- O projeto é um piloto para um único município: endpoint, camada e domínios estão fixos no código.
