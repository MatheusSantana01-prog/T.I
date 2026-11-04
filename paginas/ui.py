"""Peças de interface compartilhadas: CSS, contexto, mensagens e tabelas."""
import html
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from nucleo import armazenamento

# Nomes das páginas (também são os textos da barra de navegação)
PAG_INVENTARIO = "📋 Inventário"
PAG_MOVIMENTAR = "🔄 Movimentar"
PAG_TRANSFERIR = "🔀 Transferir"
PAG_PRODUTOS = "⚙️ Produtos"
PAG_IMPORTAR = "📥 Importar"
PAG_REPOSICAO = "🛒 Reposição"
PAG_ANALISES = "📈 Análises"
PAG_HISTORICO = "📜 Histórico"
PAG_FILIAIS = "🏢 Filiais"
PAG_USUARIOS = "👥 Usuários"

CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, .stApp, .stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3,
    .stApp h4, .stApp li, .stApp input, .stApp textarea, .stApp button,
    .stApp td, .stApp th { font-family: 'Inter', sans-serif; }
    /* mantém a fonte própria dos ícones do Streamlit (senão viram símbolos estranhos) */
    span[data-testid="stIconMaterial"], .material-symbols-rounded {
        font-family: 'Material Symbols Rounded' !important;
    }
    .stApp { background-color: #0f172a; color: #f8fafc; }

    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155; border-radius: 16px; padding: 20px !important;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); transition: transform 0.2s;
    }
    div[data-testid="stMetric"]:hover { transform: translateY(-2px); border-color: #3b82f6; }
    div[data-testid="stMetricLabel"] { color: #94a3b8 !important; font-size: 14px !important; font-weight: 600; }
    div[data-testid="stMetricValue"] { color: #ffffff !important; font-size: 28px !important; font-weight: 700; }

    div[data-baseweb="select"], input, div[data-baseweb="base-input"] {
        background-color: #1e293b !important; color: white !important;
        border-radius: 8px !important; border: 1px solid #475569 !important;
    }
    .card-info {
        background: #1e293b; padding: 24px; border-radius: 12px;
        border-left: 6px solid #3b82f6; margin-bottom: 15px;
    }
    section[data-testid="stSidebar"] { background-color: #0b0f19 !important; border-right: 1px solid #1e293b; }

    div.stButton > button,
    div[data-testid="stFormSubmitButton"] > button,
    div[data-testid="stDownloadButton"] > button,
    a[data-testid="stLinkButton"] {
        background: linear-gradient(90deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: white !important; border: none !important; border-radius: 8px !important;
        padding: 10px 20px !important; font-weight: 600 !important;
    }
    div.stButton > button:disabled { opacity: 0.4; }
</style>
"""


def aplicar_css():
    st.markdown(CSS, unsafe_allow_html=True)


@dataclass
class Contexto:
    """Tudo que as páginas precisam saber sobre a sessão atual."""

    usuarios: dict
    usuario_id: str
    usuario: dict
    filiais: dict
    filiais_visiveis: list
    eh_admin: bool
    pode_editar: bool
    filial_atual: str = ""
    categoria_sel: str = "Todas"
    status_sel: str = "Todos"
    df_atual: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def dados(self):
        return self.filiais[self.filial_atual]

    @property
    def produtos(self):
        return self.dados["produtos"]

    @property
    def historico(self):
        return self.dados["historico"]

    def salvar(self):
        try:
            armazenamento.salvar_dados(self.filiais)
        except OSError:
            st.warning("Não foi possível gravar o arquivo de dados em disco.")

    def salvar_usuarios(self):
        try:
            armazenamento.salvar_usuarios(self.usuarios)
        except OSError:
            st.warning("Não foi possível gravar o arquivo de usuários em disco.")


# ------------------------------------------------------------------ mensagens
def avisar(tipo, texto):
    """Guarda a mensagem para ser exibida depois do st.rerun()."""
    st.session_state.flash = (tipo, texto)


def mostrar_flash():
    if "flash" in st.session_state:
        tipo, texto = st.session_state.pop("flash")
        {"sucesso": st.success, "erro": st.error, "aviso": st.warning}[tipo](texto)


# ------------------------------------------------------------------ seleção segura
def sincronizar_selecao(chave, nomes):
    """Evita erro quando o item selecionado foi excluído/renomeado."""
    pendente = st.session_state.pop(f"{chave}_pendente", None)
    if pendente in nomes:
        st.session_state[chave] = pendente
    elif st.session_state.get(chave) not in nomes:
        st.session_state.pop(chave, None)


def limpar_selecao_invalida(chave, opcoes):
    """Para multiselect: tira da seleção o que não existe mais nas opções."""
    if chave in st.session_state:
        st.session_state[chave] = [v for v in st.session_state[chave] if v in opcoes]


# ------------------------------------------------------------------ filtros do inventário
def ver_itens_por_status(status):
    """Chamado ao clicar nos cartões: abre o inventário já filtrado."""
    st.session_state["filtro_status"] = status
    st.session_state["filtro_categoria"] = "Todas"
    st.session_state["pagina"] = PAG_INVENTARIO


def limpar_filtros():
    st.session_state["filtro_status"] = "Todos"
    st.session_state["filtro_categoria"] = "Todas"


# ------------------------------------------------------------------ componentes
def mostrar_tabela(df, **kwargs):
    # Compatível com versões novas e antigas do Streamlit
    try:
        st.dataframe(df, width="stretch", hide_index=True, **kwargs)
    except Exception:  # noqa: BLE001
        st.dataframe(df, use_container_width=True, hide_index=True, **kwargs)


def opcoes_categoria(produtos):
    from nucleo import config

    existentes = {i.categoria for i in produtos.values()}
    return sorted(existentes | set(config.CATEGORIAS_SUGERIDAS))


def esc(texto):
    return html.escape(str(texto))
