"""Página: Análises (gráficos simples)."""
import streamlit as st

from nucleo import servicos


def mostrar(ctx):
    if len(ctx.filiais_visiveis) > 1:
        st.subheader("🏢 Unidades em estoque por filial")
        resumo = servicos.resumo_filiais(ctx.filiais, ctx.filiais_visiveis)
        st.bar_chart(resumo.set_index("Filial")["Unidades"])

    st.subheader(f"📈 Movimentação por mês — {ctx.filial_atual}")
    mov = servicos.movimentacao_por_mes(ctx.historico)
    if mov.empty:
        st.info("Ainda não há entradas ou saídas registradas nesta filial.")
    else:
        st.bar_chart(mov)

    st.subheader(f"🏆 Itens que mais saem — {ctx.filial_atual}")
    top = servicos.top_saidas(ctx.historico)
    if top.empty:
        st.info("Ainda não há saídas registradas nesta filial.")
    else:
        st.bar_chart(top)
