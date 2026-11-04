"""Página: Lista de reposição (o que comprar), com texto para WhatsApp/e-mail."""
from urllib.parse import quote

import streamlit as st

from nucleo import servicos

from . import ui


def mostrar(ctx):
    st.subheader("🛒 Lista de reposição")
    st.caption("Reúne os itens zerados e em alerta das filiais escolhidas.")

    c1, c2 = st.columns([2, 1])
    with c1:
        ui.limpar_selecao_invalida("rep_filiais", ctx.filiais_visiveis)
        if "rep_filiais" not in st.session_state:
            st.session_state["rep_filiais"] = list(ctx.filiais_visiveis)
        escolhidas = st.multiselect("Filiais:", ctx.filiais_visiveis, key="rep_filiais")
    with c2:
        mult = st.number_input("Meta de estoque (x o nível de alerta):", min_value=1, value=2, step=1, key="rep_mult")

    df = servicos.itens_para_repor(ctx.filiais, escolhidas, mult)
    if df.empty:
        st.success("Nada para repor nas filiais escolhidas. 🎉")
        return

    ui.mostrar_tabela(df)
    st.caption("Sugestão de compra = quanto falta para chegar à meta de estoque (nível de alerta × o número acima).")

    texto = servicos.texto_reposicao(df)
    st.text_area("Texto pronto para copiar:", texto, height=200, key="rep_texto")
    b1, b2, b3 = st.columns(3)
    b1.link_button("📲 Abrir no WhatsApp", "https://wa.me/?text=" + quote(texto))
    b2.link_button("✉️ Abrir no e-mail", "mailto:?subject=" + quote("Reposição de estoque de T.I.") + "&body=" + quote(texto))
    b3.download_button("⬇️ Baixar (CSV)", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="lista_reposicao.csv", mime="text/csv")
