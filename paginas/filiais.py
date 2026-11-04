"""Página: visão geral de todas as filiais liberadas."""
import streamlit as st

from . import ui
from nucleo import servicos


def mostrar(ctx):
    st.subheader("🏢 Resumo por filial")
    ui.mostrar_tabela(servicos.resumo_filiais(ctx.filiais, ctx.filiais_visiveis))

    st.subheader("📊 Estoque de cada produto por filial")
    tabela = servicos.tabela_por_filial(ctx.filiais, ctx.filiais_visiveis)
    if tabela.empty:
        st.info("Nenhum produto cadastrado nas filiais ainda.")
        return
    busca = st.text_input("🔍 Procurar equipamento em todas as filiais...", key="busca_geral")
    if busca:
        tabela = tabela[tabela["Equipamento"].str.lower().str.contains(busca.lower(), regex=False)]
    if tabela.empty:
        st.info("Nenhum item encontrado.")
        return
    ui.mostrar_tabela(tabela)
    st.caption("0 = estoque zerado ou produto não cadastrado naquela filial.")
    st.download_button("⬇️ Baixar visão geral (CSV)", tabela.to_csv(index=False).encode("utf-8-sig"),
                       file_name="estoque_todas_filiais.csv", mime="text/csv")
