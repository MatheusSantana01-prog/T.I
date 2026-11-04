"""Página: Importar produtos de uma planilha (CSV ou Excel)."""
import pandas as pd
import streamlit as st

from nucleo import servicos

from . import ui

MODOS = {
    "Somar ao estoque atual": servicos.MODO_SOMAR,
    "Substituir o estoque pelo valor da planilha": servicos.MODO_SUBSTITUIR,
    "Pular os produtos que já existem": servicos.MODO_PULAR,
}


def mostrar(ctx):
    if not ctx.pode_editar:
        st.error("Seu perfil não tem permissão para importar planilhas.")
        return

    st.subheader(f"📥 Importar planilha para a filial {ctx.filial_atual}")
    st.caption("Colunas aceitas: **Equipamento** (obrigatória), Categoria, Estoque e Alerta. Arquivos CSV ou Excel (.xlsx).")
    st.download_button("⬇️ Baixar modelo de planilha", servicos.MODELO_PLANILHA_CSV.encode("utf-8-sig"),
                       file_name="modelo_importacao.csv", mime="text/csv")

    ver = st.session_state.get("ver_import", 0)
    arquivo = st.file_uploader("Escolha o arquivo", type=["csv", "xlsx", "xls"], key=f"upload_import_{ver}")
    if arquivo is None:
        return

    try:
        df = servicos.ler_planilha(arquivo.getvalue(), arquivo.name)
        linhas, erros = servicos.preparar_importacao(df)
    except ValueError as e:
        st.error(str(e))
        return

    if erros:
        with st.expander(f"⚠️ {len(erros)} linha(s) serão ignoradas", expanded=True):
            for e in erros:
                st.write("• " + e)
    if not linhas:
        st.error("Nenhuma linha válida para importar.")
        return

    existentes = sum(1 for l in linhas if l["nome"] in ctx.produtos)
    st.success(f"{len(linhas)} linha(s) válida(s): {len(linhas) - existentes} produto(s) novo(s) e {existentes} que já existe(m).")
    previa = pd.DataFrame(linhas).rename(
        columns={"nome": "Equipamento", "categoria": "Categoria", "estoque": "Estoque", "alerta": "Alerta"}
    )
    ui.mostrar_tabela(previa)

    modo_txt = st.radio("Para os produtos que já existem na filial:", list(MODOS), key=f"modo_import_{ver}")
    if st.button("✅ Confirmar importação", key="btn_importar"):
        r = servicos.aplicar_importacao(ctx.dados, linhas, MODOS[modo_txt], ctx.usuario_id)
        ctx.salvar()
        msg = f"Importação concluída: {r['novos']} novo(s), {r['atualizados']} atualizado(s), {r['pulados']} sem alteração."
        if r["avisos"]:
            msg += " Avisos: " + " ".join(r["avisos"])
        st.session_state["ver_import"] = ver + 1
        ui.avisar("sucesso", msg)
        st.rerun()
