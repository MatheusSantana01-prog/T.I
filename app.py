"""TI Stock PRO — ponto de entrada.   Para rodar:  streamlit run app.py"""
import streamlit as st

st.set_page_config(
    page_title="TI Stock PRO",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

from nucleo import armazenamento, config  # noqa: E402
from paginas import (  # noqa: E402
    analises, filiais as pag_filiais, historico, importar, inventario, login,
    movimentar, painel, produtos, reposicao, sidebar, transferir, ui, usuarios as pag_usuarios,
)

ui.aplicar_css()

# ------------------------------------------------------------------ login
try:
    usuarios = armazenamento.carregar_usuarios()
except armazenamento.ErroArquivo as e:
    st.error(f"{e}. O app foi pausado para não perder dados; confira o arquivo ou restaure um backup.")
    st.stop()

if not usuarios:
    login.tela_primeiro_acesso(usuarios)
    st.stop()

usuario_id = login.identificar_usuario(usuarios)
if usuario_id is None:
    login.tela_login(usuarios)
    st.stop()

login.aplicar_cookie_pendente()

# ------------------------------------------------------------------ dados (lidos a cada interação)
try:
    filiais = armazenamento.carregar_dados()
except armazenamento.ErroArquivo as e:
    st.error(f"{e}. O app foi pausado para não perder dados; confira o arquivo ou restaure um backup.")
    st.stop()

usuario = usuarios[usuario_id]
eh_admin = usuario["perfil"] == config.PERFIL_ADMIN
pode_editar = usuario["perfil"] in (config.PERFIL_ADMIN, config.PERFIL_OPERADOR)
filiais_visiveis = [n for n in filiais if eh_admin or n in usuario["filiais"]]

if not filiais_visiveis:
    st.warning("Seu usuário ainda não tem nenhuma filial liberada. Fale com o administrador.")
    st.button("🚪 Sair", on_click=login.sair, key="sair_sem_filial")
    st.stop()

ctx = ui.Contexto(
    usuarios=usuarios, usuario_id=usuario_id, usuario=usuario, filiais=filiais,
    filiais_visiveis=filiais_visiveis, eh_admin=eh_admin, pode_editar=pode_editar,
)
sidebar.construir(ctx)

# ------------------------------------------------------------------ topo
st.markdown(
    f"<h1 style='color: #ffffff; font-weight: 700;'>📦 TI Inventory Control "
    f"<span style='color:#3b82f6;'>· {ui.esc(ctx.filial_atual)}</span></h1>",
    unsafe_allow_html=True,
)
ui.mostrar_flash()
painel.mostrar(ctx)

# ------------------------------------------------------------------ navegação (conforme permissão)
ROTAS = {
    ui.PAG_INVENTARIO: inventario.mostrar,
    ui.PAG_MOVIMENTAR: movimentar.mostrar,
    ui.PAG_TRANSFERIR: transferir.mostrar,
    ui.PAG_PRODUTOS: produtos.mostrar,
    ui.PAG_IMPORTAR: importar.mostrar,
    ui.PAG_REPOSICAO: reposicao.mostrar,
    ui.PAG_ANALISES: analises.mostrar,
    ui.PAG_HISTORICO: historico.mostrar,
    ui.PAG_FILIAIS: pag_filiais.mostrar,
    ui.PAG_USUARIOS: pag_usuarios.mostrar,
}

paginas = [ui.PAG_INVENTARIO]
if pode_editar:
    paginas.append(ui.PAG_MOVIMENTAR)
paginas.append(ui.PAG_TRANSFERIR)  # todos veem o relatório; só quem edita faz transferências
if pode_editar:
    paginas += [ui.PAG_PRODUTOS, ui.PAG_IMPORTAR]
paginas += [ui.PAG_REPOSICAO, ui.PAG_ANALISES, ui.PAG_HISTORICO]
if len(filiais_visiveis) > 1:
    paginas.append(ui.PAG_FILIAIS)
if eh_admin:
    paginas.append(ui.PAG_USUARIOS)

if st.session_state.get("pagina") not in paginas:
    st.session_state.pop("pagina", None)
pagina = st.radio("Navegação", paginas, horizontal=True, key="pagina", label_visibility="collapsed")
st.divider()

ROTAS[pagina](ctx)
