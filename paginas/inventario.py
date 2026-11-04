"""Página: Inventário (tabela, busca, exportação e números de série)."""
import streamlit as st

from nucleo import config, servicos

from . import ui


def mostrar(ctx):
    df = ctx.df_atual.copy()
    if ctx.categoria_sel != "Todas":
        df = df[df["Categoria"] == ctx.categoria_sel]
    if ctx.status_sel != "Todos":
        df = df[df["Status"] == ctx.status_sel]

    if ctx.categoria_sel != "Todas" or ctx.status_sel != "Todos":
        st.info(f"Filtros ativos — Categoria: {ctx.categoria_sel} | Situação: {ctx.status_sel}")
        st.button("🧹 Limpar filtros", on_click=ui.limpar_filtros, key="btn_limpar_filtros")

    busca = st.text_input("🔍 Digite para procurar qualquer equipamento...",
                          placeholder="Ex: SSD, Cabo, Mouse...")
    if busca:
        df = df[df["Equipamento"].str.lower().str.contains(busca.lower(), regex=False)]

    if df.empty:
        st.info("Nenhum item encontrado com esses filtros.")
    else:
        ui.mostrar_tabela(
            df,
            column_config={
                "Estoque Atual": st.column_config.NumberColumn("Unidades em Armazém"),
                "Status": st.column_config.TextColumn("Estado Disponível"),
            },
        )
        st.download_button(
            "⬇️ Baixar inventário (CSV)",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"inventario_{ctx.filial_atual}.csv",
            mime="text/csv",
        )

    unidades = servicos.df_unidades(ctx.produtos)
    if not unidades.empty:
        st.divider()
        st.subheader("🔢 Números de série / patrimônio")
        c1, c2 = st.columns([2, 1])
        busca_serie = c1.text_input("🔍 Procurar por número de série, equipamento ou destino:", key="busca_serie")
        situacao = c2.selectbox("Situação:", ["Todas", config.EM_ESTOQUE, config.SAIU], key="filtro_situacao_serie")
        if busca_serie:
            termo = busca_serie.lower()
            mascara = unidades.apply(lambda r: termo in " ".join(map(str, r.values)).lower(), axis=1)
            unidades = unidades[mascara]
        if situacao != "Todas":
            unidades = unidades[unidades["Situação"] == situacao]
        if unidades.empty:
            st.info("Nenhuma unidade encontrada.")
        else:
            ui.mostrar_tabela(unidades)
