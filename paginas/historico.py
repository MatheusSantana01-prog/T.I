"""Página: Histórico com filtros."""
from datetime import date, timedelta

import streamlit as st

from nucleo import servicos

from . import ui


def mostrar(ctx):
    if not ctx.historico:
        st.info("Nenhuma movimentação registrada ainda.")
        return
    df = servicos.historico_df(ctx.historico)
    f = ctx.filial_atual

    with st.expander("🔎 Filtros", expanded=False):
        inicio = fim = None
        if st.checkbox("Filtrar por período", key=f"hist_usar_periodo_{f}"):
            d1, d2 = st.columns(2)
            inicio = d1.date_input("De:", value=date.today() - timedelta(days=30), key=f"hist_de_{f}")
            fim = d2.date_input("Até:", value=date.today(), key=f"hist_ate_{f}")
        opcoes = {
            "equipamentos": sorted(df["Equipamento"].dropna().unique()),
            "operacoes": sorted(df["Operação"].dropna().unique()),
            "usuarios": sorted(df["Usuário"].dropna().unique()),
        }
        for nome, ops in opcoes.items():
            ui.limpar_selecao_invalida(f"hist_{nome}_{f}", ops)
        m1, m2, m3 = st.columns(3)
        equips = m1.multiselect("Equipamento:", opcoes["equipamentos"], key=f"hist_equipamentos_{f}")
        operacoes = m2.multiselect("Operação:", opcoes["operacoes"], key=f"hist_operacoes_{f}")
        usuarios = m3.multiselect("Usuário:", opcoes["usuarios"], key=f"hist_usuarios_{f}")

    filtrado = servicos.filtrar_historico(df, inicio, fim, equips, operacoes, usuarios)
    filtrado = filtrado.sort_values("_data", ascending=False, na_position="last").drop(columns="_data")

    st.caption(f"{len(filtrado)} registro(s) de {len(df)}.")
    ui.mostrar_tabela(filtrado)

    h1, h2 = st.columns([1, 2])
    with h1:
        st.download_button("⬇️ Baixar histórico (CSV)", filtrado.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"historico_{f}.csv", mime="text/csv")
    with h2:
        if ctx.eh_admin and st.checkbox("Quero apagar todo o histórico desta filial", key=f"conf_limpar_hist_{f}"):
            if st.button("🧹 Limpar histórico", key="btn_limpar_hist"):
                ctx.historico.clear()
                ctx.salvar()
                ui.avisar("aviso", "Histórico apagado.")
                st.rerun()
