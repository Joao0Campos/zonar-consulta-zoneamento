"""ZONAR 0.3 — localização + consulta espacial experimental Geopixel."""
import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st
from localizacao import LocalizacaoErro, coordenadas, geocodificar, municipio_confirmado
from pesquisa import descobrir
from geopixel import GeoPixelErro, consultar, processar_resposta, geojson_texto

# Opcional: lê GEOAPIFY_API_KEY de um arquivo .env na pasta do app (requer python-dotenv).
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

st.set_page_config(page_title="ZONAR | Carapicuíba", page_icon="🗺️", layout="wide")
st.title("🗺️ ZONAR")
st.caption("MVP 0.3 · Localização + geometria experimental de zoneamento · Carapicuíba/SP")
st.warning("**Importante:** a integração com Geopixel é experimental. O sistema pode exibir polígonos, mas **a classificação ZR2/ZR3/etc. ainda não é identificada**; não equivale a certidão de zoneamento.")

chave_ambiente = os.environ.get("GEOAPIFY_API_KEY", "").strip()
with st.sidebar:
    st.subheader("Configuração de localização")
    if chave_ambiente:
        st.success("Chave Geoapify configurada por variável de ambiente.")
        chave = chave_ambiente
    else:
        chave = st.text_input("Chave Geoapify (opcional)", type="password",
                              help="A chave não é incluída no relatório. Necessária apenas para pesquisar endereços.")
    st.markdown("[Criar uma chave Geoapify](https://myprojects.geoapify.com/)")
    st.caption("Endereços pesquisados com chave são enviados à Geoapify. Não envie dados sigilosos sem aprovação interna.")

with st.form("consulta"):
    st.text_input("Município-piloto", "Carapicuíba/SP", disabled=True)
    modo = st.radio("Como deseja localizar o terreno?", ["Endereço", "Coordenadas"], horizontal=True)
    if modo == "Endereço":
        entrada = st.text_input("Endereço (rua, número, bairro e CEP, se possível)",
                                placeholder="Ex.: Rua Ouro Preto, 100, Granja Viana")
    else:
        entrada = st.text_input("Latitude, longitude", placeholder="Ex.: -23.5200, -46.8400")
    especificacao = st.text_input("Tipo de empreendimento (opcional — não analisado nesta versão)",
                                  placeholder="Ex.: residencial multifamiliar")
    pesquisar = st.form_submit_button("Localizar e buscar fontes oficiais", type="primary")

if pesquisar:
    st.session_state.pop("zonar_resultado", None)
    st.session_state.pop("zonar_geometria", None)
    try:
        if modo == "Endereço":
            if not chave:
                raise LocalizacaoErro("A pesquisa por endereço precisa de uma chave Geoapify. Configure-a na barra lateral ou utilize coordenadas.")
            with st.spinner("Localizando o endereço..."):
                possibilidades = geocodificar(entrada, chave)
        else:
            possibilidades = [coordenadas(entrada)]
        with st.spinner("Consultando as referências municipais..."):
            fontes, avisos = descobrir()
        st.session_state["zonar_resultado"] = {
            "entrada": entrada, "modo": modo, "especificacao": especificacao,
            "possibilidades": possibilidades, "fontes": fontes, "avisos": avisos,
            "consulta_em": datetime.now().astimezone().isoformat(timespec="seconds")
        }
    except LocalizacaoErro as exc:
        st.error(str(exc))

resultado = st.session_state.get("zonar_resultado")
if resultado:
    if resultado["modo"] != modo or resultado["entrada"] != entrada or resultado["especificacao"] != especificacao:
        st.info("Os campos foram alterados. Clique em pesquisar para atualizar o resultado.")
    else:
        possibilidades = resultado["possibilidades"]
        st.subheader("1. Localização do terreno")
        indice = 0
        if len(possibilidades) > 1:
            indice = st.selectbox("Selecione a localização correspondente ao endereço informado:",
                                 range(len(possibilidades)),
                                 format_func=lambda i: possibilidades[i].endereco_retornado)
        ponto = possibilidades[indice]
        col1, col2 = st.columns([2, 1])
        with col1:
            st.map(pd.DataFrame({"lat": [ponto.latitude], "lon": [ponto.longitude]}), zoom=16)
            st.caption("📍 Ponto estimado/fornecido, exibido sobre mapa-base. Não exibe zonas urbanísticas nem limites de lote.")
        with col2:
            st.write(f"**Endereço encontrado:** {ponto.endereco_retornado}")
            st.write(f"**Coordenadas:** {ponto.latitude:.6f}, {ponto.longitude:.6f}")
            st.write(f"**Precisão informada:** {ponto.precisao}")
            st.write(f"**Origem:** {ponto.origem}")
            validacao = municipio_confirmado(ponto)
            if validacao is True:
                st.success("O geocodificador retornou Carapicuíba como município.")
            elif validacao is False:
                st.error(f"Atenção: o município retornado foi {ponto.cidade_retornada}, não Carapicuíba! Confira antes de usar as fontes abaixo.")
            else:
                st.warning("Município do ponto não confirmado: não é possível garantir que esteja em Carapicuíba.")
            if ponto.precisao.casefold() not in ("building", "amenity", "ponto informado manualmente, sem verificação cadastral"):
                st.warning("A geocodificação pode representar a rua/bairro, e não o número exato. Confirme o ponto antes de qualquer análise.")

        st.subheader("2. Geometria da camada de zoneamento — experimental")
        st.caption("Camada observada no visualizador Geopixel: themeId 5156, zoneamento_lei210799_validacao, EPSG:3857.")
        st.info("O endpoint getData retornou polígonos no teste realizado, mas sem atributos de classificação. Esta etapa não determina ZR2, ZR3 ou viabilidade construtiva.")
        st.caption("A consulta envia apenas as coordenadas à Geopixel, em uma requisição por clique, sem cookies nem login. Use somente se a política do provedor e as autorizações da sua organização permitirem. Em caso de acesso negado, não tente contornar as restrições.")
        if st.button("Consultar geometria no Geopixel (experimental)", type="secondary"):
            if validacao is False:
                st.error("O geocodificador retornou outro município. Corrija a localização antes de consultar.")
            else:
                try:
                    with st.spinner("Consultando a camada 5156..."):
                        dados = consultar(ponto.latitude, ponto.longitude)
                        geo = processar_resposta(dados, ponto.latitude, ponto.longitude)
                        st.session_state["zonar_geometria"] = {
                            "lat": ponto.latitude, "lon": ponto.longitude, "result": geo
                        }
                except GeoPixelErro as exc:
                    st.error(str(exc))
        st.write("**Ou analise um JSON getData exportado manualmente do navegador:**")
        enviado = st.file_uploader("Resposta JSON obtida por consulta própria (sem credenciais)", type=["json"], key="geopixel_json")
        if enviado is not None and st.button("Analisar JSON carregado"):
            try:
                dados = json.load(enviado)
                geo = processar_resposta(dados, ponto.latitude, ponto.longitude)
                st.session_state["zonar_geometria"] = {"lat": ponto.latitude, "lon": ponto.longitude, "result": geo}
            except (ValueError, GeoPixelErro, TypeError) as exc:
                st.error(f"Não foi possível interpretar o arquivo: {exc}")
        salvo = st.session_state.get("zonar_geometria")
        if salvo is not None and (salvo["lat"], salvo["lon"]) == (ponto.latitude, ponto.longitude):
            rg = salvo["result"]
            met1, met2 = st.columns(2)
            met1.metric("Geometrias retornadas", rg["num_poligonos"])
            met2.metric("Geometrias contendo o ponto", rg["incluem_ponto"])
            for aviso in rg["erros"]:
                st.warning(f"Erro ao interpretar uma feição: {aviso}")
            if rg["num_poligonos"]:
                import pydeck as pdk
                camada = pdk.Layer(
                    "GeoJsonLayer", data=rg["geojson"], pickable=True,
                    stroked=True, filled=True, get_fill_color=[28, 155, 136, 65],
                    get_line_color=[0, 125, 111, 220], line_width_min_pixels=2,
                )
                marcador = pdk.Layer(
                    "ScatterplotLayer", data=[{"latitude": ponto.latitude, "longitude": ponto.longitude}],
                    get_position="[longitude, latitude]", get_fill_color=[225, 66, 66, 255],
                    get_radius=10, radius_min_pixels=5, pickable=True,
                )
                st.pydeck_chart(pdk.Deck(
                    layers=[camada, marcador],
                    initial_view_state=pdk.ViewState(latitude=ponto.latitude, longitude=ponto.longitude, zoom=13),
                    map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                    tooltip={"text": "Geometria retornada. Código urbanístico: não informado."},
                ))
                st.caption("Polígono(s) de resposta getData sobre mapa-base Carto; não é uma reprodução integral do visualizador oficial.")
                st.download_button("Exportar geometria GeoJSON", geojson_texto(rg),
                    file_name="zonar_carapicuiba_geometria_sem_classificacao.geojson",
                    mime="application/geo+json")
            else:
                st.warning("A consulta não retornou polígonos utilizáveis para esse ponto.")
            st.error("**Zoneamento do terreno: NÃO DETERMINADO** — a camada retorna geometria mas não fornece código de zona neste resultado.")

        st.subheader("3. Fontes oficiais municipais (comuns a todos os endereços de Carapicuíba)")
        st.info("Estas fontes são municipais, não filtradas pelo endereço. A ligação entre ponto e zona depende de obter a camada geográfica oficial.")
        st.metric("Referências", len(resultado["fontes"]))
        for fonte in resultado["fontes"]:
            with st.container(border=True):
                st.markdown(f"**{fonte.titulo}**")
                st.caption(f"{fonte.categoria} · {fonte.situacao}")
                if fonte.observacao:
                    st.write(fonte.observacao)
                st.link_button("Abrir fonte", fonte.url)
                st.caption(f"Origem: {fonte.pagina_origem}")
        for aviso in resultado["avisos"]:
            st.warning(aviso)
        st.subheader("4. Estado da análise")
        st.error("**Zoneamento do terreno: NÃO DETERMINADO.** Geometrias eventualmente obtidas não incluem o código de zona; o ponto não identifica os limites oficiais do lote.")
        registro = {
            "municipio_piloto": "Carapicuíba/SP",
            "entrada": resultado["entrada"],
            "modo_entrada": resultado["modo"],
            "especificacao_nao_analisada": resultado["especificacao"],
            "localizacao": ponto.to_dict(),
            "municipio_confirmado_pelo_geocodificador": validacao,
            "zoneamento": None,
            "geometria_consultada": bool(st.session_state.get("zonar_geometria")),
            "status_zoneamento": "NAO_DETERMINADO",
            "consulta_em": resultado["consulta_em"],
            "fontes_municipais": [fonte.to_dict() for fonte in resultado["fontes"]],
            "avisos": resultado["avisos"],
        }
        st.download_button("Baixar resultado JSON", json.dumps(registro, ensure_ascii=False, indent=2),
                           file_name="zonar_carapicuiba_localizacao.json", mime="application/json")
