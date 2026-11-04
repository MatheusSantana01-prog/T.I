"""Cartões de resumo no topo da página."""
import streamlit as st

from nucleo import config

from . import ui


def mostrar(ctx):
    produtos = ctx.produtos.values()
    total_unidades = sum(i.estoque_atual for i in produtos)
    criticos = sum(1 for i in produtos if i.status == config.STATUS_CRITICO)
    alertas = sum(1 for i in produtos if i.status == config.STATUS_ALERTA)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Linhas de Inventário", f"{len(ctx.produtos)} Produtos")
    c2.metric("Total de Unidades", f"{total_unidades} un.")
    c3.metric("Ruptura de Stock (Zerados)", f"{criticos} itens")
    c4.metric("Nível de Alerta (Baixo)", f"{alertas} itens")

    c3.button("Ver itens zerados", on_click=ui.ver_itens_por_status,
              args=(config.STATUS_CRITICO,), key="ver_criticos", disabled=criticos == 0)
    c4.button("Ver itens em alerta", on_click=ui.ver_itens_por_status,
              args=(config.STATUS_ALERTA,), key="ver_alertas", disabled=alertas == 0)
    st.markdown("<br>", unsafe_allow_html=True)
